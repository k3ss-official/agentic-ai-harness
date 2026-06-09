# Control Catalogue — Agentic AI Harness

**Version**: 1.0  
**Date**: 2026-06-01  
**Owner**: Security Engineering, Acme Corp

This catalogue documents all security and governance controls implemented in or supported by the Agentic AI Harness. Each control references the OWASP LLM Top 10 threats it addresses.

---

## CTL-001: Tool Registry
**Category**: Tool Governance  
**Description**: All tools the agent is permitted to invoke must be declared in `tools/registry.yaml`. Any tool call referencing an undeclared tool name is rejected unconditionally before any other check is applied.  
**Implementation**: `harness/tool_registry.py` `is_registered()` check at the start of `_execute_tool()` in the orchestrator.  
**Test**: `tests/test_tool_registry.py::TestIsRegistered::test_returns_false_for_unknown_tool`. Attempt to call `sudo_exec` — expect BLOCKED outcome in audit log.  
**Related Threats**: LLM07, LLM08

---

## CTL-002: Side-Effect Classification
**Category**: Tool Governance  
**Description**: Every tool is classified into one of four side-effect classes: `read`, `write`, `external`, `financial`. The class determines the minimum approval level required for execution.  
**Implementation**: `side_effect_class` field in each `ToolDefinition` in `tools/registry.yaml`. Validated by Pydantic on registry load.  
**Test**: Verify that `crm_lookup` has `side_effect_class: read` and `db_write` has `side_effect_class: write` in the registry YAML.  
**Related Threats**: LLM07, LLM08

---

## CTL-003: HITL Approval Gate
**Category**: HITL  
**Description**: Tools classified as `write` or `external` require explicit human approval before execution. Approval is requested via the approval gate and recorded with a trace ID. Execution blocks until an `approved` decision is received.  
**Implementation**: `harness/approval_gate.py` `check_approval()`. Approval decisions via `POST /approvals/{request_id}/decide`.  
**Test**: `tests/test_approval_gate.py::TestWriteToolsPending`. Call `db_write` — expect `ApprovalStatus.PENDING`.  
**Related Threats**: LLM08

---

## CTL-004: Financial Tool Hard Block
**Category**: Tool Governance  
**Description**: Tools with `side_effect_class: financial` are permanently blocked regardless of approval. The `payment_transfer` tool is in the registry with `required_approval_level: blocked` for visibility, but cannot be executed.  
**Implementation**: `ApprovalLevel.BLOCKED` check in `check_approval()` returns `ApprovalStatus.DENIED` immediately.  
**Test**: `tests/test_approval_gate.py::TestBlockedTool`. Call `payment_transfer` — expect `DENIED`.  
**Related Threats**: LLM08

---

## CTL-005: Policy Engine — Prompt Injection Detection
**Category**: Tool Governance  
**Description**: Every user request is evaluated against a priority-ordered set of regex rules before any tool is called. Rules `INJ-001` and `INJ-002` block known prompt injection and instruction override patterns.  
**Implementation**: `harness/policy_engine.py` `is_blocked()`. Rules loaded from `policy/rules.yaml`.  
**Test**: `tests/test_policy_engine.py::TestBlockingPatterns::test_prompt_injection_blocked`.  
**Related Threats**: LLM01

---

## CTL-006: Policy Engine — Financial Keyword Block
**Category**: Tool Governance  
**Description**: Rule `FIN-001` blocks any request containing financial transaction keywords at the input layer, before the tool registry is consulted.  
**Implementation**: `policy/rules.yaml` rule `FIN-001`, priority 5.  
**Test**: `tests/test_policy_engine.py::TestBlockingPatterns::test_financial_transfer_blocked`.  
**Related Threats**: LLM08

---

## CTL-007: Policy Engine — Credential Exfiltration Block
**Category**: Identity  
**Description**: Rule `CRED-001` blocks requests that attempt to elicit credentials, passwords, API keys, tokens, or secrets from the system.  
**Implementation**: `policy/rules.yaml` rule `CRED-001`, priority 5.  
**Test**: `tests/test_policy_engine.py::TestBlockingPatterns::test_credential_exfiltration_blocked`.  
**Related Threats**: LLM06, LLM10

