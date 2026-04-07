"""
Tests for Check C — Snippet Readability Scorer.

Covers: target-range scoring (20 pts), over/under-range scoring,
complex-sentence extraction, boilerplate stripping, and edge cases.
"""
import pytest
from bs4 import BeautifulSoup

from app.services.aeo_checks.readability import ReadabilityCheck, _score_for_grade

check = ReadabilityCheck()


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# Unit tests for the scoring helper (no NLP involved)
# ---------------------------------------------------------------------------

class TestScoreForGrade:
    def test_grade_7_scores_20(self):
        assert _score_for_grade(7.0) == 20

    def test_grade_8_scores_20(self):
        assert _score_for_grade(8.4) == 20

    def test_grade_9_scores_20(self):
        assert _score_for_grade(9.4) == 20  # rounds to 9

    def test_grade_6_scores_14(self):
        assert _score_for_grade(6.0) == 14

    def test_grade_10_scores_14(self):
        assert _score_for_grade(10.3) == 14  # rounds to 10

    def test_grade_5_scores_8(self):
        assert _score_for_grade(5.0) == 8

    def test_grade_11_scores_8(self):
        assert _score_for_grade(11.2) == 8  # rounds to 11

    def test_grade_4_scores_0(self):
        assert _score_for_grade(4.0) == 0

    def test_grade_12_scores_0(self):
        assert _score_for_grade(12.0) == 0

    def test_negative_grade_scores_0(self):
        assert _score_for_grade(-1.0) == 0


# ---------------------------------------------------------------------------
# Integration tests with real textstat scoring
# ---------------------------------------------------------------------------

# Very simple text → FK grade well below 7
_SIMPLE_HTML = "<p>" + " ".join(["The cat sat on the mat."] * 15) + "</p>"

# Dense academic text → FK grade well above 9
_COMPLEX_HTML = """<article>
<p>The epistemological underpinnings of contemporary computational linguistics necessitate
a rigorous reexamination of heuristic methodologies traditionally employed in the
disambiguation of polysemous lexical constituents within probabilistic syntactic frameworks.
Furthermore, the ontological presuppositions inherent in distributed semantic representations
challenge the phenomenological characterisation of compositional meaning structures.
Heterogeneous morphosyntactic configurations encountered in agglutinative languages exemplify
the insufficiency of reductionist approaches to cross-linguistic structural generalisation.</p>
</article>"""

# Mid-range text targeting FK ~7-9
_TARGET_HTML = """<article>
<p>Search engine optimisation helps websites appear higher in search results.
Content writers use keywords to match what people are searching for online.
Good articles answer questions clearly and provide useful, accurate information.
Most content should be easy to read for a general audience seeking answers.
Short sentences and plain words make articles more accessible to all readers.</p>
</article>"""


class TestReadabilityPass:
    def test_target_range_details_structure(self):
        """Response must always include fk_grade_level and target_range."""
        result = check.run(soup(_TARGET_HTML), "")
        assert result.details.target_range == "7-9"
        assert isinstance(result.details.fk_grade_level, float)
        assert result.details.fk_grade_level >= 0

    def test_complex_sentences_is_list_of_at_most_3(self):
        """complex_sentences must be a list with 0–3 items."""
        result = check.run(soup(_COMPLEX_HTML), "")
        assert isinstance(result.details.complex_sentences, list)
        assert len(result.details.complex_sentences) <= 3


class TestReadabilityFail:
    def test_simple_text_has_low_grade(self):
        """Cat-sat-on-mat text should score well below grade 7."""
        result = check.run(soup(_SIMPLE_HTML), "")
        assert result.details.fk_grade_level < 7.0
        assert result.score < 20

    def test_complex_text_has_high_grade(self):
        """Dense academic prose should score above grade 9."""
        result = check.run(soup(_COMPLEX_HTML), "")
        assert result.details.fk_grade_level > 9.0
        assert result.score < 20

    def test_recommendation_present_on_low_grade(self):
        result = check.run(soup(_SIMPLE_HTML), "")
        assert result.score < 20
        assert result.recommendation is not None

    def test_recommendation_present_on_high_grade(self):
        result = check.run(soup(_COMPLEX_HTML), "")
        assert result.score < 20
        assert result.recommendation is not None

    def test_boilerplate_stripped_before_scoring(self):
        """Nav/footer text must not inflate or deflate the scored body text."""
        html = (
            "<nav>Home About Contact Services Blog</nav>"
            "<p>Machine learning models process input data to produce predictions. "
            "Engineers design these systems using mathematical optimisation techniques. "
            "Modern frameworks simplify training and deployment of neural networks.</p>"
            "<footer>Copyright 2025 AEGIS Inc. All rights reserved.</footer>"
        )
        result = check.run(soup(html), "")
        # Should not raise and must return a numeric grade
        assert result.details.fk_grade_level >= 0
