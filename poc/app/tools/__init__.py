"""Tool registry for Phase 11 agentic architecture.

Tools are atomic, side-effect-free (except audit_write) functions exposed
via Pydantic input/output schemas. Each module in this package must export
a `tool: AgentTool` instance so the registry auto-discovers it.

The registry is intentionally a flat dict keyed by tool.name so the Planner
can list available tools without importing the implementation modules.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class AgentTool:
    name: str
    description: str
    input_fields: dict[str, str] = field(default_factory=dict)
    run: Callable[..., Any] = field(default=lambda **kw: None, repr=False)


_REGISTRY: dict[str, AgentTool] = {}


def get_tool_registry() -> dict[str, AgentTool]:
    """Auto-discover all modules in this package that export `tool: AgentTool`."""
    if _REGISTRY:
        return _REGISTRY
    pkg_path = Path(__file__).parent
    for _finder, module_name, _is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if module_name.startswith("_"):
            continue
        module = importlib.import_module(f"app.tools.{module_name}")
        if hasattr(module, "tool") and isinstance(module.tool, AgentTool):
            _REGISTRY[module.tool.name] = module.tool
    return _REGISTRY


def get_tool(name: str) -> AgentTool:
    registry = get_tool_registry()
    if name not in registry:
        raise KeyError(
            f"Tool '{name}' not in registry. Available: {sorted(registry)}"
        )
    return registry[name]
