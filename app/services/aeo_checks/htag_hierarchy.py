"""
htag_hierarchy.py
-----------------
Check B — H-tag Hierarchy Checker (max 20 pts)

Validates that the heading structure follows a logical H1 → H2 → H3 sequence
with no skipped levels, no duplicate H1s, and nothing appearing before the H1.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from app.models.schemas import CheckResult, HtagHierarchyDetails
from app.services.aeo_checks.base import BaseCheck


class HtagHierarchyCheck(BaseCheck):
    check_id = "htag_hierarchy"
    name = "H-tag Hierarchy"
    max_score = 20

    def run(self, soup: BeautifulSoup, text: str) -> CheckResult:
        h_tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        tag_names = [tag.name for tag in h_tags]           # e.g. ["h1", "h2", "h3"]
        tag_levels = [int(name[1]) for name in tag_names]  # e.g. [1, 2, 3]

        violations: list[str] = []

        # Rule 1 — exactly one H1
        h1_count = tag_names.count("h1")
        if h1_count == 0:
            violations.append("Missing H1: no H1 heading found in the content.")
        elif h1_count > 1:
            violations.append(
                f"Multiple H1s: found {h1_count} H1 headings; there must be exactly one."
            )

        # Rule 2 — nothing before H1 (only meaningful when an H1 exists)
        if h1_count >= 1:
            h1_index = tag_names.index("h1")
            if h1_index > 0:
                before = ", ".join(tag_names[:h1_index]).upper()
                violations.append(
                    f"Tag before H1: {before} appear(s) before the H1 heading."
                )

        # Rule 3 — no skipped levels (checked in DOM order, after the first H1)
        if tag_levels:
            prev = tag_levels[0]
            for pos, level in enumerate(tag_levels[1:], start=2):
                if level > prev + 1:
                    violations.append(
                        f"Skipped heading level: H{prev} jumps to H{level} "
                        f"at position {pos} (H{prev + 1} is missing)."
                    )
                prev = level

        # --- Scoring ---
        n = len(violations)
        if n == 0:
            score = 20
        elif n <= 2 and h1_count > 0:
            score = 12
        else:
            score = 0

        passed = score == 20

        if passed:
            recommendation = None
        else:
            recommendation = (
                f"Fix {n} heading structure issue(s): "
                + "; ".join(violations)
            )

        return CheckResult(
            check_id=self.check_id,
            name=self.name,
            passed=passed,
            score=score,
            max_score=self.max_score,
            details=HtagHierarchyDetails(
                violations=violations,
                h_tags_found=tag_names,
            ),
            recommendation=recommendation,
        )
