import type { DataSourceSummary } from "@/lib/types";

export type ExampleCard = {
  kind: string;
  question: string;
  vague?: boolean;
};

export type DatasetCopy = {
  heading: string;
  description: string;
  placeholder: string;
  followUpPlaceholder: string;
  examples: ExampleCard[];
};

const PAGILA: DatasetCopy = {
  heading: "Ask a question about the Pagila data",
  description:
    "A DVD-rental store: customers, rentals, payments, films and staff, from January to July 2022.",
  placeholder: "Ask about customers, rentals, payments or films",
  followUpPlaceholder: "Ask a follow-up, e.g. “only store 1”",
  examples: [
    { kind: "Ranking", question: "Which 10 customers spent the most?" },
    { kind: "Trend", question: "How did rentals change month by month?" },
    { kind: "Comparison", question: "Which store made more revenue?" },
    { kind: "Try a vague one", question: "Who are our best customers?", vague: true },
  ],
};

const RETAIL_OPS: DatasetCopy = {
  heading: "Ask a question about the Retail Ops data",
  description:
    "A retailer with stores and an online shop: customers, orders, payments, products, shipments and returns, from January 2023 to December 2024.",
  placeholder: "Ask about customers, orders, products or shipments",
  followUpPlaceholder: "Ask a follow-up, e.g. “only store 1”",
  examples: [
    { kind: "Ranking", question: "Which 10 products brought in the most revenue?" },
    { kind: "Trend", question: "How did revenue change month by month?" },
    { kind: "Comparison", question: "Which sales channel has more orders?" },
    { kind: "Try a vague one", question: "Which stores are doing best?", vague: true },
  ],
};

export function getDatasetCopy(target: DataSourceSummary | null, tableCount: number | null): DatasetCopy {
  if (target?.target_type === "demo_retail_ops") {
    return RETAIL_OPS;
  }
  if (target?.target_type === "runtime_postgres") {
    return {
      heading: `Ask a question about ${target.database_name ?? "your database"}`,
      description:
        tableCount == null ? "Your database." : `Your database: ${tableCount} ${tableCount === 1 ? "table" : "tables"}.`,
      placeholder: "Ask a question about your data",
      followUpPlaceholder: "Ask a follow-up",
      examples: [
        { kind: "Ranking", question: "Which 10 customers brought in the most revenue?" },
        { kind: "Trend", question: "How did revenue change month by month?" },
        { kind: "Comparison", question: "Compare average order value by region." },
        { kind: "Try a vague one", question: "Who are our best customers?", vague: true },
      ],
    };
  }
  return PAGILA;
}

export function targetLabel(target: DataSourceSummary): string {
  if (target.target_type === "runtime_postgres") {
    return target.database_name ?? target.display_name;
  }
  return `${target.display_name} (demo)`;
}

export const READ_ONLY_USER_GUIDE_URL = "https://github.com/Pipe1213/askdata#create-a-read-only-user";
