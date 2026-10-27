"""Score AskData against eval/questions.json.

Sends each question for the active dataset to a running backend, compares the answer with
the saved gold results in eval/expected.json, and writes per-question results plus a summary.

    make load-dataset DATASET=pagila          # then restart or reload the backend schema
    python eval/score.py --dataset pagila --label mine
    python eval/score.py --dataset retail_ops --label mine
    python eval/score.py --summarize eval/results/*_mine_*.jsonl   # combined table

Re-score saved responses without calling the backend (e.g. after changing the matcher):
    python eval/score.py --rescore eval/results/<file>.jsonl

Standard library only. The response contract it reads is described in eval/EVAL.md.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS = EVAL_DIR / "questions.json"
EXPECTED = EVAL_DIR / "expected.json"
RESULTS_DIR = EVAL_DIR / "results"

# Outcomes that count as a silent error: AskData gave an answer and the answer is wrong.
SILENT_ERRORS = {"wrong", "fabricated"}
GOOD = {"correct", "clarified", "declined"}

DATASET_SIGNATURE = {"pagila": '"rental"', "retail_ops": '"order_items"'}

# ----------------------------------------------------------------------------- values

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[ T]00:00(?::00(?:\.0+)?)?(?:Z|[+-]00(?::?00)?)?)?$")


def normalize(value):
    """Map a cell to a comparable value: float for numbers, ISO date for midnight timestamps,
    lower-cased trimmed text otherwise."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        number = float(text)
        if math.isfinite(number):
            return number
    except ValueError:
        pass
    match = _DATE_RE.match(text)
    if match:
        return match.group(1)
    return text.lower()


