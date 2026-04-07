from fastapi import APIRouter

from app.models.schemas import FanoutGenerateRequest, FanoutGenerateResponse
from app.services.fanout_engine import generate_sub_queries
from app.services.gap_analyzer import analyze_gaps

router = APIRouter()


@router.post("/generate", response_model=FanoutGenerateResponse)
def generate(request: FanoutGenerateRequest) -> FanoutGenerateResponse:
    """
    Decompose *target_query* into 12 sub-queries across 6 intent types via LLM.

    When *existing_content* is provided, each sub-query is additionally scored
    against the content using sentence-transformer cosine similarity and a
    gap summary is included in the response.
    """
    sub_queries, model_used = generate_sub_queries(request.target_query)

    gap_summary = None
    if request.existing_content:
        sub_queries, gap_summary = analyze_gaps(sub_queries, request.existing_content)

    return FanoutGenerateResponse(
        target_query=request.target_query,
        model_used=model_used,
        total_sub_queries=len(sub_queries),
        sub_queries=sub_queries,
        gap_summary=gap_summary,
    )
