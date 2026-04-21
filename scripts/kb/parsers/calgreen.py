"""CalGreen (CA Green Building Standards Code) parser.

Section numbers start with 4 (residential) or 5 (non-residential):
4.101.1, 4.303.1.1, 5.410.2 etc.
"""
from __future__ import annotations

import re
from .base import BaseCodeParser


class CalGreenParser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="CALGREEN", effective_date="2023-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        return re.compile(
            r"^\s{0,6}(?P<num>[45]\.\d{3}(?:\.\d{1,4})*)\s{1,4}[A-Z\[]"
        )
