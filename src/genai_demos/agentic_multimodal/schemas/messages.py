from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Dict, Any
import datetime
# -------------------------
# Messages / provenance
# -------------------------

class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    params: Dict[str, Any] = Field(default_factory=dict)
    started_at: float
    finished_at: float
    ok: bool
    note: Optional[str] = None

class RunRecord(BaseModel):
    """One line for manifest.jsonl"""
    run_id: str
    kind: Literal["person", "geo"]
    request: Dict[str, Any]           # serialized request model
    spec: Dict[str, Any]              # serialized output spec
    output_path: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    created_at: float = Field(default_factory=lambda: datetime.utcnow().timestamp())
    version: str = "0.1.0"

__all__ = [
    # requests
    "PersonSearchRequest", "GeoSearchRequest",
    # entities
    "OfficeTerm", "Person", "Country",
    # artifacts
    "ImageAsset", "PosterItem", "PosterSpec", "MapMarker", "MapSpec",
    # messages
    "ToolCall", "RunRecord",
]