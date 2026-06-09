"""
Main agent orchestration loop.

Demonstrates:
  1. Policy check on incoming request
  2. Tool selection and registry validation
  3. Approval gate enforcement
  4. Structured audit logging at every step
  5. Depth limit to prevent runaway loops
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from harness.audit_log import init_audit_db, log_event
from harness.approval_gate import check_approval
from harness.models import (
    AgentTurn,
    ApprovalStatus,
    AuditEvent,
    ToolCall,
)
from harness.policy_engine import is_blocked, load_rules
from harness.tool_registry import get_tool, is_registered, load_registry

logger = logging.getLogger(__name__)
MAX_DEPTH = int(os.getenv("MAX_TOOL_DEPTH", "10"))


class AgentOrchestrator:
    """
    Minimal agentic loop demonstrating the full control surface:
    policy -> registry -> approval -> execute -> audit.
    """

    def __init__(self):
        init_audit_db()
        load_registry()
        load_rules()
        self.trace_id = str(uuid.uuid4())
        self._tool_call_depth = 0

    def new_trace(self) -> str:
        self.trace_id = str(uuid.uuid4())
        self._tool_call_depth = 0
        return self.trace_id

    def process_request(
        self,
        user_input: str,
        requested_tools: Optional[List[Dict[str, Any]]] = None,
        turn_index: int = 0,
    ) -> AgentTurn:
        trace_id = self.trace_id

        blocked, policy_eval = is_blocked(user_input, trace_id)
        log_event(AuditEvent(
            trace_id=trace_id,
            event_type="policy_eval",
            actor="policy_engine",
            details=policy_eval.model_dump(mode="json"),
            outcome="blocked" if blocked else "allowed",
        ))

        if blocked:
            logger.warning("Request blocked by policy: %s", policy_eval.reason)
            turn = AgentTurn(
                trace_id=trace_id,
                turn_index=turn_index,
                user_input=user_input,
                model_response=f"[BLOCKED] Request denied by policy: {policy_eval.reason}",
                policy_decision=policy_eval.reason,
            )
            self._log_turn(turn)
            return turn

        tool_calls: List[ToolCall] = []
        response_parts: List[str] = []

        for tool_req in (requested_tools or []):
            tool_name = tool_req.get("tool_name", "")
            parameters = tool_req.get("parameters", {})
            tc, result = self._execute_tool(tool_name, parameters, trace_id)
            tool_calls.append(tc)
            response_parts.append(f"[{tool_name}] -> {result}")

        model_response = "\n".join(response_parts) if response_parts else "[No tools called]"

        turn = AgentTurn(
            trace_id=trace_id,
            turn_index=turn_index,
            user_input=user_input,
            model_response=model_response,
            tool_calls=tool_calls,
            policy_decision="allowed",
        )
        self._log_turn(turn)
        return turn

    def _execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        trace_id: str,
    ) -> Tuple[ToolCall, str]:
        if self._tool_call_depth >= MAX_DEPTH:
            msg = f"MAX_TOOL_DEPTH ({MAX_DEPTH}) exceeded — aborting"
            logger.error(msg)
            tc = ToolCall(
                trace_id=trace_id, tool_name=tool_name, parameters=parameters,
                approval_status=ApprovalStatus.DENIED, error=msg,
            )
            return tc, f"ERROR: {msg}"

        self._tool_call_depth += 1

        if not is_registered(tool_name):
            msg = f"Tool '{tool_name}' is not in the registry — blocked"
            logger.error(msg)
            log_event(AuditEvent(
                trace_id=trace_id, event_type="tool_call", actor="orchestrator",
                details={"tool": tool_name, "parameters": parameters, "reason": msg},
                outcome="blocked",
            ))
            tc = ToolCall(
                trace_id=trace_id, tool_name=tool_name, parameters=parameters,
                approval_status=ApprovalStatus.DENIED, error=msg,
            )
            return tc, f"BLOCKED: {msg}"

        tool_def = get_tool(tool_name)
        tc = ToolCall(trace_id=trace_id, tool_name=tool_name, parameters=parameters)

        approval_status = check_approval(tc, tool_def, trace_id)
        tc.approval_status = approval_status

        if approval_status in (ApprovalStatus.DENIED, ApprovalStatus.PENDING):
            msg = f"Tool '{tool_name}' not approved (status={approval_status.value})"
            logger.warning(msg)
            tc.error = msg
            return tc, f"PENDING_APPROVAL: {msg}"

        try:
            result = self._dispatch(tool_name, parameters)
            tc.completed_at = datetime.utcnow()
            tc.outcome = str(result)
            log_event(AuditEvent(
                trace_id=trace_id, event_type="tool_call", actor=tool_name,
                details={"tool": tool_name, "parameters": parameters, "result": str(result)[:500]},
                outcome="success",
            ))
            return tc, str(result)
        except Exception as exc:
            tc.error = str(exc)
            log_event(AuditEvent(
                trace_id=trace_id, event_type="error", actor=tool_name,
                details={"tool": tool_name, "error": str(exc)},
                outcome="failure",
            ))
            return tc, f"ERROR: {exc}"

    def _dispatch(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        import importlib
        tool_map = {
            "crm_lookup": ("tools.mock_crm_tool", "lookup_customer"),
            "send_email": ("tools.mock_email_tool", "send_email"),
            "db_read": ("tools.mock_db_tool", "read_record"),
            "db_write": ("tools.mock_db_tool", "write_record"),
            "http_get": ("tools.safe_http_client", "safe_get"),
        }
        if tool_name not in tool_map:
            raise ValueError(f"No dispatch mapping for tool '{tool_name}'")
        module_path, func_name = tool_map[tool_name]
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        return func(**parameters)

    def _log_turn(self, turn: AgentTurn) -> None:
        log_event(AuditEvent(
            trace_id=turn.trace_id,
            event_type="agent_turn",
            actor="orchestrator",
            details={
                "turn_id": turn.turn_id,
                "turn_index": turn.turn_index,
                "user_input": turn.user_input[:200],
                "model_response": turn.model_response[:500],
                "tool_call_count": len(turn.tool_calls),
                "policy_decision": turn.policy_decision,
            },
            outcome="success",
        ))
