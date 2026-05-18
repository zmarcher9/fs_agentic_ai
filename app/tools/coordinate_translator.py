"""LangChain tool: converts natural language locations to FireMapSim simulation coordinates."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class CoordinateResult(BaseModel):
    """Resolved geographic coordinates for the simulation grid."""

    latitude: float = Field(..., description="WGS84 latitude")
    longitude: float = Field(..., description="WGS84 longitude")
    description: str = Field(default="", description="Human-readable location label")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Geocoding confidence 0-1")


@tool
def translate_coordinates_tool(location_description: str) -> str:
    """Translate a plain-language place (e.g. 'north field near the barn') into lat/lon.

    Args:
        location_description: User-described location or landmark relative to their property.

    Returns:
        JSON string with latitude, longitude, description, and confidence.
    """
    pass  # TODO: geocode or LLM-assisted parsing; return CoordinateResult.model_dump_json()


def translate_coordinates(location_description: str) -> CoordinateResult:
    """Resolve coordinates from natural language (non-tool entry for tests)."""
    pass  # TODO: implement geocoding / property boundary lookup
