from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Literal

# -------------------------
# Artifacts (things we generate)
# -------------------------

class ImageAsset(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str                       # content hash or UUID
    path: str                     # filesystem path to image
    width: int
    height: int
    meta: Dict[str, Any] = Field(default_factory=dict)  # prompts, seed, model_id, cfg, etc.

class PosterItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    image: ImageAsset
    label: str

class PosterSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str
    subtitle: Optional[str] = None
    grid_cols: int = 6
    items: List[PosterItem]
    path: Optional[str] = None    # filled by renderer

class MapMarker(BaseModel):
    model_config = ConfigDict(frozen=True)
    lon: float
    lat: float
    label: Optional[str] = None
    image: Optional[ImageAsset] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

class MapSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    region: str
    markers: List[MapMarker]
    title: Optional[str] = None
    path: Optional[str] = None
