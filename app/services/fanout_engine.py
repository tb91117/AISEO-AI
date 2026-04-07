"""
fanout_engine.py
----------------
Calls OpenAI (GPT-4o-mini) to decompose a user query into 12 sub-queries
across 6 types, with retry + JSON validation.

Environment variables
---------------------
OPENAI_API_KEY  (required)
OPENAI_MODEL    (optional, default: gpt-4o-mini)
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import List

from fastapi import HTTPException

from app.models.schemas import SubQuery, SubQueryType

logger = logging.getLogger(__name__)

_VALID_TYPES = {t.value for t in SubQueryType}

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

# The prompt is a core deliverable — see PROMPT_LOG.md for iteration history.
#
# Key design decisions:
#   • Fixed count (exactly 12, 2 per type) prevents uneven type distribution
#     that appeared in earlier drafts with open-ended "10-15" instructions.
#   • Full worked example uses a *different* topic to prevent the model from
#     merely paraphrasing the example rather than thinking about the new query.
#   • Type definitions explain intent, not just names, so the model produces
#     semantically appropriate queries rather than surface-level keyword matches.
#   • "ONLY a valid JSON object" + strip logic in the parser handles the
#     residual ~5% of responses that still include markdown fences.
#   • Temperature 0.3 reduces variance without sacrificing topic relevance.

_PROMPT_TEMPLATE = """\
You are an AI search query analyst specialising in how AI search engines decompose user queries.

Your task: given a search query, generate sub-queries that simulate how AI search engines such \
as Perplexity, ChatGPT Search, and Google AI Mode would expand the query to build a comprehensive answer.

RULES:
1. Generate EXACTLY 12 sub-queries — exactly 2 from each of the 6 types listed below.
2. Return ONLY a valid JSON object. No markdown, no code fences, no explanation text.
3. Each sub-query must be a real, natural search query — not a description of a query.
4. Sub-queries must be topically relevant to the input query.
5. Use only the type values listed below — no other values are allowed.

THE 6 TYPES:
- comparative      : Compares the subject against alternatives, competitors, or similar options
- feature_specific : Focuses on a specific capability, feature, or attribute of the subject
- use_case         : Describes a real-world application scenario or target audience for the subject
- trust_signals    : Asks about reviews, case studies, testimonials, awards, or credibility proof
- how_to           : Procedural or instructional query about using, implementing, or getting started
- definitional     : Conceptual "what is" or explanatory query about the subject or its context

OUTPUT FORMAT — return exactly this JSON structure, nothing else:
{
  "sub_queries": [
    {"type": "comparative",      "query": "..."},
    {"type": "comparative",      "query": "..."},
    {"type": "feature_specific", "query": "..."},
    {"type": "feature_specific", "query": "..."},
    {"type": "use_case",         "query": "..."},
    {"type": "use_case",         "query": "..."},
    {"type": "trust_signals",    "query": "..."},
    {"type": "trust_signals",    "query": "..."},
    {"type": "how_to",           "query": "..."},
    {"type": "how_to",           "query": "..."},
    {"type": "definitional",     "query": "..."},
    {"type": "definitional",     "query": "..."}
  ]
}

EXAMPLE — for the query "best project management tool for startups":
{
  "sub_queries": [
    {"type": "comparative",      "query": "Asana vs Notion vs Linear for startup project management"},
    {"type": "comparative",      "query": "Monday.com vs Jira for small startup teams"},
    {"type": "feature_specific", "query": "project management tool with GitHub integration for engineers"},
    {"type": "feature_specific", "query": "kanban board with time tracking for startup teams"},
    {"type": "use_case",         "query": "project management software for remote startup team under 20 people"},
    {"type": "use_case",         "query": "agile project tool for seed-stage B2B SaaS startup"},
    {"type": "trust_signals",    "query": "Linear vs Notion startup team reviews and case studies 2025"},
    {"type": "trust_signals",    "query": "best rated project management tool for tech startups"},
    {"type": "how_to",           "query": "how to set up sprint planning in Linear for a startup"},
    {"type": "how_to",           "query": "how to use Notion for project management with a small team"},
    {"type": "definitional",     "query": "what is agile project management for software startups"},
    {"type": "definitional",     "query": "what does kanban mean in startup project planning"}
  ]
}

Now generate sub-queries for this query: "{target_query}"
"""


# ---------------------------------------------------------------------------
# Response parsing + validation
# ---------------------------------------------------------------------------

def _parse_llm_response(raw: str) -> List[SubQuery]:
    """
    Parse and validate a raw LLM string into a list of SubQuery objects.

    Strips markdown fences if present (defensive — the model occasionally
    wraps output in ```json … ``` despite being told not to).
    Raises ValueError or json.JSONDecodeError on any structural problem.
    """
    cleaned = raw.strip()

    # Strip markdown code fences
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        cleaned = "\n".join(lines[start:end])

    data = json.loads(cleaned)  # raises json.JSONDecodeError on bad JSON

    if "sub_queries" not in data:
        raise ValueError("Response missing 'sub_queries' key")

    items = data["sub_queries"]
    if len(items) < 10:
        raise ValueError(f"Too few sub-queries: got {len(items)}, expected at least 10")

    result: List[SubQuery] = []
    for item in items:
        if "type" not in item or "query" not in item:
            raise ValueError(f"Sub-query missing required fields: {item}")
        if item["type"] not in _VALID_TYPES:
            raise ValueError(f"Invalid sub-query type: '{item['type']}'")
        result.append(SubQuery(type=item["type"], query=item["query"]))

    return result


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def generate_sub_queries(
    target_query: str, max_retries: int = 3
) -> tuple[List[SubQuery], str]:
    """
    Generate sub-queries for *target_query* using OpenAI.

    Returns
    -------
    (sub_queries, model_name)

    Raises
    ------
    HTTPException 503 if all retries are exhausted or no API key is set.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "llm_unavailable",
                "message": "No API key configured. Set OPENAI_API_KEY.",
                "detail": "Missing environment variable",
            },
        )

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt = _PROMPT_TEMPLATE.replace("{target_query}", target_query)

    last_error: str = ""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            return _parse_llm_response(response.choices[0].message.content), model_name
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("OpenAI attempt %d/%d — parse error: %s", attempt + 1, max_retries, last_error)
        except Exception as exc:
            last_error = str(exc)
            logger.error("OpenAI attempt %d/%d — call error: %s", attempt + 1, max_retries, last_error)

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # exponential back-off: 1 s, 2 s, 4 s

    raise HTTPException(
        status_code=503,
        detail={
            "error": "llm_unavailable",
            "message": "Fan-out generation failed. The LLM returned an invalid response after 3 retries.",
            "detail": last_error,
        },
    )
