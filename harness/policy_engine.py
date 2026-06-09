"""
Policy engine — classifies requests and enforces rules.

Loads rules from policy/rules.yaml and evaluates each incoming request.
Rules are evaluated in order; first match wins.
"""
from __future__ import annotations
import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from harness.models import PolicyAction, PolicyEvaluation

logger = logging.getLogger(__name__)


class PolicyRule:
    def __init__(self, rule_id: str, name: str, pattern: str,
                 action: str, reason: str, priority: int = 100):
        self.rule_id = rule_id
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.action = PolicyAction(action)
        self.reason = reason
        self.priority = priority

    def matches(self, text: str) -> bool:
        return bool(self.pattern.search(text))


_rules: List[PolicyRule] = []


def load_rules(path: Optional[str] = None) -> List[PolicyRule]:
    global _rules
    rules_path = path or os.getenv("POLICY_RULES_PATH", "policy/rules.yaml")
    raw = yaml.safe_load(Path(rules_path).read_text())
    rules = []
    for r in raw.get("rules", []):
        rules.append(PolicyRule(
            rule_id=r["id"],
            name=r["name"],
            pattern=r["pattern"],
            action=r["action"],
            reason=r["reason"],
            priority=r.get("priority", 100),
        ))
    rules.sort(key=lambda x: x.priority)
    _rules = rules
    logger.info("Policy engine loaded: %d rules", len(rules))
    return rules


def evaluate(text: str, trace_id: str) -> PolicyEvaluation:
    """Evaluate text against policy rules. Returns first matching rule's action, or ALLOW."""
    matched = []
    final_action = PolicyAction.ALLOW
    final_reason = "No policy rules matched — default allow"

    for rule in _rules:
        if rule.matches(text):
            matched.append(rule.rule_id)
            final_action = rule.action
            final_reason = f"Rule '{rule.rule_id}' ({rule.name}): {rule.reason}"
            break  # First match wins

    return PolicyEvaluation(
        trace_id=trace_id,
        input_text=text[:500],
        matched_rules=matched,
        action=final_action,
        reason=final_reason,
    )


def is_blocked(text: str, trace_id: str) -> Tuple[bool, PolicyEvaluation]:
    eval_result = evaluate(text, trace_id)
    return eval_result.action == PolicyAction.BLOCK, eval_result
