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
  conversation_context?: ConversationMessage[];
};

export type QueryResponse = {
  question: string;
  answer_summary: string;
  generated_sql: string;
  columns: string[];
  rows: Array<Array<unknown>>;
  chart_recommendation: ChartRecommendation;
  warnings: string[];
  used_tables: string[];
};

export type QueryErrorResponse = {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
  warnings: string[];
};

export type ConversationTurn =
  | {
      id: string;
      question: string;
      status: "loading";
    }
  | {
      id: string;
      question: string;
      status: "success";
      response: QueryResponse;
    }
  | {
      id: string;
      question: string;
      status: "error";
      error: QueryErrorResponse;
    };

export type ExampleQuestion = {
  question: string;
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
