"""Aggregates the LangChain tools the FireMapSim agent registers with create_agent()."""

from app.agent.tools_ui_help import explain_ui_step

TOOLS = [
    explain_ui_step,
]
