import type {
  QueryRequest,
  QueryErrorResponse,
  QueryResponse,
  ExampleQuestion,
  SchemaOverviewResponse,
} from "@/lib/types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export class ApiError extends Error {
  payload: QueryErrorResponse;
  status: number;

  constructor(payload: QueryErrorResponse, status: number) {
    super(payload.error.message);
    this.name = "ApiError";
    this.payload = payload;
    this.status = status;
  }
}

export async function queryAskData(payload: QueryRequest): Promise<QueryResponse> {
  return requestJson<QueryResponse>("/query", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchExampleQuestions(): Promise<ExampleQuestion[]> {
  const response = await requestJson<{ examples: string[] }>("/examples");
  return response.examples.map((question) => ({ question }));
}

export async function fetchSchemaOverview(): Promise<SchemaOverviewResponse> {
  return requestJson<SchemaOverviewResponse>("/schema/overview");
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : null;

  if (!response.ok) {
    const errorPayload = isQueryErrorResponse(data)
      ? data
      : buildFallbackErrorResponse(response.status);
    throw new ApiError(errorPayload, response.status);
  }

  return data as T;
}

function getApiBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_ASKDATA_API_BASE_URL?.replace(/\/$/, "") ??
    DEFAULT_API_BASE_URL
  );
}

function isQueryErrorResponse(value: unknown): value is QueryErrorResponse {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as QueryErrorResponse;
  return (
    typeof candidate.error?.code === "string" &&
    typeof candidate.error?.message === "string" &&
    Array.isArray(candidate.warnings)
  );
}

function buildFallbackErrorResponse(status: number): QueryErrorResponse {
  return {
    error: {
      code: "http_error",
      message: `The backend request failed with status ${status}.`,
      details: { status },
    },
    warnings: [],
  };
}
