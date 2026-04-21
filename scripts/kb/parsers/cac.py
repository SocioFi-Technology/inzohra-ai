"""CAC (California Administrative Code / Title 24 Part 1) parser.

Section numbers: 1-101, 1-307 etc. — formatted as "1-101. Title text"
or "Section 1-101." in the body of the PDF.
"""
from __future__ import annotations

import re
from typing import Iterator
from .base import BaseCodeParser, RawSection


class CACParser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="CAC", effective_date="2023-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        # CAC uses: "1-101. Abbreviations." at line start (period after number)
        # Also matches plain numeric like "101.1 Title"
        return re.compile(
            r"^\s{0,6}(?P<num>\d+[-\u2013]\d+(?:\.\d{1,4})*|\d{3,4}(?:\.\d{1,4})*)(?:\.|\.|\s{1,4})[A-Z\[]"
        )

    def _split_into_sections(self, full_text: str) -> Iterator[RawSection]:
        """Override to handle CAC's 'N-NNN. Title.' section format."""
        current: RawSection | None = None
        # Pattern: "1-101. Title." or "1-101 Title" at line start
        sec_pat = re.compile(
            r"^\s{0,6}(?P<num>\d{1,4}-\d{1,4}(?:\.\d{1,4})*)\.?\s+(?P<title>[A-Z][^\n]{2,80})"
        )
        # Also match plain numeric sections: "101.1 Title"
        num_pat = re.compile(
            r"^\s{0,6}(?P<num>\d{3,4}(?:\.\d{1,4})+)\s{1,4}(?P<title>[A-Z][^\n]{2,80})"
        )

        for line in full_text.splitlines():
            stripped = line.strip()

            m = sec_pat.match(line) or num_pat.match(line)
            if m:
                if current is not None:
                    yield current
                num = m.group("num")
                title = m.group("title").rstrip(".").strip()
                current = RawSection(section_number=num, title=title)
                continue

            if current is not None and stripped:
                if re.match(r"^\d+$", stripped):
                    continue
                current.body_lines.append(stripped)

        if current is not None:
            yield current
