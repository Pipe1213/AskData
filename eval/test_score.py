"""Tests for the scoring logic (no backend or database needed).

    python -m pytest eval/test_score.py     # or: python eval/test_score.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import score

EVAL_DIR = Path(__file__).resolve().parent
ITEMS = {i["id"]: i for i in json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))["items"]}
EXPECTED = json.loads((EVAL_DIR / "expected.json").read_text(encoding="utf-8"))


def body_from(result: dict, **extra) -> dict:
    return {"columns": list(result["columns"]), "rows": copy.deepcopy(result["rows"]),
            "row_count": len(result["rows"]), "answer_summary": "", **extra}


def outcome(item_id: str, body: dict, status: int = 200) -> str:
    return score.classify(ITEMS[item_id], EXPECTED.get(item_id, {}), status, body)[0]


def gold(item_id: str, variant: int = 0) -> dict:
    return EXPECTED[item_id]["variants"][variant]


# ---------------------------------------------------------------- data integrity

def test_every_gold_query_has_expected_results():
    for item_id, item in ITEMS.items():
        if item["kind"] == "answerable":
            assert len(EXPECTED[item_id]["variants"]) == len(item["gold_sql"]), item_id
        if item["kind"] == "ambiguous":
            assert len(EXPECTED[item_id]["interpretations"]) == len(item["interpretations"]), item_id


def test_ids_are_unique_and_splits_valid():
    raw = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))["items"]
    assert len({i["id"] for i in raw}) == len(raw)
    assert {i["split"] for i in raw} == {"dev", "heldout"}


def test_gold_answers_itself():
    for item_id, item in ITEMS.items():
        if item["kind"] != "answerable":
            continue
        for v in EXPECTED[item_id]["variants"]:
            assert outcome(item_id, body_from(v)) == "correct", item_id


# ---------------------------------------------------------------- answerable matching

def test_screenshot_answer_is_wrong():
    wrong = {"columns": ["customer_id", "first_name", "total_spent"], "rows": [
        [178, "MARION", 64.87], [181, "ANA", 58.91], [236, "MARCIA", 57.88], [585, "PERRY", 56.90],
        [240, "MARLENE", 56.90], [363, "ROY", 55.90], [558, "JIMMIE", 53.91], [468, "TIM", 53.88],
        [372, "STEVE", 52.89], [86, "JACQUELINE", 51.88]]}
    assert outcome("pg-dev-01", wrong) == "wrong"


def test_column_names_order_and_extra_columns_do_not_matter():
    g = gold("pg-dev-01")
    rows = [[r[4], r[3], "extra", r[0]] for r in g["rows"]]  # total, name, junk, id
    assert outcome("pg-dev-01", {"columns": ["spend", "who", "x", "id"], "rows": rows}) == "correct"


def test_name_only_identity_is_enough():
    g = gold("pg-dev-01")
    rows = [[r[3].title(), float(r[4])] for r in g["rows"]]
    assert outcome("pg-dev-01", {"columns": ["customer", "total"], "rows": rows}) == "correct"


def test_metric_must_be_in_order_for_rankings():
    g = gold("pg-dev-01")
    rows = list(reversed(g["rows"]))
    assert outcome("pg-dev-01", {"columns": g["columns"], "rows": rows}) == "wrong"


def test_rows_must_line_up():
    g = gold("pg-dev-03")
    rows = copy.deepcopy(g["rows"])
    rows[0][4], rows[1][4] = rows[1][4], rows[0][4]  # swap revenue between staff
    assert outcome("pg-dev-03", {"columns": g["columns"], "rows": rows}) == "wrong"


def test_rounded_averages_are_accepted():
    g = gold("pg-ho-03")
    rows = [[r[0], round(float(r[1]), 2)] for r in g["rows"]]
    assert outcome("pg-ho-03", {"columns": g["columns"], "rows": rows}) == "correct"


def test_prefix_of_open_ranking_is_accepted():
    g = gold("pg-ho-08")
    assert outcome("pg-ho-08", {"columns": g["columns"], "rows": g["rows"][:1]}) == "correct"
    assert outcome("pg-ho-08", {"columns": g["columns"], "rows": g["rows"][1:3]}) == "wrong"


def test_fixed_size_ranking_rejects_wrong_size():
    g = gold("pg-dev-01")
    assert outcome("pg-dev-01", {"columns": g["columns"], "rows": g["rows"][:9]}) == "wrong"


def test_ties_at_cutoff_are_tolerated():
    g = gold("pg-ho-06")  # 10th place has 31 rentals, shared by more films
    rows = copy.deepcopy(g["rows"])
    assert float(rows[-1][2]) == 31
    rows[-1] = ["9999", "SOME OTHER FILM", "31"]
    assert outcome("pg-ho-06", {"columns": g["columns"], "rows": rows}) == "correct"
    rows[-1] = ["9999", "SOME OTHER FILM", "30"]
    assert outcome("pg-ho-06", {"columns": g["columns"], "rows": rows}) == "wrong"


def test_zero_filled_months_variant():
    assert outcome("pg-dev-04", body_from(gold("pg-dev-04", 1))) == "correct"
    assert outcome("pg-dev-04", body_from(gold("pg-dev-04", 0))) == "correct"


def test_empty_answers():
    assert outcome("pg-dev-10", {"columns": ["rental_id"], "rows": []}) == "correct"
    assert outcome("pg-dev-10", {"columns": ["rental_id"], "rows": [[1]]}) == "wrong"
    g = gold("pg-dev-01")
    assert outcome("pg-dev-01", {"columns": g["columns"], "rows": []}) == "wrong"


def test_dates_and_timestamps_normalize():
    assert score.normalize("2022-02-01 00:00:00+00") == "2022-02-01"
    assert score.normalize("2022-02-01T00:00:00Z") == "2022-02-01"
    assert score.normalize("2022-02-01") == "2022-02-01"
    assert score.normalize(" PG-13 ") == "pg-13"
    assert score.normalize("221.55") == 221.55


# ---------------------------------------------------------------- behaviour outcomes

def test_unanswerable_outcomes():
    assert outcome("pg-ho-14", {"response_type": "cannot_answer", "columns": [], "rows": []}) == "declined"
    assert outcome("pg-ho-14", {"columns": ["film", "margin"], "rows": [["A", 1.0]]}) == "fabricated"
    assert outcome("pg-ho-14", {"response_type": "clarification", "columns": [], "rows": []}) == "clarified"


def test_ambiguous_outcomes():
    interp = EXPECTED["pg-ho-11"]["interpretations"][1]["variants"][0]  # rented the most
    top5 = {"columns": interp["columns"], "rows": interp["rows"][:5]}
    assert outcome("pg-ho-11", {"response_type": "clarification", "columns": [], "rows": []}) == "clarified"
    assert outcome("pg-ho-11", {**top5, "assumptions": ["best = most rentals"]}) == "assumed_stated"
    assert outcome("pg-ho-11", top5) == "assumed_silent"
    assert outcome("pg-ho-11", {"columns": ["x", "y"], "rows": [["nobody", 1]]}) == "wrong"


def test_answerable_behaviour_outcomes():
    assert outcome("pg-dev-01", {"response_type": "clarification", "columns": [], "rows": []}) == "unneeded_clarification"
    assert outcome("pg-dev-01", {"response_type": "cannot_answer", "columns": [], "rows": []}) == "false_refusal"
    assert outcome("pg-dev-01", {"error": {"code": "sql_execution_failed"}}, status=422) == "error"


def test_schema_lookup():
    assert outcome("pg-dev-06", {"answer_summary": "Payments are in the payment table.", "columns": [], "rows": []}) == "correct"
    assert outcome("pg-dev-06", {"answer_summary": "See the film table.", "columns": [], "rows": []}) == "wrong"


def test_summary_metrics():
    recs = [
        {"kind": "answerable", "split": "dev", "dataset": "pagila", "outcome": "correct", "latency_s": 1.0, "usage": {"cost_usd": 0.002}},
        {"kind": "answerable", "split": "dev", "dataset": "pagila", "outcome": "wrong", "latency_s": 2.0, "usage": None},
        {"kind": "ambiguous", "split": "heldout", "dataset": "pagila", "outcome": "clarified", "latency_s": 3.0, "usage": None},
        {"kind": "unanswerable", "split": "heldout", "dataset": "pagila", "outcome": "fabricated", "latency_s": 4.0, "usage": None},
    ]
    s = score.compute_summary(recs)
    assert s["overall"]["answerable_accuracy"] == 0.5
    assert s["overall"]["ambiguous_clarified"] == 1.0
    assert s["overall"]["unanswerable_declined"] == 0.0
    assert s["overall"]["silent_error_rate"] == 0.5
    assert s["latency_s"]["median"] == 2.5
    assert s["cost_usd"]["questions_with_usage"] == 1


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"pass  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}")
    raise SystemExit(1 if failures else 0)
