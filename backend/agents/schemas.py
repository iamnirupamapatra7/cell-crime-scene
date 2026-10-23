from typing import Literal, Optional

from pydantic import BaseModel, Field

ACTIONS = ["watershed_split", "erosion_split", "remove_small_objects", "resegment_threshold", "accept", "abstain"]


class ToolParams(BaseModel):
    base: Optional[Literal["baseline", "best"]] = None
    target: Optional[Literal["suspicious", "all"]] = None
    landscape: Optional[Literal["distance", "intensity"]] = None
    min_distance: Optional[int] = None
    sigma: Optional[float] = None
    radius: Optional[int] = None
    min_size: Optional[int] = None
    method: Optional[Literal["otsu", "li", "local"]] = None


class Decision(BaseModel):
    observations: list[str] = Field(default_factory=list)
    hypothesis: str
    action: Literal["watershed_split", "erosion_split", "remove_small_objects", "resegment_threshold",
                    "accept", "abstain"]
    params: ToolParams = Field(default_factory=ToolParams)
    rationale: str
    confidence: float = 0.5


class Report(BaseModel):
    summary: str
    what_changed: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    recommendation: str = ""


# Hand-written response schemas for Gemini structured output (OpenAPI subset, no defaults).
_STR_LIST = {"type": "ARRAY", "items": {"type": "STRING"}}

DECISION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "observations": _STR_LIST,
        "hypothesis": {"type": "STRING"},
        "action": {"type": "STRING", "enum": ACTIONS},
        "params": {
            "type": "OBJECT",
            "properties": {
                "base": {"type": "STRING", "enum": ["baseline", "best"], "nullable": True},
                "target": {"type": "STRING", "enum": ["suspicious", "all"], "nullable": True},
                "landscape": {"type": "STRING", "enum": ["distance", "intensity"], "nullable": True},
                "min_distance": {"type": "INTEGER", "nullable": True},
                "sigma": {"type": "NUMBER", "nullable": True},
                "radius": {"type": "INTEGER", "nullable": True},
                "min_size": {"type": "INTEGER", "nullable": True},
                "method": {"type": "STRING", "enum": ["otsu", "li", "local"], "nullable": True},
            },
        },
        "rationale": {"type": "STRING"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["observations", "hypothesis", "action", "params", "rationale", "confidence"],
}

REPORT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "what_changed": _STR_LIST,
        "improvements": _STR_LIST,
        "uncertainties": _STR_LIST,
        "recommendation": {"type": "STRING"},
    },
    "required": ["summary", "what_changed", "improvements", "uncertainties", "recommendation"],
}
