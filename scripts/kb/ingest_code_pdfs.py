#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ingest Building Code PDFs into the code_sections KB table.

Parses each PDF in the 'Building Codes/' directory, splits the text into
individual code sections, embeds them using text-embedding-3-large (or the
HashEmbedder fallback), and upserts into the code_sections table.

Usage (from repo root)::

    # Dry run — print section counts without writing to DB
    uv run scripts/kb/ingest_code_pdfs.py --dry-run

    # Real run — embeds and upserts all sections
    uv run scripts/kb/ingest_code_pdfs.py

    # Single code only
    uv run scripts/kb/ingest_code_pdfs.py --code CRC

    # Custom codes dir (default: "Building Codes")
    uv run scripts/kb/ingest_code_pdfs.py --codes-dir "Building Codes"

Requires OPENAI_API_KEY and DATABASE_URL in .env (or environment).
Idempotent: existing (canonical_id, effective_date) rows are skipped.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve repo root and load .env
# scripts/kb/ingest_code_pdfs.py → scripts/kb/ → scripts/ → repo root
# ---------------------------------------------------------------------------

_repo_root = Path(__file__).resolve().parent.parent.parent

# Add scripts/kb/ to sys.path so relative parser imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_repo_root / ".env", override=True)

# ---------------------------------------------------------------------------
# Imports after env load
# ---------------------------------------------------------------------------

import psycopg  # noqa: E402
import psycopg.rows  # noqa: E402

from app.codekb.embedder import EMBED_DIM, get_embedder  # noqa: E402
from app.codekb.seed_data import SeedSection  # noqa: E402

# Import parsers
from parsers.cbc import CBCParser  # noqa: E402
from parsers.crc import CRCParser  # noqa: E402
from parsers.cpc import CPCParser  # noqa: E402
from parsers.cmc import CMCParser  # noqa: E402
from parsers.cec import CECParser  # noqa: E402
from parsers.calgreen import CalGreenParser  # noqa: E402
from parsers.cfc import CFCParser  # noqa: E402
from parsers.cac import CACParser  # noqa: E402
from parsers.referenced_standard import ASCE7Parser, ACI318Parser, NDSParser, AISCParser  # noqa: E402

# ---------------------------------------------------------------------------
# PDF -> Parser registry
# Filename substring match (case-insensitive) -> parser instance
# ---------------------------------------------------------------------------

PDF_REGISTRY: list[tuple[str, object]] = [
    ("building code vol 1",  CBCParser()),
    ("building code vol 2",  CBCParser()),
    ("residential code",     CRCParser()),
    ("plumbing",             CPCParser()),
    ("mechanical",           CMCParser()),
    ("electrical",           CECParser()),
    ("fire code",            CFCParser()),
    ("green building",       CalGreenParser()),
    ("admin",                CACParser()),
    ("aci 318",              ACI318Parser()),
    ("asce 7",               ASCE7Parser()),
    ("nds-2018-171117",      NDSParser()),
    ("nds-2018-supplement",  NDSParser()),
    ("aisc",                 AISCParser()),
]

BATCH_SIZE = 20


def find_parser(pdf_path: Path) -> object | None:
    name_lower = pdf_path.name.lower()
    for substring, parser in PDF_REGISTRY:
        if substring.lower() in name_lower:
            return parser
    return None