def values_equal(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= max(0.011, 1e-4 * max(abs(a), abs(b)))
    return a == b


def _sort_key(value):
    if value is None:
        return (0, "")
    if isinstance(value, float):
        return (1, value)
    return (2, str(value))


def lists_equal(gold: list, pred: list, ordered: bool) -> bool:
    if len(gold) != len(pred):
        return False
    if not ordered:
        gold, pred = sorted(gold, key=_sort_key), sorted(pred, key=_sort_key)
    return all(values_equal(g, p) for g, p in zip(gold, pred))


def tuples_equal(gold: list[tuple], pred: list[tuple]) -> bool:
    if len(gold) != len(pred):
        return False
    key = lambda row: tuple(_sort_key(v) for v in row)  # noqa: E731
    return all(
        all(values_equal(g, p) for g, p in zip(gr, pr))
        for gr, pr in zip(sorted(gold, key=key), sorted(pred, key=key))
    )


# ----------------------------------------------------------------------------- matching

def result_matches(gold: dict, pred_columns: list, pred_rows: list, match: dict) -> bool:
    """True when the predicted table answers the question the same way as one gold result.

    Column names are ignored: each required group of gold columns must be found among the
    predicted columns by value. Extra predicted columns are fine. Rows must line up
    (compared as tuples of the matched columns). With an ordered column, its sequence must
    match; with prefix_ok, a top-N subset of the gold ranking is accepted. Rows tied with
    the last value of an ordered ranking are left out of the identity check, because which
    of them appear is arbitrary.
    """
    if match.get("expect_empty"):
        return len(pred_rows) == 0

    g_cols = [str(c) for c in gold["columns"]]
    g_rows = [[normalize(v) for v in row] for row in gold["rows"]]
    p_rows = [[normalize(v) for v in row] for row in pred_rows]
    if not p_rows:
        return len(g_rows) == 0

    n = len(p_rows)
    if match.get("prefix_ok"):
        if n > len(g_rows):
            return False
        g_rows = g_rows[:n]
    elif n != len(g_rows):
        return False

    def g_col(name):
        return [row[g_cols.index(name)] for row in g_rows]

    def p_col(j):
        return [row[j] if j < len(row) else None for row in p_rows]

    ordered_col = match.get("ordered_column")
    chosen: list[tuple[int, int]] = []  # (gold column index, predicted column index)
    metric_pair = None

    groups = list(match.get("required", []))
    if ordered_col:
        groups.sort(key=lambda grp: ordered_col not in grp)  # ordered group first

    for group in groups:
        found = None
        for name in group:
            if name not in g_cols:
                continue
            ordered = name == ordered_col
            for j in range(len(pred_columns) or len(p_rows[0])):
                if any(j == pj for _, pj in chosen):
                    continue
                if lists_equal(g_col(name), p_col(j), ordered):
                    found = (g_cols.index(name), j)
                    break
            if found:
                break
        if not found:
            # Identity columns can differ only in rows tied at the cut-off; retry without them.
            if metric_pair is not None and ordered_col not in group:
                found = _match_ignoring_ties(group, g_cols, g_rows, p_rows, metric_pair, chosen)
            if not found:
                return False
        if ordered_col in group:
            metric_pair = found
        chosen.append(found)

    gi = [g for g, _ in chosen]
    pi = [p for _, p in chosen]
    g_tuples = [tuple(row[i] for i in gi) for row in g_rows]
    p_tuples = [tuple(row[i] if i < len(row) else None for i in pi) for row in p_rows]
    if metric_pair is not None:
        cutoff = g_rows[-1][metric_pair[0]]
        g_tuples = [t for t, row in zip(g_tuples, g_rows) if not values_equal(row[metric_pair[0]], cutoff)]
        p_tuples = [t for t, row in zip(p_tuples, p_rows) if not values_equal(row[metric_pair[1]], cutoff)]
    return tuples_equal(g_tuples, p_tuples)


def _match_ignoring_ties(group, g_cols, g_rows, p_rows, metric_pair, chosen):
    cutoff = g_rows[-1][metric_pair[0]]
    g_keep = [r for r in g_rows if not values_equal(r[metric_pair[0]], cutoff)]
    p_keep = [r for r in p_rows if not values_equal(r[metric_pair[1]], cutoff)]
    for name in group:
        if name not in g_cols:
            continue
        gi = g_cols.index(name)
        for j in range(len(p_rows[0])):
            if any(j == pj for _, pj in chosen):
                continue
            if lists_equal([r[gi] for r in g_keep], [r[j] for r in p_keep], ordered=False):
                return (gi, j)
    return None


def any_variant_matches(variants: list[dict], pred_columns, pred_rows, match: dict) -> bool:
    return any(result_matches(v, pred_columns, pred_rows, match) for v in variants)


# ----------------------------------------------------------------------------- outcomes

def response_type(body: dict | None) -> str:
    if body is None:
        return "error"
    return body.get("response_type") or "answer"


def classify(item: dict, expected: dict, status: int, body: dict | None) -> tuple[str, str]:
    """Return (outcome, detail) for one question."""
    if status != 200 or body is None:
        code = ((body or {}).get("error") or {}).get("code", f"http_{status}")
        return "error", code

    rtype = response_type(body)
    kind = item["kind"]
    cols, rows = body.get("columns") or [], body.get("rows") or []

    if kind == "unanswerable":
        if rtype == "cannot_answer":
            return "declined", ""
        if rtype == "clarification":
            return "clarified", ""
        return "fabricated", f"answered with {len(rows)} rows"

    if rtype == "cannot_answer":
        return "false_refusal", ""

    if kind == "ambiguous":
        if rtype == "clarification":
            return "clarified", ""
        for interp in expected.get("interpretations", []):
            spec = next(i for i in item["interpretations"] if i["label"] == interp["label"])
            if any_variant_matches(interp["variants"], cols, rows, spec["match"]):
                stated = bool(body.get("assumptions"))
                return ("assumed_stated" if stated else "assumed_silent"), interp["label"]
        return "wrong", "matches no interpretation"

    if rtype == "clarification":
        return "unneeded_clarification", ""

    if kind == "schema_lookup":
        haystack = json.dumps([body.get("answer_summary"), body.get("used_tables"), rows]).lower()
        hit = any(m.lower() in haystack for m in item["expected_mentions"])
        return ("correct", "") if hit else ("wrong", "expected table not mentioned")

    ok = any_variant_matches(expected.get("variants", []), cols, rows, item["match"])
    return ("correct", "") if ok else ("wrong", f"{len(rows)} rows did not match gold")


# ----------------------------------------------------------------------------- running

def post_json(url: str, payload: dict, token: str, timeout: float) -> tuple[int, dict | None]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-AskData-Client-Token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"null")
        except json.JSONDecodeError:
            return exc.code, None
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, {"error": {"code": f"connection_failed: {exc}"}}


def check_active_dataset(base_url: str, dataset: str) -> None:
    try:
        with urllib.request.urlopen(f"{base_url}/schema/overview", timeout=30) as response:
            text = response.read().decode()
    except urllib.error.URLError as exc:
        sys.exit(f"Backend not reachable at {base_url}: {exc}")
    if DATASET_SIGNATURE[dataset] not in text:
        sys.exit(f"The backend's active schema is not '{dataset}'. Run `make load-dataset DATASET={dataset}` "
                 "and `make reload-schema-cache`, then try again.")


def run(args) -> Path:
    items = json.loads(QUESTIONS.read_text(encoding="utf-8"))["items"]
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    base_url = args.url.rstrip("/")
    check_active_dataset(base_url, args.dataset)

    selected = [i for i in items if i["dataset"] == args.dataset
                and (args.split == "all" or i["split"] == args.split)]
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{stamp}_{args.label}_{args.dataset}.jsonl"

    with out_path.open("w", encoding="utf-8") as out:
        for item in selected:
            payload = {"question": item["question"], "conversation_context": item["conversation_context"]}
            started = time.perf_counter()
            status, body = post_json(f"{base_url}/query", payload, args.token, args.timeout)
            latency = time.perf_counter() - started
            outcome, detail = classify(item, expected.get(item["id"], {}), status, body)
            record = _record(item, outcome, detail, status, body, latency, args.label)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            mark = "OK " if outcome in GOOD else ("!! " if outcome in SILENT_ERRORS else ".. ")
            print(f"{mark}{item['id']:<10} {outcome:<22} {latency:5.1f}s  {item['question']}")
    print(f"\nSaved {out_path}\n")
    summarize([out_path])
    return out_path


