import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.core.config import Settings, get_settings
from app.db.connection import get_db_connection
from app.schemas.query import ConversationMessage, QueryErrorResponse, QueryResponse
from app.schemas.session import SessionDetail, SessionSummary, SessionTurn


@dataclass
class PersistedTurnRef:
    session_id: str
    turn_id: str
    created_at: str


class SessionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.schema_name = "askdata_app"
        self.preview_row_limit = 50

    def initialize_storage(self) -> None:
        with get_db_connection(self.settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema_name}")
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.schema_name}.chat_sessions (
                        id TEXT PRIMARY KEY,
                        client_token TEXT NOT NULL,
                        title TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.schema_name}.chat_turns (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL REFERENCES {self.schema_name}.chat_sessions(id) ON DELETE CASCADE,
                        question TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('success', 'error')),
                        answer_summary TEXT,
                        generated_sql TEXT,
                        columns_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        rows_preview_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        row_count INTEGER NOT NULL DEFAULT 0,
                        chart_type TEXT,
                        chart_x TEXT,
                        chart_y TEXT,
                        warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        used_tables_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        error_code TEXT,
                        error_message TEXT,
                        repaired BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS chat_sessions_client_updated_idx
                    ON {self.schema_name}.chat_sessions (client_token, updated_at DESC)
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS chat_turns_session_created_idx
                    ON {self.schema_name}.chat_turns (session_id, created_at ASC)
                    """
                )

    def list_sessions(self, client_token: str) -> list[SessionSummary]:
        with get_db_connection(self.settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        s.id,
                        s.title,
                        s.created_at,
                        s.updated_at,
                        COALESCE(turn_counts.turn_count, 0) AS turn_count,
                        latest_turn.question AS last_question,
                        latest_turn.status AS last_status
                    FROM {self.schema_name}.chat_sessions AS s
                    LEFT JOIN (
                        SELECT session_id, COUNT(*) AS turn_count
                        FROM {self.schema_name}.chat_turns
                        GROUP BY session_id
                    ) AS turn_counts
                        ON turn_counts.session_id = s.id
                    LEFT JOIN LATERAL (
                        SELECT question, status
                        FROM {self.schema_name}.chat_turns
                        WHERE session_id = s.id
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) AS latest_turn ON TRUE
                    WHERE s.client_token = %s
                    ORDER BY s.updated_at DESC
                    """,
                    (client_token,),
                )
                rows = cursor.fetchall()

        return [
            SessionSummary(
                id=row["id"],
                title=row["title"],
                created_at=self._isoformat(row["created_at"]),
                updated_at=self._isoformat(row["updated_at"]),
                turn_count=int(row["turn_count"] or 0),
                last_question=row.get("last_question"),
                last_status=row.get("last_status"),
            )
            for row in rows
        ]

    def get_session(self, client_token: str, session_id: str) -> SessionDetail | None:
        with get_db_connection(self.settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, title, created_at, updated_at
                    FROM {self.schema_name}.chat_sessions
                    WHERE id = %s AND client_token = %s
                    """,
                    (session_id, client_token),
                )
                session_row = cursor.fetchone()
                if session_row is None:
                    return None

                cursor.execute(
                    f"""
                    SELECT
                        id,
                        question,
                        status,
                        answer_summary,
                        generated_sql,
                        columns_json,
                        rows_preview_json,
                        row_count,
                        chart_type,
                        chart_x,
                        chart_y,
                        warnings_json,
                        used_tables_json,
                        error_code,
                        error_message,
                        repaired,
                        created_at
                    FROM {self.schema_name}.chat_turns
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                )
                turn_rows = cursor.fetchall()

        return SessionDetail(
            id=session_row["id"],
            title=session_row["title"],
            created_at=self._isoformat(session_row["created_at"]),
            updated_at=self._isoformat(session_row["updated_at"]),
            turns=[self._build_session_turn(session_id, row) for row in turn_rows],
        )

    def rename_session(
        self,
        client_token: str,
        session_id: str,
        title: str,
    ) -> SessionSummary | None:
        normalized_title = " ".join(title.strip().split())
        if not normalized_title:
            raise ValueError("Session title must not be empty.")

        with get_db_connection(self.settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE {self.schema_name}.chat_sessions
                    SET title = %s, updated_at = NOW()
                    WHERE id = %s AND client_token = %s
                    RETURNING id, title, created_at, updated_at
                    """,
                    (normalized_title[:120], session_id, client_token),
                )
                updated = cursor.fetchone()
                if updated is None:
                    return None

        return SessionSummary(
            id=updated["id"],
            title=updated["title"],
            created_at=self._isoformat(updated["created_at"]),
            updated_at=self._isoformat(updated["updated_at"]),
            turn_count=0,
        )

    def persist_success(
        self,
        client_token: str,
        response: QueryResponse,
        session_id: str | None = None,
    ) -> PersistedTurnRef:
        active_session_id = self._ensure_session(
            client_token=client_token,
            question=response.question,
            session_id=session_id,
        )
        turn_id = self._new_id()

        with get_db_connection(self.settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {self.schema_name}.chat_turns (
                        id,
                        session_id,
                        question,
                        status,
                        answer_summary,
                        generated_sql,
                        columns_json,
                        rows_preview_json,
                        row_count,
                        chart_type,
                        chart_x,
                        chart_y,
                        warnings_json,
                        used_tables_json,
                        repaired
                    ) VALUES (
                        %s, %s, %s, 'success', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING created_at
                    """,
                    (
                        turn_id,
                        active_session_id,
                        response.question,
                        response.answer_summary,
                        response.generated_sql,
                        Jsonb(self._to_jsonable(response.columns)),
                        Jsonb(self._to_jsonable(response.rows[: self.preview_row_limit])),
                        response.row_count,
                        response.chart_recommendation.type,
                        response.chart_recommendation.x,
                        response.chart_recommendation.y,
                        Jsonb(self._to_jsonable(response.warnings)),
                        Jsonb(self._to_jsonable(response.used_tables)),
                        response.repaired,
                    ),
                )
                created_row = cursor.fetchone()
                cursor.execute(
                    f"""
                    UPDATE {self.schema_name}.chat_sessions
                    SET updated_at = NOW()
                    WHERE id = %s
                    """,
                    (active_session_id,),
                )

        return PersistedTurnRef(
            session_id=active_session_id,
            turn_id=turn_id,
            created_at=self._isoformat(created_row["created_at"]),
        )

    def persist_error(
        self,
        client_token: str,
        question: str,
        error_payload: QueryErrorResponse,
        session_id: str | None = None,
    ) -> PersistedTurnRef:
        active_session_id = self._ensure_session(
            client_token=client_token,
            question=question,
            session_id=session_id,
        )
        turn_id = self._new_id()

        with get_db_connection(self.settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {self.schema_name}.chat_turns (
                        id,
                        session_id,
                        question,
                        status,
                        warnings_json,
                        used_tables_json,
                        error_code,
                        error_message
                    ) VALUES (
                        %s, %s, %s, 'error', %s, '[]'::jsonb, %s, %s
                    )
                    RETURNING created_at
                    """,
                    (
                        turn_id,
                        active_session_id,
                        question,
                        Jsonb(self._to_jsonable(error_payload.warnings)),
                        error_payload.error.code,
                        error_payload.error.message,
                    ),
                )
                created_row = cursor.fetchone()
                cursor.execute(
                    f"""
                    UPDATE {self.schema_name}.chat_sessions
                    SET updated_at = NOW()
                    WHERE id = %s
                    """,
                    (active_session_id,),
                )

        return PersistedTurnRef(
            session_id=active_session_id,
            turn_id=turn_id,
            created_at=self._isoformat(created_row["created_at"]),
        )

    def get_turn_rerun_context(
        self,
        client_token: str,
        session_id: str,
        turn_id: str,
    ) -> tuple[str, list[ConversationMessage]] | None:
        session = self.get_session(client_token, session_id)
        if session is None:
            return None

        target_index: int | None = None
        for index, turn in enumerate(session.turns):
            if turn.id == turn_id:
                target_index = index
                break

        if target_index is None:
            return None

        target_turn = session.turns[target_index]
        prior_successful_turns = [
            turn
            for turn in session.turns[:target_index]
            if turn.status == "success" and turn.response is not None
        ][-3:]

        context: list[ConversationMessage] = []
        for turn in prior_successful_turns:
            context.extend(
                [
                    ConversationMessage(role="user", content=turn.question),
                    ConversationMessage(
                        role="assistant",
                        content=turn.response.answer_summary,
                    ),
                ]
            )

        return target_turn.question, context

    def export_turn_csv(
        self,
        client_token: str,
        session_id: str,
        turn_id: str,
    ) -> str | None:
        with get_db_connection(self.settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT columns_json, rows_preview_json, status
                    FROM {self.schema_name}.chat_turns AS t
                    JOIN {self.schema_name}.chat_sessions AS s
                        ON s.id = t.session_id
                    WHERE t.id = %s AND t.session_id = %s AND s.client_token = %s
                    """,
                    (turn_id, session_id, client_token),
                )
                row = cursor.fetchone()

        if row is None or row["status"] != "success":
            return None

        output = io.StringIO()
        writer = csv.writer(output)
        columns = list(row["columns_json"] or [])
        rows = list(row["rows_preview_json"] or [])

        if columns:
            writer.writerow(columns)

        for record in rows:
            writer.writerow(record)

        return output.getvalue()

    def _ensure_session(
        self,
        client_token: str,
        question: str,
        session_id: str | None,
    ) -> str:
        if session_id:
            with get_db_connection(self.settings) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT id
                        FROM {self.schema_name}.chat_sessions
                        WHERE id = %s AND client_token = %s
                        """,
                        (session_id, client_token),
                    )
                    existing = cursor.fetchone()
            if existing is None:
                raise ValueError("Session was not found for the current client token.")
            return session_id

        created_session_id = self._new_id()
        with get_db_connection(self.settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {self.schema_name}.chat_sessions (
                        id,
                        client_token,
                        title
                    ) VALUES (%s, %s, %s)
                    """,
                    (
                        created_session_id,
                        client_token,
                        self._build_session_title(question),
                    ),
                )
        return created_session_id

    def _build_session_turn(self, session_id: str, row: dict[str, Any]) -> SessionTurn:
        created_at = self._isoformat(row["created_at"])
        if row["status"] == "success":
            response = QueryResponse(
                question=row["question"],
                answer_summary=row["answer_summary"] or "",
                generated_sql=row["generated_sql"] or "",
                columns=list(row["columns_json"] or []),
                rows=list(row["rows_preview_json"] or []),
                row_count=int(row["row_count"] or 0),
                chart_recommendation={
                    "type": row["chart_type"] or "table_only",
                    "x": row["chart_x"],
                    "y": row["chart_y"],
                },
                warnings=list(row["warnings_json"] or []),
                used_tables=list(row["used_tables_json"] or []),
                session_id=session_id,
                turn_id=row["id"],
                persisted=True,
                created_at=created_at,
                repaired=bool(row["repaired"]),
            )
            return SessionTurn(
                id=row["id"],
                question=row["question"],
                status="success",
                created_at=created_at,
                response=response,
            )

        error = QueryErrorResponse(
            error={
                "code": row["error_code"] or "unknown_error",
                "message": row["error_message"] or "The query failed.",
                "details": {},
            },
            warnings=list(row["warnings_json"] or []),
            session_id=session_id,
            turn_id=row["id"],
            persisted=True,
            created_at=created_at,
        )
        return SessionTurn(
            id=row["id"],
            question=row["question"],
            status="error",
            created_at=created_at,
            error=error,
        )

    def _build_session_title(self, question: str) -> str:
        normalized = " ".join(question.strip().split())
        if len(normalized) <= 72:
            return normalized
        return normalized[:69].rstrip() + "..."

    def _isoformat(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    def _new_id(self) -> str:
        return str(uuid4())

    def _to_jsonable(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, list):
            return [self._to_jsonable(item) for item in value]
        if isinstance(value, tuple):
            return [self._to_jsonable(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._to_jsonable(item) for key, item in value.items()}
        return value
