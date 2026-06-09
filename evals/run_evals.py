#!/usr/bin/env python3
"""
Eval runner — tests the policy engine and approval gate against YAML test suites.

Usage:
    python evals/run_evals.py

Exits with code 0 if all tests pass, 1 if any fail.
"""
from __future__ import annotations
import os
import sys
import uuid
from pathlib import Path

import yaml

# Ensure the repo root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("AUDIT_DB_PATH", "/tmp/eval_audit.db")
os.environ.setdefault("TOOL_REGISTRY_PATH", "tools/registry.yaml")
os.environ.setdefault("POLICY_RULES_PATH", "policy/rules.yaml")
os.environ.setdefault("DRY_RUN", "false")

from harness.audit_log import init_audit_db
from harness.policy_engine import evaluate, load_rules
from harness.tool_registry import get_tool, is_registered, load_registry
from harness.approval_gate import check_approval
from harness.models import ToolCall

PASS = "PASS"
FAIL = "FAIL"


def run_injection_tests(path: str = "evals/injection_tests.yaml") -> list:
    """Run all injection / policy engine tests."""
    load_rules()
    results = []
    data = yaml.safe_load(Path(path).read_text())
    for test in data.get("tests", []):
        tid = test["id"]
        name = test["name"]
        text = test["input"]
        expected_action = test.get("expected_action")
        expected_rule = test.get("expected_policy_rule")

        trace_id = str(uuid.uuid4())
        eval_result = evaluate(text, trace_id)
        actual_action = eval_result.action.value

        passed = True
        reasons = []

        if expected_action and actual_action != expected_action:
            passed = False
            reasons.append(f"expected action={expected_action!r}, got {actual_action!r}")

        if expected_rule and expected_rule not in eval_result.matched_rules:
            passed = False
            reasons.append(
                f"expected rule {expected_rule!r} to match, "
                f"got matched_rules={eval_result.matched_rules}"
            )

        status = PASS if passed else FAIL
        results.append({
            "id": tid, "name": name, "status": status,
            "actual_action": actual_action,
            "matched_rules": eval_result.matched_rules,
            "reason": "; ".join(reasons) if reasons else "",
        })
    return results


def run_policy_tool_tests(path: str = "evals/policy_eval.yaml") -> list:
    """Run approval gate tests."""
    load_registry()
    init_audit_db()
    results = []
    data = yaml.safe_load(Path(path).read_text())
    for test in data.get("tests", []):
        tid = test["id"]
        name = test["name"]
        tool_name = test["tool_name"]
        expected_blocked = test.get("expected_blocked", False)
        expected_status = test.get("expected_approval_status")

        trace_id = str(uuid.uuid4())
        passed = True
        reasons = []
        actual_status = None

        if expected_blocked:
            # Expect the tool is not registered
            registered = is_registered(tool_name)
            if registered:
                passed = False
                reasons.append(f"Tool {tool_name!r} is registered but expected to be blocked (unregistered)")
            actual_status = "not_registered" if not registered else "registered"
        else:
            tool_def = get_tool(tool_name)
            if not tool_def:
                passed = False
                reasons.append(f"Tool {tool_name!r} not found in registry")
                actual_status = "not_found"
            else:
                tc = ToolCall(
                    trace_id=trace_id,
                    tool_name=tool_name,
                    parameters={},
                )
                status = check_approval(tc, tool_def, trace_id)
                actual_status = status.value
                if expected_status and actual_status != expected_status:
                    passed = False
                    reasons.append(f"expected approval_status={expected_status!r}, got {actual_status!r}")

        result_status = PASS if passed else FAIL
        results.append({
            "id": tid, "name": name, "status": result_status,
            "actual_approval_status": actual_status,
            "reason": "; ".join(reasons) if reasons else "",
        })
    return results


def print_results(suite_name: str, results: list) -> int:
    """Print results table. Returns number of failures."""
    failures = 0
    print(f"\n{'='*70}")
    print(f"  {suite_name}")
    print(f"{'='*70}")
    for r in results:
        status_display = f"[{r['status']}]"
        line = f"  {status_display:8s} {r['id']:12s} {r['name']}"
        if r["status"] == FAIL:
            failures += 1
            line += f"\n           REASON: {r['reason']}"
        print(line)
    passed = len(results) - failures
    print(f"{'='*70}")
    print(f"  Results: {passed}/{len(results)} passed, {failures} failed")
    print(f"{'='*70}\n")
    return failures


def main():
    total_failures = 0

    injection_results = run_injection_tests()
    total_failures += print_results("Injection / Policy Engine Tests", injection_results)

    policy_results = run_policy_tool_tests()
    total_failures += print_results("Approval Gate / Tool Registry Tests", policy_results)

    if total_failures > 0:
        print(f"EVAL SUITE FAILED: {total_failures} test(s) failed.")
        sys.exit(1)
    else:
        print("EVAL SUITE PASSED: all tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
