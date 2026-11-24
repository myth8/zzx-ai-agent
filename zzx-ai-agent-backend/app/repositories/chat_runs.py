"""Persistence and guarded state transitions for chat runs."""
from __future__ import annotations

import uuid

from app.db import connection, transaction


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "timed_out"}
ALLOWED_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"succeeded", "failed", "cancelled", "timed_out"},
}


def create_chat_run(
    conn, *, user_id, session_id, user_message_id, agent_type,
    request_id, model=None, run_id=None
):
    run_id = run_id or str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_runs "
            "(id, user_id, session_id, user_message_id, status, model, "
            "agent_type, request_id) VALUES (%s, %s, %s, %s, 'queued', %s, %s, %s)",
            (
                run_id, user_id, session_id, user_message_id, model,
                agent_type, request_id,
            ),
        )
    return run_id


def get_chat_run(user_id, run_id):
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM chat_runs WHERE id=%s AND user_id=%s",
            (run_id, user_id),
        )
        return cur.fetchone()


def transition_chat_run(
    user_id, run_id, *, from_status, to_status, expected_version,
    assistant_message_id=None, error_code=None, error_message=None,
    prompt_tokens=None, completion_tokens=None, total_tokens=None,
    estimated_cost=None
):
    """Compare-and-swap a run state; stale workers update zero rows."""
    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise ValueError(f"invalid chat run transition: {from_status} -> {to_status}")
    started_sql = "started_at=COALESCE(started_at, UTC_TIMESTAMP(6)), " if to_status == "running" else ""
    finished_sql = "finished_at=UTC_TIMESTAMP(6), " if to_status in TERMINAL_STATUSES else ""
    with transaction() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chat_runs SET status=%s, "
            f"{started_sql}{finished_sql}"
            "assistant_message_id=COALESCE(%s, assistant_message_id), "
            "error_code=%s, error_message=%s, "
            "prompt_tokens=COALESCE(%s, prompt_tokens), "
            "completion_tokens=COALESCE(%s, completion_tokens), "
            "total_tokens=COALESCE(%s, total_tokens), "
            "estimated_cost=COALESCE(%s, estimated_cost), "
            "version=version+1, updated_at=UTC_TIMESTAMP(6) "
            "WHERE id=%s AND user_id=%s AND status=%s AND version=%s",
            (
                to_status, assistant_message_id, error_code, error_message,
                prompt_tokens, completion_tokens, total_tokens, estimated_cost,
                run_id, user_id, from_status, expected_version,
            ),
        )
        return cur.rowcount == 1
