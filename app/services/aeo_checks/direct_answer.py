"""
direct_answer.py
----------------
Check A — Direct Answer Detection (max 20 pts)

Tests whether the first paragraph answers the primary query in ≤ 60 words
with a clear declarative statement and no hedging language.
"""
from __future__ import annotations

from functools import lru_cache

import spacy
from bs4 import BeautifulSoup

from app.models.schemas import CheckResult, DirectAnswerDetails
from app.services.aeo_checks.base import BaseCheck
from app.services.content_parser import extract_first_paragraph

# Phrases that signal vague, non-committal answers — each penalises the score
_HEDGE_PHRASES = [
    "it depends",
    "may vary",
    "in some cases",
    "this varies",
    "generally speaking",
]


@lru_cache(maxsize=1)
def _load_nlp() -> spacy.language.Language:
    """Load spaCy model once per process; prefer lg for better dependency parsing."""
    try:
        return spacy.load("en_core_web_lg")
    except OSError:
        return spacy.load("en_core_web_sm")


def _is_declarative(text: str) -> bool:
    """
    Return True if *text* contains at least one complete declarative sentence.

    Uses spaCy's dependency parser to verify the presence of a nominal subject
    (nsubj / nsubjpass) and a root verb in the same sentence.  A question or
    bare fragment will fail this check.
    """
    if not text.strip():
        return False

    nlp = _load_nlp()
    doc = nlp(text[:1000])  # cap to keep latency predictable

    for sent in doc.sents:
        has_subject = any(tok.dep_ in ("nsubj", "nsubjpass") for tok in sent)
        has_root_verb = any(tok.dep_ == "ROOT" and tok.pos_ in ("VERB", "AUX") for tok in sent)
        if has_subject and has_root_verb:
            return True

    return False


class DirectAnswerCheck(BaseCheck):
    check_id = "direct_answer"
    name = "Direct Answer Detection"
    max_score = 20

    def run(self, soup: BeautifulSoup, text: str) -> CheckResult:
        paragraph = extract_first_paragraph(soup)
        word_count = len(paragraph.split()) if paragraph else 0
        lower_para = paragraph.lower()

        has_hedge = any(phrase in lower_para for phrase in _HEDGE_PHRASES)
        is_declarative = _is_declarative(paragraph)

        # --- Scoring (spec-exact) ---
        if word_count <= 60:
            score = 20 if (is_declarative and not has_hedge) else 12
        elif word_count <= 90:
            score = 8
        else:
            score = 0

        passed = score == 20

        # --- Recommendation ---
        if passed:
            recommendation = None
        elif word_count > 90:
            recommendation = (
                f"Your opening paragraph is {word_count} words. "
                "Trim it to under 60 words with a direct, declarative answer."
            )
        elif word_count > 60:
            recommendation = (
                f"Your opening paragraph is {word_count} words. "
                "Trim it to under 60 words."
            )
        elif has_hedge:
            recommendation = (
                "Remove hedging phrases (e.g. 'it depends', 'may vary') "
                "from your opening paragraph to make your answer definitive."
            )
        else:
            recommendation = (
                "Your opening paragraph should be a complete declarative statement "
                "with a clear subject and verb."
            )

        return CheckResult(
            check_id=self.check_id,
            name=self.name,
            passed=passed,
            score=score,
            max_score=self.max_score,
            details=DirectAnswerDetails(
                word_count=word_count,
                threshold=60,
                is_declarative=is_declarative,
                has_hedge_phrase=has_hedge,
            ),
            recommendation=recommendation,
        )
