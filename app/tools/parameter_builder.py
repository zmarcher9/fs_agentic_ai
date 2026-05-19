"""LangChain tool: builds FireMapSim simulation config from extracted user intent."""

from langchain_core.tools import tool

from app.firesim.schemas import SimulationInput


@tool
def build_parameters_tool(
    user_intent_json: str,
    coordinates_json: str,
) -> str:
    """Merge user intent and coordinates into a complete SimulationInput JSON.

    Args:
        user_intent_json: Extracted scenario fields (wind, fuel, ignition, duration, etc.).
        coordinates_json: Output from coordinate_translator.

    Returns:
        JSON string matching SimulationInput schema ready for run_simulation_tool.
    """
    pass  # TODO: merge dicts; validate SimulationInput; return model_dump_json()


def build_parameters(user_intent: dict, coordinates: dict) -> SimulationInput:
    """Construct validated simulation input (non-tool entry for tests)."""
    pass  # TODO: SimulationInput(**merged fields)
