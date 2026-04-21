"""CAC (California Administrative Code / Title 24 Part 1) parser.

Section numbers: 1-101, 1-307 etc. — formatted as "1-101. Title text"
or "Section 1-101." in the body of the PDF.
"""
from __future__ import annotations

import re
from .base import BaseCodeParser


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
