"""Aggregates the LangChain tools the FireMapSim agent registers with create_agent()."""

from app.agent.tools_config import build_project_config
from app.agent.tools_navigate_map import navigate_map
from app.agent.tools_resolve_location import resolve_location_tool
from app.agent.tools_ui_help import explain_ui_step

TOOLS = [
    build_project_config,
    explain_ui_step,
    resolve_location_tool,
    navigate_map,
]
