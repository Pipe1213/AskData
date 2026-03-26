"use client";

import { useEffect, useState } from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { ExamplePrompts } from "@/components/query/example-prompts";
import { QuestionForm } from "@/components/query/question-form";
import { QueryError } from "@/components/query/query-error";
import { QueryWorkspace } from "@/components/query/query-workspace";
import { ApiError, fetchExampleQuestions, queryAskData } from "@/lib/api";
import type { ExampleQuestion, QueryErrorResponse, QueryResponse } from "@/lib/types";

const fallbackPrompts = [
  "What are the top 10 film categories by total revenue?",
  "Which customers spent the most in total?",
  "How much revenue did each staff member process?",
  "What is the monthly trend of rentals this year?",
];

const defaultQuestion = fallbackPrompts[0];

export function QueryDashboard() {
  const [question, setQuestion] = useState(defaultQuestion);
  const [queryResult, setQueryResult] = useState<QueryResponse | null>(null);
  const [queryError, setQueryError] = useState<QueryErrorResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [examplePrompts, setExamplePrompts] = useState<string[]>(fallbackPrompts);
  const [examplesState, setExamplesState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const showContextRail = isLoading || Boolean(queryResult) || hasVisibleWarnings(queryResult, queryError);

  useEffect(() => {
    let isActive = true;

    async function loadExamples() {
      setExamplesState("loading");

      try {
        const examples = await fetchExampleQuestions();
        if (!isActive) {
          return;
        }

        const questions = normalizeExamples(examples);
        if (questions.length > 0) {
          setExamplePrompts(questions);
        }
        setExamplesState("success");
      } catch {
        if (!isActive) {
          return;
        }

        setExamplesState("error");
      }
    }

    void loadExamples();

    return () => {
      isActive = false;
    };
  }, []);

  async function handleSubmit() {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isLoading) {
      return;
    }

    setIsLoading(true);
    setQueryError(null);

    try {
      const result = await queryAskData({ question: trimmedQuestion });
      setQueryResult(result);
    } catch (error) {
      const normalizedError = normalizeQueryError(error);
      setQueryResult(null);
      setQueryError(normalizedError);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className={`mt-6 grid gap-6 ${showContextRail ? "xl:grid-cols-[minmax(0,1fr)_320px]" : ""}`}>
      <section className="space-y-6">
        <div className="panel bg-hero-wash p-6 md:p-8">
          <div className="eyebrow">AskData</div>
          <div className="mt-4 grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
            <div>
              <h1 className="max-w-[12ch] font-serif text-4xl leading-[0.95] tracking-[-0.04em] text-ink md:text-6xl">
                Ask better questions. Inspect better answers.
              </h1>
              <p className="mt-5 max-w-[58ch] text-base leading-7 text-muted md:text-lg">
                Ask a business question about the Pagila dataset and review the answer, SQL, and
                result data in one place.
              </p>
              <p className="mt-5 text-sm leading-6 text-muted">
                {examplesState === "success"
                  ? "Example prompts below are loaded from the backend."
                  : examplesState === "loading"
                    ? "Loading curated example prompts..."
                    : "Using local fallback prompts while the backend examples load."}
              </p>
            </div>
            <QuestionForm
              question={question}
              isLoading={isLoading}
              onQuestionChange={setQuestion}
              onSubmit={handleSubmit}
            />
          </div>
        </div>

        <ExamplePrompts
          prompts={examplePrompts}
          disabled={isLoading}
          onSelectPrompt={setQuestion}
        />

        {queryError ? (
          <QueryError
            title="Request failed"
            message={queryError.error.message}
            warnings={queryError.warnings}
            errorCode={queryError.error.code}
          />
        ) : null}

        <QueryWorkspace
          queryResult={queryResult}
          isLoading={isLoading}
          hasError={Boolean(queryError)}
        />
      </section>

      {showContextRail ? (
        <Sidebar
          warnings={queryResult?.warnings ?? queryError?.warnings ?? []}
          usedTables={queryResult?.used_tables ?? []}
          isLoading={isLoading}
        />
      ) : null}
    </main>
  );
}

function normalizeQueryError(error: unknown): QueryErrorResponse {
  if (error instanceof ApiError) {
    return error.payload;
  }

  if (isQueryErrorResponse(error)) {
    return error;
  }

  if (error instanceof Error) {
    return {
      error: {
        code: "frontend_error",
        message: error.message,
        details: {},
      },
      warnings: [],
    };
  }

  return {
    error: {
      code: "frontend_error",
      message: "An unexpected frontend error occurred.",
      details: {},
    },
    warnings: [],
  };
}

function isQueryErrorResponse(error: unknown): error is QueryErrorResponse {
  if (!error || typeof error !== "object") {
    return false;
  }

  const candidate = error as QueryErrorResponse;
  return (
    typeof candidate.error?.code === "string" &&
    typeof candidate.error?.message === "string" &&
    Array.isArray(candidate.warnings)
  );
}

function normalizeExamples(examples: ExampleQuestion[]): string[] {
  return examples
    .map((example) => example.question.trim())
    .filter((question) => question.length > 0);
}

function hasVisibleWarnings(
  queryResult: QueryResponse | null,
  queryError: QueryErrorResponse | null,
): boolean {
  return (queryResult?.warnings.length ?? 0) > 0 || (queryError?.warnings.length ?? 0) > 0;
}