---

## CTL-008: Policy Engine — Bulk Data Deletion Block
**Category**: Tool Governance  
**Description**: Rule `DATA-001` blocks any request containing bulk deletion patterns (`DELETE ALL`, `TRUNCATE`, `DROP TABLE/DATABASE`). These operations are never permitted via the agent regardless of tool approval.  
**Implementation**: `policy/rules.yaml` rule `DATA-001`, priority 5.  
**Test**: `tests/test_policy_engine.py::TestBlockingPatterns::test_bulk_delete_blocked`.  
**Related Threats**: LLM08

---

## CTL-009: Policy Rule Priority Ordering
**Category**: Tool Governance  
**Description**: Policy rules are evaluated in ascending priority order; the first match wins. Safety-critical rules (injection, financial, credential) have priority 1–5; informational rules have priority 10–20; the default allow rule has priority 999. This prevents a lower-priority allow rule from overriding a higher-priority block.  
**Implementation**: `rules.sort(key=lambda x: x.priority)` in `load_rules()`.  
**Test**: `tests/test_policy_engine.py::TestPriorityOrdering`.  
**Related Threats**: LLM01

---

## CTL-010: Immutable Audit Log
**Category**: Observability  
**Description**: Every action — policy evaluation, tool call, approval request, approval decision, agent turn, error — is written to an append-only SQLite audit log. No UPDATE or DELETE operations are issued against the audit table by application code.  
**Implementation**: `harness/audit_log.py`. Schema in `init_audit_db()`. INSERT-only `log_event()`.  
**Test**: `tests/test_audit_log.py::TestEventInsertion`.  
**Related Threats**: LLM08

---

## CTL-011: Trace ID Correlation
**Category**: Observability  
**Description**: Every agent workflow is assigned a UUID trace ID. All events within a workflow share this trace ID, enabling full reconstruction of any interaction sequence for forensic investigation.  
**Implementation**: `AgentOrchestrator.new_trace()` generates a UUID. All `AuditEvent` instances receive the trace ID.  
**Test**: `tests/test_audit_log.py::TestGetTrace::test_get_trace_returns_events_in_order`.  
**Related Threats**: LLM08

---

## CTL-012: Scoped Credential Keys
**Category**: Identity  
**Description**: Each tool specifies a `scoped_credential_key` — the name of the environment variable for that tool's unique credential. Tools cannot share credentials. This enforces least privilege at the tool level.  
**Implementation**: `scoped_credential_key` field in `ToolDefinition`. Documented in `tools/registry.yaml`.  
**Test**: Verify that `crm_lookup` and `db_write` have distinct `scoped_credential_key` values. Verify `payment_transfer` has `null`.  
**Related Threats**: LLM06, LLM07

---

## CTL-013: HTTP Domain Allowlist
**Category**: Tool Governance  
**Description**: The `http_get` tool enforces a static allowlist of permitted domains. Any request to a domain not on the list raises a `PermissionError` and is blocked before the HTTP request is made, preventing SSRF.  
**Implementation**: `tools/safe_http_client.py` `ALLOWED_DOMAINS` set checked before `httpx.get()`.  
**Test**: Call `safe_get` with `url="https://evil.com/exfiltrate"` — expect `PermissionError`.  
**Related Threats**: LLM07, LLM02

---

## CTL-014: Maximum Tool Call Depth
**Category**: Tool Governance  
**Description**: A per-orchestrator-instance counter tracks tool call depth. When `MAX_TOOL_DEPTH` is reached, further tool calls are rejected with an error logged to the audit trail. This prevents infinite recursion and resource exhaustion.  
**Implementation**: `self._tool_call_depth` counter in `AgentOrchestrator`. Configurable via `MAX_TOOL_DEPTH` env var (default: 10).  
**Test**: Instantiate orchestrator, call `_execute_tool` eleven times on a registered read tool, verify the 11th returns an error.  
**Related Threats**: LLM04

---

