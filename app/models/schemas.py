from __future__ import annotations

from typing import List, Literal, Optional, Union
from enum import Enum

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AEOAnalyzeRequest(BaseModel):
    input_type: Literal["url", "text"]
    input_value: str


class FanoutGenerateRequest(BaseModel):
    target_query: str
    existing_content: Optional[str] = None


# ---------------------------------------------------------------------------
# AEO check detail models (one per check)
# ---------------------------------------------------------------------------

class DirectAnswerDetails(BaseModel):
    word_count: int
    threshold: int = 60
    is_declarative: bool
    has_hedge_phrase: bool


class HtagHierarchyDetails(BaseModel):
    violations: List[str]
    h_tags_found: List[str]


class ReadabilityDetails(BaseModel):
    fk_grade_level: float
    target_range: str = "7-9"
    complex_sentences: List[str]


# ---------------------------------------------------------------------------
# AEO response models
# ---------------------------------------------------------------------------

class CheckResult(BaseModel):
    check_id: str
    name: str
    passed: bool
    score: int
    max_score: int
    details: Union[DirectAnswerDetails, HtagHierarchyDetails, ReadabilityDetails]
    recommendation: Optional[str] = None


class AEOAnalyzeResponse(BaseModel):
    aeo_score: float
    band: str
    checks: List[CheckResult]


# ---------------------------------------------------------------------------
# Fan-out sub-query models
# ---------------------------------------------------------------------------

class SubQueryType(str, Enum):
    comparative = "comparative"
    feature_specific = "feature_specific"
    use_case = "use_case"
    trust_signals = "trust_signals"
    how_to = "how_to"
    definitional = "definitional"


class SubQuery(BaseModel):
    type: SubQueryType
    query: str
    covered: Optional[bool] = None
    similarity_score: Optional[float] = None


class GapSummary(BaseModel):
    covered: int
    total: int
    coverage_percent: int
    covered_types: List[str]
    missing_types: List[str]


class FanoutGenerateResponse(BaseModel):
    target_query: str
    model_used: str
    total_sub_queries: int
    sub_queries: List[SubQuery]
    gap_summary: Optional[GapSummary] = None


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: Optional[str] = None
