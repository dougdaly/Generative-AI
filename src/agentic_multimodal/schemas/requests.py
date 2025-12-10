from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal

# -------------------------
# Requests (inputs to flows)
# -------------------------

class PersonSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    query: str = Field(..., description="Original user text")
    series: Literal["us_presidents", "uk_prime_ministers"] = "us_presidents"
    include_years: bool = True
    style: Optional[str] = None
    grid_cols: int = 6

class GeoSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    region: str = Field(..., description="e.g., 'Europe'")
    scope: Literal["countries", "states"] = "countries"
    show_flags: bool = True
    style: Optional[str] = None


class FlightPathRequest(BaseModel):
    origin: str = Field(..., description="Place name, e.g., 'Seattle, WA'")
    destination: str = Field(..., description="Place name, e.g., 'London, UK'")
    step_miles: int = Field(50, ge=10, le=200)
    pad_degrees: float = Field(5.0, ge=0, le=20) # degrees to pad bbox
    lat_cap: float = Field(70.0, ge=60, le=85)  # max latitude for path points (+/-)
    title: Optional[str] = None
