from app.services.database_target_service import ResolvedDatabaseTarget
from app.services.examples_service import ExamplesService


def test_examples_service_uses_demo_target_dataset_file() -> None:
    service = ExamplesService()
    target = ResolvedDatabaseTarget(
        target_id="demo_retail_ops",
        target_type="demo_retail_ops",
        display_name="Retail Ops",
        persistence_allowed=True,
        dataset_name="retail_ops",
        schema_allowlist=["public"],
    )

    examples = service.get_examples(target)

    assert examples
    assert any("revenue" in example.lower() for example in examples)


def test_examples_service_uses_generic_prompts_for_runtime_targets() -> None:
    service = ExamplesService()
    target = ResolvedDatabaseTarget(
        target_id="runtime_postgres:test-token",
        target_type="runtime_postgres",
        display_name="analytics @ localhost",
        persistence_allowed=False,
        schema_allowlist=["public"],
    )

    examples = service.get_examples(target)

    assert examples
    assert any("last 12 months" in example.lower() for example in examples)
