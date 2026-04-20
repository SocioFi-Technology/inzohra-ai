#!/usr/bin/env python
"""Seed the code KB with Phase-01 sections (CBC §107 + Ch 11B + §508/716).

Usage (from repo root)::

    uv run scripts/seed_kb.py

    # Force deterministic HashEmbedder (no OpenAI key needed):
    OPENAI_API_KEY=sk-xxx uv run scripts/seed_kb.py

Reads ``DATABASE_URL`` and (optionally) ``OPENAI_API_KEY`` from ``.env`` at
the repo root.  When a real OpenAI key is present, ``text-embedding-3-large``
is used; otherwise the deterministic ``HashEmbedder`` produces placeholder
vectors that exercise the full pipeline without semantic recall.

Idempotent: a row where ``(canonical_id, effective_date)`` already exists in
``code_sections`` is silently skipped. Safe to run multiple times.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve paths and load .env before importing any service code
# ---------------------------------------------------------------------------

_repo_root = Path(__file__).resolve().parent.parent

# Expose the review-service package so `app.codekb.*` imports resolve.
sys.path.insert(0, str(_repo_root / "services" / "review"))

from dotenv import load_dotenv  # noqa: E402  (after sys.path surgery)

load_dotenv(_repo_root / ".env", override=True)

# ---------------------------------------------------------------------------
# Now safe to import project code
# ---------------------------------------------------------------------------

import psycopg  # noqa: E402
import psycopg.rows  # noqa: E402

from app.codekb.embedder import EMBED_DIM, get_embedder  # noqa: E402
from app.codekb.seed_data import ALL_SEED_SECTIONS  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BATCH_SIZE = 20  # texts per embedding API call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vec_literal(vec: list[float]) -> str:
    """Format a float list as a pgvector wire literal: ``[x1,x2,...,xN]``."""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set in environment / .env", file=sys.stderr)
        sys.exit(1)

    total = len(ALL_SEED_SECTIONS)
    print(f"KB seeder — {total} sections to process")
    print(f"  DB : {database_url.split('@')[-1] if '@' in database_url else database_url[:48]}...")

    # --- generate embeddings ---
    embedder = get_embedder()
    print(f"  Embedder : {type(embedder).__name__}  (model={embedder.model_id})")

    texts = [s.body_text for s in ALL_SEED_SECTIONS]
    vectors: list[list[float]] = []

    print(f"  Embedding {total} texts (batch={BATCH_SIZE}) …")
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        batch_vecs = embedder.embed(batch)
        vectors.extend(batch_vecs)
        done = min(i + BATCH_SIZE, total)
        print(f"    {done:>3}/{total}  ✓")

    # Sanity-check dimensionality
    if vectors and len(vectors[0]) != EMBED_DIM:
        print(
            f"ERROR: expected {EMBED_DIM}-dim vectors, got {len(vectors[0])}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- insert into DB ---
    conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)
    inserted = 0
    skipped = 0

    try:
        with conn.transaction():
            for section, vec in zip(ALL_SEED_SECTIONS, vectors, strict=True):
                # Idempotent: skip when (canonical_id, effective_date) already present.
                # The code_sections table has a plain index (not UNIQUE) on these
                # columns, so we use a WHERE NOT EXISTS guard instead of ON CONFLICT.
                result = conn.execute(
                    """
                    INSERT INTO code_sections (
                        canonical_id,
                        code,
                        section_number,
                        title,
                        body_text,
                        effective_date,
                        embedding,
                        cross_references,
                        referenced_standards
                    )
                    SELECT
                        %(cid)s,
                        %(code)s,
                        %(snum)s,
                        %(title)s,
                        %(body)s,
                        %(eff)s::date,
                        %(vec)s::vector,
                        %(xrefs)s,
                        %(stdards)s
                    WHERE NOT EXISTS (
                        SELECT 1
                          FROM code_sections
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
                    print(f"  + {section.canonical_id:<30}  inserted")
                else:
                    skipped += 1
                    print(f"  ~ {section.canonical_id:<30}  skipped (exists)")
    finally:
        conn.close()

    print()
    print(f"  Inserted : {inserted}")
    print(f"  Skipped  : {skipped}  (already in DB)")
    print(f"\n[OK] Code KB seed complete — {inserted + skipped} sections available")


if __name__ == "__main__":
    main()
