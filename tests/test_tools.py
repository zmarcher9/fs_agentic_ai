"""Tests for LangChain tools (simulation run, parameters, results parsing)."""

import pytest

from app.firesim.schemas import SimulationInput, SimulationOutput
from app.tools.parameter_builder import build_parameters
from app.tools.parse_results import parse_results
from app.tools.run_simulation import run_simulation


@pytest.fixture
def sample_input() -> SimulationInput:
    """Example simulation input for tool tests."""
    pass  # TODO: return SimulationInput(latitude=-37.0, longitude=144.0, simulation_hours=12.0)


@pytest.fixture
def sample_output() -> SimulationOutput:
    """Example simulation output for parse_results tests."""
    pass  # TODO: return SimulationOutput(run_id="test-1", burned_area_ha=10.5)


def test_build_parameters_merges_intent_and_coordinates() -> None:
    """Parameter builder should produce valid SimulationInput."""
    pass  # TODO: result = build_parameters({...}, {...}); assert isinstance(result, SimulationInput)


def test_run_simulation_accepts_valid_input(sample_input: SimulationInput) -> None:
    """Run simulation should return SimulationOutput when client is mocked."""
    pass  # TODO: patch FireMapSimClient.run_simulation; assert output.run_id


def test_parse_results_returns_non_empty_summary(sample_output: SimulationOutput) -> None:
    """Parse results should return human-readable text."""
    pass  # TODO: summary = parse_results(sample_output); assert len(summary) > 0
