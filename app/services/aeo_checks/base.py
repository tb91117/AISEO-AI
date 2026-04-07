"""
base.py
-------
Abstract base class that every AEO check must implement.
Each check receives the full BeautifulSoup tree and the pre-stripped plain text,
so individual checks can reach either the DOM or the clean text as needed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from bs4 import BeautifulSoup

from app.models.schemas import CheckResult


class BaseCheck(ABC):
    check_id: str
    name: str
    max_score: int

    @abstractmethod
    def run(self, soup: BeautifulSoup, text: str) -> CheckResult:
        """
        Execute the check.

        Parameters
        ----------
        soup:
            Full BeautifulSoup DOM of the page (with boilerplate intact).
            Use this when you need to query specific HTML elements (<p>, <h1> …).
        text:
            Boilerplate-stripped plain text of the page.
            Use this for readability / corpus-level scoring.

        Returns
        -------
        CheckResult
            Populated result including score, details, and an optional recommendation.
        """
        ...
