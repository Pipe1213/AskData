"use client";

import { useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { AlertIcon, CheckIcon, ShieldIcon } from "@/components/ui/icons";
import { READ_ONLY_USER_GUIDE_URL } from "@/lib/datasets";
import type { RuntimeConnectionTestResponse, RuntimePostgresConnectionInput, SslMode } from "@/lib/types";

type ConnectDatabaseProps = {
  onTest: (payload: RuntimePostgresConnectionInput) => Promise<RuntimeConnectionTestResponse>;
  onConnect: (payload: RuntimePostgresConnectionInput) => Promise<void>;
};

type Status = { kind: "success" | "error"; text: string } | null;

const inputClass =
  "h-11 w-full rounded-[10px] border border-inputLine bg-surface px-3 text-sm text-ink placeholder:text-muted";

export function ConnectDatabase({ onTest, onConnect }: ConnectDatabaseProps) {
  const [useSeparateFields, setUseSeparateFields] = useState(false);
  const [connectionUrl, setConnectionUrl] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("5432");
  const [database, setDatabase] = useState("");
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [sslmode, setSslmode] = useState<SslMode>("prefer");
  const [schemas, setSchemas] = useState("public");
  const [status, setStatus] = useState<Status>(null);
  const [pending, setPending] = useState<"test" | "connect" | null>(null);

  function buildPayload(): RuntimePostgresConnectionInput {
    const schemaAllowlist = schemas
      .split(",")
      .map((schema) => schema.trim())
      .filter(Boolean);
    if (!useSeparateFields) {
      return { connection_url: connectionUrl.trim(), schema_allowlist: schemaAllowlist };
    }
    return {
      host: host.trim(),
      port: Number(port) || 5432,
      database: database.trim(),
      user: user.trim(),
      password,
      sslmode,
      schema_allowlist: schemaAllowlist,
    };
  }

  async function handleTest() {
    setPending("test");
    setStatus(null);
    try {
      const result = await onTest(buildPayload());
      setStatus({
        kind: "success",
        text: `Connection test passed: ${result.table_count} ${result.table_count === 1 ? "table" : "tables"} found, user is read-only.`,
      });
    } catch (error) {
      setStatus({ kind: "error", text: errorText(error) });
    } finally {
      setPending(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending("connect");
    setStatus(null);
    try {
      await onConnect(buildPayload());
    } catch (error) {
      setStatus({ kind: "error", text: errorText(error) });
    } finally {
      setPending(null);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex w-full max-w-[560px] flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="m-0 text-[28px] font-semibold tracking-[-0.02em]">Connect your PostgreSQL database</h1>
        <p className="m-0 text-[15px] leading-normal text-muted">
          AskData reads your tables and answers questions about them. It never changes your data.
        </p>
      </div>

      {useSeparateFields ? (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[minmax(0,1fr)_120px]">
            <Field id="host" label="Host">
              <input id="host" value={host} onChange={(e) => setHost(e.target.value)} placeholder="localhost" className={inputClass} required />
            </Field>
            <Field id="port" label="Port">
              <input id="port" inputMode="numeric" value={port} onChange={(e) => setPort(e.target.value)} className={inputClass} />
            </Field>
          </div>
          <Field id="database" label="Database">
            <input id="database" value={database} onChange={(e) => setDatabase(e.target.value)} placeholder="shop" className={inputClass} required />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field id="user" label="User">
              <input id="user" value={user} onChange={(e) => setUser(e.target.value)} placeholder="askdata_reader" autoComplete="off" className={inputClass} required />
            </Field>
            <Field id="password" label="Password">
              <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" className={inputClass} />
            </Field>
          </div>
          <Field id="sslmode" label="SSL">
            <select id="sslmode" value={sslmode} onChange={(e) => setSslmode(e.target.value as SslMode)} className={inputClass}>
              <option value="prefer">Prefer</option>
              <option value="require">Require</option>
              <option value="verify-full">Verify full</option>
              <option value="disable">Disable</option>
            </select>
          </Field>
          <button type="button" onClick={() => setUseSeparateFields(false)} className="text-link self-start text-[13px]">
            Use a connection URL instead
          </button>
        </div>
      ) : (
        <Field id="url" label="Connection URL">
          <input
            id="url"
            value={connectionUrl}
            onChange={(e) => setConnectionUrl(e.target.value)}
            placeholder="postgresql://askdata_reader:••••••••@localhost:5432/shop"
            autoComplete="off"
            spellCheck={false}
            className={`${inputClass} font-mono`}
            required
          />
          <button type="button" onClick={() => setUseSeparateFields(true)} className="text-link self-start text-[13px]">
            Enter host, port and user separately
          </button>
        </Field>
      )}

      <Field
        id="schemas"
        label={
          <>
            Schemas to include <span className="font-normal text-muted">(optional)</span>
          </>
        }
      >
        <input id="schemas" value={schemas} onChange={(e) => setSchemas(e.target.value)} placeholder="public" className={inputClass} />
      </Field>

      <div className="flex gap-3 rounded-[10px] bg-infoBg px-4 py-3.5 text-sm leading-normal text-ink">
        <ShieldIcon size={18} className="mt-0.5 shrink-0 text-info" />
        <div>
          Use a <strong>read-only user</strong>. AskData checks its permissions and won&apos;t connect with a user that can
          change data or read server files. The connection is kept in memory for this session only and never saved.{" "}
          <a href={READ_ONLY_USER_GUIDE_URL} target="_blank" rel="noreferrer" className="text-link">
            How to create a read-only user
          </a>
        </div>
      </div>

      {status ? (
        <div
          role={status.kind === "error" ? "alert" : "status"}
          className={`flex items-start gap-2.5 rounded-[10px] border px-4 py-3 text-sm leading-normal ${
            status.kind === "success" ? "border-successLine bg-successBg" : "border-dangerLine bg-dangerBg"
          }`}
        >
          {status.kind === "success" ? (
            <CheckIcon size={18} className="mt-0.5 shrink-0 text-success" />
          ) : (
            <AlertIcon size={18} className="mt-0.5 shrink-0 text-danger" />
          )}
          <span>{status.text}</span>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleTest}
          disabled={pending !== null}
          className="h-11 rounded-[10px] border border-inputLine bg-surface px-[18px] text-[15px] font-medium text-ink hover:border-muted disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending === "test" ? "Testing…" : "Test connection"}
        </button>
        <button
          type="submit"
          disabled={pending !== null}
          className="h-11 rounded-[10px] bg-accent px-[22px] text-[15px] font-medium text-white hover:bg-accentHover disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending === "connect" ? "Connecting…" : "Connect and start asking"}
        </button>
      </div>
      <p className="m-0 text-[13px] text-muted">Questions about your own database are not saved in the history.</p>
    </form>
  );
}

function Field({ id, label, children }: { id: string; label: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children}
    </div>
  );
}

function errorText(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "The connection failed. Check the details and try again.";
}
