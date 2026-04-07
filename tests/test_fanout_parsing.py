"""
Tests for the fan-out engine's JSON parsing and LLM call logic.

All LLM calls are mocked so these tests run without any API key.
Covers: valid parse, markdown fence stripping, missing key errors,
invalid type rejection, sub-query count validation, and a full
mocked Gemini call that exercises generate_sub_queries().
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import SubQueryType
from app.services.fanout_engine import _parse_llm_response, generate_sub_queries

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_PAYLOAD = {
    "sub_queries": [
        {"type": "comparative",      "query": "Tool A vs Tool B for enterprise teams"},
        {"type": "comparative",      "query": "Tool A vs Tool C pricing comparison 2025"},
        {"type": "feature_specific", "query": "Tool A real-time collaboration features"},
        {"type": "feature_specific", "query": "Tool A API integration and webhook support"},
        {"type": "use_case",         "query": "Tool A for remote marketing teams"},
        {"type": "use_case",         "query": "Tool A for startup content operations at scale"},
        {"type": "trust_signals",    "query": "Tool A customer reviews and case studies 2025"},
        {"type": "trust_signals",    "query": "Tool A G2 Crowd rating and analyst testimonials"},
        {"type": "how_to",           "query": "how to set up Tool A for a content workflow"},
        {"type": "how_to",           "query": "how to integrate Tool A with Slack and Notion"},
        {"type": "definitional",     "query": "what is AI-assisted content optimisation"},
        {"type": "definitional",     "query": "what does content gap analysis mean in SEO"},
    ]
}
_VALID_JSON = json.dumps(_VALID_PAYLOAD)


# ---------------------------------------------------------------------------
# _parse_llm_response — happy paths
# ---------------------------------------------------------------------------

class TestParseLLMResponseValid:
    def test_parses_correct_json(self):
        sub_queries = _parse_llm_response(_VALID_JSON)
        assert len(sub_queries) == 12

    def test_all_six_types_present(self):
        sub_queries = _parse_llm_response(_VALID_JSON)
        found_types = {sq.type.value for sq in sub_queries}
        assert found_types == {t.value for t in SubQueryType}

    def test_exactly_two_per_type(self):
        sub_queries = _parse_llm_response(_VALID_JSON)
        from collections import Counter
        counts = Counter(sq.type.value for sq in sub_queries)
        assert all(v == 2 for v in counts.values())

    def test_strips_json_markdown_fence(self):
        fenced = f"```json\n{_VALID_JSON}\n```"
        sub_queries = _parse_llm_response(fenced)
        assert len(sub_queries) == 12

    def test_strips_plain_markdown_fence(self):
        fenced = f"```\n{_VALID_JSON}\n```"
        sub_queries = _parse_llm_response(fenced)
        assert len(sub_queries) == 12

    def test_leading_trailing_whitespace_ignored(self):
        padded = f"\n\n  {_VALID_JSON}  \n\n"
        sub_queries = _parse_llm_response(padded)
        assert len(sub_queries) == 12


# ---------------------------------------------------------------------------
# _parse_llm_response — error paths
# ---------------------------------------------------------------------------

class TestParseLLMResponseErrors:
    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_response("this is not json at all")

    def test_raises_on_missing_sub_queries_key(self):
        bad = json.dumps({"results": []})
        with pytest.raises(ValueError, match="missing 'sub_queries'"):
            _parse_llm_response(bad)

    def test_raises_on_invalid_type_value(self):
        bad = json.dumps({
            "sub_queries": [{"type": "hallucinated_type", "query": "test"}] * 12
        })
        with pytest.raises(ValueError, match="Invalid sub-query type"):
            _parse_llm_response(bad)

    def test_raises_when_fewer_than_10_sub_queries(self):
        few = json.dumps({
            "sub_queries": [{"type": "comparative", "query": "q"}] * 5
        })
        with pytest.raises(ValueError, match="Too few sub-queries"):
            _parse_llm_response(few)

    def test_raises_on_missing_query_field(self):
        bad = json.dumps({
            "sub_queries": [{"type": "comparative"}] * 12  # no "query" key
        })
        with pytest.raises(ValueError, match="missing required fields"):
            _parse_llm_response(bad)

    def test_raises_on_missing_type_field(self):
        bad = json.dumps({
            "sub_queries": [{"query": "some query"}] * 12  # no "type" key
        })
        with pytest.raises(ValueError, match="missing required fields"):
            _parse_llm_response(bad)


# ---------------------------------------------------------------------------
# generate_sub_queries — mocked OpenAI call
# ---------------------------------------------------------------------------

class TestGenerateSubQueriesMocked:
    def _make_openai_response(self, content: str) -> MagicMock:
        """Build a MagicMock that looks like an OpenAI ChatCompletion response."""
        mock = MagicMock()
        mock.choices[0].message.content = content
        return mock

    def test_successful_openai_call_returns_12_queries(self):
        """Full happy-path: mocked OpenAI returns valid JSON → 12 SubQuery objects."""
        mock_response = self._make_openai_response(_VALID_JSON)

        with patch("openai.OpenAI") as MockClient, \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-abc"}):

            MockClient.return_value.chat.completions.create.return_value = mock_response
            sub_queries, model_name = generate_sub_queries("best AI writing tool")

        assert len(sub_queries) == 12
        assert "gpt" in model_name

    def test_openai_retries_on_bad_json_then_succeeds(self):
        """First call returns invalid JSON; second call returns valid JSON → success."""
        bad_response = self._make_openai_response("not valid json")
        good_response = self._make_openai_response(_VALID_JSON)

        with patch("openai.OpenAI") as MockClient, \
             patch("time.sleep"), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-abc"}):

            MockClient.return_value.chat.completions.create.side_effect = [
                bad_response, good_response
            ]
            sub_queries, model_name = generate_sub_queries("best CRM for startups")

        assert len(sub_queries) == 12

    def test_openai_raises_503_after_all_retries_fail(self):
        """All 3 attempts return invalid JSON → HTTPException 503."""
        from fastapi import HTTPException

        bad_response = self._make_openai_response("still not json")

        with patch("openai.OpenAI") as MockClient, \
             patch("time.sleep"), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-abc"}):

            MockClient.return_value.chat.completions.create.return_value = bad_response
            with pytest.raises(HTTPException) as exc_info:
                generate_sub_queries("test query", max_retries=3)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"] == "llm_unavailable"

    def test_no_api_key_raises_503(self):
        """Missing OPENAI_API_KEY → HTTPException 503 immediately (no LLM call)."""
        from fastapi import HTTPException
        import os

        with patch.dict("os.environ", {}, clear=True):
            os.environ.pop("OPENAI_API_KEY", None)

            with pytest.raises(HTTPException) as exc_info:
                generate_sub_queries("test query")

        assert exc_info.value.status_code == 503
