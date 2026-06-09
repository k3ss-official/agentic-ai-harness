# Architectural Decision Log — Agentic AI Harness

**Document reference**: ADR-HARNESS  
**Last updated**: 2026-06-01

---

## ADR-001: SQLite for the Audit Log

**Date**: 2026-01-10  
**Status**: Accepted

### Context
The audit log must be immutable, queryable by trace ID, and available for forensic investigation. Options considered: PostgreSQL (hosted), MongoDB Atlas, AWS DynamoDB, SQLite (embedded).

### Decision
Use SQLite as the audit log storage backend for the initial implementation.

### Rationale
- **Zero operational overhead**: SQLite requires no separate database server to run, configure, or monitor. For a portfolio demonstration and for single-instance production deployments, this removes a significant operational dependency.
- **ACID guarantees**: SQLite provides full ACID transactions, which means an audit event is either written completely or not at all. There are no partial writes.
- **Queryable**: Full SQL query capability for forensic investigation, including the trace viewer's aggregate queries (`GROUP BY trace_id`).
- **Portability**: The audit DB is a single file that can be backed up with `cp`, attached as a volume in Docker, or archived to S3 for long-term retention.
- **Append-only by convention**: While SQLite supports UPDATE and DELETE, the application code only uses INSERT, enforcing immutability at the application layer.

### Consequences
- Not suitable for multi-instance (horizontally scaled) deployments. If the harness is deployed with more than one replica, the audit log must be migrated to a shared database (PostgreSQL recommended).
- File-level locking means concurrent writes from multiple threads may queue; acceptable for current request volumes.
- Production must implement file-level encryption and regular backup of the `.db` file.

### Alternatives Rejected
- **PostgreSQL**: Correct choice at scale, but adds operational overhead not justified for this implementation stage.
- **DynamoDB**: Excellent scalability, but adds AWS lock-in and operational complexity.

---

## ADR-002: First-Match Policy Rules Over Scoring

**Date**: 2026-01-15  
**Status**: Accepted

### Context
The policy engine must classify incoming requests as allow, block, require_approval, etc. Two main approaches: (1) first-match rule evaluation (each rule evaluated in priority order; first match wins), or (2) scoring/ensemble (multiple rules evaluated; final decision based on aggregate score or majority vote).

### Decision
Use first-match rule evaluation with explicit priority ordering.

### Rationale
- **Predictability**: First-match evaluation produces deterministic, auditable outcomes. Given the same input and rule set, the same rule always fires. This is critical for a security control — defenders must be able to reason about exactly which rule will match a given input.
- **Debuggability**: The audit log records `matched_rules`, making it trivial to understand why a request was blocked or allowed. With a scoring system, explaining "why was this blocked?" requires exposing the full score breakdown.
- **Fail-safe ordering**: Safety-critical rules (injection, financial, credential) have the lowest priority numbers and therefore match first. A default-allow rule at priority 999 ensures normal requests are not impeded without making it possible for a new rule to accidentally override a safety rule.
- **Operational simplicity**: Rule updates require only editing a YAML file; no retraining or threshold calibration required.

### Consequences
- Rule ordering matters — adding a new rule requires careful consideration of its priority relative to existing rules. The YAML file must be reviewed by Security Engineering before any rule changes are merged.
- A single regex-based rule with low priority could accidentally catch legitimate requests if written too broadly. The eval suite exists to detect this.

### Alternatives Rejected
- **Scoring/ensemble**: More robust against novel phrasings but non-deterministic and harder to audit. Appropriate for a complementary classifier but not as the primary enforcement mechanism.

---

## ADR-003: Hierarchical Approval Levels Over RBAC

**Date**: 2026-01-20  
**Status**: Accepted

### Context
Tools require different levels of oversight. Options: (1) Role-Based Access Control (RBAC) where specific user roles can approve specific tools, (2) hierarchical approval levels (`none` / `async` / `sync` / `blocked`) applied to tool classes rather than individual users.

### Decision
Use hierarchical approval levels defined at the tool level, not role-based access control.

### Rationale
- **Simpler to reason about**: Operators can look at any tool definition and immediately understand its approval requirements. RBAC requires understanding the role hierarchy, group memberships, and permission inheritance.
- **Class-based, not identity-based**: The control question is "what does this tool do?" (its side-effect class) not "who is calling it?". A write tool should require approval regardless of whether the caller is an admin or a standard user.
- **Extensible to RBAC**: The `ApprovalLevel` enum can be extended to include role checks without breaking existing tools. The approval gate webhook (`POST /approvals/{request_id}/decide`) already accepts a `decided_by` field that can carry role information.

