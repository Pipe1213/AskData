export type ChartRecommendation = {
  type: "bar" | "line" | "table_only";
  x?: string | null;
  y?: string | null;
};

export type ConversationMessage = {
  role: "user" | "assistant";
  content: string;
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
  debug?: {
    stage?: string | null;
    retrieval_tables: string[];
    validation_classification?: string | null;
    detected_tables: string[];
    repair_attempted: boolean;
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
  debug?: {
    stage?: string | null;
    retrieval_tables: string[];
    validation_classification?: string | null;
    detected_tables: string[];
    repair_attempted: boolean;
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
