import logging
from decimal import Decimal

from app.core.config import Settings, get_settings
from app.core.exceptions import QueryPipelineError
from app.db.metadata_models import DatabaseSchema
from app.llm.base import LLMClientError
from app.llm.usage import log_usage, track_llm_usage
from app.schemas.data_source import PostgresConnectionSettings
from app.schemas.query import (
    CannotAnswerPayload,
    ChartRecommendation,
    ClarificationPayload,
    ConversationMessage,
    DebugPayload,
    MemoryContext,
    QueryPlan,
    QueryResponse,
    QueryTrace,
    QueryTraceStep,
    QuestionTriageResult,
)
from app.services.dataset_adapters import DatasetAdapter, resolve_dataset_adapter
from app.services.planner_service import PlannerService
from app.services.response_formatter_service import ResponseFormatterService
from app.services.retrieval_service import RetrievalService
from app.services.sql_execution_service import SQLExecutionService
from app.services.sql_generation_service import SQLGenerationService
from app.services.sql_validation_service import SQLValidationService
from app.utils.text import significant_tokens

logger = logging.getLogger(__name__)


class QueryPipelineService:
    def __init__(
        self,
        planner_service: PlannerService | None = None,
        retrieval_service: RetrievalService | None = None,
        sql_generation_service: SQLGenerationService | None = None,
        sql_validation_service: SQLValidationService | None = None,
        sql_execution_service: SQLExecutionService | None = None,
        response_formatter_service: ResponseFormatterService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.planner_service = planner_service or PlannerService()
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
        connection_settings: PostgresConnectionSettings | None = None,
        conversation_context: list[ConversationMessage] | None = None,
        memory_context: MemoryContext | None = None,
    ) -> QueryResponse:
        with track_llm_usage() as usage_meter:
            try:
                response = self._run_query(
                    question=question,
                    schema=schema,
                    connection_settings=connection_settings,
                    conversation_context=conversation_context,
                    memory_context=memory_context,
                )
            except QueryPipelineError as exc:
                exc.usage = usage_meter.summary()
                log_usage(exc.usage)
                raise

        usage = usage_meter.summary()
        log_usage(usage)
        return response.model_copy(update={"usage": usage})

    def _run_query(
        self,
        question: str,
        schema: DatabaseSchema | None,
        connection_settings: PostgresConnectionSettings | None = None,
        conversation_context: list[ConversationMessage] | None = None,
        memory_context: MemoryContext | None = None,
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
        dataset_adapter = resolve_dataset_adapter(schema)
        plan = self.planner_service.build_plan(
            normalized_question,
            conversation_context=normalized_conversation_context,
            memory_context=memory_context,
        )
        trace = self._new_trace(plan)
        triage_result = self._triage_question(
            question=normalized_question,
            schema=schema,
            conversation_context=normalized_conversation_context,
            memory_context=memory_context,
            dataset_adapter=dataset_adapter,
            plan=plan,
            trace=trace,
        )
        if triage_result is not None and triage_result.decision != "answerable":
            return self._build_non_answer_response(
                question=normalized_question,
                triage_result=triage_result,
                plan=plan,
                trace=trace,
            )

        retry_reasons: list[str] = []
        retry_classifications: list[str] = []
        recovery_actions: list[str] = []
        original_error: QueryPipelineError | None = None

        try:
            attempt = self._run_attempt(
                question=normalized_question,
                schema=schema,
                connection_settings=connection_settings,
                conversation_context=normalized_conversation_context,
                memory_context=memory_context,
                dataset_adapter=dataset_adapter,
                plan=plan,
                broaden=False,
                trace=trace,
            )
        except QueryPipelineError as exc:
            original_error = exc
            if not self._should_retry_after_error(exc, plan):
                raise

            retry_reason = "The first attempt failed, so AskData broadened the schema search and retried once."
            retry_reasons.append(retry_reason)
            retry_classifications.append(self._classify_retry_from_error(exc))
            recovery_actions.append("broaden_retrieval")
            trace.retries.append(retry_reason)
            trace.stages.append(
                QueryTraceStep(
                    stage="retry",
                    label="Broadened schema search",
                    detail=exc.message,
                )
            )
            attempt = self._run_attempt(
                question=normalized_question,
                schema=schema,
                connection_settings=connection_settings,
                conversation_context=normalized_conversation_context,
                memory_context=memory_context,
                dataset_adapter=dataset_adapter,
                plan=plan,
                broaden=True,
                trace=trace,
            )

        if self._should_retry_after_no_rows(
            plan=plan,
            attempt=attempt,
            retry_reasons=retry_reasons,
        ):
            retry_reason = "The first query returned no rows, so AskData retried once with a broader schema focus."
            retry_reasons.append(retry_reason)
            retry_classifications.append("plausible_overfiltered_no_rows")
            recovery_actions.append("broaden_retrieval")
            trace.retries.append(retry_reason)
            trace.stages.append(
                QueryTraceStep(
                    stage="retry",
                    label="Retried after no rows",
                    detail="Expanded the schema context to avoid an over-restrictive first interpretation.",
                )
            )
            try:
                broader_attempt = self._run_attempt(
                    question=normalized_question,
                    schema=schema,
                    connection_settings=connection_settings,
                    conversation_context=normalized_conversation_context,
                    memory_context=memory_context,
                    dataset_adapter=dataset_adapter,
                    plan=plan,
                    broaden=True,
                    trace=trace,
                )
                if broader_attempt["pipeline_result"]["execution_result"].row_count > 0:
                    attempt = broader_attempt
            except QueryPipelineError:
                if original_error is not None:
                    raise original_error

        if self._should_retry_after_relative_time_no_rows(
            question=normalized_question,
            attempt=attempt,
            recovery_actions=recovery_actions,
        ):
            retry_reason = (
                "The earlier query returned no rows, so AskData retried once by relaxing the "
                "current-relative time interpretation to the latest available period in the data."
            )
            retry_reasons.append(retry_reason)
            retry_classifications.append("relative_time_no_rows")
            recovery_actions.append("reinterpret_relative_time")
            trace.retries.append(retry_reason)
            trace.stages.append(
                QueryTraceStep(
                    stage="retry",
                    label="Retried with relative time reinterpretation",
                    detail="Adjusted the time filter toward the latest available data period after an empty result.",
                )
            )
            try:
                relative_time_attempt = self._retry_after_no_rows_with_relative_time(
                    question=normalized_question,
                    attempt=attempt,
                    connection_settings=connection_settings,
                    conversation_context=normalized_conversation_context,
                    memory_context=memory_context,
                    dataset_adapter=dataset_adapter,
                    plan=plan,
                    trace=trace,
                )
                if relative_time_attempt["pipeline_result"]["execution_result"].row_count > 0:
                    attempt = relative_time_attempt
            except QueryPipelineError:
                if original_error is not None:
                    raise original_error

        if self._reads_no_data(plan, attempt, schema):
            # The model wrote its conclusion as a constant instead of reading a table, usually because
            # the columns it needed weren't in the schema context. Look wider once, then say so plainly.
            if "broaden_retrieval" not in recovery_actions:
                retry_reason = "The query read no table, so AskData broadened the schema search and retried once."
                retry_reasons.append(retry_reason)
                retry_classifications.append("constant_only_query")
                recovery_actions.append("broaden_retrieval")
                trace.retries.append(retry_reason)
                trace.stages.append(
                    QueryTraceStep(stage="retry", label="Retried after a query that read no table")
                )
                try:
                    broader_attempt = self._run_attempt(
                        question=normalized_question,
                        schema=schema,
                        connection_settings=connection_settings,
                        conversation_context=normalized_conversation_context,
                        memory_context=memory_context,
                        dataset_adapter=dataset_adapter,
                        plan=plan,
                        broaden=True,
                        trace=trace,
                    )
                    attempt = broader_attempt
                except QueryPipelineError:
                    pass

            if self._reads_no_data(plan, attempt, schema):
                return self._build_non_answer_response(
                    question=normalized_question,
                    triage_result=QuestionTriageResult(
                        decision="unanswerable",
                        reason=self._constant_only_reason(attempt),
                    ),
                    plan=plan,
                    trace=trace,
                )

        response = self._build_response(
            question=normalized_question,
            schema=schema,
            plan=plan,
            attempt=attempt,
            trace=trace,
            retry_reasons=retry_reasons,
            retry_classifications=retry_classifications,
            recovery_actions=recovery_actions,
            connection_settings=connection_settings,
        )
        if self.settings.debug_mode:
            return response.model_copy(
                update={
                    "debug": DebugPayload(
                        stage="success",
                        dataset_adapter=dataset_adapter.name,
                        retrieval_tables=[table.full_name for table in attempt["retrieval_context"].tables],
                        validation_classification=attempt["pipeline_result"]["validation_result"].classification,
                        detected_tables=attempt["pipeline_result"]["validation_result"].detected_tables,
                        repair_attempted=bool(attempt["pipeline_result"]["repair_warnings"]),
                        planner_task_type=plan.task_type,
                        planner_confidence=plan.confidence,
                        planner_table_families=plan.candidate_table_families,
                        planner_retry_guidance=plan.retry_guidance,
                        retry_reasons=retry_reasons,
                        retry_classifications=retry_classifications,
                        recovery_actions=recovery_actions,
                        inherited_turn_ids=plan.inherited_from_turn_ids,
                    )
                }
            )

        return response

    def _run_attempt(
        self,
        question: str,
        schema: DatabaseSchema,
        connection_settings: PostgresConnectionSettings | None,
        conversation_context: list[ConversationMessage],
        memory_context: MemoryContext | None,
        dataset_adapter: DatasetAdapter,
        plan: QueryPlan,
        broaden: bool,
        trace: QueryTrace,
    ) -> dict:
        retrieval_question = self._build_retrieval_question(question, conversation_context)
        dataset_hints = dataset_adapter.prompt_hints(significant_tokens(question))
        retrieval_context = self.retrieval_service.retrieve_schema_context(
            retrieval_question,
            schema,
            plan=plan,
            memory_context=memory_context,
            max_tables=8 if broaden else 5,
            max_columns_per_table=10 if broaden else 8,
            broaden=broaden,
        )
        if not retrieval_context.tables:
            raise QueryPipelineError(
                code="invalid_request",
                message="No relevant schema context could be found for the question.",
                stage="retrieval",
                retryable=False,
                details={"warnings": retrieval_context.warnings},
            )

        trace.stages.append(
            QueryTraceStep(
                stage="retrieve",
                label="Focused on schema area",
                detail=", ".join(table.table_name for table in retrieval_context.tables[:4]),
            )
        )
        trace.schema_focus = list(
            dict.fromkeys(
                [
                    *plan.candidate_table_families,
                    *retrieval_context.intent_hints.table_family_hints,
                ]
            )
        )

        try:
            generation_result = self.sql_generation_service.generate_sql(
                question=question,
                schema_context=retrieval_context,
                conversation_context=conversation_context,
                plan=plan,
                memory_context=memory_context,
                dataset_hints=dataset_hints,
            )
        except LLMClientError as exc:
            raise QueryPipelineError(
                code="sql_generation_failed",
                message=str(exc),
                stage="generation",
                retryable=True,
            ) from exc

        generation_result, semantic_review_warnings = self._apply_semantic_review(
            question=question,
            retrieval_context=retrieval_context,
            generation_result=generation_result,
            conversation_context=conversation_context,
            memory_context=memory_context,
            dataset_hints=dataset_hints,
            plan=plan,
            trace=trace,
        )

        pipeline_result = self._validate_and_execute_once(
            question=question,
            retrieval_context=retrieval_context,
            generation_result=generation_result,
            connection_settings=connection_settings,
            allow_repair=True,
            conversation_context=conversation_context,
            memory_context=memory_context,
            dataset_hints=dataset_hints,
            plan=plan,
            trace=trace,
        )

        return {
            "retrieval_context": retrieval_context,
            "generation_result": generation_result,
            "pipeline_result": pipeline_result,
            "semantic_review_warnings": semantic_review_warnings,
        }

    def _build_response(
        self,
        question: str,
        schema: DatabaseSchema,
        plan: QueryPlan,
        attempt: dict,
        trace: QueryTrace,
        retry_reasons: list[str],
        retry_classifications: list[str],
        recovery_actions: list[str],
        connection_settings: PostgresConnectionSettings | None = None,
    ) -> QueryResponse:
        used_tables = self._merge_used_tables(
            schema=schema,
            generated_tables=attempt["pipeline_result"]["generation_result"].used_tables,
            detected_tables=attempt["pipeline_result"]["validation_result"].detected_tables,
        )
        merged_warnings = [
            *attempt["retrieval_context"].warnings,
            *attempt["pipeline_result"]["generation_result"].notes,
            *attempt["pipeline_result"]["validation_result"].warnings,
            *attempt["semantic_review_warnings"],
            *attempt["pipeline_result"]["repair_warnings"],
            *retry_reasons,
        ]

        execution_result = attempt["pipeline_result"]["execution_result"]
        trace.stages.append(
            QueryTraceStep(
                stage="execute",
                label="Returned result",
                detail=f"{execution_result.row_count} rows returned",
            )
        )

        return self.response_formatter_service.format_query_response(
            question=question,
            generated_sql=(
                attempt["pipeline_result"]["validation_result"].validated_sql
                or attempt["pipeline_result"]["generation_result"].sql
            ),
            execution_result=execution_result,
            used_tables=used_tables,
            warnings=merged_warnings,
            repaired=bool(
                attempt["pipeline_result"]["repair_warnings"]
                or attempt["semantic_review_warnings"]
            ),
            plan=plan,
            trace=trace,
            assumptions=attempt["pipeline_result"]["generation_result"].assumptions,
            data_coverage=(
                self._describe_data_coverage(used_tables, schema, connection_settings)
                if execution_result.row_count == 0
                else []
            ),
        )

    def _describe_data_coverage(
        self,
        used_tables: list[str],
        schema: DatabaseSchema,
        connection_settings: PostgresConnectionSettings | None,
        max_tables: int = 2,
        max_columns_per_table: int = 3,
    ) -> list[str]:
        """Date ranges of the tables an empty answer used, so the answer can say what the data covers."""
        tables_by_name = {table.full_name: table for table in schema.tables}
        coverage: list[str] = []

        for full_name in used_tables[:max_tables]:
            table = tables_by_name.get(full_name)
            if table is None:
                continue
            date_columns = [
                column.name
                for column in table.columns
                if column.data_type.startswith(("date", "timestamp"))
                and not any(marker in column.name.lower() for marker in ("update", "modified"))
            ][:max_columns_per_table]
            if not date_columns:
                continue

            # Distinct aliases: result rows are built from dicts, so repeated names would collapse.
            selects = ", ".join(
                f"MIN({_quote_identifier(name)})::date::text AS earliest_{index}, "
                f"MAX({_quote_identifier(name)})::date::text AS latest_{index}"
                for index, name in enumerate(date_columns)
            )
            sql = (
                f"SELECT {selects} FROM {_quote_identifier(table.schema_name)}.{_quote_identifier(table.table_name)}"
            )
            try:
                result = self.sql_execution_service.execute_sql(sql, connection_settings=connection_settings)
            except Exception:
                logger.warning("Could not read date coverage for %s.", full_name, exc_info=True)
                continue
            if not result.success or not result.rows:
                continue

            values = result.rows[0]
            for index, name in enumerate(date_columns):
                earliest, latest = values[2 * index], values[2 * index + 1]
                if earliest and latest:
                    label = f"{table.table_name.replace('_', ' ')} {name.replace('_', ' ')}"
                    coverage.append(f"{label} from {earliest} to {latest}")

        return coverage

    def _triage_question(
        self,
        question: str,
        schema: DatabaseSchema,
        conversation_context: list[ConversationMessage],
        memory_context: MemoryContext | None,
        dataset_adapter: DatasetAdapter,
        plan: QueryPlan,
        trace: QueryTrace,
    ) -> QuestionTriageResult | None:
        """Decide answer / clarify / decline before any SQL; None means "answer" (fail open)."""
        if not hasattr(self.sql_generation_service, "triage_question"):
            return None

        retrieval_context = self.retrieval_service.retrieve_schema_context(
            self._build_retrieval_question(question, conversation_context),
            schema,
            plan=plan,
            memory_context=memory_context,
            max_tables=8,
            max_columns_per_table=10,
            broaden=True,
        )
        if not retrieval_context.tables:
            return None

        try:
            result = self.sql_generation_service.triage_question(
                question=question,
                schema_context=retrieval_context,
                schema=schema,
                conversation_context=conversation_context,
            )
        except LLMClientError:
            logger.warning("Question triage failed; continuing to SQL generation.", exc_info=True)
            return None

        options = [option.strip() for option in result.options if option.strip()][:4]
        alternatives = [item.strip() for item in result.alternatives if item.strip()][:2]
        decision = result.decision
        if decision == "ambiguous" and (len(options) < 2 or not result.clarification_question.strip()):
            # Without a question and at least two options there is nothing to ask; answer instead.
            decision = "answerable"
        if decision == "unanswerable" and not result.reason.strip():
            decision = "answerable"

        trace.stages.append(
            QueryTraceStep(
                stage="triage",
                label={
                    "answerable": "Checked the question can be answered",
                    "ambiguous": "Asked which reading was meant",
                    "unanswerable": "Found the data can't answer this",
                }[decision],
                detail=result.reason.strip() or None,
            )
        )
        return result.model_copy(
            update={
                "decision": decision,
                "reason": result.reason.strip(),
                "clarification_question": result.clarification_question.strip(),
                "options": options,
                "alternatives": alternatives,
            }
        )

    def _build_non_answer_response(
        self,
        question: str,
        triage_result: QuestionTriageResult,
        plan: QueryPlan,
        trace: QueryTrace,
    ) -> QueryResponse:
        clarification = None
        cannot_answer = None
        if triage_result.decision == "ambiguous":
            clarification = ClarificationPayload(
                question=triage_result.clarification_question,
                options=triage_result.options,
            )
            # Plain-text form for clients that only show answer_summary (and for session history).
            answer_summary = " ".join(
                [
                    clarification.question,
                    *[f"({index}) {option}" for index, option in enumerate(clarification.options, start=1)],
                ]
            )
            response_type = "clarification"
        else:
            cannot_answer = CannotAnswerPayload(
                reason=triage_result.reason,
                alternatives=triage_result.alternatives,
            )
            answer_summary = cannot_answer.reason
            if cannot_answer.alternatives:
                answer_summary += " You could ask: " + " / ".join(cannot_answer.alternatives)
            response_type = "cannot_answer"

        return QueryResponse(
            question=question,
            response_type=response_type,
            clarification=clarification,
            cannot_answer=cannot_answer,
            answer_summary=answer_summary,
            generated_sql="",
            chart_recommendation=ChartRecommendation(type="table_only"),
            primary_artifact="summary",
            plan=plan,
            trace=trace,
        )

    def _apply_semantic_review(
        self,
        question: str,
        retrieval_context,
        generation_result,
        conversation_context: list[ConversationMessage],
        memory_context: MemoryContext | None,
        dataset_hints: list[str],
        plan: QueryPlan,
        trace: QueryTrace,
    ):
        if not hasattr(self.sql_generation_service, "review_sql"):
            return generation_result, []

        try:
            review_result = self.sql_generation_service.review_sql(
                question=question,
                schema_context=retrieval_context,
                generated_sql=generation_result.sql,
                conversation_context=conversation_context,
                plan=plan,
                memory_context=memory_context,
                dataset_hints=dataset_hints,
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
                failure_message="Semantic review: " + "; ".join(
                    issues or ["Refocus the SQL on the user's business intent."]
                ),
                conversation_context=conversation_context,
                plan=plan,
                memory_context=memory_context,
                dataset_hints=dataset_hints,
            )
        except LLMClientError:
            return generation_result, []

        trace.stages.append(
            QueryTraceStep(
                stage="repair",
                label="Rewrote SQL after semantic review",
                detail="Aligned the generated query more closely with the interpreted business intent.",
            )
        )
        return rewritten, ["SQL was rewritten once after a semantic review."]

    def _validate_and_execute_once(
        self,
        question: str,
        retrieval_context,
        generation_result,
        connection_settings: PostgresConnectionSettings | None,
        allow_repair: bool,
        conversation_context: list[ConversationMessage],
        memory_context: MemoryContext | None,
        dataset_hints: list[str],
        plan: QueryPlan,
        trace: QueryTrace,
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
                    memory_context=memory_context,
                    dataset_hints=dataset_hints,
                    plan=plan,
                    trace=trace,
                )
                result = self._validate_and_execute_once(
                    question=question,
                    retrieval_context=retrieval_context,
                    generation_result=repaired_result,
                    connection_settings=connection_settings,
                    allow_repair=False,
                    conversation_context=conversation_context,
                    memory_context=memory_context,
                    dataset_hints=dataset_hints,
                    plan=plan,
                    trace=trace,
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
            validation_result.validated_sql or generation_result.sql,
            connection_settings=connection_settings,
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
                    memory_context=memory_context,
                    dataset_hints=dataset_hints,
                    plan=plan,
                    trace=trace,
                )
                result = self._validate_and_execute_once(
                    question=question,
                    retrieval_context=retrieval_context,
                    generation_result=repaired_result,
                    connection_settings=connection_settings,
                    allow_repair=False,
                    conversation_context=conversation_context,
                    memory_context=memory_context,
                    dataset_hints=dataset_hints,
                    plan=plan,
                    trace=trace,
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

    def _retry_after_no_rows_with_relative_time(
        self,
        question: str,
        attempt: dict,
        connection_settings: PostgresConnectionSettings | None,
        conversation_context: list[ConversationMessage],
        memory_context: MemoryContext | None,
        dataset_adapter: DatasetAdapter,
        plan: QueryPlan,
        trace: QueryTrace,
    ) -> dict:
        retrieval_context = attempt["retrieval_context"]
        previous_sql = (
            attempt["pipeline_result"]["validation_result"].validated_sql
            or attempt["pipeline_result"]["generation_result"].sql
        )
        dataset_hints = dataset_adapter.prompt_hints(significant_tokens(question))
        rewritten_generation = self._repair_generation(
            question=question,
            retrieval_context=retrieval_context,
            previous_sql=previous_sql,
            failure_message=(
                "The query returned no rows. If the request uses a current-relative time phrase like "
                "'this year' or 'this month', reinterpret it against the latest available period in the "
                "dataset instead of the wall-clock current date."
            ),
            repair_stage="no_rows",
            conversation_context=conversation_context,
            memory_context=memory_context,
            dataset_hints=dataset_hints,
            plan=plan,
            trace=trace,
        )
        pipeline_result = self._validate_and_execute_once(
            question=question,
            retrieval_context=retrieval_context,
            generation_result=rewritten_generation,
            connection_settings=connection_settings,
            allow_repair=False,
            conversation_context=conversation_context,
            memory_context=memory_context,
            dataset_hints=dataset_hints,
            plan=plan,
            trace=trace,
        )
        return {
            "retrieval_context": retrieval_context,
            "generation_result": rewritten_generation,
            "pipeline_result": pipeline_result,
            "semantic_review_warnings": [
                "SQL was rewritten once after a no-row result to reinterpret the relative time period."
            ],
        }

    def _repair_generation(
        self,
        question: str,
        retrieval_context,
        previous_sql: str,
        failure_message: str,
        repair_stage: str,
        conversation_context: list[ConversationMessage],
        memory_context: MemoryContext | None,
        dataset_hints: list[str],
        plan: QueryPlan,
        trace: QueryTrace,
    ):
        try:
            repaired = self.sql_generation_service.repair_sql(
                question=question,
                schema_context=retrieval_context,
                previous_sql=previous_sql,
                failure_message=failure_message,
                conversation_context=conversation_context,
                plan=plan,
                memory_context=memory_context,
                dataset_hints=dataset_hints,
            )
            trace.stages.append(
                QueryTraceStep(
                    stage="repair",
                    label=f"Repaired SQL after {repair_stage} issue",
                    detail=failure_message[:180],
                )
            )
            return repaired
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

    def _new_trace(self, plan: QueryPlan) -> QueryTrace:
        stages = [
            QueryTraceStep(
                stage="plan",
                label="Planned the answer strategy",
                detail=plan.interpreted_goal,
            )
        ]
        return QueryTrace(
            task_type=plan.task_type,
            interpreted_goal=plan.interpreted_goal,
            confidence=plan.confidence,
            schema_focus=list(plan.candidate_table_families),
            retries=[],
            stages=stages,
            memory_summary=plan.memory_summary,
        )

    def _should_retry_after_error(self, exc: QueryPipelineError, plan: QueryPlan) -> bool:
        if exc.code in {"unsafe_sql", "schema_unavailable"}:
            return False
        if not self.planner_service.should_retry_with_broader_retrieval(plan):
            return False
        return exc.code in {"invalid_request", "sql_generation_failed", "sql_validation_failed", "sql_execution_failed"}

    def _should_retry_after_no_rows(
        self,
        plan: QueryPlan,
        attempt: dict,
        retry_reasons: list[str],
    ) -> bool:
        if retry_reasons:
            return False
        if "retry_no_rows_with_broader_focus" not in plan.retry_guidance:
            return False
        return attempt["pipeline_result"]["execution_result"].row_count == 0

    def _should_retry_after_relative_time_no_rows(
        self,
        question: str,
        attempt: dict,
        recovery_actions: list[str],
    ) -> bool:
        execution_result = attempt["pipeline_result"]["execution_result"]
        if execution_result.row_count != 0 and not self._has_only_empty_measures(execution_result.rows):
            return False
        if "reinterpret_relative_time" in recovery_actions:
            return False
        return self._has_relative_time_phrase(question)

    def _reads_no_data(self, plan: QueryPlan, attempt: dict, schema: DatabaseSchema) -> bool:
        """True when a data question was answered by a query that reads no table (only constants).

        Questions about the schema itself are answered that way on purpose (table names as text),
        so they are left alone: by task type, or when a value names a table as schema.table.
        """
        if plan.task_type == "schema_lookup":
            return False
        if attempt["pipeline_result"]["validation_result"].detected_tables:
            return False
        full_names = {table.full_name.lower() for table in schema.tables}
        for row in attempt["pipeline_result"]["execution_result"].rows:
            for value in row:
                text = str(value).lower()
                if any(name in text for name in full_names):
                    return False
        return True

    def _constant_only_reason(self, attempt: dict) -> str:
        rows = attempt["pipeline_result"]["execution_result"].rows
        if len(rows) == 1 and len(rows[0]) == 1 and isinstance(rows[0][0], str) and 0 < len(rows[0][0]) <= 300:
            return rows[0][0].strip()
        return "I couldn't find columns in this database that hold what this question asks for."

    def _has_only_empty_measures(self, rows: list[list]) -> bool:
        """True when rows exist but every numeric value is 0 or missing (e.g. a zero-filled calendar)."""
        saw_measure_cell = False
        for row in rows:
            for value in row:
                if isinstance(value, bool):
                    continue
                if value is None:
                    saw_measure_cell = True
                    continue
                if isinstance(value, (int, float, Decimal)):
                    saw_measure_cell = True
                    if value != 0:
                        return False
        return saw_measure_cell

    def _has_relative_time_phrase(self, question: str) -> bool:
        normalized = question.lower()
        phrases = (
            "this year",
            "this month",
            "this quarter",
            "current year",
            "current month",
            "current quarter",
            "last year",
            "last month",
            "last quarter",
        )
        return any(phrase in normalized for phrase in phrases)

    def _classify_retry_from_error(self, exc: QueryPipelineError) -> str:
        if exc.code == "invalid_request" and exc.stage == "retrieval":
            return "weak_retrieval"
        if exc.code == "sql_generation_failed":
            return "generation_failure"
        if exc.code == "sql_validation_failed":
            return "semantic_or_validation_mismatch"
        if exc.code == "sql_execution_failed":
            return "execution_failure"
        return "retryable_failure"


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