## CTL-015: Model Registry
**Category**: Supplier Risk  
**Description**: All LLM models used in agent workflows must be declared in `policy/model-registry.yaml` with their approved use cases, maximum data classification level, and PII permissions. Unapproved models cannot be used.  
**Implementation**: `policy/model-registry.yaml`. Enforced at the operator/deployment level; runtime enforcement would require model ID extraction from LLM API calls.  
**Test**: Review model registry to confirm all deployed model IDs are present with CISO approval and review dates.  
**Related Threats**: LLM03, LLM05

---

## CTL-016: Dry-Run Mode
**Category**: Evaluation  
**Description**: When `DRY_RUN=true`, all write and external tool calls are auto-approved without execution. This allows testing of policy and audit coverage without triggering side effects.  
**Implementation**: `DRY_RUN` flag in `harness/approval_gate.py`.  
**Test**: `tests/test_approval_gate.py::TestDryRunMode::test_dry_run_auto_approves_writes`.  
**Related Threats**: LLM08

---

## CTL-017: Eval Suite with CI Gate
**Category**: Evaluation  
**Description**: `evals/run_evals.py` runs a suite of injection and policy tests. The runner exits with code 1 on any failure. This gate should be enforced in the CI pipeline to catch policy regressions.  
**Implementation**: `evals/run_evals.py`. Test cases in `evals/injection_tests.yaml` and `evals/policy_eval.yaml`.  
**Test**: Run `python evals/run_evals.py` — all tests must pass. Introduce a deliberate policy regression and verify exit code 1.  
**Related Threats**: LLM01, LLM08

---

## CTL-018: CLI Trace Viewer
**Category**: Observability  
**Description**: `observability/trace_viewer.py` provides a CLI interface to query the audit log by trace ID, list recent events, or enumerate all traces. Colour-coded output highlights event types and outcomes for rapid incident triage.  
**Implementation**: `observability/trace_viewer.py`. Reads directly from the SQLite audit DB.  
**Test**: Run a `/run` request, capture the trace ID, run `python observability/trace_viewer.py --trace-id <id>` and verify all expected events appear.  
**Related Threats**: LLM08

---

## CTL-019: DPIA and Lawful Basis Documentation
**Category**: Governance  
**Description**: A Data Protection Impact Assessment (`risk/dpia-summary.md`) documents the categories of personal data processed, the lawful basis, risk assessment, mitigations, and DPO sign-off, satisfying GDPR Article 35 obligations.  
**Implementation**: `risk/dpia-summary.md`. Reviewed annually and before material changes to data processing scope.  
**Test**: DPIA must be present, dated, and signed off by the DPO. Review date must be in the future.  
**Related Threats**: LLM06

---

## CTL-020: Supplier Security Register
**Category**: Supplier Risk  
**Description**: `risk/supplier-register.csv` maintains a record of all external AI and infrastructure suppliers, their data classification limits, DPA status, ISO 27001 certification, last security review date, and risk tier.  
**Implementation**: `risk/supplier-register.csv`. Reviewed quarterly.  
**Test**: All suppliers used in production must have a current security review (within 12 months), a DPA, and documented data classification limits.  
**Related Threats**: LLM05

---

## CTL-021: Audit Log Input Truncation
**Category**: Observability  
**Description**: User input and tool results are truncated to 500 characters before being written to the audit log. This limits the amount of potentially sensitive content retained in the audit trail while preserving enough context for forensic use.  
**Implementation**: `input_text=text[:500]` in `evaluate()`. `"result": str(result)[:500]` in `_execute_tool()`. `user_input: turn.user_input[:200]` in `_log_turn()`.  
**Test**: Submit a user input longer than 500 characters; verify the `input_text` field in the audit event is truncated at 500 characters.  
**Related Threats**: LLM06

---

## CTL-022: Pydantic Schema Validation
**Category**: Tool Governance  
**Description**: All data crossing API and internal module boundaries is validated by Pydantic v2 models. Invalid data is rejected with a structured error response before reaching business logic.  
**Implementation**: `harness/models.py`. FastAPI uses these models for request and response validation automatically.  
**Test**: POST `/run` with missing `user_input` field — expect HTTP 422 Unprocessable Entity.  
**Related Threats**: LLM07
