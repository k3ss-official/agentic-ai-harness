"""Tests for the tool registry."""
from __future__ import annotations
import os
import pytest

os.environ.setdefault("TOOL_REGISTRY_PATH", "tools/registry.yaml")

from harness.tool_registry import load_registry, get_tool, is_registered, requires_approval, list_tools
from harness.models import ApprovalLevel, SideEffectClass


@pytest.fixture(autouse=True)
def loaded_registry():
    load_registry()


class TestRegistryLoading:
    def test_loads_from_valid_yaml(self):
        tools = list_tools()
        assert len(tools) > 0

    def test_all_expected_tools_present(self):
        for name in ["crm_lookup", "db_read", "db_write", "send_email", "http_get", "payment_transfer"]:
            assert is_registered(name), f"Expected tool '{name}' not found in registry"


class TestGetTool:
    def test_returns_correct_definition(self):
        tool = get_tool("crm_lookup")
        assert tool is not None
        assert tool.name == "crm_lookup"
        assert tool.side_effect_class == SideEffectClass.READ
        assert tool.required_approval_level == ApprovalLevel.NONE

    def test_returns_none_for_unknown(self):
        assert get_tool("nonexistent_tool") is None

    def test_blocked_tool_has_correct_level(self):
        tool = get_tool("payment_transfer")
        assert tool is not None
        assert tool.required_approval_level == ApprovalLevel.BLOCKED


class TestIsRegistered:
    def test_returns_true_for_known_tool(self):
        assert is_registered("crm_lookup") is True

    def test_returns_false_for_unknown_tool(self):
        assert is_registered("sudo_exec") is False
        assert is_registered("") is False
        assert is_registered("rm -rf /") is False


class TestRequiresApproval:
    def test_read_tools_do_not_require_approval(self):
        assert requires_approval("crm_lookup") is False
        assert requires_approval("db_read") is False

    def test_write_tools_require_approval(self):
        assert requires_approval("db_write") is True

    def test_external_tools_require_approval(self):
        assert requires_approval("send_email") is True
        assert requires_approval("http_get") is True

    def test_unknown_tool_requires_approval(self):
        """Unknown tools must always require approval — fail safe."""
        assert requires_approval("unknown_tool_xyz") is True
