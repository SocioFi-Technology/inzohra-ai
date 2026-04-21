"""Base class for all code PDF parsers."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pdfplumber


MAX_CHUNK_CHARS = 6000   # ~1200 tokens; split sections larger than this
PAGE_BATCH = 80          # pages to hold in memory at once (limits peak RAM)


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

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def parse(self, pdf_path: Path) -> list:
        """Stream the PDF page-by-page in batches to cap peak memory use."""
        from app.codekb.seed_data import SeedSection

        results: list[SeedSection] = []
        current: RawSection | None = None   # section that spans a batch boundary

        with pdfplumber.open(str(pdf_path)) as pdf:
            total = len(pdf.pages)
            batch_lines: list[str] = []

            for idx, page in enumerate(pdf.pages):
                text = (page.extract_text(layout=True) or "").strip()
                if len(text) > 30:
                    batch_lines.extend(text.splitlines())

                at_end = idx == total - 1
                if len(batch_lines) >= PAGE_BATCH * 60 or at_end:  # ~60 lines/page
                    completed, current = self._split_lines(batch_lines, current)
                    for raw in completed:
                        results.extend(self._to_seed_sections(raw))
                    batch_lines = []

        # Flush the last in-progress section
        if current is not None:
            results.extend(self._to_seed_sections(current))

        return results

    # ------------------------------------------------------------------
    # Extension points for subclasses
    # ------------------------------------------------------------------

    def _split_lines(
        self,
        lines: list[str],
        current: RawSection | None,
    ) -> tuple[list[RawSection], RawSection | None]:
        """
        Process a batch of lines.  Returns (completed_sections, carry_over).
        Subclasses override _handle_line to inject extra header patterns.
        """
        completed: list[RawSection] = []
        pat = self.section_pattern

        for line in lines:
            m = pat.match(line)
            if m:
                if current is not None:
                    completed.append(current)
                num = m.group("num")
                title_part = line[m.end():].strip().rstrip(".")
                current = RawSection(section_number=num, title=title_part)
            else:
                result = self._handle_extra_header(line, current)
                if result is not None:
                    # subclass detected a special header; result = new RawSection
                    if current is not None:
                        completed.append(current)
                    current = result
                else:
                    stripped = line.strip()
                    if current is not None and stripped:
                        if re.match(r"^\d+$", stripped):
                            continue   # bare page number
                        current.body_lines.append(stripped)

        return completed, current

    def _handle_extra_header(
        self, line: str, current: RawSection | None
    ) -> RawSection | None:
        """
        Override in subclasses to detect additional header patterns
        (e.g. 'ARTICLE N' in CEC).  Return a new RawSection to start,
        or None to treat the line as body text.
        """
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_seed_sections(self, raw: RawSection) -> list:
        from app.codekb.seed_data import SeedSection

        body = raw.body_text
        if not body or len(body) < 20:
            return []

        canonical = self._make_canonical_id(raw.section_number)
        title = raw.title[:200] if raw.title else raw.section_number

        if len(body) <= MAX_CHUNK_CHARS:
            return [SeedSection(
                canonical_id=canonical,
                code=self.code,
                section_number=raw.section_number,
                title=title,
                body_text=body,
                effective_date=self.effective_date,
            )]

        chunks = self._split_body(body, MAX_CHUNK_CHARS)
        out = []
        for i, chunk in enumerate(chunks):
            suffix = f"-chunk-{i + 1}" if len(chunks) > 1 else ""
            out.append(SeedSection(
                canonical_id=f"{canonical}{suffix}",
                code=self.code,
                section_number=raw.section_number,
                title=f"{title} (part {i + 1})" if len(chunks) > 1 else title,
                body_text=chunk,
                effective_date=self.effective_date,
                cross_references=[canonical] if i > 0 else [],
            ))
        return out

    def _make_canonical_id(self, section_number: str) -> str:
        return f"{self.code}-{section_number}"

    @staticmethod
    def _split_body(body: str, max_chars: int) -> list[str]:
        """Split at sentence boundaries with 200-char overlap."""
        sentences = re.split(r"(?<=[.!?])\s+", body)
        chunks: list[str] = []
        current_parts: list[str] = []
        current_len = 0

        for sent in sentences:
            if current_len + len(sent) > max_chars and current_parts:
                chunk_text = " ".join(current_parts)
                chunks.append(chunk_text)
                overlap = chunk_text[-200:]
                current_parts = [overlap, sent] if overlap else [sent]
                current_len = len(overlap) + len(sent)
            else:
                current_parts.append(sent)
                current_len += len(sent)

        if current_parts:
            chunks.append(" ".join(current_parts))

        return chunks if chunks else [body[:max_chars]]
