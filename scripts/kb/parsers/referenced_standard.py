"""Parser for referenced standards: ASCE 7, ACI 318, NDS, AISC.

These have varying formats; we use a chapter+section approach.
"""
from __future__ import annotations

import re
from .base import BaseCodeParser


class ASCE7Parser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="ASCE7", effective_date="2016-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        # Matches: 11.4.1  or  C11.4.1 (commentary prefix)
        return re.compile(
            r"^\s{0,6}(?P<num>C?\d{1,2}(?:\.\d{1,4})+)\s{1,4}[A-Z\[]"
        )


class ACI318Parser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="ACI318", effective_date="2019-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        return re.compile(
            r"^\s{0,6}(?P<num>\d{1,2}(?:\.\d{1,4})+)\s{1,4}[A-Z\[]"
        )


class NDSParser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="NDS", effective_date="2018-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        return re.compile(
            r"^\s{0,6}(?P<num>\d{1,2}(?:\.\d{1,4})+)\s{1,4}[A-Z\[]"
        )


class AISCParser(BaseCodeParser):
    def __init__(self) -> None:
        super().__init__(code="AISC", effective_date="2005-01-01")

    @property
    def section_pattern(self) -> re.Pattern[str]:
        # AISC uses letter-prefixed sections: A1, B1.1, C2.1
        return re.compile(
            r"^\s{0,6}(?P<num>[A-K]\d{1,2}(?:\.\d{1,4})*)\s{1,4}[A-Z\[]"
        )
