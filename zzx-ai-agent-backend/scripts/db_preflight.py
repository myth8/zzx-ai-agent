"""Generate a read-only JSON report before applying database migrations."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from dotenv import dotenv_values


def configuration():
    values = dict(dotenv_values(Path(__file__).resolve().parents[1] / ".env"))
    values.update(os.environ)
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = configuration()
    conn = pymysql.connect(
        host=cfg.get("MYSQL_HOST", "127.0.0.1"),
        port=int(cfg.get("MYSQL_PORT", "3306")),
        user=cfg["MYSQL_USER"],
        password=cfg["MYSQL_PASSWORD"],
        database=cfg.get("MYSQL_DB", "zzx_agent_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=30,
    )
    checks = {
        "table_counts": "SELECT 'users' name,COUNT(*) count FROM users UNION ALL SELECT 'sessions',COUNT(*) FROM sessions UNION ALL SELECT 'chat_messages',COUNT(*) FROM chat_messages UNION ALL SELECT 'chat_summaries',COUNT(*) FROM chat_summaries",
        "session_id_lengths": "SELECT CHAR_LENGTH(session_id) id_length,COUNT(*) count FROM sessions GROUP BY CHAR_LENGTH(session_id) ORDER BY id_length",
        "orphan_sessions": "SELECT s.id,s.user_id,s.session_id FROM sessions s LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL ORDER BY s.id",
        "orphan_messages": "SELECT m.id,m.session_id FROM chat_messages m LEFT JOIN sessions s ON s.session_id=m.session_id WHERE s.session_id IS NULL ORDER BY m.id",
        "duplicate_message_orders": "SELECT session_id,msg_order,COUNT(*) count FROM chat_messages GROUP BY session_id,msg_order HAVING COUNT(*)>1",
        "message_order_gaps": "SELECT session_id,COUNT(*) count,MIN(msg_order) min_order,MAX(msg_order) max_order FROM chat_messages GROUP BY session_id HAVING min_order<>1 OR max_order<>count",
        "stale_session_timestamps": "SELECT s.session_id,s.updated_at,MAX(m.created_at) last_message_at FROM sessions s JOIN chat_messages m ON m.session_id=s.session_id GROUP BY s.session_id,s.updated_at HAVING s.updated_at<last_message_at",
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": cfg.get("MYSQL_DB", "zzx_agent_db"),
        "checks": {},
    }
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() version")
            report["mysql_version"] = cur.fetchone()["version"]
            for name, sql in checks.items():
                cur.execute(sql)
                rows = cur.fetchall()
                for row in rows:
                    for key, value in tuple(row.items()):
                        if hasattr(value, "isoformat"):
                            row[key] = value.isoformat()
                report["checks"][name] = rows
    finally:
        conn.close()
    report["blocking"] = bool(
        report["checks"]["orphan_messages"]
        or report["checks"]["duplicate_message_orders"]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Migration preflight report written to {args.output}")
    print(f"blocking={str(report['blocking']).lower()}")


if __name__ == "__main__":
    main()
