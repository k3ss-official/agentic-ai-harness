"""Mock database tool — read requires no approval, write requires approval."""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_db: Dict[str, Dict[str, Any]] = {
    "users": {
        "u-001": {"id": "u-001", "name": "Alice", "role": "admin", "active": True},
        "u-002": {"id": "u-002", "name": "Bob", "role": "viewer", "active": True},
    },
    "orders": {
        "o-001": {"id": "o-001", "customer_id": "cust-001", "amount": 4000.00, "status": "completed"},
        "o-002": {"id": "o-002", "customer_id": "cust-002", "amount": 200.00, "status": "pending"},
    },
}


def read_record(
    table: str,
    record_id: str,
    fields: Optional[List[str]] = None,
) -> dict:
    """Read a record. No approval required."""
    if table not in _db:
        return {"found": False, "error": f"Table '{table}' not found"}
    record = _db[table].get(record_id)
    if not record:
        return {"found": False, "table": table, "record_id": record_id}
    if fields:
        record = {k: v for k, v in record.items() if k in fields}
    logger.info("DB READ: table=%s record_id=%s", table, record_id)
    return {"found": True, "table": table, "record": record}


def write_record(table: str, record_id: str, data: Dict[str, Any]) -> dict:
    """Write a record. REQUIRES approval — should never be called without it."""
    if table not in _db:
        _db[table] = {}
    _db[table][record_id] = {"id": record_id, **data}
    logger.warning("DB WRITE: table=%s record_id=%s data_keys=%s", table, record_id, list(data.keys()))
    return {"status": "ok", "table": table, "record_id": record_id, "written": True}
