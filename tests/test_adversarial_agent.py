"""Regression tests for the Q&A helper's no-actuation / tool-boundary guarantees.

The agent may explain and point, never operate the page. These tests pin
that down structurally (the model gets no tools, the server imports no
browser driver) rather than trusting the prompt alone. Hostile highlight
keys are covered in tests/test_agent.py and tests/test_ui_steps.py.

If a doc-grounded tool ever lands, it breaks the no-tools guarantee on
purpose: add doc-content-injection cases here (a reference file containing
directive text must come back as narrated data, and the tool must resolve
queries against its own enumerated file list, never an LLM-supplied path).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.agent.prompts import FIRESIM_SYSTEM_PROMPT

REPO_ROOT = Path(__file__).resolve().parent.parent

# Anything that would hand the model a callable: LangChain tool decorators,
# tool binding, agent factories with tool lists.
_TOOL_MARKERS = ("bind_tools", "create_agent", "StructuredTool", "BaseTool", "ToolNode")


def _server_files() -> list[Path]:
    return list((REPO_ROOT / "app").rglob("*.py")) + list((REPO_ROOT / "api").rglob("*.py"))


def test_the_model_is_given_no_tools_at_all():
    # The helper only explains and points: there is nothing for an injected
    # instruction to call. Highlighting comes from the structured answer.
    for path in _server_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        offenders = names & set(_TOOL_MARKERS)
        decorated = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(getattr(d, "id", getattr(d, "attr", None)) == "tool" for d in node.decorator_list)
        ]
        assert not offenders and not decorated, f"{path.relative_to(REPO_ROOT)}: {offenders or decorated}"


def test_prompt_forbids_operating_the_site():
    prompt = FIRESIM_SYSTEM_PROMPT.lower()
    assert "you cannot move the map, fill in any field" in prompt
    assert "untrusted data" in prompt
    # The prompt rule is a partial mitigation and must say so.
    assert "does not fully remove" in prompt


def test_prompt_has_no_actuation_workflow_left():
    for stale in ("navigate_map", "resolve_location", "build_project_config", "automatically pan", "explain_ui_step"):
        assert stale not in FIRESIM_SYSTEM_PROMPT


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_server_code_never_imports_a_browser_driver():
    server_files = _server_files()
    assert server_files
    for path in server_files:
        offenders = {m for m in _imported_modules(path) if m.split(".")[0] in {"playwright", "playwright_guide"}}
        assert not offenders, f"{path.relative_to(REPO_ROOT)} imports {offenders}"
