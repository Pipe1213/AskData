export type ChartRecommendation = {
  type: "bar" | "line" | "table_only";
  x?: string | null;
  y?: string | null;
};

export type ConversationMessage = {
  role: "user" | "assistant";
  content: string;
};

export type QueryPlan = {
  task_type:
    | "aggregation"
    | "comparison"
    | "follow_up_refinement"
    | "lookup"
    | "ranking"
    | "schema_lookup"
    | "trend"
    | "ambiguous";
  execution_strategy: "single_query" | "schema_guided";
  interpreted_goal: string;
  metric_targets: string[];
  dimension_targets: string[];
  time_targets: string[];
  candidate_table_families: string[];
  ambiguity_notes: string[];
  confidence: "low" | "medium" | "high";
  memory_summary?: string | null;
  inherited_from_turn_ids: string[];
};

export type QueryTraceStep = {
  stage: "plan" | "retrieve" | "retry" | "repair" | "execute";
  label: string;
  detail?: string | null;
};

export type QueryTrace = {
  task_type: string;
  interpreted_goal: string;
  confidence: "low" | "medium" | "high";
  schema_focus: string[];
  retries: string[];
  stages: QueryTraceStep[];
  memory_summary?: string | null;
};

export type TurnMemory = {
  source_turn_id?: string | null;
  question: string;
  task_type: string;
  interpreted_goal: string;
  metric_targets: string[];
  dimension_targets: string[];
  time_targets: string[];
  candidate_table_families: string[];
  used_tables: string[];
  generated_sql: string;
  answer_summary: string;
  row_count: number;
  result_focus?: string | null;
  memory_tags: string[];
};

export type QueryRequest = {
  question: string;
  session_id?: string | null;
  conversation_context?: ConversationMessage[];
};

export type QueryResponse = {
  question: string;
  answer_summary: string;
  generated_sql: string;
  columns: string[];
  rows: Array<Array<unknown>>;
  row_count: number;
  chart_recommendation: ChartRecommendation;
  warnings: string[];
  used_tables: string[];
  session_id?: string | null;
  turn_id?: string | null;
  persisted: boolean;
  created_at?: string | null;
  repaired: boolean;
  primary_artifact: "summary" | "table" | "chart" | "chart_and_table";
  memory?: TurnMemory | null;
  plan?: QueryPlan | null;
  trace?: QueryTrace | null;
  debug?: {
    stage?: string | null;
    retrieval_tables: string[];
    validation_classification?: string | null;
    detected_tables: string[];
    repair_attempted: boolean;
    planner_task_type?: string | null;
    planner_confidence?: string | null;
    planner_table_families: string[];
    retry_reasons: string[];
    inherited_turn_ids: string[];
  } | null;
};

export type QueryErrorResponse = {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
  warnings: string[];
  session_id?: string | null;
  turn_id?: string | null;
  persisted: boolean;
  created_at?: string | null;
  plan?: QueryPlan | null;
  trace?: QueryTrace | null;
  debug?: {
    stage?: string | null;
    retrieval_tables: string[];
    validation_classification?: string | null;
    detected_tables: string[];
    repair_attempted: boolean;
    planner_task_type?: string | null;
    planner_confidence?: string | null;
    planner_table_families: string[];
    retry_reasons: string[];
    inherited_turn_ids: string[];
  } | null;
};

export type ConversationTurn =
  | {
      id: string;
      question: string;
      status: "loading";
      created_at?: string | null;
    }
  | {
      id: string;
      question: string;
      status: "success";
      response: QueryResponse;
      created_at?: string | null;
    }
  | {
      id: string;
      question: string;
      status: "error";
      error: QueryErrorResponse;
      created_at?: string | null;
    };

export type ExampleQuestion = {
  question: string;
};

export type ExamplePromptGroup = {
  title: string;
  prompts: string[];
};

export type SessionSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  turn_count: number;
  last_question?: string | null;
  last_status?: "success" | "error" | null;
};

export type SessionDetail = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  turns: Array<
    | {
        id: string;
        question: string;
        status: "success";
        created_at: string;
        response: QueryResponse;
      }
    | {
        id: string;
        question: string;
        status: "error";
        created_at: string;
        error: QueryErrorResponse;
      }
  >;
};

export type SchemaTableSummary = {
  name: string;
  schema_name: string;
  description?: string | null;
  columns: Array<{
    name: string;
    data_type: string;
    nullable: boolean;
    description?: string | null;
  }>;
  primary_key: string[];
  foreign_keys: Array<{
    name: string;
    columns: string[];
    references_schema: string;
    references_table: string;
    references_columns: string[];
  }>;
};

export type SchemaOverviewResponse = {
  tables: SchemaTableSummary[];
};
