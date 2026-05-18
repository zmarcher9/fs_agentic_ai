"""Pydantic models for FireMapSim simulation input parameters and output results."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SimulationInput(BaseModel):
    """Validated parameters passed to FireMapSim for a single run."""

    latitude: float = Field(..., description="Ignition or domain center latitude")
    longitude: float = Field(..., description="Ignition or domain center longitude")
    wind_speed_kmh: float | None = Field(default=None, description="Wind speed in km/h")
    wind_direction_deg: float | None = Field(default=None, description="Wind direction in degrees")
    fuel_model: str | None = Field(default=None, description="Fuel model identifier")
    simulation_hours: float = Field(default=24.0, description="Simulation duration in hours")
    extra_params: dict[str, Any] = Field(default_factory=dict, description="Additional sim-specific fields")


class SimulationOutput(BaseModel):
    """Structured results returned from FireMapSim."""

    run_id: str = Field(..., description="Unique run identifier")
    completed_at: datetime | None = Field(default=None, description="When the run finished")
    burned_area_ha: float | None = Field(default=None, description="Total burned area in hectares")
    max_spread_rate_m_per_min: float | None = Field(default=None, description="Peak spread rate")
    raw_output: dict[str, Any] = Field(default_factory=dict, description="Full simulator output payload")


class SimulationError(BaseModel):
    """Error payload when a simulation run fails."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
