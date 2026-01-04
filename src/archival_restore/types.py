from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class PageArtifact:
    page_index: int
    source_image: str
    clean_image: str
    orientation_rotate_deg: int
    orientation_conf: float
    deskew_angle_deg: float
    ocr_mean_conf: float
    ocr_text_path: str
    artifact_json_path: str
    trace: List[Dict[str, Any]]

@dataclass
class EditProposal:
    page_index: int
    start: int
    end: int
    from_text: str
    to_text: str
    edit_type: str  # 'ocr_confusion', 'punctuation', 'hyphen_join', 'hand_correction', ...
    reason: str
    risk: str  # 'low'|'med'|'high'
    evidence: Dict[str, Any]

@dataclass
class EvalDecision:
    proposal: EditProposal
    decision: str  # 'approve'|'reject'|'flag'
    rationale: str