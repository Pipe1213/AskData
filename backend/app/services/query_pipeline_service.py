from app.core.config import Settings, get_settings
from app.core.exceptions import QueryPipelineError
from app.db.metadata_models import DatabaseSchema
from app.llm.base import LLMClientError
from app.schemas.query import ConversationMessage, DebugPayload, QueryResponse
from app.services.response_formatter_service import ResponseFormatterService
from app.services.retrieval_service import RetrievalService
from app.services.sql_execution_service import SQLExecutionService
from app.services.sql_generation_service import SQLGenerationService
from app.services.sql_validation_service import SQLValidationService
from app.utils.text import significant_tokens


class QueryPipelineService:
    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        sql_generation_service: SQLGenerationService | None = None,
        sql_validation_service: SQLValidationService | None = None,
        sql_execution_service: SQLExecutionService | None = None,
        response_formatter_service: ResponseFormatterService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.retrieval_service = retrieval_service or RetrievalService()
        self.sql_generation_service = sql_generation_service or SQLGenerationService(
            settings=self.settings
        )
        self.sql_validation_service = sql_validation_service or SQLValidationService(
            settings=self.settings
        )
        self.sql_execution_service = sql_execution_service or SQLExecutionService(
            settings=self.settings
        )
        self.response_formatter_service = (
            response_formatter_service
            or ResponseFormatterService(settings=self.settings)
        )

    def run_query(
        self,
        question: str,
        schema: DatabaseSchema | None,
        conversation_context: list[ConversationMessage] | None = None,
    ) -> QueryResponse:
        normalized_question = question.strip()
        if not normalized_question:
            raise QueryPipelineError(
                code="invalid_request",
                message="Question must not be empty.",
                stage="input",
                retryable=False,
            )

        if schema is None:
            raise QueryPipelineError(
                code="schema_unavailable",
                message="Schema metadata is not available.",
                stage="schema",
                retryable=False,
            )

        normalized_conversation_context = self._normalize_conversation_context(
            conversation_context
        )
        retrieval_question = self._build_retrieval_question(
            normalized_question,
            normalized_conversation_context,
        )

        retrieval_context = self.retrieval_service.retrieve_schema_context(
            retrieval_question,
            schema,
        )
        if not retrieval_context.tables:
            raise QueryPipelineError(
                code="invalid_request",
                message="No relevant schema context could be found for the question.",
                stage="retrieval",
                retryable=False,
                details={"warnings": retrieval_context.warnings},
            )

        try:
            generation_result = self.sql_generation_service.generate_sql(
                question=normalized_question,
                schema_context=retrieval_context,
                conversation_context=normalized_conversation_context,
            )
        except LLMClientError as exc:
            raise QueryPipelineError(
                code="sql_generation_failed",
                message=str(exc),
                stage="generation",
                retryable=True,
            ) from exc

        generation_result, semantic_review_warnings = self._apply_semantic_review(
            question=normalized_question,
            retrieval_context=retrieval_context,
            generation_result=generation_result,
            conversation_context=normalized_conversation_context,
        )

        pipeline_result = self._validate_and_execute_once(
            question=normalized_question,
            retrieval_context=retrieval_context,
            generation_result=generation_result,
            allow_repair=True,
            conversation_context=normalized_conversation_context,
        )

        used_tables = self._merge_used_tables(
            schema=schema,
            generated_tables=pipeline_result["generation_result"].used_tables,
            detected_tables=pipeline_result["validation_result"].detected_tables,
        )
        merged_warnings = [
            *retrieval_context.warnings,
            *pipeline_result["generation_result"].notes,
            *pipeline_result["validation_result"].warnings,
            *semantic_review_warnings,
            *pipeline_result["repair_warnings"],
        ]

        response = self.response_formatter_service.format_query_response(
            question=normalized_question,
            generated_sql=(
                pipeline_result["validation_result"].validated_sql
                or pipeline_result["generation_result"].sql
            ),
            execution_result=pipeline_result["execution_result"],
            used_tables=used_tables,
            warnings=merged_warnings,
            repaired=bool(pipeline_result["repair_warnings"] or semantic_review_warnings),
        )
        if self.settings.debug_mode:
            return response.model_copy(
                update={
                    "debug": DebugPayload(
                        stage="success",
                        retrieval_tables=[table.full_name for table in retrieval_context.tables],
                        validation_classification=pipeline_result["validation_result"].classification,
                        detected_tables=pipeline_result["validation_result"].detected_tables,
                        repair_attempted=bool(pipeline_result["repair_warnings"]),
                    )
                }
            )

        return response

    def _apply_semantic_review(
        self,
        question: str,
        retrieval_context,
        generation_result,
        conversation_context: list[ConversationMessage],
    ):
        if not hasattr(self.sql_generation_service, "review_sql"):
            return generation_result, []

        try:
            review_result = self.sql_generation_service.review_sql(
                question=question,
                schema_context=retrieval_context,
                generated_sql=generation_result.sql,
                conversation_context=conversation_context,
            )
        except LLMClientError:
            return generation_result, []

        if not review_result.should_rewrite:
            return generation_result, []

        issues = [issue.strip() for issue in review_result.issues if issue.strip()]
        if review_result.suggested_focus:
            issues.append(review_result.suggested_focus.strip())

        try:
            rewritten = self.sql_generation_service.repair_sql(
                question=question,
                schema_context=retrieval_context,
                previous_sql=generation_result.sql,
                failure_message="Semantic review: " + "; ".join(issues or ["Refocus the SQL on the user's business intent."]),
                conversation_context=conversation_context,
            )
        except LLMClientError:
            return generation_result, []

        return rewritten, ["SQL was rewritten once after a semantic review."]

    def _validate_and_execute_once(
        self,
        question: str,
        retrieval_context,
        generation_result,
        allow_repair: bool,
        conversation_context: list[ConversationMessage],
    ) -> dict:
        validation_result = self.sql_validation_service.validate_sql(generation_result.sql)
        if not validation_result.is_valid:
            if validation_result.classification == "hard_safety_failure":
                raise QueryPipelineError(
                    code="unsafe_sql",
                    message="Generated SQL violated the read-only safety policy.",
                    stage="validation",
                    retryable=False,
                    details={"errors": validation_result.errors},
                )

            if allow_repair:
                repaired_result = self._repair_generation(
                    question=question,
                    retrieval_context=retrieval_context,
                    previous_sql=generation_result.sql,
                    failure_message="; ".join(validation_result.errors),
                    repair_stage="validation",
                    conversation_context=conversation_context,
                )
                result = self._validate_and_execute_once(
                    question=question,
                    retrieval_context=retrieval_context,
                    generation_result=repaired_result,
                    allow_repair=False,
                    conversation_context=conversation_context,
                )
                result["repair_warnings"] = [
                    "SQL was repaired once after a validation failure.",
                    *result["repair_warnings"],
                ]
                return result

            raise QueryPipelineError(
                code="sql_validation_failed",
                message="Generated SQL failed validation.",
                stage="validation",
                retryable=False,
                details={"errors": validation_result.errors},
            )

        execution_result = self.sql_execution_service.execute_sql(
            validation_result.validated_sql or generation_result.sql
        )
        if not execution_result.success:
            if allow_repair:
                repaired_result = self._repair_generation(
                    question=question,
                    retrieval_context=retrieval_context,
                    previous_sql=validation_result.validated_sql or generation_result.sql,
                    failure_message=(
                        execution_result.error.message
                        if execution_result.error is not None
                        else "SQL execution failed."
                    ),
                    repair_stage="execution",
                    conversation_context=conversation_context,
                )
                result = self._validate_and_execute_once(
                    question=question,
                    retrieval_context=retrieval_context,
                    generation_result=repaired_result,
                    allow_repair=False,
                    conversation_context=conversation_context,
                )
                result["repair_warnings"] = [
                    "SQL was repaired once after an execution failure.",
                    *result["repair_warnings"],
                ]
                return result

            raise QueryPipelineError(
                code="sql_execution_failed",
                message=(
                    execution_result.error.message
                    if execution_result.error is not None
                    else "SQL execution failed."
                ),
                stage="execution",
                retryable=False,
                details=(
                    execution_result.error.details
                    if execution_result.error is not None
                    else {}
                ),
            )

        return {
            "generation_result": generation_result,
            "validation_result": validation_result,
            "execution_result": execution_result,
            "repair_warnings": [],
        }

    def _repair_generation(
        self,
        question: str,
        retrieval_context,
        previous_sql: str,
        failure_message: str,
        repair_stage: str,
        conversation_context: list[ConversationMessage],
    ):
        try:
            return self.sql_generation_service.repair_sql(
                question=question,
                schema_context=retrieval_context,
                previous_sql=previous_sql,
                failure_message=failure_message,
                conversation_context=conversation_context,
            )
        except LLMClientError as exc:
            raise QueryPipelineError(
                code="sql_generation_failed",
                message=str(exc),
                stage=repair_stage,
                retryable=False,
            ) from exc

    def _merge_used_tables(
        self,
        schema: DatabaseSchema,
        generated_tables: list[str],
        detected_tables: list[str],
    ) -> list[str]:
        full_name_map = {
            table.full_name.lower(): table.full_name
            for table in schema.tables
        }
        short_name_map: dict[str, str | None] = {}
        for table in schema.tables:
            table_key = table.table_name.lower()
            if table_key not in short_name_map:
                short_name_map[table_key] = table.full_name
            else:
                short_name_map[table_key] = None

        canonical_tables: list[str] = []
        seen: set[str] = set()

        for table_name in [*detected_tables, *generated_tables]:
            canonical_name = self._canonicalize_table_name(
                table_name=table_name,
                full_name_map=full_name_map,
                short_name_map=short_name_map,
            )
            if canonical_name is None or canonical_name in seen:
                continue

            seen.add(canonical_name)
            canonical_tables.append(canonical_name)

        return canonical_tables

    def _canonicalize_table_name(
        self,
        table_name: str,
        full_name_map: dict[str, str],
        short_name_map: dict[str, str | None],
    ) -> str | None:
        normalized_name = table_name.strip().lower()
        if not normalized_name:
            return None

        if normalized_name in full_name_map:
            return full_name_map[normalized_name]

        if "." not in normalized_name:
            return short_name_map.get(normalized_name)

        return None

    def _normalize_conversation_context(
        self,
        conversation_context: list[ConversationMessage] | None,
    ) -> list[ConversationMessage]:
        if not conversation_context:
            return []

        normalized_messages: list[ConversationMessage] = []
        for message in conversation_context[-6:]:
            content = message.content.strip()
            if not content:
                continue

            normalized_messages.append(
                ConversationMessage(
                    role=message.role,
                    content=content[:500],
                )
            )

        return normalized_messages

    def _build_retrieval_question(
        self,
        question: str,
        conversation_context: list[ConversationMessage],
    ) -> str:
        if not conversation_context:
            return question

        if not self._should_apply_context_to_retrieval(question):
            return question

        context_hints = " ".join(message.content for message in conversation_context)
        return f"{question}\nContext hints: {context_hints}"

    def _should_apply_context_to_retrieval(self, question: str) -> bool:
        normalized_question = question.strip().lower()
        question_tokens = significant_tokens(normalized_question)
        referential_terms = {
            "that",
            "those",
            "them",
            "it",
            "now",
            "same",
            "previous",
            "above",
            "instead",
            "only",
            "also",
        }

        if len(question_tokens) <= 3:
            return True

        return any(term in normalized_question.split() for term in referential_terms)
