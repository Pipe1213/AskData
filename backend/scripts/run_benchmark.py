from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_QUESTIONS_DIR = ROOT / "demo_data" / "example_questions"
ACTIVE_DATASET_FILE = ROOT / "demo_data" / "active_dataset.txt"
DEFAULT_DATASET = "pagila"


def main() -> None:
    backend_url = os.environ.get("ASKDATA_BENCHMARK_URL", "http://127.0.0.1:8000").rstrip("/")
    dataset_name = os.environ.get("ASKDATA_BENCHMARK_DATASET", _default_dataset_name())
    benchmark_path = Path(
        os.environ.get(
            "ASKDATA_BENCHMARK_FILE",
            str(EXAMPLE_QUESTIONS_DIR / f"{dataset_name}_benchmark.json"),
        )
    )
    client_token = os.environ.get("ASKDATA_BENCHMARK_CLIENT_TOKEN", "benchmark-runner")

    with benchmark_path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)

    counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    dataset_counts: Counter[str] = Counter()

    with httpx.Client(timeout=60.0, headers={"X-AskData-Client-Token": client_token}) as client:
        for case in cases:
            payload = {"question": case["question"]}
            if case.get("conversation_context"):
                payload["conversation_context"] = case["conversation_context"]

            response = client.post(f"{backend_url}/query", json=payload)
            category = case.get("category", "uncategorized")
            dataset = case.get("dataset", dataset_name)
            category_counts[category] += 1
            dataset_counts[dataset] += 1

            if response.status_code == 200:
                body = response.json()
                issues = _evaluate_expectations(case, body)

                if int(body.get("row_count", 0)) == 0:
                    result_key = "success_no_rows"
                    if not case.get("allow_no_rows", False):
                        issues.append("unexpected_no_rows")
                else:
                    result_key = "success"

                if issues:
                    counts["expectation_gap"] += 1
                    counts[result_key] += 1
                else:
                    counts[result_key] += 1

                print(f"[{dataset}/{category}] {case['question']}")
                print(f"  -> {result_key}")
                if issues:
                    print(f"  -> expectation gaps: {', '.join(issues)}")
            else:
                body = response.json()
                result_key = str(body.get("error", {}).get("code", "unknown_error"))
                counts[result_key] += 1
                print(f"[{dataset}/{category}] {case['question']}")
                print(f"  -> {result_key}")

    print("\nSummary")
    print("-------")
    print(f"Benchmark file: {benchmark_path}")
    print(f"Backend URL: {backend_url}")
    print(f"Total cases: {sum(category_counts.values())}")
    print()

    for key, count in sorted(counts.items()):
        print(f"{key}: {count}")

    print("\nDatasets")
    for key, count in sorted(dataset_counts.items()):
        print(f"{key}: {count}")

    print("\nCategories")
    for key, count in sorted(category_counts.items()):
        print(f"{key}: {count}")


def _evaluate_expectations(case: dict, body: dict) -> list[str]:
    issues: list[str] = []

    expected_task_type = case.get("expected_task_type")
    actual_task_type = ((body.get("plan") or {}).get("task_type"))
    if expected_task_type and actual_task_type != expected_task_type:
        issues.append(f"task_type={actual_task_type or 'missing'}")

    expected_primary_artifact = case.get("expected_primary_artifact")
    actual_primary_artifact = body.get("primary_artifact")
    if expected_primary_artifact and actual_primary_artifact != expected_primary_artifact:
        issues.append(f"primary_artifact={actual_primary_artifact or 'missing'}")

    expected_used_tables = case.get("expected_used_tables", [])
    actual_used_tables = set(body.get("used_tables") or [])
    if expected_used_tables:
        missing_tables = [table for table in expected_used_tables if table not in actual_used_tables]
        if len(missing_tables) == len(expected_used_tables):
            issues.append("used_tables_miss")

    return issues


def _default_dataset_name() -> str:
    if ACTIVE_DATASET_FILE.exists():
        value = ACTIVE_DATASET_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return DEFAULT_DATASET


if __name__ == "__main__":
    main()
