"""
readability.py
--------------
Check C — Snippet Readability Scorer (max 20 pts)

Scores content against the Flesch-Kincaid Grade Level target of 7–9
and surfaces the three most complex sentences to guide revision.
"""
from __future__ import annotations

import textstat
from bs4 import BeautifulSoup

from app.models.schemas import CheckResult, ReadabilityDetails
from app.services.aeo_checks.base import BaseCheck


def _syllable_density(sentence: str) -> float:
    """Syllables-per-word ratio — used to rank sentence complexity."""
    words = sentence.split()
    if not words:
        return 0.0
    return textstat.syllable_count(sentence) / len(words)


def _top_complex_sentences(text: str, n: int = 3) -> list[str]:
    """
    Split *text* into sentences and return the *n* with the highest
    syllable density (syllables ÷ word count).  Sentences with fewer
    than 5 words are excluded to avoid sentence-boundary fragments.
    """
    # Simple sentence splitting; spaCy would be more robust but adds latency
    raw_sentences = []
    for chunk in text.replace("!", ".").replace("?", ".").split("."):
        s = chunk.strip()
        if len(s.split()) >= 5:
            raw_sentences.append(s)

    ranked = sorted(raw_sentences, key=_syllable_density, reverse=True)
    return ranked[:n]


def _score_for_grade(fk_grade: float) -> int:
    """
    Map a (potentially fractional) FK grade to the spec-defined score bands.
    We round to the nearest integer so that e.g. 6.7 maps to grade 7 (score 20)
    and 9.4 maps to grade 9 (score 20), while 9.6 maps to grade 10 (score 14).
    """
    grade = round(fk_grade)
    if 7 <= grade <= 9:
        return 20
    if grade in (6, 10):
        return 14
    if grade in (5, 11):
        return 8
    return 0


class ReadabilityCheck(BaseCheck):
    check_id = "readability"
    name = "Snippet Readability"
    max_score = 20

    def run(self, soup: BeautifulSoup, text: str) -> CheckResult:
        # `text` is already boilerplate-stripped (passed in by the endpoint)
        clean = text.strip() if text.strip() else soup.get_text(separator=" ", strip=True)

        # textstat can return negative values for very short texts — clamp to 0
        fk_grade = max(0.0, textstat.flesch_kincaid_grade(clean))
        score = _score_for_grade(fk_grade)
        passed = score == 20

        complex_sentences = _top_complex_sentences(clean)

        if passed:
            recommendation = None
        elif fk_grade < 7:
            recommendation = (
                f"Content reads at Grade {fk_grade:.1f}. "
                "Add more depth and precise vocabulary to reach Grade 7–9."
            )
        else:
            recommendation = (
                f"Content reads at Grade {fk_grade:.1f}. "
                "Shorten sentences and replace technical jargon with plain language "
                "to reach Grade 7–9."
            )

        return CheckResult(
            check_id=self.check_id,
            name=self.name,
            passed=passed,
            score=score,
            max_score=self.max_score,
            details=ReadabilityDetails(
                fk_grade_level=round(fk_grade, 1),
                target_range="7-9",
                complex_sentences=complex_sentences,
            ),
            recommendation=recommendation,
        )
