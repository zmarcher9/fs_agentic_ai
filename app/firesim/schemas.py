"""Pydantic models for FireMapSim simulation input parameters and output results."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Coordinate(BaseModel):
    """A single WGS84 geographic point."""

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")


class ProjectAreaInput(BaseModel):
    """Bounding box for the simulation domain, defined by four corner points."""

    corners: list[Coordinate] = Field(
        ...,
        description="Four corners of the project area (typically SW, SE, NE, NW order)",
    )

    @field_validator("corners")
    @classmethod
    def corners_must_be_four(cls, corners: list[Coordinate]) -> list[Coordinate]:
        if len(corners) != 4:
            raise ValueError("corners must contain exactly 4 coordinates")
        return corners


class IgnitionLineInput(BaseModel):
    """Ordered polyline defining where fire is ignited along a line."""

    points: list[Coordinate] = Field(
        ...,
        description="Vertices of the ignition line, in draw order",
    )

    @field_validator("points")
    @classmethod
    def points_must_have_at_least_two(cls, points: list[Coordinate]) -> list[Coordinate]:
        if len(points) < 2:
            raise ValueError("points must contain at least 2 coordinates")
        return points


class FuelBreakInput(BaseModel):
    """Ordered polyline representing a fuel break barrier path."""

    points: list[Coordinate] = Field(
        ...,
        description="Vertices of the fuel break path, in draw order",
    )

    @field_validator("points")
    @classmethod
    def points_must_have_at_least_two(cls, points: list[Coordinate]) -> list[Coordinate]:
        if len(points) < 2:
            raise ValueError("points must contain at least 2 coordinates")
        return points


class SimulationConfig(BaseModel):
    """Top-level FireMapSim input composing project area, ignitions, and fuel breaks."""

    project_area: ProjectAreaInput = Field(..., description="Simulation domain bounding box")
    ignition_lines: list[IgnitionLineInput] = Field(
        default_factory=list,
        description="One or more ignition polylines",
    )
    fuel_breaks: list[FuelBreakInput] = Field(
        default_factory=list,
        description="Fuel break paths that modify spread behavior",
    )


class SimulationResult(BaseModel):
    """Placeholder output returned after a simulation run."""

    simulation_id: str = Field(..., description="Unique identifier for this run")
    status: str = Field(..., description="Run status (e.g. pending, completed, failed)")
    output_data: dict[str, Any] | None = Field(
        default=None,
        description="Raw or structured simulator output when available",
    )


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
