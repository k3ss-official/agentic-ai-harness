# Incident Playbooks — Agentic AI Harness

**Version**: 1.0  
**Date**: 2026-06-01  
**Owner**: Security Engineering, Acme Corp  
**Review cycle**: Quarterly

---

## Playbook 1: Prompt Injection Event

**Trigger**: Audit log shows a `policy_eval` event with `outcome: blocked` and `matched_rules` containing `INJ-001` or `INJ-002`. Volume of blocked injection attempts exceeds 10 per hour. Or: a request that should have been blocked was not (policy miss detected by eval regression).

**Severity**: P2 (High) for a single detected-and-blocked event. P1 (Critical) if a bypass is suspected (missed block).

**Immediate Actions (first 15 minutes)**:
1. Pull the audit trail for the suspicious trace ID: `python observability/trace_viewer.py --trace-id <id>`
2. Verify the event was blocked (`outcome: blocked`) and no tool calls followed the blocked `policy_eval` event.
3. If tool calls DID follow a blocked policy event — escalate to P1 immediately and page the on-call security engineer.
4. Alert the Security Engineering team via the incident channel.
5. If a bypass is confirmed, set `DRY_RUN=true` to halt all write/external tool execution pending investigation.

**Investigation Steps**:
1. Extract the `input_text` from the blocked `policy_eval` event details.
2. Determine the source: which user/API key submitted the request? (Check API gateway access logs)
3. Check for related events in the same trace — did the attacker make multiple attempts with slight variations?
4. Check whether any tool calls within the same session completed successfully prior to the blocked event.
5. Determine whether the injection payload came from user input directly or was embedded in tool response data (indirect injection).
6. Review the 24 hours of audit logs for the same source IP/user: `GET /audit/recent?limit=200`

**Containment**:
- If a specific user or API key is identified as the source: revoke the API key and block the user account.
- If the injection was indirect (embedded in data from a third-party source): quarantine the data source and disable the relevant tool pending review.
- Add new policy rules to `policy/rules.yaml` to catch the variant that triggered the incident.
- Run the full eval suite to verify new rules do not break legitimate use cases.

**Recovery**:
1. Re-enable write/external tools once containment is confirmed (if `DRY_RUN` was set).
2. Deploy updated `policy/rules.yaml` to production.
3. Re-run eval suite in CI to confirm 100% pass rate.

**Post-Incident Review**:
- Within 5 business days: conduct a blameless post-mortem.
- Document the injection payload, attack vector, and time to detect/contain.
- Add the new payload as a test case in `evals/injection_tests.yaml`.
- Review whether the embedding-based classifier enhancement should be prioritised.

**Owner**: Security Engineering

---

## Playbook 2: Unauthorised External Action — Tool Called Without Approval

**Trigger**: Audit log shows a `tool_call` event with `outcome: success` for a tool with `required_approval_level: sync` or `async`, but no corresponding `approval_decision` event with `outcome: approved` in the same trace.

**Severity**: P1 (Critical) — this indicates a control bypass.

**Immediate Actions (first 15 minutes)**:
1. Page the on-call security engineer immediately.
2. Set `DRY_RUN=true` to halt all write/external tool execution pending investigation.
3. Pull the full trace: `python observability/trace_viewer.py --trace-id <id>`
4. Identify which tool was called and what parameters were passed (check the `details` field in the tool_call audit event).
5. Assess the business impact: Was an email sent? Was a database record modified? Was an external API called?
6. Notify the business owner of the affected system (CRM, DB, email, etc.).

**Investigation Steps**:
1. Determine how the tool call bypassed the approval gate:
   - Was `DRY_RUN` accidentally set to `true` in production?
   - Was the tool's `required_approval_level` changed to `none` in the registry without approval?
   - Was there a code defect in the approval gate logic?
2. Review the git log for recent changes to `tools/registry.yaml` and `harness/approval_gate.py`.
3. Review deployment logs for the relevant application version.
4. Check whether any approval decision was created by an automated system rather than a human (check `decided_by` field).

**Containment**:
- If `DRY_RUN` was misconfigured: correct the environment variable and redeploy.
- If the registry was misconfigured: revert `tools/registry.yaml` to the last approved version.
- If a code defect: roll back to the previous known-good deployment.
- Revoke credentials used by the tool that was called without approval.
- Reverse any state changes made by the unauthorised tool call (e.g., restore DB record, recall email if possible).

**Recovery**:
1. Re-enable tools once root cause is identified and fixed.
2. Add a CI check that validates `required_approval_level` for all tools with side effects.
3. Redeploy with fix.

**Post-Incident Review**:
- Root cause analysis within 3 business days.
- Document how the bypass occurred and which control failed.
- Add a new test to the approval gate test suite covering the failure mode.
- Review whether additional defence-in-depth (e.g., network-level block on tool destinations without a valid approval token) should be added.

**Owner**: Platform Engineering + Security Engineering

---

## Playbook 3: Sensitive Data Leakage — PII or RESTRICTED Content Sent to External Endpoint

**Trigger**: DLP alert from Zscaler indicating PII patterns in outbound traffic from the agent service. Or: audit log shows `http_get` or `send_email` tool call with parameters containing PII fields (email addresses, names, customer IDs) sent to an external endpoint outside the approved allowlist.

**Severity**: P1 (Critical) — potential GDPR breach requiring 72-hour supervisory authority notification.

**Immediate Actions (first 30 minutes)**:
1. Page the on-call security engineer, DPO, and Legal counsel.
2. Set `DRY_RUN=true` to halt all write/external tool execution.
3. Pull the full trace and document the data elements exposed, the destination endpoint, and the timestamp.
4. Preserve all relevant audit log entries: export the audit DB or take a snapshot.
5. Notify the CISO.

