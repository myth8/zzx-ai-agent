"""Atomic idempotency-record operations used inside a caller transaction."""
from __future__ import annotations

import json


def try_create_record(
    conn, *, user_id, endpoint, idempotency_key, request_hash,
    lock_seconds=60, expires_hours=24
):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO idempotency_records "
            "(user_id, endpoint, idempotency_key, request_hash, status, "
            "locked_until, expires_at) "
            "VALUES (%s, %s, %s, %s, 'processing', "
            "DATE_ADD(UTC_TIMESTAMP(6), INTERVAL %s SECOND), "
            "DATE_ADD(UTC_TIMESTAMP(6), INTERVAL %s HOUR))",
            (
                user_id, endpoint, idempotency_key, request_hash,
                lock_seconds, expires_hours,
            ),
        )
        return cur.lastrowid


def get_record_by_id(conn, record_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM idempotency_records WHERE id=%s",
            (record_id,),
        )
        return cur.fetchone()


def get_record_for_update(conn, *, user_id, endpoint, idempotency_key):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM idempotency_records "
            "WHERE user_id=%s AND endpoint=%s AND idempotency_key=%s FOR UPDATE",
            (user_id, endpoint, idempotency_key),
        )
        return cur.fetchone()


def complete_record(
    conn, *, record_id, resource_type, resource_id, response_status,
    response_body
):
    encoded = json.dumps(response_body, ensure_ascii=False, separators=(",", ":"))
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE idempotency_records SET status='completed', "
            "resource_type=%s, resource_id=%s, response_status=%s, "
            "response_body=%s, locked_until=NULL, updated_at=UTC_TIMESTAMP(6) "
            "WHERE id=%s AND status='processing'",
            (
                resource_type, resource_id, response_status, encoded,
                record_id,
            ),
        )
        if cur.rowcount != 1:
            raise RuntimeError("idempotency record was not in processing state")
