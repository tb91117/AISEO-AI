"""
Tests for Check A — Direct Answer Detection.

Each test exercises the check in isolation (no endpoint, no HTTP).
Covers: word-count boundaries, hedge phrases, declarative detection,
missing paragraphs, and recommendation presence/absence.
"""
import pytest
from bs4 import BeautifulSoup

from app.services.aeo_checks.direct_answer import DirectAnswerCheck

check = DirectAnswerCheck()


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# Passing cases
# ---------------------------------------------------------------------------

class TestDirectAnswerPass:
    def test_perfect_score_short_declarative(self):
        """≤60 words, declarative, no hedge → 20 pts."""
        html = (
            "<p>Python is a high-level programming language known for its "
            "simplicity and readability, making it popular among developers.</p>"
        )
        result = check.run(soup(html), "")
        assert result.score == 20
        assert result.passed is True
        assert result.details.is_declarative is True
        assert result.details.has_hedge_phrase is False
        assert result.recommendation is None

    def test_word_count_at_boundary_60(self):
        """Exactly 60 words + no hedge → score must be 12 or 20 (≤60 branch)."""
        # "FastAPI is a modern web framework." = 6 words; 54 pads = 60 total
        words = ["word"] * 54
        html = f"<p>FastAPI is a modern web framework. {' '.join(words)}</p>"
        result = check.run(soup(html), "")
        assert result.details.word_count == 60
        assert result.score in (12, 20)  # depends on declarative detection


# ---------------------------------------------------------------------------
# Failing cases
# ---------------------------------------------------------------------------

class TestDirectAnswerFail:
    def test_zero_score_over_90_words(self):
        """Word count > 90 → 0 pts."""
        long_para = " ".join(["word"] * 95)
        html = f"<p>{long_para}</p>"
        result = check.run(soup(html), "")
        assert result.score == 0
        assert result.passed is False
        assert result.details.word_count > 90
        assert "Trim" in result.recommendation

    def test_partial_score_hedge_phrase_it_depends(self):
        """≤60 words but contains 'it depends' → 12 pts."""
        html = (
            "<p>It depends on your specific use case and the requirements "
            "of the project you are building with this framework.</p>"
        )
        result = check.run(soup(html), "")
        assert result.score == 12
        assert result.details.has_hedge_phrase is True
        assert result.details.word_count <= 60

    def test_partial_score_hedge_phrase_may_vary(self):
        """'may vary' is also a penalised hedge."""
        html = "<p>Performance may vary depending on the hardware configuration used in production.</p>"
        result = check.run(soup(html), "")
        assert result.details.has_hedge_phrase is True
        assert result.score == 12

    def test_partial_score_61_to_90_words(self):
        """61–90 word paragraph → 8 pts regardless of quality."""
        mid = " ".join(["word"] * 70)
        html = f"<p>{mid}</p>"
        result = check.run(soup(html), "")
        assert result.score == 8
        assert 61 <= result.details.word_count <= 90

    def test_no_paragraph_gracefully_handled(self):
        """Content with no <p> tag falls back to text splitting; should not raise."""
        html = "<div>No paragraph element here at all</div>"
        result = check.run(soup(html), "")
        # Either 0 (empty fallback) or a valid score — must not crash
        assert result.score >= 0
        assert isinstance(result.details.word_count, int)

    def test_hedge_phrase_case_insensitive(self):
        """Hedge detection is case-insensitive."""
        html = "<p>Generally Speaking, this approach works for most software teams.</p>"
        result = check.run(soup(html), "")
        assert result.details.has_hedge_phrase is True

    def test_recommendation_present_on_imperfect_score(self):
        """Any non-perfect score must include a recommendation."""
        html = f"<p>{' '.join(['word'] * 70)}</p>"
        result = check.run(soup(html), "")
        assert result.score < 20
        assert result.recommendation is not None and len(result.recommendation) > 0
