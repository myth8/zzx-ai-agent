"""Best-effort persisted telemetry for the admin observability page.

Borrowed from DSH's telemetry philosophy: structured run/step records with
session and request identity, explicit redaction (no prompts, tool arguments or
answers), and best-effort persistence. This project stores records in MySQL
instead of shipping OTLP; an OTel exporter can be added later without changing
the Agent loop.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from flask import has_app_context

from app.config import Config
from app.db import connection, transaction


logger = logging.getLogger(__name__)

TERMINAL_TRACE_EVENTS = {"run_finish", "run_error"}


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


def _parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key, value in list(result.items()):
        if isinstance(value, (datetime, date)):
            # Telemetry timestamps are stored as UTC; make that explicit so
            # the browser converts them to the viewer's local timezone.
            result[key] = value.isoformat() + ("Z" if value.tzinfo is None else "")
    for key in ("context", "payload"):
        if key in result:
            result[key] = _parse_json(result[key])
    for key in ("duration_ms", "steps", "tool_calls", "tool_errors",
                "prompt_tokens", "completion_tokens", "total_tokens"):
        if result.get(key) is not None:
            result[key] = int(result[key])
    return result


class TelemetryRecorder:
    """Persist one Agent run and its step events without affecting the run."""

    def __init__(
        self,
        engine: str,
        session_id: str,
        request_id: str,
        user_id=None,
        input_text: str = "",
    ):
        self.engine = engine
        self.session_id = session_id
        self.request_id = request_id
        self.user_id = user_id
        self.input_text = input_text or ""
        self.run_id = str(uuid.uuid4())
        self.seq = 0
        self.enabled = bool(Config.AGENT_TELEMETRY_ENABLED)

    def start(self) -> bool:
        if not self.enabled:
            return False
        if not has_app_context():
            # Direct engine tests and CLI benchmark runs have no Flask app.
            self.enabled = False
            return False
        try:
            with transaction() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_telemetry_runs "
                    "(id, request_id, session_id, user_id, engine, status, "
                    "input_text, started_at, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, 'running', %s, "
                    "UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))",
                    (
                        self.run_id,
                        self.request_id or "unavailable",
                        self.session_id or None,
                        self.user_id,
                        self.engine,
                        self.input_text,
                    ),
                )
            return True
        except Exception:
            self.enabled = False
            logger.warning(
                "Agent telemetry disabled: run table unavailable or write failed",
                exc_info=True,
            )
            return False

    def set_output(self, output_text: str) -> None:
        """Store the final answer after the Agent loop, outside trace logs."""
        if not self.enabled or not output_text:
            return
        try:
            with transaction() as conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE agent_telemetry_runs SET output_text=%s WHERE id=%s",
                    (str(output_text), self.run_id),
                )
        except Exception:
            self.enabled = False
            logger.warning(
                "Agent telemetry output update failed run_id=%s",
                self.run_id,
                exc_info=True,
            )

    def trace(self):
        from app.agent_core.observability import AgentTrace

        return AgentTrace(
            self.engine,
            session_id=self.session_id,
            request_id=self.request_id,
            run_id=self.run_id,
            sink=self.record,
        )

    def record(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        event = str(payload.get("event") or "unknown")
        self.seq += 1
        try:
            with transaction() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_telemetry_events "
                    "(run_id, seq, event_type, payload, created_at) "
                    "VALUES (%s, %s, %s, %s, UTC_TIMESTAMP(6))",
                    (self.run_id, self.seq, event, _json(payload)),
                )
                if event == "run_finish":
                    prompt = int(payload.get("prompt_tokens") or 0)
                    completion = int(payload.get("completion_tokens") or 0)
                    cur.execute(
                        "UPDATE agent_telemetry_runs SET "
                        "status=%s, finished_at=UTC_TIMESTAMP(6), "
                        "duration_ms=%s, steps=%s, tool_calls=%s, tool_errors=%s, "
                        "prompt_tokens=%s, completion_tokens=%s, total_tokens=%s, "
                        "context=%s, output_chars=%s, error_type=%s "
                        "WHERE id=%s",
                        (
                            "succeeded" if payload.get("status") == "success" else "failed",
                            int(payload.get("duration_ms") or 0),
                            int(payload.get("steps") or 0),
                            int(payload.get("tool_calls") or 0),
                            int(payload.get("tool_errors") or 0),
                            prompt,
                            completion,
                            prompt + completion,
                            _json(payload.get("context")),
                            int(payload.get("output_chars") or 0),
                            payload.get("error_type"),
                            self.run_id,
                        ),
                    )
                elif event == "run_error":
                    cur.execute(
                        "UPDATE agent_telemetry_runs SET "
                        "status='failed', finished_at=UTC_TIMESTAMP(6), "
                        "duration_ms=%s, error_type=%s WHERE id=%s",
                        (
                            int(payload.get("elapsed_ms") or 0),
                            payload.get("error_type"),
                            self.run_id,
                        ),
                    )
        except Exception:
            self.enabled = False
            logger.warning(
                "Agent telemetry disabled: event write failed run_id=%s",
                self.run_id,
                exc_info=True,
            )


def _filters(engine=None, status=None, session_id=None):
    clauses = []
    params: list[Any] = []
    if engine:
        clauses.append("engine=%s")
        params.append(engine)
    if status:
        clauses.append("status=%s")
        params.append(status)
    if session_id:
        clauses.append("session_id=%s")
        params.append(session_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def list_runs(*, engine=None, status=None, session_id=None, limit=50, offset=0):
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    where, params = _filters(engine, status, session_id)
    with connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM agent_telemetry_runs{where}", params)
        total = int(cur.fetchone()["total"])
        cur.execute(
            "SELECT id, request_id, session_id, user_id, engine, status, "
            "started_at, finished_at, duration_ms, steps, tool_calls, tool_errors, "
            "prompt_tokens, completion_tokens, total_tokens, context, "
            "output_chars, error_type, input_text, output_text, created_at "
            f"FROM agent_telemetry_runs{where} "
            "ORDER BY started_at DESC, id DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        runs = [_serialize_row(row) for row in cur.fetchall()]
    return runs, total


def list_conversations(*, engine=None, limit=100):
    """Aggregate runs by session for the left-hand conversation rail."""
    limit = max(1, min(int(limit), 200))
    clauses = ["r.session_id IS NOT NULL", "r.session_id <> ''"]
    params: list[Any] = []
    if engine:
        clauses.append("r.engine=%s")
        params.append(engine)
    where = " WHERE " + " AND ".join(clauses)
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT r.session_id, MAX(r.engine) AS engine, "
            "COALESCE(MAX(s.title), '未命名会话') AS title, "
            "COUNT(*) AS runs, "
            "COALESCE(SUM(r.status='succeeded'), 0) AS succeeded, "
            "COALESCE(SUM(r.status='failed'), 0) AS failed, "
            "COALESCE(SUM(r.total_tokens), 0) AS total_tokens, "
            "COALESCE(AVG(r.duration_ms), 0) AS avg_duration_ms, "
            "MAX(r.started_at) AS last_run_at, MIN(r.started_at) AS first_run_at "
            "FROM agent_telemetry_runs r "
            "LEFT JOIN sessions s ON s.session_id=r.session_id"
            f"{where} "
            "GROUP BY r.session_id ORDER BY last_run_at DESC LIMIT %s",
            [*params, limit],
        )
        rows = [_serialize_row(row) for row in cur.fetchall()]
    for row in rows:
        row["runs"] = int(row["runs"])
        row["succeeded"] = int(row["succeeded"])
        row["failed"] = int(row["failed"])
        row["total_tokens"] = int(row["total_tokens"])
        row["avg_duration_ms"] = round(float(row["avg_duration_ms"] or 0), 1)
    return rows


def get_run(run_id):
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM agent_telemetry_runs WHERE id=%s", (run_id,))
        row = cur.fetchone()
        if row is None:
            return None, []
        cur.execute(
            "SELECT seq, event_type, payload, created_at "
            "FROM agent_telemetry_events WHERE run_id=%s ORDER BY seq ASC",
            (run_id,),
        )
        events = [_serialize_row(event) for event in cur.fetchall()]
    return _serialize_row(row), events


def summary(*, hours=24):
    hours = max(1, min(int(hours), 24 * 30))
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS runs, "
            "COALESCE(SUM(status='succeeded'), 0) AS succeeded, "
            "COALESCE(SUM(status='failed'), 0) AS failed, "
            "COALESCE(SUM(status='running'), 0) AS running, "
            "COALESCE(SUM(total_tokens), 0) AS total_tokens, "
            "COALESCE(AVG(duration_ms), 0) AS avg_duration_ms, "
            "COALESCE(SUM(tool_errors), 0) AS tool_errors "
            "FROM agent_telemetry_runs "
            "WHERE started_at >= UTC_TIMESTAMP() - INTERVAL %s HOUR",
            (hours,),
        )
        row = cur.fetchone() or {}
    runs = int(row.get("runs") or 0)
    succeeded = int(row.get("succeeded") or 0)
    return {
        "hours": hours,
        "runs": runs,
        "succeeded": succeeded,
        "failed": int(row.get("failed") or 0),
        "running": int(row.get("running") or 0),
        "success_rate": round(succeeded / runs, 3) if runs else 0,
        "total_tokens": int(row.get("total_tokens") or 0),
        "avg_duration_ms": round(float(row.get("avg_duration_ms") or 0), 1),
        "tool_errors": int(row.get("tool_errors") or 0),
    }
