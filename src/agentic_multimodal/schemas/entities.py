from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Tuple

# -------------------------
# Domain entities (research)
# -------------------------

class OfficeTerm(BaseModel):
    model_config = ConfigDict(frozen=True)
    start: Optional[str] = None   # ISO 'YYYY-MM-DD'
    end: Optional[str] = None

    @field_validator("start", "end")
    @classmethod
    def _strip_plus(cls, v: Optional[str]) -> Optional[str]:
        return v.lstrip("+") if isinstance(v, str) else v

class Person(BaseModel):
    model_config = ConfigDict(frozen=True)
    qid: str
    name: str
    image_url: Optional[str] = None
    terms: List[OfficeTerm] = Field(default_factory=list)

class Country(BaseModel):
    model_config = ConfigDict(frozen=True)
    qid: str
    name: str
    capital_name: Optional[str] = None
    capital_coords: Optional[Tuple[float, float]] = None  # (lon, lat)
    flag_svg_url: Optional[str] = None