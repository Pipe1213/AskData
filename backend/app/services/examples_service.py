import json
from pathlib import Path


class ExamplesService:
    def __init__(self, examples_path: Path | None = None) -> None:
        self.examples_path = examples_path

    def get_examples(self) -> list[str]:
        with self._resolve_examples_path().open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        examples = payload.get("examples", [])
        if not isinstance(examples, list):
            raise ValueError("Examples payload must contain a list under 'examples'.")

        return [str(example) for example in examples]

    def _resolve_examples_path(self) -> Path:
        if self.examples_path is not None:
            return self.examples_path

        root = Path(__file__).resolve().parents[3]
        active_dataset_file = root / "demo_data" / "active_dataset.txt"
        dataset_name = "pagila"
        if active_dataset_file.exists():
            dataset_name = active_dataset_file.read_text(encoding="utf-8").strip() or dataset_name

        dataset_examples_path = root / "demo_data" / "example_questions" / f"{dataset_name}_questions.json"
        if dataset_examples_path.exists():
            return dataset_examples_path

        return root / "demo_data" / "example_questions" / "pagila_questions.json"
