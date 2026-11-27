"""Administrator-only observability API for Agent telemetry."""
import logging

import pymysql
from flask import Blueprint, jsonify, request

from app.auth import admin_required
from app.telemetry import get_run, list_conversations, list_runs, summary
from app.utils.rate_limit import admin_read_rate_limit
from app.utils.responses import api_error


logger = logging.getLogger(__name__)

telemetry_admin_bp = Blueprint(
    "telemetry_admin", __name__, url_prefix="/api/admin/telemetry"
)

VALID_ENGINES = {"react", "toolcalling", "code"}
VALID_STATUSES = {"running", "succeeded", "failed", "cancelled"}


def _unavailable(error):
    logger.warning("Agent telemetry query failed: %s", error)
    return api_error(
        "TELEMETRY_UNAVAILABLE",
        "观测数据表尚未就绪，请先执行 alembic upgrade head",
        503,
    )


def _int_arg(name, default, minimum, maximum):
    raw = request.args.get(name, "")
    if raw == "":
        return default
    try:
        return max(minimum, min(int(raw), maximum))
    except ValueError:
        raise ValueError(f"{name} must be an integer")


@telemetry_admin_bp.route("/runs", methods=["GET"])
@admin_required
@admin_read_rate_limit
def runs():
    engine = request.args.get("engine", "").strip()
    status = request.args.get("status", "").strip()
    if engine and engine not in VALID_ENGINES:
        return api_error("TELEMETRY_FILTER_INVALID", "engine 参数无效", 400)
    if status and status not in VALID_STATUSES:
        return api_error("TELEMETRY_FILTER_INVALID", "status 参数无效", 400)
    try:
        limit = _int_arg("limit", 50, 1, 200)
        offset = _int_arg("offset", 0, 0, 10_000_000)
    except ValueError as exc:
        return api_error("TELEMETRY_FILTER_INVALID", str(exc), 400)
    session_id = request.args.get("session_id", "").strip()[:100]
    try:
        rows, total = list_runs(
            engine=engine or None,
            status=status or None,
            session_id=session_id or None,
            limit=limit,
            offset=offset,
        )
    except (pymysql.err.ProgrammingError, pymysql.err.OperationalError) as exc:
        return _unavailable(exc)
    return jsonify({
        "code": 0,
        "data": {"runs": rows, "total": total, "limit": limit, "offset": offset},
    })


@telemetry_admin_bp.route("/conversations", methods=["GET"])
@admin_required
@admin_read_rate_limit
def conversations():
    engine = request.args.get("engine", "").strip()
    if engine and engine not in VALID_ENGINES:
        return api_error("TELEMETRY_FILTER_INVALID", "engine 参数无效", 400)
    try:
        limit = _int_arg("limit", 100, 1, 200)
    except ValueError as exc:
        return api_error("TELEMETRY_FILTER_INVALID", str(exc), 400)
    try:
        rows = list_conversations(engine=engine or None, limit=limit)
    except (pymysql.err.ProgrammingError, pymysql.err.OperationalError) as exc:
        return _unavailable(exc)
    return jsonify({"code": 0, "data": {"conversations": rows, "limit": limit}})


@telemetry_admin_bp.route("/runs/<run_id>", methods=["GET"])
@admin_required
@admin_read_rate_limit
def run_detail(run_id):
    try:
        run, events = get_run(run_id)
    except (pymysql.err.ProgrammingError, pymysql.err.OperationalError) as exc:
        return _unavailable(exc)
    if run is None:
        return api_error("TELEMETRY_RUN_NOT_FOUND", "观测记录不存在", 404)
    return jsonify({"code": 0, "data": {"run": run, "events": events}})


@telemetry_admin_bp.route("/summary", methods=["GET"])
@admin_required
@admin_read_rate_limit
def stats():
    try:
        hours = _int_arg("hours", 24, 1, 24 * 30)
    except ValueError as exc:
        return api_error("TELEMETRY_FILTER_INVALID", str(exc), 400)
    try:
        data = summary(hours=hours)
    except (pymysql.err.ProgrammingError, pymysql.err.OperationalError) as exc:
        return _unavailable(exc)
    return jsonify({"code": 0, "data": data})
