from fastapi import APIRouter

from app.models.schemas import AEOAnalyzeRequest, AEOAnalyzeResponse
from app.services.aeo_checks.direct_answer import DirectAnswerCheck
from app.services.aeo_checks.htag_hierarchy import HtagHierarchyCheck
from app.services.aeo_checks.readability import ReadabilityCheck
from app.services.content_parser import fetch_content, strip_boilerplate

router = APIRouter()

_CHECKS = [DirectAnswerCheck(), HtagHierarchyCheck(), ReadabilityCheck()]
_MAX_RAW = sum(c.max_score for c in _CHECKS)  # 60


def _band(score: float) -> str:
    if score >= 85:
        return "AEO Optimized"
    if score >= 65:
        return "Needs Improvement"
    if score >= 40:
        return "Significant Gaps"
    return "Not AEO Ready"


@router.post("/analyze", response_model=AEOAnalyzeResponse)
def analyze(request: AEOAnalyzeRequest) -> AEOAnalyzeResponse:
    """
    Score content across three NLP checks and return an AEO Readiness Score (0–100).

    Accepts either a URL (fetched with httpx) or raw HTML / plain text.
    FastAPI runs sync endpoints in a thread pool automatically, which is
    appropriate here because spaCy and textstat are CPU-bound.
    """
    soup = fetch_content(request.input_type, request.input_value)
    text = strip_boilerplate(soup)  # shared clean-text for readability check

    results = [check.run(soup, text) for check in _CHECKS]

    raw_score = sum(r.score for r in results)
    aeo_score = round((raw_score / _MAX_RAW) * 100, 1)

    return AEOAnalyzeResponse(
        aeo_score=aeo_score,
        band=_band(aeo_score),
        checks=results,
    )
