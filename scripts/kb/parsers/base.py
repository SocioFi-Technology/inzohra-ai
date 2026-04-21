"""Base class for all code PDF parsers."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pdfplumber


MAX_CHUNK_CHARS = 6000  # ~1200 tokens; split sections larger than this


@dataclass
class RawSection:
    section_number: str
    title: str
    body_lines: list[str] = field(default_factory=list)

    @property
    def body_text(self) -> str:
        return " ".join(line.strip() for line in self.body_lines if line.strip())


class BaseCodeParser(ABC):
    """Extract SeedSection objects from a code PDF."""

    def __init__(self, code: str, effective_date: str) -> None:
        self.code = code
        self.effective_date = effective_date

    @property
    @abstractmethod
    def section_pattern(self) -> re.Pattern[str]:
        """Regex with one named group `num` matching the section number."""
        ...

    def extract_pages(self, pdf_path: Path) -> Iterator[str]:
        """Yield text of each page (skipping blank/image-only pages)."""
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=True) or ""
                text = text.strip()
                if len(text) > 30:  # skip header-only pages
                    yield text

    def parse(self, pdf_path: Path) -> list["SeedSectionLike"]:
        """Main entry point. Returns list of SeedSection-compatible dicts."""
        from app.codekb.seed_data import SeedSection

        # 1. Join all page text
        full_text = "\n".join(self.extract_pages(pdf_path))

        # 2. Split into raw sections
        raw_sections = list(self._split_into_sections(full_text))

        # 3. Convert to SeedSection, chunking large bodies
        results: list[SeedSection] = []
        for raw in raw_sections:
            body = raw.body_text
            if not body or len(body) < 20:
                continue  # skip empty sections
            canonical = self._make_canonical_id(raw.section_number)
            title = raw.title[:200] if raw.title else raw.section_number

            if len(body) <= MAX_CHUNK_CHARS:
                results.append(SeedSection(
                    canonical_id=canonical,
                    code=self.code,
                    section_number=raw.section_number,
                    title=title,
                    body_text=body,
                    effective_date=self.effective_date,
                ))
            else:
                # Split into overlapping chunks
                chunks = self._split_body(body, MAX_CHUNK_CHARS)
                for i, chunk in enumerate(chunks):
                    suffix = f"-chunk-{i+1}" if len(chunks) > 1 else ""
                    results.append(SeedSection(
                        canonical_id=f"{canonical}{suffix}",
                        code=self.code,
                        section_number=raw.section_number,
                        title=f"{title} (part {i+1})" if len(chunks) > 1 else title,
                        body_text=chunk,
                        effective_date=self.effective_date,
                        cross_references=[canonical] if i > 0 else [],
                    ))

        return results

    def _split_into_sections(self, full_text: str) -> Iterator[RawSection]:
        """Scan text line by line, yield RawSection when a header is found."""
        current: RawSection | None = None
        pat = self.section_pattern

        for line in full_text.splitlines():
            m = pat.match(line)
            if m:
                if current is not None:
                    yield current
                num = m.group("num")
                # Rest of the line after the section number is the title
                title_part = line[m.end():].strip()
                # Clean trailing period
                title_clean = title_part.rstrip(".")
                current = RawSection(section_number=num, title=title_clean)
            else:
                # Skip page headers/footers: lines that are all-caps and < 5 words
                stripped = line.strip()
                if current is not None and stripped:
                    # Skip apparent page numbers
                    if re.match(r"^\d+$", stripped):
                        continue
                    current.body_lines.append(stripped)

        if current is not None:
            yield current

    def _make_canonical_id(self, section_number: str) -> str:
        return f"{self.code}-{section_number}"

    @staticmethod
    def _split_body(body: str, max_chars: int) -> list[str]:
        """Split body at sentence boundaries, with 200-char overlap."""
        sentences = re.split(r"(?<=[.!?])\s+", body)
        chunks: list[str] = []
        current_parts: list[str] = []
        current_len = 0
        overlap_buf = ""

        for sent in sentences:
            if current_len + len(sent) > max_chars and current_parts:
                chunk_text = " ".join(current_parts)
                chunks.append(chunk_text)
                # Keep last 200 chars as overlap
                overlap_buf = chunk_text[-200:]
                current_parts = [overlap_buf, sent] if overlap_buf else [sent]
                current_len = len(overlap_buf) + len(sent)
            else:
                current_parts.append(sent)
                current_len += len(sent)

        if current_parts:
            chunks.append(" ".join(current_parts))

        return chunks if chunks else [body[:max_chars]]
