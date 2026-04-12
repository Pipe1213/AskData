import json
from pathlib import Path

from app.services.database_target_service import ResolvedDatabaseTarget


GENERIC_RUNTIME_EXAMPLES = [
    "What were the top 10 customers by revenue last quarter?",
    "Show monthly revenue trend for the last 12 months.",
    "Which products or categories are growing the fastest?",
    "Compare average order value by region.",
    "Which records had the highest activity this month?",
]


class ExamplesService:
    def __init__(self, examples_path: Path | None = None) -> None:
        self.examples_path = examples_path

    def get_examples(self, target: ResolvedDatabaseTarget | None = None) -> list[str]:
        if target is not None and target.target_type == "runtime_postgres":
            return list(GENERIC_RUNTIME_EXAMPLES)

        with self._resolve_examples_path(target).open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        examples = payload.get("examples", [])
        if not isinstance(examples, list):
            raise ValueError("Examples payload must contain a list under 'examples'.")

        return [str(example) for example in examples]

    def _resolve_examples_path(self, target: ResolvedDatabaseTarget | None = None) -> Path:
        if self.examples_path is not None:
            return self.examples_path

        root = Path(__file__).resolve().parents[3]
        dataset_name = target.dataset_name if target is not None and target.dataset_name else "pagila"

        dataset_examples_path = root / "demo_data" / "example_questions" / f"{dataset_name}_questions.json"
        if dataset_examples_path.exists():
            return dataset_examples_path

        return root / "demo_data" / "example_questions" / "pagila_questions.json"
