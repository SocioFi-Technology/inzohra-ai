"""CEC (California Electrical Code) parser.

Based on NEC structure: articles + dot-sections.
Section numbers: 90.1, 100, 210.12, 230.3 etc.
Also handles "Article 100 — Definitions" headers.
"""
from __future__ import annotations

import re
from .base import BaseCodeParser, RawSection
from typing import Iterator


class CECParser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="CEC", effective_date="2023-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        # Matches: 210.12  or  90.1  (NEC article.section style)
        return re.compile(
            r"^\s{0,6}(?P<num>\d{1,3}(?:\.\d{1,4})*)\s{1,4}[A-Z\(]"
        )

    def _split_into_sections(self, full_text: str) -> Iterator[RawSection]:
        """Override to also capture Article-level headers."""
        current: RawSection | None = None
        article_pat = re.compile(r"^\s*ARTICLE\s+(\d+)\s*[—–-]?\s*(.*)$", re.IGNORECASE)
        sec_pat = self.section_pattern

        for line in full_text.splitlines():
            stripped = line.strip()

            # Check for Article header
            ma = article_pat.match(line)
            if ma:
                if current is not None:
                    yield current
                num = f"Art.{ma.group(1)}"
                current = RawSection(section_number=num, title=ma.group(2).strip())
                continue

            ms = sec_pat.match(line)
            if ms:
                if current is not None:
                    yield current
                num = ms.group("num")
                title_part = line[ms.end():].strip().rstrip(".")
                current = RawSection(section_number=num, title=title_part)
                continue

            if current is not None and stripped:
                if re.match(r"^\d+$", stripped):
                    continue
                current.body_lines.append(stripped)

        if current is not None:
            yield current
