"""
HITL Approval Gate.

Two modes:
  1. In-process (demo): auto-approve reads, prompt human for writes.
  2. FastAPI webhook: POST /approvals/{request_id}/decide for integration with
     external HITL systems (Slack, PagerDuty, custom dashboards).

In DRY_RUN mode, all write/external actions are logged as approved without
executing the actual tool — for testing policy and audit coverage.
"""
from __future__ import annotations
import logging
import os
from typing import Dict

from harness.models import (
    ApprovalDecision,
    ApprovalLevel,
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    ToolCall,
)
from harness.audit_log import log_event

logger = logging.getLogger(__name__)
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

_pending: Dict[str, ApprovalRequest] = {}
_decisions: Dict[str, ApprovalDecision] = {}


def request_approval(
    tool_call: ToolCall,
    tool_definition,
    trace_id: str,
    reason: str = "",
) -> ApprovalRequest:
    req = ApprovalRequest(
        trace_id=trace_id,
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        parameters=tool_call.parameters,
        reason=reason or (
            f"Tool '{tool_call.tool_name}' requires approval "
            f"(side_effect={tool_definition.side_effect_class})"
        ),
        side_effect_class=tool_definition.side_effect_class,
    )
    _pending[req.request_id] = req
    log_event(AuditEvent(
        trace_id=trace_id,
        event_type="approval_request",
        actor="approval_gate",
        details=req.model_dump(mode="json"),
        outcome="pending",
    ))
    logger.info("Approval requested: request_id=%s tool=%s", req.request_id, tool_call.tool_name)
    return req


def decide_approval(decision: ApprovalDecision) -> None:
    _decisions[decision.request_id] = decision
    req = _pending.pop(decision.request_id, None)
    outcome = "approved" if decision.approved else "denied"
    log_event(AuditEvent(
        trace_id=req.trace_id if req else "unknown",
        event_type="approval_decision",
        actor=decision.decided_by,
        details=decision.model_dump(mode="json"),
        outcome=outcome,
    ))
    logger.info(
        "Approval decision: request_id=%s approved=%s by=%s",
        decision.request_id, decision.approved, decision.decided_by
    )


def check_approval(
    tool_call: ToolCall,
    tool_definition,
    trace_id: str,
) -> ApprovalStatus:
    """
    Determine whether this tool call can proceed.

    - NONE approval level -> AUTO_APPROVED (read-only tools)
    - DRY_RUN -> AUTO_APPROVED with warning
    - BLOCKED -> DENIED
    - Otherwise -> PENDING (requires human decision via decide_approval)
    """
    level = tool_definition.required_approval_level

    if level == ApprovalLevel.NONE:
        return ApprovalStatus.AUTO_APPROVED

    if level == ApprovalLevel.BLOCKED:
        log_event(AuditEvent(
            trace_id=trace_id,
            event_type="tool_call",
            actor="approval_gate",
            details={"tool": tool_call.tool_name, "reason": "Tool is BLOCKED in registry"},
            outcome="blocked",
        ))
        return ApprovalStatus.DENIED

    if DRY_RUN:
        logger.warning("DRY_RUN: would require approval for %s — auto-approving", tool_call.tool_name)
        return ApprovalStatus.AUTO_APPROVED

    req = request_approval(tool_call, tool_definition, trace_id)
    logger.warning(
        "HITL REQUIRED: Tool '%s' is pending approval. POST /approvals/%s/decide to proceed.",
        tool_call.tool_name, req.request_id,
    )
    return ApprovalStatus.PENDING


def get_pending_approvals() -> list:
    return [r.model_dump(mode="json") for r in _pending.values()]
