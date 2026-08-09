"""LangChain tool: parses FireMapSim output into farmer-friendly summaries."""

from langchain_core.tools import tool

from app.firesim.schemas import SimulationOutput


@tool
def parse_results_tool(simulation_output_json: str) -> str:
    """Summarize raw FireMapSim results for a non-technical user.

    Args:
        simulation_output_json: JSON from run_simulation matching SimulationOutput.

    Returns:
        Plain-language summary of spread, timing, affected area, and recommendations.
    """
    pass  # TODO: SimulationOutput.model_validate_json(...); format key metrics in prose


def parse_results(output: SimulationOutput) -> str:
    """Build readable summary from structured simulation output (non-tool entry for tests)."""
    pass  # TODO: template or LLM-assisted summarization of burn area, rate, direction, etc.
