# Data Protection Impact Assessment (DPIA) — Summary

**Document reference**: DPIA-2026-AI-HARNESS-001
**System name**: Acme AI Agent Harness
**Data Controller**: Acme Corp Ltd, 1 Technology Park, London EC1A 1BB
**Data Protection Officer**: dpo@acme-corp.example.com
**Assessment date**: 2026-06-01
**Next review date**: 2027-06-01
**Status**: Approved by DPO

---

## 1. Purpose and Context

The Acme AI Agent Harness is an internal system that enables autonomous AI-driven workflows across Acme Corp's business operations. The harness acts as a governance and control wrapper around large language model (LLM) APIs, allowing employees and internal systems to submit natural-language requests that may result in queries to internal databases, CRM systems, and communication platforms.

The primary business purposes are:
- Accelerating internal data lookup tasks (customer records, order status, user data)
- Automating routine communications (email drafts requiring human approval before send)
- Enabling exploratory data queries through a natural language interface

The system is **not** intended for autonomous financial transactions, health data processing, or any decision-making that produces legal or similarly significant effects on individuals without human review.

---

## 2. Categories of Personal Data Processed

| Data Category | Examples | Data Subjects | Sensitivity |
|---|---|---|---|
| Customer contact data | Name, email address, phone number | Customers | Standard personal data |
| Customer commercial data | Contract value, plan tier, account status | Customers | Commercially sensitive |
| Employee data | Name, role, email (for internal lookups) | Employees | Standard personal data |
| Communication content | Email subject and body (draft, pre-approval) | Customers, third parties | Potentially sensitive |
| Audit trail metadata | User ID, query text, timestamps | Internal users | Low sensitivity |

The system does **not** process special category data (health, biometric, financial account numbers, political opinions, or criminal records). Processing of any special category data is explicitly blocked by the tool registry and policy engine.

---

## 3. Lawful Basis for Processing

**Primary basis**: Legitimate interests (Article 6(1)(f) GDPR)

Acme Corp has a legitimate interest in processing customer and employee data to deliver its contracted services efficiently and to maintain accurate business records. The AI harness processes data that employees would otherwise access directly through CRM and database interfaces. The harness does not expand the scope of data access; it provides a more efficient interface to existing, authorised data sources.

**Legitimate Interests Assessment (LIA) summary**: The processing is necessary for the legitimate purpose of operational efficiency. The impact on data subjects is minimal because the harness does not make automated decisions with significant effects, all write actions require human approval, and the data accessed is already accessible to authorised employees by other means. The interests of data subjects do not override Acme Corp's legitimate interests given these safeguards.

**Where consent may be required**: If the harness is used to draft communications to individuals who have opted out of direct marketing, those communications must not be sent without verifying consent status. This check is the responsibility of the approving human at the approval gate.

---

## 4. Data Flows

1. **User query** entered into the harness API (internal network only; no public endpoint)
2. **Policy engine** evaluates query text — query text is stored in the audit log (truncated to 500 characters)
3. **Tool calls** are dispatched to internal systems (CRM, DB); data returned is used to construct a response and is stored in the audit log (truncated to 500 characters)
4. **LLM API call** (where applicable): query context and retrieved data sent to approved external LLM provider (OpenAI or Anthropic) for summarisation or reasoning. **Only INTERNAL-classified data may be sent to external providers.** PII must be redacted before external LLM API calls.
5. **Audit log** retains event records in SQLite. Retention period: 12 months, then secure deletion.
6. **Approval requests** containing tool parameters (which may include personal data) are stored in-memory during the approval workflow and then persisted to the audit log.

**Data transfers outside the UK/EEA**: OpenAI and Anthropic process data in the United States. Both suppliers have executed Standard Contractual Clauses (SCCs) under Article 46 GDPR. Transfer impact assessments have been completed.

---

## 5. Risk Assessment

| Risk | Likelihood | Impact | Inherent Risk | Mitigations | Residual Risk |
|---|---|---|---|---|---|
| PII sent to external LLM provider | Medium | High | High | Data classification enforcement; model registry; policy rules blocking bulk PII export | Medium |
| Audit log retains sensitive query content | Medium | Medium | Medium | Truncation to 500 chars; DB access controls; 12-month retention limit | Low |
| Unsanctioned write action modifying personal data | Low | High | Medium | Sync approval gate; HITL requirement for all write tools | Low |
| Credential exfiltration via crafted query | Low | High | Medium | CRED-001 policy rule; no credentials in prompt context | Low |
| Agentic loop processing data beyond scope of request | Low | Medium | Low | MAX_TOOL_DEPTH limit; policy engine scope restriction | Very Low |

Overall residual risk assessment: **LOW**. The harness does not expand data access rights; it wraps existing authorised access with additional controls. The principal residual risk is PII leakage to external LLM providers, which is mitigated by the model registry classification controls and the data classification policy enforced at the operator level.

---

## 6. Measures to Address Risk (Technical and Organisational)

**Technical measures:**
- Policy engine with regex and classification-based rules blocks queries containing known PII exfiltration patterns
- Tool registry enforces data classification at the tool level (read-only tools cannot modify data)
- Approval gate requires human sign-off for all write and external actions
- Audit log truncation prevents excessive personal data retention in logs
- HTTP allowlist prevents data exfiltration to unapproved external endpoints
- MAX_TOOL_DEPTH prevents runaway processing loops

**Organisational measures:**
- Data classification policy defines which data may be sent to which model tier
- Model registry documents approved models and their data classification limits
- HITL approval process ensures a human reviews all write actions before execution
- Quarterly access reviews for tool credentials
- Annual DPIA review
- Incident response playbooks cover PII leakage scenarios
- Staff training on AI system appropriate use

---

## 7. Consultation

The following stakeholders were consulted during this assessment:
- Data Protection Officer: participated in risk assessment and approved mitigations
- CISO: reviewed technical controls and supplier security assessments
- Legal Counsel: confirmed legitimate interests basis and reviewed SCCs with US providers
- Platform Engineering Lead: confirmed technical implementation of stated controls
- Compliance Manager: cross-referenced against EU AI Act Article 9 risk management requirements

---

## 8. DPO Sign-Off

> This DPIA has been reviewed and the described processing activity is assessed as lawful under Article 6(1)(f) GDPR. The identified risks are adequately mitigated by the technical and organisational measures described. The processing does not require prior consultation with the supervisory authority under Article 36 GDPR. This assessment must be reviewed before any material change to the system's data processing scope, before onboarding new LLM providers, and on an annual basis.
>
> **DPO Sign-off**: J. Williams, Data Protection Officer, Acme Corp Ltd
> **Date**: 2026-06-01
> **Next review**: 2027-06-01
