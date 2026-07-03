"""Skill registry for Phase 11 agentic architecture.

A Skill bundles a system prompt, tool list, and input/output metadata
into a single, versioned unit. Each module in this package must export
a `skill: Skill` instance.

Security boundary: `skill_catalog_for_planner()` exposes ONLY name,
description, owner_worker, and input_fields — never system_prompt.
This prevents the Planner from being used to exfiltrate internal
instructions via prompt injection.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class Skill:
    name: str                                    # unique, kebab-case
    description: str                             # Planner-visible (1-2 lines)
    owner_worker: Literal["rag", "data", "report", "memory", "any"]
    model: str = "qwen2.5:7b"
    system_prompt: str = ""                      # NOT exposed to Planner
    input_fields: dict[str, str] = field(default_factory=dict)
    tools_used: list[str] = field(default_factory=list)
    requires_approval: bool = False              # Phase 12: pre-execution gate


_REGISTRY: dict[str, Skill] = {}


def get_skill_registry() -> dict[str, Skill]:
    """Auto-discover all modules in this package that export `skill: Skill`."""
    if _REGISTRY:
        return _REGISTRY
    pkg_path = Path(__file__).parent
    for _finder, module_name, _is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if module_name.startswith("_"):
            continue
        module = importlib.import_module(f"app.skills.{module_name}")
        if hasattr(module, "skill") and isinstance(module.skill, Skill):
            _REGISTRY[module.skill.name] = module.skill
    return _REGISTRY


def get_skill(name: str) -> Skill:
    registry = get_skill_registry()
    if name not in registry:
        raise KeyError(
            f"Skill '{name}' not found. Available: {sorted(registry)}"
        )
    return registry[name]


def skill_catalog_for_planner() -> str:
    """Return a text catalog of all skills for planner prompt injection.

    Exposes name, description, owner_worker, and input_fields only.
    System prompts are intentionally hidden (security boundary).
    """
    registry = get_skill_registry()
    lines: list[str] = []
    for skill in registry.values():
        fields = (
            ", ".join(
                f"{k} ({v})" for k, v in skill.input_fields.items()
            )
            if skill.input_fields
            else "none"
        )
        lines.append(
            f"- **{skill.name}** [{skill.owner_worker}]: {skill.description}\n"
            f"  input fields: {fields}"
        )
    return "\n".join(lines)
