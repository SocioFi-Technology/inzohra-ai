"""CRC (California Residential Code) parser.

Section numbers: R101.1, R310.2.1, R302.1 etc. — all R-prefix.
"""
from __future__ import annotations

import re
from .base import BaseCodeParser


class CRCParser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="CRC", effective_date="2023-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        return re.compile(
            r"^\s{0,6}(?P<num>R\d{3,4}(?:\.\d{1,4})*)\s{1,4}[A-Z\[]"
        )
