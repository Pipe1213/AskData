"""Hook for dataset-specific prompt hints.

AskData ships no dataset-specific hints: retrieval and prompts work only from what the database
itself says (table and column names, types, comments, foreign keys), so evaluation results
reflect the generic pipeline.
"""

from app.db.metadata_models import DatabaseSchema


class DatasetAdapter:
    name = "generic_postgres"

    def prompt_hints(self, question_tokens: set[str]) -> list[str]:
        return []


class GenericPostgresAdapter(DatasetAdapter):
    name = "generic_postgres"


def resolve_dataset_adapter(schema: DatabaseSchema) -> DatasetAdapter:
    return GenericPostgresAdapter()