def collect_pdfs(codes_dir: Path) -> list[Path]:
    """Recursively find all PDFs under codes_dir."""
    return sorted(codes_dir.rglob("*.pdf"))


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def upsert_sections(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    sections: list[SeedSection],
    vectors: list[list[float]],
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    for section, vec in zip(sections, vectors, strict=True):
        result = conn.execute(
            """
            INSERT INTO code_sections (
                canonical_id, code, section_number, title,
                body_text, effective_date, embedding,
                cross_references, referenced_standards
            )
            SELECT
                %(cid)s, %(code)s, %(snum)s, %(title)s,
                %(body)s, %(eff)s::date, %(vec)s::vector,
                %(xrefs)s, %(stdards)s
            WHERE NOT EXISTS (
                SELECT 1 FROM code_sections
                 WHERE canonical_id  = %(cid)s
                   AND effective_date = %(eff)s::date
            )
            """,
            {
                "cid":    section.canonical_id,
                "code":   section.code,
                "snum":   section.section_number,
                "title":  section.title,
                "body":   section.body_text,
                "eff":    section.effective_date,
                "vec":    _vec_literal(vec),
                "xrefs":  section.cross_references or [],
                "stdards": section.referenced_standards or [],
            },
        )
        if result.rowcount == 1:
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


def process_pdf(
    pdf_path: Path,
    parser: object,
    embedder: object,
    conn: psycopg.Connection | None,  # type: ignore[type-arg]
    dry_run: bool,
) -> tuple[int, int]:
    """Parse, embed, upsert one PDF. Returns (inserted, skipped)."""
    print(f"\n  {pdf_path.name}")

    try:
        sections: list[SeedSection] = parser.parse(pdf_path)  # type: ignore[attr-defined]
    except Exception as e:
        print(f"     WARN parse error: {e}")
        return 0, 0

    print(f"     sections parsed: {len(sections)}")

    if dry_run or not sections:
        if dry_run:
            # Show sample of section IDs
            sample = [s.canonical_id for s in sections[:5]]
            print(f"     sample IDs: {sample}")
        return 0, 0

    # Embed in batches
    all_vectors: list[list[float]] = []
    texts = [s.body_text for s in sections]
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i: i + BATCH_SIZE]
        vecs = embedder.embed(batch)  # type: ignore[attr-defined]
        all_vectors.extend(vecs)
        done = min(i + BATCH_SIZE, len(texts))
        print(f"     embedded {done}/{len(texts)}", end="\r")
    print()

    # Validate dimensions
    if all_vectors and len(all_vectors[0]) != EMBED_DIM:
        print(f"     WARN dim mismatch: expected {EMBED_DIM}, got {len(all_vectors[0])}")
        return 0, 0

    # Upsert
    assert conn is not None
    with conn.transaction():
        inserted, skipped = upsert_sections(conn, sections, all_vectors)

    print(f"     inserted={inserted}  skipped={skipped}")
    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Building Code PDFs into code_sections KB")
    parser.add_argument(
        "--codes-dir",
        default="Building Codes",
        help="Path to Building Codes folder (relative to repo root or absolute)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse PDFs and report section counts without writing to DB",
    )
    parser.add_argument(
        "--code",
        default=None,
        help="Only process a specific code (e.g. CRC, CBC, ASCE7)",
    )
    args = parser.parse_args()

    # Resolve codes dir
    codes_path = Path(args.codes_dir)
    if not codes_path.is_absolute():
        codes_path = _repo_root / codes_path
    if not codes_path.exists():
        print(f"ERROR: codes-dir not found: {codes_path}", file=sys.stderr)
        sys.exit(1)

    pdfs = collect_pdfs(codes_path)
    if not pdfs:
        print(f"ERROR: no PDFs found in {codes_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Building Code PDF Ingestion")
    print(f"  codes-dir : {codes_path}")
    print(f"  PDFs found: {len(pdfs)}")
    print(f"  dry-run   : {args.dry_run}")
    if args.code:
        print(f"  filter    : {args.code}")

    # Setup embedder
    embedder = get_embedder()
    print(f"  embedder  : {type(embedder).__name__} ({embedder.model_id})")

    # Setup DB connection (not needed for dry run)
    conn = None
    if not args.dry_run:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            print("ERROR: DATABASE_URL not set in .env", file=sys.stderr)
            sys.exit(1)
        conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)

    total_inserted = 0
    total_skipped = 0
    total_parsed = 0

    try:
        for pdf_path in pdfs:
            code_parser = find_parser(pdf_path)
            if code_parser is None:
                print(f"\n  WARN no parser for: {pdf_path.name} — skipping")
                continue

            # Filter by --code if specified
            if args.code and code_parser.code.upper() != args.code.upper():  # type: ignore[attr-defined]
                continue

            ins, skp = process_pdf(pdf_path, code_parser, embedder, conn, args.dry_run)
            total_inserted += ins
            total_skipped += skp
            total_parsed += 1
    finally:
        if conn is not None:
            conn.close()

    print(f"\n{'-'*50}")
    print(f"  PDFs processed : {total_parsed}")
    print(f"  Inserted       : {total_inserted}")
    print(f"  Skipped        : {total_skipped} (already in DB)")
    print(f"\n[{'DRY RUN' if args.dry_run else 'OK'}] Done")


if __name__ == "__main__":
    main()
