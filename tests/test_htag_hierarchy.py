"""
Tests for Check B — H-tag Hierarchy Checker.

Covers: valid hierarchy, missing H1, multiple H1s, skipped levels,
tags appearing before H1, DOM order tracking, and scoring thresholds.
"""
import pytest
from bs4 import BeautifulSoup

from app.services.aeo_checks.htag_hierarchy import HtagHierarchyCheck

check = HtagHierarchyCheck()


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# Passing cases
# ---------------------------------------------------------------------------

class TestHtagHierarchyPass:
    def test_perfect_valid_hierarchy(self):
        """H1 → H2 → H3 → H2 with no violations → 20 pts."""
        html = "<h1>Title</h1><h2>Section A</h2><h3>Subsection</h3><h2>Section B</h2>"
        result = check.run(soup(html), "")
        assert result.score == 20
        assert result.passed is True
        assert result.details.violations == []
        assert result.recommendation is None

    def test_h1_only_is_valid(self):
        """A page with only an H1 has no hierarchy violations."""
        html = "<h1>The Only Heading</h1><p>Some content.</p>"
        result = check.run(soup(html), "")
        assert result.score == 20
        assert result.details.violations == []

    def test_h_tags_found_in_dom_order(self):
        """h_tags_found must reflect DOM order exactly."""
        html = "<h1>A</h1><h2>B</h2><h2>C</h2><h3>D</h3>"
        result = check.run(soup(html), "")
        assert result.details.h_tags_found == ["h1", "h2", "h2", "h3"]


# ---------------------------------------------------------------------------
# Failing cases
# ---------------------------------------------------------------------------

class TestHtagHierarchyFail:
    def test_zero_score_missing_h1(self):
        """No H1 → score 0 (spec: missing H1 → 0)."""
        html = "<h2>Section</h2><h3>Subsection</h3><p>Content.</p>"
        result = check.run(soup(html), "")
        assert result.score == 0
        assert result.passed is False
        assert any("H1" in v or "h1" in v.lower() for v in result.details.violations)

    def test_partial_score_multiple_h1(self):
        """Two H1 headings is 1 violation → 12 pts."""
        html = "<h1>First Title</h1><h2>Section</h2><h1>Second Title</h1>"
        result = check.run(soup(html), "")
        # Multiple H1 is 1 violation; score should be 12 (not 0, since H1 exists)
        assert result.score == 12
        assert any("Multiple" in v or "multiple" in v.lower() for v in result.details.violations)

    def test_violation_skipped_level_h1_to_h3(self):
        """H1 jumping directly to H3 (missing H2) is a violation."""
        html = "<h1>Title</h1><h3>Skipped to H3</h3>"
        result = check.run(soup(html), "")
        assert len(result.details.violations) > 0
        assert any("Skipped" in v or "skip" in v.lower() for v in result.details.violations)

    def test_violation_tag_before_h1(self):
        """H2 appearing before the H1 is a violation."""
        html = "<h2>Preamble</h2><h1>Actual Title</h1><h2>Section</h2>"
        result = check.run(soup(html), "")
        assert any("before" in v.lower() for v in result.details.violations)

    def test_zero_score_three_violations(self):
        """Three or more violations → 0 pts."""
        # Multiple H1 (1) + tag before H1 (1) + skipped level (1) = 3 violations
        html = "<h2>Before</h2><h1>Title</h1><h1>Second Title</h1><h3>Skipped</h3>"
        result = check.run(soup(html), "")
        assert result.score == 0

    def test_no_headings_scores_zero(self):
        """Page with no heading elements at all → missing H1 → 0 pts."""
        html = "<p>Just a paragraph, no headings.</p>"
        result = check.run(soup(html), "")
        assert result.score == 0
        assert result.details.h_tags_found == []

    def test_recommendation_included_on_violations(self):
        """Any violations must produce a non-empty recommendation."""
        html = "<h2>No H1 here</h2>"
        result = check.run(soup(html), "")
        assert result.score < 20
        assert result.recommendation is not None and len(result.recommendation) > 0
