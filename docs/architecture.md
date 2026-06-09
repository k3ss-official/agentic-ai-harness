# Architecture — Agentic AI Harness

## The Problem: Why Unguarded LLM Tool Use Is Dangerous

Modern large language models can generate tool calls in addition to text. When an orchestration framework executes those tool calls automatically, the LLM gains the ability to take real-world actions: querying databases, sending emails, calling APIs, modifying records. This is the promise of agentic AI — and it is also a significant source of enterprise risk.

Without a governance layer, an autonomous agent can:

1. **Exfiltrate data** by calling read tools beyond the scope of the user's request, then routing output to an external endpoint.
2. **Be manipulated by prompt injection** — malicious instructions embedded in data the agent reads (emails, documents, CRM notes) that redirect the agent's behaviour.
3. **Take irreversible actions** without human awareness — sending emails, modifying database records, or initiating API calls with real-world consequences.
4. **Leave no audit trail**, making incident investigation impossible and regulatory compliance unachievable.
5. **Escalate privileges** by calling tools that were not intended to be accessible from the specific workflow context.
6. **Loop indefinitely** if a tool's output triggers further tool calls, consuming resources and potentially amplifying side effects.

The Acme AI Agent Harness is designed to eliminate each of these failure modes through a layered control architecture.

---

## Component Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│  TRUST BOUNDARY: External / End-user                              │
│                                                                    │
│   User / Calling System                                           │
│        │  POST /run  {user_input, requested_tools}                │
└───────────────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────┐
│  TRUST BOUNDARY: Internal Service Perimeter                       │
│                                                                    │
│  ┌─────────────────────────────┐                               │
│  │  FastAPI (harness/main.py)    │                               │
│  │  - Auth middleware (future)   │                               │
│  │  - Request validation         │                               │
│  │  - Approval webhook endpoints │                               │
│  │  - Audit query endpoints      │                               │
│  └──────────────┬──────────────┘                               │
│                       │                                           │
│                       ▼                                           │
│  ┌─────────────────────────────┐                               │
│  │  AgentOrchestrator           │                               │
│  │  (harness/orchestrator.py)   │                               │
│  └───┬────────┬────────┬──────┘                               │
│       │        │        │                                        │
│       ▼        ▼        ▼                                        │
│  ┌────────┐ ┌───────┐ ┌───────────┐                          │
│  │ Policy  │ │ Tool   │ │ Approval  │                          │
│  │ Engine  │ │Registry│ │ Gate      │                          │
│  │(rules   │ │(YAML   │ │(HITL      │                          │
│  │ .yaml)  │ │ def.)  │ │ webhook)  │                          │
│  └────────┘ └───────┘ └─────┬─────┘                          │
│                               │                                   │
│                               ▼                                   │
│  ┌────────────────────────┐                                  │
│  │  Tool Implementations        │                                  │
│  │  mock_crm_tool               │                                  │
│  │  mock_db_tool                │                                  │
│  │  mock_email_tool             │                                  │
│  │  safe_http_client            │                                  │
│  └────────────┬───────────┘                                  │
│               │  (all tool calls logged)                           │
│               ▼                                                   │
│  ┌────────────────────────┐                                  │
│  │  Audit Log (SQLite)          │                                  │
│  │  data/audit.db               │                                  │
│  └────────────────────────┘                                  │
│                                                                    │
└───────────────────────────────────────────────────────────────────┘
```

---

## Control Surface Description

### Policy Engine
The policy engine (`harness/policy_engine.py`) is the first check applied to every user request. It loads rules from `policy/rules.yaml` and evaluates the input text using regex pattern matching with priority ordering. Rules cover prompt injection signatures, financial action keywords, credential exfiltration patterns, and bulk data operations. The first matching rule wins. This approach is intentionally conservative: a false positive (blocking a legitimate request) is far less harmful than a false negative (allowing a malicious request to proceed). The default rule at the end of the priority list is `allow`, ensuring normal requests are not impeded.

### Tool Registry
The tool registry (`harness/tool_registry.py`) maintains a YAML-backed dictionary of all tools the agent is permitted to invoke. Every tool call passes through a registry check before execution. If the tool name is not in the registry, it is blocked unconditionally. Each tool definition includes its side-effect class, the required approval level, which credential it uses, and the set of permitted parameter names. This makes the attack surface explicit and auditable: an operator can enumerate exactly what the agent can do by reading `tools/registry.yaml`.

### Approval Gate
The approval gate (`harness/approval_gate.py`) enforces the HITL requirement. It maps approval levels to outcomes: tools with `none` approval level are auto-approved (read-only tools), `blocked` tools are always denied, and `sync`/`async` tools must enter the pending queue. In production, pending approvals would be pushed to an external HITL system (Slack, PagerDuty, or a custom dashboard) and execution would block until a decision arrives via the `POST /approvals/{request_id}/decide` webhook.

### Audit Log
The audit log (`harness/audit_log.py`) records every significant event to a SQLite database with indexed trace IDs, event types, and timestamps. The schema is append-only by convention (no `UPDATE` or `DELETE` operations). Every policy evaluation, tool call, approval request, approval decision, agent turn, and error is logged with a structured JSON details field. The trace viewer (`observability/trace_viewer.py`) provides CLI access to the audit trail.

---

## Trust Boundary Analysis

The harness defines three explicit trust boundaries:

1. **External boundary (User / Calling System)**: Inputs from this boundary are fully untrusted. Every request is subjected to policy evaluation before any action is taken. Malicious inputs including prompt injection attempts are caught at this layer.

2. **Internal Service Perimeter**: The FastAPI process, orchestrator, policy engine, tool registry, approval gate, and audit log operate within this boundary. Credentials for internal tools are accessible here. The principal threat within this boundary is a compromised tool implementation or a supply chain attack on a Python dependency.

3. **External Tool Boundary**: When an approved external HTTP call is made, the response crosses back into the internal perimeter. The response must not be trusted — it may contain injected instructions. In a production deployment, responses from external tools would be sanitised before being incorporated into LLM context.

---

## Credential Scoping Design

Each tool in the registry specifies a `scoped_credential_key` — the name of the environment variable that holds that tool's credential. This design enforces least privilege at the tool level: the CRM read tool uses `CRM_READ_TOKEN`, the database write tool uses `DB_WRITE_TOKEN`, and so on. No tool shares credentials with another. In production, these credentials would be retrieved from a secrets manager (e.g., HashiCorp Vault) at runtime and injected into the tool's execution context, rather than being held as long-lived environment variables.

The `payment_transfer` tool has `scoped_credential_key: null` and `required_approval_level: blocked`, which means it is registered for audit visibility but can never be executed and never has credentials loaded.

---

## Audit Trail Design

The audit trail is designed for forensic usefulness, not just compliance checkbox ticking. Key design decisions:

- **Immutable by convention**: The audit DB uses `INSERT` only. Application code contains no `UPDATE` or `DELETE` against the audit table. In production, database-level permissions would enforce this.
- **Trace IDs**: Every request generates a UUID trace ID. All events within a single agent workflow share this trace ID, making it possible to reconstruct the complete history of any interaction in sequence.
- **Structured details**: The `details` JSON field contains event-specific structured data (tool name, parameters, result, policy rule matched) enabling programmatic analysis.
- **Indexed for query performance**: Indexes on `trace_id`, `event_type`, and `timestamp` allow efficient filtering for the trace viewer and audit API endpoints.
- **Truncation**: User input and tool results are truncated to 500 characters in the audit log to limit the amount of potentially sensitive data retained. Full data is available in application logs at a higher classification level.
