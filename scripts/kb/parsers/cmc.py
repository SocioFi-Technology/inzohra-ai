"""CMC (California Mechanical Code) parser."""
from __future__ import annotations

import re
from .base import BaseCodeParser


class CMCParser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="CMC", effective_date="2023-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        return re.compile(
            r"^\s{0,6}(?P<num>\d{3,4}(?:\.\d{1,4})*)\s{1,4}[A-Z\[]"
        )
