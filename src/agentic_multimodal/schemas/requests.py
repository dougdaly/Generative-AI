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
