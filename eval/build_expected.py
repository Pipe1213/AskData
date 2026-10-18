"""Run every gold query in eval/questions.json and save the results to eval/expected.json.

The scorer compares AskData's answers against these saved results, so scoring does not
need direct database access. Re-run this only when the questions or the seed data change.

Usage (one dataset at a time, because the demo database holds one dataset at a time):

    make load-dataset DATASET=pagila
    python eval/build_expected.py --dataset pagila --dsn postgresql://postgres:postgres@localhost:55432/pagila

Uses psycopg when installed (backend venv); otherwise falls back to the `psql` CLI,
where --dsn is passed straight to psql.
Queries run in a read-only transaction with timezone=UTC (the Docker image default).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS = EVAL_DIR / "questions.json"
EXPECTED = EVAL_DIR / "expected.json"


def _to_jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def run_psycopg(dsn: str, sql: str) -> dict:
    import psycopg  # noqa: PLC0415

    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("SET LOCAL timezone = 'UTC'")
            cur.execute(sql)
            columns = [d.name for d in cur.description]
            rows = [[_to_jsonable(v) for v in row] for row in cur.fetchall()]
    return {"columns": columns, "rows": rows}


def run_psql(dsn: str, sql: str) -> dict:
    script = f"BEGIN READ ONLY;\nSET LOCAL timezone = 'UTC';\n\\pset footer off\n{sql};\nCOMMIT;\n"
    out = subprocess.run(
        ["psql", dsn, "-X", "-q", "--csv", "-v", "ON_ERROR_STOP=1"],
        input=script, capture_output=True, text=True, check=True,
    ).stdout
    lines = [line for line in out.splitlines() if line not in ("BEGIN", "SET", "COMMIT")]
    parsed = list(csv.reader(io.StringIO("\n".join(lines))))
    if not parsed:
        return {"columns": [], "rows": []}
    columns, rows = parsed[0], parsed[1:]
    rows = [[None if v == "" else v for v in row] for row in rows]
    return {"columns": columns, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, choices=["pagila", "retail_ops"])
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", action="store_true", help="force the psql CLI backend")
    args = parser.parse_args()

    runner = run_psql
    if not args.psql:
        try:
            import psycopg  # noqa: F401, PLC0415
            runner = run_psycopg
        except ImportError:
            pass

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))["items"]
    expected = json.loads(EXPECTED.read_text(encoding="utf-8")) if EXPECTED.exists() else {}

    for item in questions:
        if item["dataset"] != args.dataset:
            continue
        entry: dict = {}
        if item["kind"] == "answerable":
            entry["variants"] = [runner(args.dsn, sql) for sql in item["gold_sql"]]
        elif item["kind"] == "ambiguous":
            entry["interpretations"] = [
                {"label": i["label"], "variants": [runner(args.dsn, sql) for sql in i["gold_sql"]]}
                for i in item["interpretations"]
            ]
        else:
            continue
        expected[item["id"]] = entry
        sizes = [len(v["rows"]) for v in entry.get("variants", [])] or [
            len(i["variants"][0]["rows"]) for i in entry["interpretations"]
        ]
        print(f"{item['id']}: rows {sizes}")

    EXPECTED.write_text(json.dumps(dict(sorted(expected.items())), indent=1) + "\n", encoding="utf-8")
    print(f"Saved {EXPECTED}")


if __name__ == "__main__":
    main()
