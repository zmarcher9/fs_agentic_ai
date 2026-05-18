"""Interface wrapper for invoking FireMapSim via subprocess or HTTP API."""

import subprocess
from typing import Literal

import httpx

from app.config import Settings, get_settings
from app.firesim.schemas import SimulationInput, SimulationOutput


class FireMapSimClient:
    """Calls FireMapSim using path/URL from settings (executable or REST base URL)."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize client with optional settings override for testing."""
        pass  # TODO: self._settings = settings or get_settings(); detect api vs executable

    def run_simulation(self, params: SimulationInput) -> SimulationOutput:
        """Execute a simulation and return structured output."""
        pass  # TODO: dispatch to _run_via_subprocess or _run_via_api

    def _run_via_subprocess(self, params: SimulationInput) -> SimulationOutput:
        """Invoke FireMapSim CLI with serialized parameters."""
        pass  # TODO: subprocess.run([firesim_path, ...], capture_output=True)

    def _run_via_api(self, params: SimulationInput) -> SimulationOutput:
        """POST simulation request to FireMapSim HTTP API."""
        pass  # TODO: httpx.Client().post(f"{base}/simulate", json=params.model_dump())

    @staticmethod
    def _detect_mode(firesim_path: str) -> Literal["api", "executable"]:
        """Infer whether FIRESIM_PATH is a URL or local executable path."""
        pass  # TODO: return "api" if firesim_path.startswith("http") else "executable"
