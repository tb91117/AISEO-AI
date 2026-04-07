"""
content_parser.py
-----------------
Responsible for fetching and cleaning HTML content from a URL or raw text input.
"""
from __future__ import annotations

from copy import deepcopy

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

# Tags whose content is considered boilerplate and excluded from readability scoring
_BOILERPLATE_TAGS = ["nav", "footer", "header", "script", "style", "aside", "form", "noscript"]


def fetch_content(input_type: str, input_value: str) -> BeautifulSoup:
    """Return a BeautifulSoup object from a URL or raw HTML/text string."""
    if input_type == "url":
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                response = client.get(
                    input_value,
                    headers={"User-Agent": "Mozilla/5.0 AEGIS/1.0"},
                )
                response.raise_for_status()
                html = response.text
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "url_fetch_failed",
                    "message": "Could not retrieve content from the provided URL.",
                    "detail": "Connection timeout after 10s",
                },
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "url_fetch_failed",
                    "message": "Could not retrieve content from the provided URL.",
                    "detail": f"HTTP {exc.response.status_code}",
                },
            )
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "url_fetch_failed",
                    "message": "Could not retrieve content from the provided URL.",
                    "detail": str(exc),
                },
            )
    else:
        html = input_value

    return BeautifulSoup(html, "html.parser")


def extract_first_paragraph(soup: BeautifulSoup) -> str:
    """
    Return the text of the first meaningful paragraph.

    Strips boilerplate elements first so navigation <p> tags are not selected.
    Falls back to splitting plain text on double newlines if no <p> tag is found.
    """
    soup_copy = deepcopy(soup)
    for tag in _BOILERPLATE_TAGS:
        for element in soup_copy.find_all(tag):
            element.decompose()

    p = soup_copy.find("p")
    if p:
        return p.get_text(separator=" ", strip=True)

    # Plain-text fallback — split on blank lines
    raw_text = soup_copy.get_text()
    paragraphs = [block.strip() for block in raw_text.split("\n\n") if block.strip()]
    return paragraphs[0] if paragraphs else ""


def strip_boilerplate(soup: BeautifulSoup) -> str:
    """
    Remove nav, footer, header, scripts, and other boilerplate elements and
    return the remaining text content as a single string.
    """
    soup_copy = deepcopy(soup)
    for tag in _BOILERPLATE_TAGS:
        for element in soup_copy.find_all(tag):
            element.decompose()

    return soup_copy.get_text(separator=" ", strip=True)
