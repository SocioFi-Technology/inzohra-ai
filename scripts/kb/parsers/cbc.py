"""CBC (California Building Code) parser — volumes 1 and 2.

Section numbers: 101.1, 107.2.1, 1601.1.2, 11B-202.4, etc.
Special: Chapter 11B sections use hyphen prefix (11B-xxx).
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import BaseCodeParser


class CBCParser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="CBC", effective_date="2023-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        # Matches:  107.2.1  or  11B-202.4  or  1101A.1
        return re.compile(
            r"^\s{0,6}"
            r"(?P<num>"
            r"(?:\d{1,4}[A-Z]?[-][A-Z\d]+(?:\.\d{1,4})*"  # 11B-202.4 style
            r"|\d{1,4}[A-Z]?(?:\.\d{1,4})+"               # 107.2.1 style
            r")"
            r")\s{1,4}[A-Z\[]"   # followed by space then uppercase or [Exception]
        )
