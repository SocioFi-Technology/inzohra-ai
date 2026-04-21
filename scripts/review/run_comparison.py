#!/usr/bin/env python
"""
Run ComparisonAgent on the fixture project B25-2734.

Usage:
    uv run scripts/run_comparison.py [--project-id <uuid>] [--round <n>]

Steps:
  1. Parse fixture expected-bv-letter.pdf -> external_review_comments (insert if not present).
  2. Fetch AI findings for the project + round.
  3. Run alignment algorithm -> alignment_records (insert, idempotent by deleting old rows first).
  4. Print precision/recall summary.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "services" / "review"))

from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / ".env", override=True)

import psycopg
import psycopg.rows

from app.comparison.alignment import align, AlignmentRecord

_FIXTURE_PDF = _REPO_ROOT / "data" / "fixtures" / "2008-dennis-ln" / "expected-bv-letter.pdf"


# ---------------------------------------------------------------------------
# Parse expected BV letter
# ---------------------------------------------------------------------------

def _parse_bv_letter(pdf_path: Path) -> list[dict[str, str | int | None]]:
    """Extract numbered comments from the expected BV letter PDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF not installed; skipping BV letter parse.")
        return []

    doc = fitz.open(str(pdf_path))
    full_text = "\n".join(page.get_text() for page in doc)

    # Match numbered comments: "N. Sheet X: ..." or "N. <text>"
    pattern = re.compile(
        r"(?m)^(\d+)\.\s+((?:Sheet\s+\S+:?|Project-wide:?)?\s*.+?)(?=^\d+\.\s+|\Z)",
        re.DOTALL,
    )

    comments: list[dict[str, str | int | None]] = []
    for m in pattern.finditer(full_text):
        num = int(m.group(1))
        body = " ".join(m.group(2).split())  # normalise whitespace

        # Extract sheet ref if present
        sheet_m = re.match(r"^(Sheet\s+\S+|Project-wide)[:,]?\s*", body, re.I)
        sheet_ref: str | None = sheet_m.group(1) if sheet_m else None
        text = body[sheet_m.end():].strip() if sheet_m else body

        comments.append({
            "comment_number": num,
            "sheet_ref": sheet_ref,
            "comment_text": text,
            "discipline": None,  # enriched later if needed
        })

    print(f"Parsed {len(comments)} comments from {pdf_path.name}")
    return comments


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ensure_comments(
    conn: psycopg.Connection,
    project_id: str,
    review_round: int,
    parsed: list[dict[str, str | int | None]],
) -> list[dict[str, str | int | None]]:
    """Insert external_review_comments if not already present; return all rows."""
    existing: int = conn.execute(
        "SELECT COUNT(*) FROM external_review_comments WHERE project_id = %s AND review_round = %s",
        (project_id, review_round),
    ).fetchone()[0]

    if existing == 0 and parsed:
        for c in parsed:
            conn.execute(
                """
                INSERT INTO external_review_comments
                    (comment_id, project_id, review_round, comment_number, sheet_ref, comment_text)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    project_id,
                    review_round,
                    c["comment_number"],
                    c.get("sheet_ref"),
                    c["comment_text"],
                ),
            )
        print(f"Inserted {len(parsed)} external review comments.")
    else:
        print(f"Already have {existing} external review comments; skipping insert.")

    rows = conn.execute(
        """
        SELECT comment_id, comment_number, sheet_ref, comment_text
        FROM external_review_comments
        WHERE project_id = %s AND review_round = %s
        ORDER BY comment_number
        """,
        (project_id, review_round),
    ).fetchall()
    return [dict(r) for r in rows]


def _fetch_findings(
    conn: psycopg.Connection,
    project_id: str,
    review_round: int,
) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT finding_id, rule_id, discipline, severity,
               sheet_reference, citations, draft_comment_text, confidence
        FROM findings
        WHERE project_id = %s AND review_round = %s
        ORDER BY created_at
        """,
        (project_id, review_round),
    ).fetchall()
    return [dict(r) for r in rows]


def _insert_alignment(
    conn: psycopg.Connection,
    project_id: str,
    review_round: int,
    records: list[AlignmentRecord],
) -> None:
    # Idempotent: delete old records for this project+round first
    conn.execute(
        "DELETE FROM alignment_records WHERE project_id = %s AND review_round = %s",
        (project_id, review_round),
    )
    for r in records:
        conn.execute(
            """
            INSERT INTO alignment_records
                (alignment_id, project_id, review_round, finding_id, comment_id, bucket, similarity_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                r.alignment_id,
                r.project_id,
                r.review_round,
                r.finding_id,
                r.comment_id,
                r.bucket,
                r.similarity_score,
            ),
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ComparisonAgent on the fixture project B25-2734."
    )
    parser.add_argument("--project-id", default=None, help="UUID of the project (auto-detected if omitted)")
    parser.add_argument("--round", type=int, default=1, help="Review round number (default: 1)")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    conn = psycopg.connect(db_url, row_factory=psycopg.rows.dict_row)
    try:
        if args.project_id:
            project_id = args.project_id
        else:
            row = conn.execute(
                "SELECT project_id FROM projects WHERE permit_number = 'B25-2734' LIMIT 1"
            ).fetchone()
            if not row:
                print("ERROR: fixture project B25-2734 not found")
                sys.exit(1)
            project_id = str(row["project_id"])

        review_round: int = args.round
        print(f"project_id={project_id}  round={review_round}")

        # 1. Parse + insert external comments
        parsed = _parse_bv_letter(_FIXTURE_PDF)
        comments = _ensure_comments(conn, project_id, review_round, parsed)

        # 2. Fetch AI findings
        findings = _fetch_findings(conn, project_id, review_round)
        print(f"AI findings: {len(findings)}   Authority comments: {len(comments)}")

        # 3. Align
        records = align(findings, comments, project_id, review_round)

        # 4. Persist
        _insert_alignment(conn, project_id, review_round, records)
        conn.commit()

        # 5. Summary
        counts = Counter(r.bucket for r in records)
        total_c = len(comments)
        matched = counts["matched"]
        precision = matched / len(findings) if findings else 0.0
        recall = matched / total_c if total_c else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        print(f"\nResults:")
        print(
            f"  matched={matched}  partial={counts['partial']}  "
            f"false_positive={counts['false_positive']}  missed={counts['missed']}"
        )
        print(f"  precision={precision:.3f}  recall={recall:.3f}  F1={f1:.3f}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
