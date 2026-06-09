"""Tests for the approval gate."""
from __future__ import annotations
import os
import uuid
import pytest

os.environ.setdefault("TOOL_REGISTRY_PATH", "tools/registry.yaml")
os.environ.setdefault("AUDIT_DB_PATH", "/tmp/test_audit_gate.db")
os.environ["DRY_RUN"] = "false"

from harness.audit_log import init_audit_db
from harness.tool_registry import load_registry, get_tool
from harness.approval_gate import check_approval, decide_approval, get_pending_approvals
from harness.models import ApprovalDecision, ApprovalStatus, ToolCall


@pytest.fixture(autouse=True)
def setup():
    load_registry()
    init_audit_db()
    # Reset DRY_RUN to false for all tests unless overridden
    os.environ["DRY_RUN"] = "false"
    # Reset the dry run flag in the module
    import harness.approval_gate as ag
    ag.DRY_RUN = False
    yield


def _tc(tool_name: str) -> ToolCall:
    return ToolCall(
        trace_id=str(uuid.uuid4()),
        tool_name=tool_name,
        parameters={},
    )


def _trace() -> str:
    return str(uuid.uuid4())


class TestReadOnlyAutoApproved:
    def test_crm_lookup_auto_approved(self):
        tc = _tc("crm_lookup")
        tool_def = get_tool("crm_lookup")
        status = check_approval(tc, tool_def, tc.trace_id)
        assert status == ApprovalStatus.AUTO_APPROVED

    def test_db_read_auto_approved(self):
        tc = _tc("db_read")
        tool_def = get_tool("db_read")
        status = check_approval(tc, tool_def, tc.trace_id)
        assert status == ApprovalStatus.AUTO_APPROVED


class TestWriteToolsPending:
    def test_db_write_returns_pending(self):
        tc = _tc("db_write")
        tool_def = get_tool("db_write")
        status = check_approval(tc, tool_def, tc.trace_id)
        assert status == ApprovalStatus.PENDING

    def test_send_email_returns_pending(self):
        tc = _tc("send_email")
        tool_def = get_tool("send_email")
        status = check_approval(tc, tool_def, tc.trace_id)
        assert status == ApprovalStatus.PENDING


class TestDryRunMode:
    def test_dry_run_auto_approves_writes(self):
        import harness.approval_gate as ag
        ag.DRY_RUN = True
        try:
            tc = _tc("db_write")
            tool_def = get_tool("db_write")
            status = check_approval(tc, tool_def, tc.trace_id)
            assert status == ApprovalStatus.AUTO_APPROVED
        finally:
            ag.DRY_RUN = False


class TestBlockedTool:
    def test_payment_transfer_denied(self):
        tc = _tc("payment_transfer")
        tool_def = get_tool("payment_transfer")
        status = check_approval(tc, tool_def, tc.trace_id)
        assert status == ApprovalStatus.DENIED


class TestApprovalDecision:
    def test_approval_decision_recorded(self):
        # Create a pending approval
        tc = _tc("db_write")
        tool_def = get_tool("db_write")
        check_approval(tc, tool_def, tc.trace_id)

        pending = get_pending_approvals()
        assert len(pending) >= 1
        request_id = pending[-1]["request_id"]

        decision = ApprovalDecision(
            request_id=request_id,
            approved=True,
            decided_by="test_user",
            decision_reason="approved in test",
        )
        decide_approval(decision)

        # Should no longer be in pending
        still_pending = [p for p in get_pending_approvals() if p["request_id"] == request_id]
        assert len(still_pending) == 0
