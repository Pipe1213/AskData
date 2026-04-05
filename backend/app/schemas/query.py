from typing import Any, Literal

from pydantic import BaseModel, Field


PrimaryArtifact = Literal["summary", "table", "chart", "chart_and_table"]


class QueryPlan(BaseModel):
    task_type: Literal[
        "aggregation",
        "comparison",
        "follow_up_refinement",
        "lookup",
        "ranking",
        "schema_lookup",
        "trend",
        "ambiguous",
    ] = "lookup"
    execution_strategy: Literal["single_query", "schema_guided"] = "single_query"
    interpreted_goal: str
    metric_targets: list[str] = Field(default_factory=list)
    dimension_targets: list[str] = Field(default_factory=list)
    time_targets: list[str] = Field(default_factory=list)
    candidate_table_families: list[str] = Field(default_factory=list)
    ambiguity_notes: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    memory_summary: str | None = None
    inherited_from_turn_ids: list[str] = Field(default_factory=list)


class QueryTraceStep(BaseModel):
    stage: Literal["plan", "retrieve", "retry", "repair", "execute"]
    label: str
    detail: str | None = None


class QueryTrace(BaseModel):
    task_type: str
    interpreted_goal: str
    confidence: Literal["low", "medium", "high"]
    schema_focus: list[str] = Field(default_factory=list)
    retries: list[str] = Field(default_factory=list)
    stages: list[QueryTraceStep] = Field(default_factory=list)
    memory_summary: str | None = None


class TurnMemory(BaseModel):
    source_turn_id: str | None = None
    question: str
    task_type: str
    interpreted_goal: str
    metric_targets: list[str] = Field(default_factory=list)
    dimension_targets: list[str] = Field(default_factory=list)
    time_targets: list[str] = Field(default_factory=list)
    candidate_table_families: list[str] = Field(default_factory=list)
    used_tables: list[str] = Field(default_factory=list)
    generated_sql: str
    answer_summary: str
    row_count: int = 0
    result_focus: str | None = None
    memory_tags: list[str] = Field(default_factory=list)


class MemoryContext(BaseModel):
    relevant_turn_memories: list[TurnMemory] = Field(default_factory=list)
    memory_summary: str | None = None
    suggested_metric_targets: list[str] = Field(default_factory=list)
    suggested_dimension_targets: list[str] = Field(default_factory=list)
    suggested_time_targets: list[str] = Field(default_factory=list)
    suggested_table_families: list[str] = Field(default_factory=list)
    inherited_from_turn_ids: list[str] = Field(default_factory=list)


class SQLGenerationResult(BaseModel):
    sql: str
    used_tables: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SQLSemanticReviewResult(BaseModel):
    should_rewrite: bool = False
    issues: list[str] = Field(default_factory=list)
    suggested_focus: str | None = None


class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None
    conversation_context: list["ConversationMessage"] = Field(default_factory=list)


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChartRecommendation(BaseModel):
    type: Literal["bar", "line", "table_only"]
    x: str | None = None
    y: str | None = None


class DebugPayload(BaseModel):
    stage: str | None = None
    retrieval_tables: list[str] = Field(default_factory=list)
    validation_classification: str | None = None
    detected_tables: list[str] = Field(default_factory=list)
    repair_attempted: bool = False
    planner_task_type: str | None = None
    planner_confidence: str | None = None
    planner_table_families: list[str] = Field(default_factory=list)
    retry_reasons: list[str] = Field(default_factory=list)
    inherited_turn_ids: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    question: str
    answer_summary: str
    generated_sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    chart_recommendation: ChartRecommendation
    warnings: list[str] = Field(default_factory=list)
    used_tables: list[str] = Field(default_factory=list)
    session_id: str | None = None
    turn_id: str | None = None
    persisted: bool = False
    created_at: str | None = None
    repaired: bool = False
    primary_artifact: PrimaryArtifact = "summary"
    memory: TurnMemory | None = None
    plan: QueryPlan | None = None
    trace: QueryTrace | None = None
    debug: DebugPayload | None = None


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class QueryErrorResponse(BaseModel):
    error: ErrorPayload
    warnings: list[str] = Field(default_factory=list)
    session_id: str | None = None
    turn_id: str | None = None
    persisted: bool = False
    created_at: str | None = None
    plan: QueryPlan | None = None
    trace: QueryTrace | None = None
    debug: DebugPayload | None = None
