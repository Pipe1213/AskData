import json
from pathlib import Path


class ExamplesService:
    def __init__(self, examples_path: Path | None = None) -> None:
        self.examples_path = examples_path or self._default_examples_path()

    def get_examples(self) -> list[str]:
        with self.examples_path.open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        examples = payload.get("examples", [])
        if not isinstance(examples, list):
            raise ValueError("Examples payload must contain a list under 'examples'.")

        return [str(example) for example in examples]

    def _default_examples_path(self) -> Path:
        return Path(__file__).resolve().parents[3] / "demo_data" / "example_questions" / "pagila_questions.json"
