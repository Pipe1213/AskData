from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import httpx


DEFAULT_BENCHMARK_PATH = (
    Path(__file__).resolve().parents[2] / "demo_data" / "example_questions" / "v1_benchmark.json"
)


def main() -> None:
    backend_url = os.environ.get("ASKDATA_BENCHMARK_URL", "http://127.0.0.1:8000").rstrip("/")
    benchmark_path = Path(
        os.environ.get("ASKDATA_BENCHMARK_FILE", str(DEFAULT_BENCHMARK_PATH))
    )
    client_token = os.environ.get("ASKDATA_BENCHMARK_CLIENT_TOKEN", "benchmark-runner")

    with benchmark_path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)

    counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()

    with httpx.Client(timeout=60.0, headers={"X-AskData-Client-Token": client_token}) as client:
        for case in cases:
            payload = {"question": case["question"]}
            if case.get("conversation_context"):
                payload["conversation_context"] = case["conversation_context"]

            response = client.post(f"{backend_url}/query", json=payload)
            category = case.get("category", "uncategorized")
            category_counts[category] += 1

            if response.status_code == 200:
                body = response.json()
                if int(body.get("row_count", 0)) == 0:
                    counts["success_no_rows"] += 1
                    result_key = "success_no_rows"
                else:
                    counts["success"] += 1
                    result_key = "success"
            else:
                body = response.json()
                result_key = str(body.get("error", {}).get("code", "unknown_error"))
                counts[result_key] += 1

            print(f"[{category}] {case['question']}")
            print(f"  -> {result_key}")

    print("\nSummary")
    print("-------")
    print(f"Benchmark file: {benchmark_path}")
    print(f"Backend URL: {backend_url}")
    print(f"Total cases: {sum(category_counts.values())}")
    print()

    for key, count in sorted(counts.items()):
        print(f"{key}: {count}")

    print("\nCategories")
    for key, count in sorted(category_counts.items()):
        print(f"{key}: {count}")


if __name__ == "__main__":
    main()
