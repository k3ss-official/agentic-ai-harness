"""Pydantic schemas for the agentic AI harness."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


class SideEffectClass(str, Enum):
    READ = "read"           # No side effects
    WRITE = "write"         # Modifies state — requires approval
    EXTERNAL = "external"   # Calls external APIs — requires approval
    FINANCIAL = "financial" # Money movement — always requires approval


class ApprovalLevel(str, Enum):
    NONE = "none"       # No approval required
    ASYNC = "async"     # Async approval (log and continue if timeout)
    SYNC = "sync"       # Must wait for explicit approval
    BLOCKED = "blocked" # Never allowed


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"
    AUTO_APPROVED = "auto_approved"


class PolicyAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_APPROVAL = "require_approval"
    SANITISE = "sanitise"
    ESCALATE = "escalate"


class ToolDefinition(BaseModel):
    name: str
    description: str
    side_effect_class: SideEffectClass
    required_approval_level: ApprovalLevel
    scoped_credential_key: Optional[str] = None
    allowed_parameters: List[str] = Field(default_factory=list)
    rate_limit_per_minute: int = 60
    timeout_seconds: int = 30
    tags: List[str] = Field(default_factory=list)


class ToolCall(BaseModel):
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str
    tool_name: str
    parameters: Dict[str, Any]
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    outcome: Optional[str] = None
    error: Optional[str] = None


class AgentTurn(BaseModel):
    turn_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str
    turn_index: int
    user_input: str
    model_response: str
    tool_calls: List[ToolCall] = Field(default_factory=list)
    policy_decision: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ApprovalRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str
    call_id: str
    tool_name: str
    parameters: Dict[str, Any]
    reason: str
    side_effect_class: SideEffectClass
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    timeout_seconds: int = 300


class ApprovalDecision(BaseModel):
    request_id: str
    approved: bool
    decided_by: str = "human"
    decision_reason: str = ""
    decided_at: datetime = Field(default_factory=datetime.utcnow)


class PolicyEvaluation(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str
    input_text: str
    matched_rules: List[str]
    action: PolicyAction
    reason: str
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str
    event_type: str
    actor: str
    details: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    outcome: str = "unknown"
