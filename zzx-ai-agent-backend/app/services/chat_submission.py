"""Atomic, idempotent admission of one user message and chat run."""
from __future__ import annotations

import hashlib
import json
import random
import time
import uuid

import pymysql

from app.chat_history import save_message
from app.db import transaction
from app.repositories.chat_runs import create_chat_run
from app.repositories.idempotency import (
    complete_record,
    get_record_by_id,
    get_record_for_update,
    try_create_record,
)


class IdempotencyConflict(Exception):
    """One key was reused for a different canonical request."""


def canonical_request_hash(*, session_id, client_message_id, content, agent_type):
    payload = json.dumps(
        {
            "agent_type": agent_type,
            "client_message_id": client_message_id,
            "content": content,
            "session_id": session_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _decode_response(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def create_chat_submission(
    *, user_id, session_id, content, client_message_id, idempotency_key,
    endpoint, agent_type, request_id, model=None
):
    """Create exactly one user message and run for an idempotency key."""
    # Reject malformed client identifiers before acquiring database locks.
    uuid.UUID(client_message_id)
    if not idempotency_key or len(idempotency_key) > 128:
        raise ValueError("idempotency_key must contain 1 to 128 characters")
    request_hash = canonical_request_hash(
        session_id=session_id,
        client_message_id=client_message_id,
        content=content,
        agent_type=agent_type,
    )

    for attempt in range(3):
        try:
            return _create_chat_submission_once(
                user_id=user_id,
                session_id=session_id,
                content=content,
                client_message_id=client_message_id,
                idempotency_key=idempotency_key,
                endpoint=endpoint,
                agent_type=agent_type,
                request_id=request_id,
                model=model,
                request_hash=request_hash,
            )
        except pymysql.err.IntegrityError as exc:
            if not exc.args or exc.args[0] != 1062:
                raise
            # Leave the failed INSERT transaction first. Reading in a fresh
            # transaction avoids retaining duplicate-key/gap locks.
            return _read_existing_submission(
                user_id=user_id,
                endpoint=endpoint,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
        except pymysql.err.OperationalError as exc:
            retryable = bool(exc.args and exc.args[0] in {1205, 1213})
            if not retryable or attempt == 2:
                raise
            # This operation is safe to retry because the unique idempotency
            # scope is acquired before either the message or run is created.
            time.sleep((0.01 * (2 ** attempt)) + random.uniform(0, 0.01))


def _create_chat_submission_once(
    *, user_id, session_id, content, client_message_id, idempotency_key,
    endpoint, agent_type, request_id, model, request_hash
):

    with transaction() as conn:
        record_id = try_create_record(
            conn,
            user_id=user_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        record = get_record_by_id(conn, record_id)

        message = save_message(
            user_id,
            session_id,
            "user",
            content,
            message_id=str(uuid.uuid4()),
            client_message_id=client_message_id,
            conn=conn,
        )
        if message is None:
            raise LookupError("session not found")
        run_id = create_chat_run(
            conn,
            user_id=user_id,
            session_id=session_id,
            user_message_id=message["message_id"],
            agent_type=agent_type,
            request_id=request_id,
            model=model,
        )
        response = {
            "message_id": message["message_id"],
            "run_id": run_id,
            "status": "queued",
        }
        complete_record(
            conn,
            record_id=record["id"],
            resource_type="chat_run",
            resource_id=run_id,
            response_status=202,
            response_body=response,
        )
        return {"created": True, "status_code": 202, "data": response}


def _read_existing_submission(
    *, user_id, endpoint, idempotency_key, request_hash
):
    with transaction() as conn:
        record = get_record_for_update(
            conn,
            user_id=user_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
        )
        if record is None:
            raise RuntimeError("idempotency record disappeared after duplicate key")
        if record["request_hash"] != request_hash:
            raise IdempotencyConflict(
                "idempotency key was reused with another request"
            )
        return {
            "created": False,
            "status_code": record["response_status"] or 202,
            "data": _decode_response(record["response_body"]) or {
                "run_id": record["resource_id"],
                "status": record["status"],
            },
        }