**Investigation Steps**:
1. Identify the data subject(s) affected: which customer records or employee records were exposed?
2. Identify the destination: which external endpoint received the data? Is it an approved supplier?
3. Determine whether the destination can be requested to delete the data.
4. Assess whether PII reached an unapproved LLM provider in violation of the data classification policy.
5. Review whether the data was encrypted in transit (TLS).
6. Check audit log for the same data subject appearing in other recent traces — was this a targeted or opportunistic leak?

**Containment**:
- If data was sent to an approved supplier (OpenAI/Anthropic): contact the supplier's DPA team to request deletion and document the request.
- If data was sent to an unapproved endpoint: treat as a potential malicious exfiltration and escalate to P1 security incident.
- Disable the tool that was used for the leak pending review.
- Revoke the tool's scoped credential.

**Recovery**:
1. Identify and fix the control gap that permitted the leak (missing PII redaction, incorrect data classification, policy rule miss).
2. Add PII redaction layer before any external tool call.
3. Re-enable tools with PII redaction in place.
4. Re-run data classification review on all tool parameters.

**Post-Incident Review — GDPR Obligations**:
- DPO must assess whether this constitutes a personal data breach under GDPR Article 33.
- If the breach is likely to result in a risk to individuals' rights and freedoms: notify the supervisory authority within 72 hours.
- If high risk to individuals: also notify affected data subjects under Article 34.
- Complete internal breach register entry.
- Review and update the DPIA (`risk/dpia-summary.md`).

**Owner**: DPO + Security Engineering

---

## Playbook 4: LLM Provider Outage

**Trigger**: Health checks to the approved LLM provider API return non-200 responses for more than 2 consecutive minutes. Agent `/run` endpoint begins returning errors. Provider status page shows an incident.

**Severity**: P2 (High) — agent workflows unavailable but no data loss or security breach.

**Immediate Actions (first 10 minutes)**:
1. Confirm the outage via the provider status page (OpenAI: status.openai.com; Anthropic: anthropicstatus.com).
2. Post a service degradation notice to the internal agent service status channel.
3. Check whether the self-hosted model (`acme-internal-llm-v2`) is available as a fallback for workflows that do not require cloud provider capabilities.
4. If the self-hosted model is available: update the `MODEL_ID` environment variable to point to the self-hosted endpoint and redeploy.

**Investigation Steps**:
1. Determine the scope of the outage: is it a full outage or partial (specific regions, specific model versions)?
2. Assess which agent workflows are blocked vs. which can continue with the self-hosted model.
3. Identify any workflows that were mid-execution when the outage began: check the audit log for traces with `policy_eval` events but no corresponding `agent_turn` events.

**Containment**:
- Route all non-PII, non-RESTRICTED workflows to the alternative approved provider if one is available.
- Queue high-priority workflows for retry when the provider recovers.
- Inform affected users of the outage and expected recovery time.

**Recovery**:
1. Monitor the provider status page for recovery.
2. Once the provider reports recovery, run a smoke test: `curl -X POST http://localhost:8000/run -d '{"user_input": "Look up customer cust-001"}'`
3. Verify the response is healthy and the audit log shows a successful `agent_turn`.
4. Revert `MODEL_ID` to the primary provider if it was changed.
5. Clear the retry queue.

**Post-Incident Review**:
- Document the outage duration and number of affected workflows.
- Review whether provider SLA commitments were met and whether credits are applicable.
- Assess whether a circuit breaker pattern should be implemented to automatically failover without manual intervention.

**Owner**: Platform Engineering

---

## Playbook 5: Eval Regression — Safety Eval Pass Rate Drops Below Threshold

**Trigger**: CI pipeline reports that `evals/run_evals.py` exits with code 1 (one or more safety tests failed). Or: a model version upgrade causes a previously passing test to fail.

**Severity**: P2 (High) — a safety control may have been degraded.

**Immediate Actions (first 15 minutes)**:
1. Block the deployment that introduced the regression — do not merge or promote to production.
2. Run the eval suite locally to reproduce the failure: `python evals/run_evals.py`
3. Identify the specific failing test(s) from the output.
4. Determine whether the failure is a policy engine regression (a blocking rule no longer firing) or an approval gate regression (wrong approval status returned).

**Investigation Steps**:
1. Review the git diff for recent changes to `policy/rules.yaml`, `harness/policy_engine.py`, `harness/approval_gate.py`, and `tools/registry.yaml`.
2. Identify the change that caused the regression.
3. If the regression was caused by a model version change: verify which model version is being tested and whether the new version's output format has changed in a way that affects pattern matching.
4. Check whether any test cases in `evals/injection_tests.yaml` need updating due to legitimate behaviour changes (this must be approved by the Security Engineering team, not just the change author).

**Containment**:
- Revert the change that caused the regression if it cannot be quickly fixed.
- Do not change the expected outcomes in the eval YAML without explicit Security Engineering sign-off — modifying expected results to make a failing test pass is not a valid fix.

**Recovery**:
1. Fix the root cause (patch the policy rule, fix the approval gate logic, or update the registry).
2. Re-run the full eval suite: `python evals/run_evals.py` — all tests must pass.
3. Run the unit test suite: `pytest tests/` — all tests must pass.
4. Request a Security Engineering review of the change before merging.
5. Merge and promote to production.

**Post-Incident Review**:
- Document which control regressed, why, and how long it would have been in production without the CI gate.
- This reinforces the value of the eval gate — share the finding with the broader engineering team.
- Consider adding more granular eval tests to catch similar regressions earlier.

**Owner**: ML Engineering + Security Engineering
