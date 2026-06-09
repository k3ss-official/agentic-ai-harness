"""Tool registry — loads and validates the YAML tool definitions."""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Dict, Optional

import yaml

from harness.models import ApprovalLevel, ToolDefinition

logger = logging.getLogger(__name__)
_registry: Dict[str, ToolDefinition] = {}


def load_registry(path: Optional[str] = None) -> Dict[str, ToolDefinition]:
    global _registry
    registry_path = path or os.getenv("TOOL_REGISTRY_PATH", "tools/registry.yaml")
    raw = yaml.safe_load(Path(registry_path).read_text())
    tools = {}
    for tool_data in raw.get("tools", []):
        td = ToolDefinition(**tool_data)
        tools[td.name] = td
        logger.info(
            "Registered tool: %s (side_effect=%s, approval=%s)",
            td.name, td.side_effect_class, td.required_approval_level
        )
    _registry = tools
    logger.info("Tool registry loaded: %d tools", len(tools))
    return tools


def get_tool(name: str) -> Optional[ToolDefinition]:
    return _registry.get(name)


def list_tools() -> Dict[str, ToolDefinition]:
    return dict(_registry)


def is_registered(name: str) -> bool:
    return name in _registry


def requires_approval(tool_name: str) -> bool:
    tool = get_tool(tool_name)
    if not tool:
        return True
    return tool.required_approval_level in (ApprovalLevel.SYNC, ApprovalLevel.ASYNC)
