"""Pydantic models for FireMapSim simulation input parameters and output results."""

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator


class Segment(BaseModel):
    """A single polyline segment in grid coordinates."""

    start_x: int
    end_x: int
    start_y: int
    end_y: int
    speed: float = 0.6
    mode: str = "continuous_dynamic"
    distance: None = None


class TeamInfo(BaseModel):
    """One ignition line composed of grid-coordinate segments."""

    team_name: str
    info_num: int
    details: list[Segment]

    @model_validator(mode="after")
    def info_num_matches_details(self) -> Self:
        if self.info_num != len(self.details):
            raise ValueError("info_num must equal len(details)")
        return self


class SupLine(BaseModel):
    """A fuel break segment in grid coordinates."""

    type: str = "supLine"
    start_x: int
    start_y: int
    end_x: int
    end_y: int


class SimulationConfig(BaseModel):
    """Top-level FireMapSim project file schema."""

    name: str = ""
    info_type: str = "simulation"
    team_num: int
    total_sim_time: int = 12000
    team_infos: list[TeamInfo]
    windSpeed: float
    windDegree: float
    sup_infos: list[SupLine] = Field(default_factory=list)
    proj_center_lng: float
    proj_center_lat: float
    fuel_data_adjusted: list[Any] = Field(default_factory=list)
    customizedFuelGrid: str = ""
    slope_data_adjusted: list[Any] = Field(default_factory=list)
    aspect_data_adjusted: list[Any] = Field(default_factory=list)
    cellResolution: int = 30
    cellSpaceDimension: int = 200
    cellSpaceDimensionLat: int = 200
    customized_cell_state: list[Any] = Field(default_factory=list)
    sup_num: int

    @model_validator(mode="after")
    def counts_match_lists(self) -> Self:
        if self.team_num != len(self.team_infos):
            raise ValueError("team_num must equal len(team_infos)")
        if self.sup_num != len(self.sup_infos):
            raise ValueError("sup_num must equal len(sup_infos)")
        return self


class SimulationResult(BaseModel):
    """Placeholder output returned after a simulation run."""

    simulation_id: str = Field(..., description="Unique identifier for this run")
    status: str = Field(..., description="Run status (e.g. pending, completed, failed)")
    output_data: dict[str, Any] | None = Field(
        default=None,
        description="Raw or structured simulator output when available",
    )


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
