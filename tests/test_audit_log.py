"""Tests for the audit log."""
from __future__ import annotations
import os
import time
import uuid
import pytest

# Use a temp DB for tests
os.environ["AUDIT_DB_PATH"] = "/tmp/test_audit_log_unit.db"

from harness.audit_log import init_audit_db, log_event, get_trace, get_recent_events
from harness.models import AuditEvent


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db_path = str(tmp_path / "audit.db")
    os.environ["AUDIT_DB_PATH"] = db_path
    # Reload the module-level DB_PATH
    import harness.audit_log as al
    al.DB_PATH = db_path
    init_audit_db()
    yield


def _event(trace_id: str, event_type: str = "tool_call", outcome: str = "success") -> AuditEvent:
    return AuditEvent(
        trace_id=trace_id,
        event_type=event_type,
        actor="test_actor",
        details={"key": "value"},
        outcome=outcome,
    )


class TestEventInsertion:
    def test_event_can_be_inserted(self):
        trace_id = str(uuid.uuid4())
        event = _event(trace_id)
        log_event(event)  # Should not raise
        events = get_trace(trace_id)
        assert len(events) == 1
        assert events[0]["event_id"] == event.event_id

    def test_event_details_preserved(self):
        trace_id = str(uuid.uuid4())
        event = _event(trace_id)
        event.details = {"tool": "crm_lookup", "result": "found"}
        log_event(event)
        events = get_trace(trace_id)
        assert events[0]["details"]["tool"] == "crm_lookup"


class TestGetTrace:
    def test_get_trace_returns_events_in_order(self):
        trace_id = str(uuid.uuid4())
        for i in range(3):
            e = _event(trace_id, event_type=f"event_{i}")
            log_event(e)
            time.sleep(0.01)
        events = get_trace(trace_id)
        assert len(events) == 3
        # Should be ascending by timestamp
        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps)

    def test_get_trace_not_found_returns_empty(self):
        result = get_trace("nonexistent-trace-id")
        assert result == []
        # Must not raise an exception


class TestGetRecentEvents:
    def test_returns_correct_count(self):
        trace_id = str(uuid.uuid4())
        for _ in range(5):
            log_event(_event(trace_id))
        events = get_recent_events(limit=3)
        assert len(events) <= 3

    def test_filter_by_event_type(self):
        trace_id = str(uuid.uuid4())
        log_event(_event(trace_id, event_type="tool_call"))
        log_event(_event(trace_id, event_type="policy_eval"))
        log_event(_event(trace_id, event_type="tool_call"))

        tool_events = get_recent_events(limit=50, event_type="tool_call")
        for e in tool_events:
            assert e["event_type"] == "tool_call"

    def test_empty_db_returns_empty_list(self):
        # Fresh DB from fixture
        result = get_recent_events(limit=10)
        assert result == []
