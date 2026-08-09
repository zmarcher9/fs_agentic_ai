"""LangChain tool: triggers a FireMapSim simulation run from validated parameters."""

from langchain_core.tools import tool

from app.firesim.client import FireMapSimClient
from app.firesim.schemas import SimulationConfig, SimulationOutput


@tool
def run_simulation_tool(params_json: str) -> str:
    """Run FireMapSim with the given simulation parameters (JSON matching SimulationConfig).

    Use after coordinates and scenario parameters have been built and confirmed.
    Returns a JSON string of SimulationOutput or an error description.
    """
    pass  # TODO: parse params_json -> SimulationConfig; client.run_simulation(); return output.model_dump_json()


def run_simulation(params: SimulationConfig, client: FireMapSimClient | None = None) -> SimulationOutput:
    """Execute simulation via FireMapSim client (non-tool entry for tests)."""
    pass  # TODO: FireMapSimClient().run_simulation(params)
