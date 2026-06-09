"""Immutable audit log using SQLite."""
from __future__ import annotations
import json
import logging
import os
import sqlite3
from typing import List, Optional

from harness.models import AuditEvent

logger = logging.getLogger(__name__)
DB_PATH = os.getenv("AUDIT_DB_PATH", "data/audit.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_audit_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            event_id    TEXT PRIMARY KEY,
            trace_id    TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            actor       TEXT NOT NULL,
            details     TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            outcome     TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace ON audit_log (trace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON audit_log (event_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log (timestamp)")
    conn.commit()
    conn.close()
    logger.info("Audit DB initialised at %s", DB_PATH)


def log_event(event: AuditEvent) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO audit_log (event_id, trace_id, event_type, actor, details, timestamp, outcome) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.trace_id,
                event.event_type,
                event.actor,
                json.dumps(event.details),
                event.timestamp.isoformat(),
                event.outcome,
            )
        )
        conn.commit()
        logger.debug("Audit event logged: %s / %s", event.event_type, event.event_id)
    except Exception as exc:
        logger.error("AUDIT LOG FAILURE — event not persisted: %s", exc)
        raise
    finally:
        conn.close()


def get_trace(trace_id: str) -> List[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE trace_id = ? ORDER BY timestamp ASC",
        (trace_id,)
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["details"] = json.loads(d["details"])
        result.append(d)
    return result


def get_recent_events(limit: int = 50, event_type: Optional[str] = None) -> List[dict]:
    conn = _get_conn()
    if event_type:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
            (event_type, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["details"] = json.loads(d["details"])
        result.append(d)
    return result
