"""CEC (California Electrical Code) parser.

Based on NEC structure: articles + dot-sections.
Section numbers: 90.1, 100, 210.12, 230.3 etc.
Also handles "Article 100 — Definitions" headers.
"""
from __future__ import annotations

import re
from .base import BaseCodeParser, RawSection


class CECParser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="CEC", effective_date="2023-01-01")

    _article_pat = re.compile(r"^\s*ARTICLE\s+(\d+)\s*[—–-]?\s*(.*)$", re.IGNORECASE)

    @property
    def section_pattern(self) -> re.Pattern[str]:
        # Matches: 210.12  or  90.1  (NEC article.section style)
        return re.compile(
            r"^\s{0,6}(?P<num>\d{1,3}(?:\.\d{1,4})*)\s{1,4}[A-Z\(]"
        )

    def _handle_extra_header(
        self, line: str, current: RawSection | None
    ) -> RawSection | None:
        ma = self._article_pat.match(line)
        if ma:
            return RawSection(
                section_number=f"Art.{ma.group(1)}",
                title=ma.group(2).strip(),
            )
        return None
