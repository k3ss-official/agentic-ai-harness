"""Agentic AI Harness — FastAPI entrypoint."""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from harness.approval_gate import decide_approval, get_pending_approvals
from harness.audit_log import get_recent_events, get_trace, init_audit_db
from harness.models import ApprovalDecision
from harness.orchestrator import AgentOrchestrator
from harness.tool_registry import list_tools, load_registry
from harness.policy_engine import load_rules

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agentic AI Harness",
    description="Enterprise-grade governance and control wrapper for agentic AI workflows.",
    version="1.0.0",
)


class RunRequest(BaseModel):
    user_input: str
    requested_tools: Optional[List[Dict[str, Any]]] = None
    trace_id: Optional[str] = None


@app.on_event("startup")
def startup():
    init_audit_db()
    load_registry()
    load_rules()
    logger.info("Agentic AI Harness started.")


@app.get("/health")
def health():
    return {"status": "ok", "service": "agentic-ai-harness"}


@app.post("/run")
def run(req: RunRequest):
    orchestrator = AgentOrchestrator()
    if req.trace_id:
        orchestrator.trace_id = req.trace_id
    else:
        req.trace_id = orchestrator.new_trace()
    turn = orchestrator.process_request(
        user_input=req.user_input,
        requested_tools=req.requested_tools or [],
    )
    return {
        "trace_id": orchestrator.trace_id,
        "turn": turn.model_dump(mode="json"),
    }


@app.get("/tools")
def get_tools():
    tools = list_tools()
    return {"tools": [t.model_dump() for t in tools.values()]}


@app.get("/approvals/pending")
def pending_approvals():
    return {"pending": get_pending_approvals()}


@app.post("/approvals/{request_id}/decide")
def make_approval_decision(request_id: str, decision: ApprovalDecision):
    decision.request_id = request_id
    decide_approval(decision)
    return {"status": "ok", "request_id": request_id, "approved": decision.approved}


@app.get("/audit/trace/{trace_id}")
def audit_trace(trace_id: str):
    events = get_trace(trace_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found.")
    return {"trace_id": trace_id, "events": events}


@app.get("/audit/recent")
def audit_recent(limit: int = 50, event_type: Optional[str] = None):
    return {"events": get_recent_events(limit=limit, event_type=event_type)}