def _record(item, outcome, detail, status, body, latency, label):
    body = body or {}
    return {
        "id": item["id"], "dataset": item["dataset"], "split": item["split"], "kind": item["kind"],
        "category": item["category"], "question": item["question"], "label": label,
        "outcome": outcome, "detail": detail, "status": status,
        "latency_s": round(latency, 3),
        "response_type": response_type(body) if status == 200 else "error",
        "usage": body.get("usage"),
        "generated_sql": body.get("generated_sql"),
        "assumptions": body.get("assumptions"),
        "answer_summary": body.get("answer_summary"),
        "response": body,
    }


def rescore(paths: list[Path]) -> None:
    items = {i["id"]: i for i in json.loads(QUESTIONS.read_text(encoding="utf-8"))["items"]}
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    for path in paths:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for rec in records:
            body = rec.get("response")
            rec["outcome"], rec["detail"] = classify(items[rec["id"]], expected.get(rec["id"], {}),
                                                     rec["status"], body)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    summarize(paths)


# ----------------------------------------------------------------------------- summary

def compute_summary(records: list[dict]) -> dict:
    def rate(num, den):
        return round(num / den, 3) if den else None

    def block(recs):
        by_kind = defaultdict(Counter)
        for r in recs:
            by_kind[r["kind"]][r["outcome"]] += 1
        answerable = by_kind["answerable"] + by_kind["schema_lookup"]
        n_ans = sum(answerable.values())
        n_amb = sum(by_kind["ambiguous"].values())
        n_un = sum(by_kind["unanswerable"].values())
        silent = sum(1 for r in recs if r["outcome"] in SILENT_ERRORS)
        return {
            "questions": len(recs),
            "answerable_accuracy": rate(answerable["correct"], n_ans),
            "ambiguous_clarified": rate(by_kind["ambiguous"]["clarified"], n_amb),
            "ambiguous_handled": rate(by_kind["ambiguous"]["clarified"] + by_kind["ambiguous"]["assumed_stated"], n_amb),
            "unanswerable_declined": rate(by_kind["unanswerable"]["declined"], n_un),
            "silent_error_rate": rate(silent, len(recs)),
            "errors": sum(1 for r in recs if r["outcome"] == "error"),
            "outcomes": {k: dict(v) for k, v in by_kind.items()},
        }

    latencies = [r["latency_s"] for r in records if r.get("latency_s") is not None]
    costs = [r["usage"].get("cost_usd") for r in records if isinstance(r.get("usage"), dict)
             and r["usage"].get("cost_usd") is not None]
    summary = {
        "overall": block(records),
        "by_split": {s: block([r for r in records if r["split"] == s]) for s in sorted({r["split"] for r in records})},
        "by_dataset": {d: block([r for r in records if r["dataset"] == d]) for d in sorted({r["dataset"] for r in records})},
        "latency_s": {
            "median": round(statistics.median(latencies), 2) if latencies else None,
            "p90": round(sorted(latencies)[max(0, math.ceil(0.9 * len(latencies)) - 1)], 2) if latencies else None,
        },
        "cost_usd": {
            "total": round(sum(costs), 4) if costs else None,
            "per_question": round(sum(costs) / len(costs), 5) if costs else None,
            "questions_with_usage": len(costs),
        },
    }
    return summary


def summarize(paths: list[Path]) -> dict:
    records = []
    for path in paths:
        records += [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = compute_summary(records)

    def pct(x):
        return "–" if x is None else f"{100 * x:.0f}%"

    print("| Split | Questions | Answerable accuracy | Vague: asked | Unanswerable: declined | Silent errors |")
    print("|---|---|---|---|---|---|")
    rows = [*summary["by_split"].items(), ("all", summary["overall"])]
    for name, b in rows:
        print(f"| {name} | {b['questions']} | {pct(b['answerable_accuracy'])} | {pct(b['ambiguous_clarified'])} "
              f"| {pct(b['unanswerable_declined'])} | {pct(b['silent_error_rate'])} |")
    lat, cost = summary["latency_s"], summary["cost_usd"]
    print(f"\nLatency median {lat['median']} s, p90 {lat['p90']} s. "
          f"Cost per question: {cost['per_question'] if cost['per_question'] is not None else 'not reported'}.")
    if len(paths) == 1:
        Path(str(paths[0]).replace(".jsonl", ".summary.json")).write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", choices=["pagila", "retail_ops"])
    parser.add_argument("--split", choices=["dev", "heldout", "all"], default="all")
    parser.add_argument("--label", default="run", help="name for this run, e.g. baseline or v3")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="eval-runner")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--rescore", nargs="+", type=Path)
    parser.add_argument("--summarize", nargs="+", type=Path)
    args = parser.parse_args()

    if args.rescore:
        rescore(args.rescore)
    elif args.summarize:
        summarize(args.summarize)
    elif args.dataset:
        run(args)
    else:
        parser.error("give --dataset, --rescore or --summarize")


if __name__ == "__main__":
    main()
