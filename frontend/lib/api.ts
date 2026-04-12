import type {
  DataSourceActivationResponse,
  DataSourcesResponse,
  ExampleQuestion,
  QueryErrorResponse,
  QueryRequest,
  QueryResponse,
  RuntimeConnectionTestResponse,
  RuntimePostgresConnectionInput,
  RuntimeTargetActivationResponse,
  SchemaOverviewResponse,
  SessionDetail,
  SessionSummary,
} from "@/lib/types";
import { getClientToken } from "@/lib/session";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const CLIENT_TOKEN_HEADER = "X-AskData-Client-Token";

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

export async function fetchDataSources(): Promise<DataSourcesResponse> {
  return requestJson<DataSourcesResponse>("/data-sources");
}

export async function activateDemoDataSource(
  targetId: "demo_pagila" | "demo_retail_ops",
): Promise<DataSourceActivationResponse> {
  return requestJson<DataSourceActivationResponse>("/data-sources/demo/activate", {
    method: "POST",
    body: JSON.stringify({ target_id: targetId }),
  });
}

export async function testRuntimePostgresConnection(
  payload: RuntimePostgresConnectionInput,
): Promise<RuntimeConnectionTestResponse> {
  return requestJson<RuntimeConnectionTestResponse>("/data-sources/runtime/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function activateRuntimePostgresConnection(
  payload: RuntimePostgresConnectionInput,
): Promise<RuntimeTargetActivationResponse> {
  return requestJson<RuntimeTargetActivationResponse>("/data-sources/runtime/activate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function disconnectRuntimeDataSource(): Promise<DataSourceActivationResponse> {
  return requestJson<DataSourceActivationResponse>("/data-sources/runtime", {
    method: "DELETE",
  });
}

export async function fetchSchemaOverview(): Promise<SchemaOverviewResponse> {
  return requestJson<SchemaOverviewResponse>("/schema/overview");
}

export async function fetchSessions(): Promise<SessionSummary[]> {
  const response = await requestJson<{ sessions: SessionSummary[] }>("/sessions");
  return response.sessions;
}

export async function fetchSessionDetail(sessionId: string): Promise<SessionDetail> {
  const response = await requestJson<{ session: SessionDetail }>(`/sessions/${sessionId}`);
  return response.session;
}

export async function renameSession(sessionId: string, title: string): Promise<SessionDetail> {
  const response = await requestJson<{ session: SessionDetail }>(`/sessions/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
  return response.session;
}

export async function rerunSessionTurn(
  sessionId: string,
  turnId: string,
): Promise<QueryResponse> {
  return requestJson<QueryResponse>(`/sessions/${sessionId}/turns/${turnId}/rerun`, {
    method: "POST",
  });
}

export async function exportSessionTurnCsv(
  sessionId: string,
  turnId: string,
): Promise<Blob> {
  const response = await fetch(`${getApiBaseUrl()}/sessions/${sessionId}/turns/${turnId}/export.csv`, {
    method: "GET",
    headers: buildHeaders(),
    cache: "no-store",
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    const data = contentType.includes("application/json") ? await response.json() : null;
    const errorPayload = normalizeErrorPayload(data, response.status);
    throw new ApiError(errorPayload, response.status);
  }

  return response.blob();
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: buildHeaders(init?.headers),
    cache: "no-store",
  });

  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : null;

  if (!response.ok) {
    const errorPayload = normalizeErrorPayload(data, response.status);
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

function buildHeaders(existingHeaders?: HeadersInit): Headers {
  const headers = new Headers(existingHeaders);
  headers.set("Content-Type", "application/json");

  const clientToken = getClientToken();
  if (clientToken) {
    headers.set(CLIENT_TOKEN_HEADER, clientToken);
  }

  return headers;
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

function normalizeErrorPayload(data: unknown, status: number): QueryErrorResponse {
  if (isQueryErrorResponse(data)) {
    return data;
  }

  if (data && typeof data === "object" && "error" in data) {
    const candidate = data as { error?: { code?: unknown; message?: unknown; details?: unknown } };
    if (
      typeof candidate.error?.code === "string" &&
      typeof candidate.error?.message === "string"
    ) {
      return {
        error: {
          code: candidate.error.code,
          message: candidate.error.message,
          details:
            candidate.error.details && typeof candidate.error.details === "object"
              ? (candidate.error.details as Record<string, unknown>)
              : {},
        },
        warnings: [],
        persisted: false,
      };
    }
  }

  if (data && typeof data === "object" && "detail" in data) {
    const candidate = data as {
      detail?:
        | string
        | {
            code?: unknown;
            message?: unknown;
            details?: unknown;
          };
    };

    if (typeof candidate.detail === "string") {
      return {
        error: {
          code: "http_detail_error",
          message: candidate.detail,
          details: { status },
        },
        warnings: [],
        persisted: false,
      };
    }

    if (
      candidate.detail &&
      typeof candidate.detail === "object" &&
      typeof candidate.detail.code === "string" &&
      typeof candidate.detail.message === "string"
    ) {
      return {
        error: {
          code: candidate.detail.code,
          message: candidate.detail.message,
          details:
            candidate.detail.details && typeof candidate.detail.details === "object"
              ? (candidate.detail.details as Record<string, unknown>)
              : {},
        },
        warnings: [],
        persisted: false,
      };
    }
  }

  return buildFallbackErrorResponse(status);
}

function buildFallbackErrorResponse(status: number): QueryErrorResponse {
  return {
    error: {
      code: "http_error",
      message: `The backend request failed with status ${status}.`,
      details: { status },
    },
    warnings: [],
    persisted: false,
  };
}