### Consequences
- No user-level access control is implemented in this version. All authenticated callers of the `/run` endpoint have equal access to all registered tools, subject to approval gates. Production deployment must add API key validation and caller identity to the approval request.

### Alternatives Rejected
- **Full RBAC**: Correct at enterprise scale, but significantly increases implementation complexity and is out of scope for the initial architecture. The approval gate webhook is the integration point for a future RBAC layer.

---

## ADR-004: Synchronous Approval for Write Tools

**Date**: 2026-01-25  
**Status**: Accepted

### Context
Write and external tools require human approval. Two options: (1) sync approval (execution blocks until a human decides), or (2) async approval (execution proceeds after a timeout if no decision is made).

### Decision
Write tools (`db_write`, `send_email`) use `required_approval_level: sync`. The `http_get` tool (external read) uses `async`.

### Rationale
- **Irreversibility principle**: Write operations modify persistent state; sending an email is irreversible. Allowing these to proceed on timeout creates a situation where inaction by the approver permits an action — the opposite of the intended control. Sync approval enforces explicit human intent.
- **Async is appropriate for reads**: The `http_get` tool makes a read-only external request. If an approver does not respond in time, the worst outcome is that a read did not happen, not that state was modified. Async is therefore acceptable.
- **Operational pressure**: Sync approval creates pressure on the HITL process to be responsive. If approvers consistently fail to respond, this surfaces a process problem that should be fixed, not masked by auto-approving on timeout.

### Consequences
- Agent workflows involving write tools will block indefinitely if no approver responds. Production deployment must implement timeout handling and escalation notifications.
- The in-process demo returns `PENDING` status immediately. A production HITL system must poll or subscribe to the approval decision.

---

## ADR-005: In-Process Orchestration Over LangGraph or LlamaIndex

**Date**: 2026-02-01  
**Status**: Accepted

### Context
Several orchestration frameworks exist: LangGraph (stateful graph execution), LlamaIndex Workflows, AutoGen, CrewAI. The question is whether to build on one of these or implement a minimal in-process orchestrator.

### Decision
Implement a minimal in-process orchestrator in `harness/orchestrator.py` without adopting an external orchestration framework.

### Rationale
- **Auditability**: A purpose-built orchestrator with explicit audit logging at every step is easier to reason about and audit than a framework that abstracts execution flow. Every decision point in the orchestrator is visible in the code and the audit log.
- **Security control**: External frameworks make assumptions about execution order, retry behaviour, and state management that may conflict with the harness's control requirements. The approval gate, for example, requires the ability to block execution at a specific point and wait for an external decision — this is non-trivial to implement in a framework not designed for it.
- **Dependency surface**: Each additional framework adds dependencies, potential vulnerabilities, and a learning curve for security review. The harness deliberately minimises its dependency surface.
- **Portfolio clarity**: As a portfolio piece, a purpose-built orchestrator demonstrates understanding of the underlying mechanics, whereas using LangGraph demonstrates knowledge of a specific framework.

### Consequences
- Features that frameworks provide for free (streaming, memory, multi-agent coordination) must be implemented manually if needed.
- As workflows grow in complexity, a framework may become the correct choice. This orchestrator is designed to be replaced: the tool registry, approval gate, and audit log are all framework-agnostic.

---

## ADR-006: Extractive-First Answers Over LLM-First

**Date**: 2026-02-10  
**Status**: Accepted

### Context
For data lookup tasks (CRM, database), two approaches: (1) LLM-first — pass the query to the LLM, which generates a tool call, receives the result, and synthesises a natural language response; (2) extractive-first — execute the tool call directly and return the raw structured result to the caller.

### Decision
Use extractive-first for all data lookup operations in the current architecture. LLM synthesis is optional and applied only when explicitly requested.

### Rationale
- **Hallucination risk**: When an LLM synthesises a response from tool output, it may embellish, paraphrase incorrectly, or hallucinate fields that were not in the tool response. Returning raw tool output eliminates this risk for data lookups.
- **Provenance**: Raw tool output can be traced directly to its source (a specific database record, a specific CRM entry). LLM-synthesised output loses this provenance.
- **Overreliance**: Users are less likely to over-rely on a raw structured record than on a confident-sounding natural language summary. The format signals that this is data, not analysis.
- **Compliance**: For regulated data (customer PII, financial records), raw output with clear provenance is easier to justify to auditors than an LLM summary.

### Consequences
- The user experience for complex queries requiring synthesis is degraded — users receive structured data they must interpret themselves.
- This is appropriate for the harness's role as a governance layer. If synthesis is needed, it should be added as a clearly labelled, optional post-processing step with citation grounding.
