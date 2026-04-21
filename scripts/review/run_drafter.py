#!/usr/bin/env python
"""Run CommentDrafterAgent on all findings for a project + round.

Usage::
    uv run scripts/run_drafter.py [--project-id <uuid>] [--round <n>]

The script:
  1. Fetches all findings for the given project and review round.
  2. Skips findings that already have a comment_draft row (idempotent).
  3. Calls CommentDrafterAgent.draft() for each remaining finding.
  4. Bulk-inserts results to the comment_drafts table.
  5. Bulk-inserts LLM call log rows to the llm_call_log table.
  6. Prints a summary: X findings drafted, total cost $Y.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: repo root on sys.path so services/review is importable.
# ---------------------------------------------------------------------------

_REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "services" / "review"))

from dotenv import load_dotenv  # noqa: E402 — must come after sys.path insert

load_dotenv(_REPO_ROOT / ".env", override=True)

import psycopg  # noqa: E402
import psycopg.rows  # noqa: E402

from app.drafter.drafter import CommentDrafterAgent  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_project_id(conn: psycopg.Connection, raw: str | None) -> str:
    """Return the project UUID, defaulting to the fixture permit B25-2734."""
    if raw:
        return raw
    row = conn.execute(
        "SELECT project_id FROM projects WHERE permit_number = 'B25-2734' LIMIT 1"
    ).fetchone()
    if row is None:
        print("ERROR: fixture project B25-2734 not found. Run ingest first.")
        sys.exit(1)
    return str(row["project_id"])


def _fetch_findings(
    conn: psycopg.Connection,
    project_id: str,
    review_round: int,
) -> list[dict]:
    """Return all findings for the given project + round."""
    rows = conn.execute(
        """
        SELECT finding_id, project_id, submittal_id, review_round,
               discipline, rule_id, severity, requires_licensed_review,
               sheet_reference, evidence, citations,
               draft_comment_text, confidence, created_at
          FROM findings
         WHERE project_id = %s AND review_round = %s
         ORDER BY created_at
        """,
        (project_id, review_round),
    ).fetchall()
    return list(rows)


def _fetch_existing_draft_finding_ids(
    conn: psycopg.Connection,
    project_id: str,
    review_round: int,
) -> set[str]:
    """Return the set of finding_ids that already have a comment_draft row."""
    rows = conn.execute(
        """
        SELECT finding_id::text
          FROM comment_drafts
         WHERE project_id = %s AND review_round = %s
        """,
        (project_id, review_round),
    ).fetchall()
    return {str(r["finding_id"]) for r in rows}


def _insert_comment_draft(
    conn: psycopg.Connection,
    finding_id: str,
    project_id: str,
    review_round: int,
    result_polished_text: str,
    prompt_hash: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    cost_usd: float,
) -> None:
    """Insert a single row into comment_drafts."""
    conn.execute(
        """
        INSERT INTO comment_drafts
            (draft_id, finding_id, project_id, review_round,
             polished_text, prompt_hash, model,
             tokens_in, tokens_out, latency_ms, cost_usd)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(uuid.uuid4()),
            finding_id,
            project_id,
            review_round,
            result_polished_text,
            prompt_hash,
            model,
            tokens_in,
            tokens_out,
            latency_ms,
            round(cost_usd, 8),
        ),
    )


def _insert_llm_call_log_rows(
    conn: psycopg.Connection,
    call_log_rows: list[dict],
) -> None:
    """Bulk-insert LLM call log rows to llm_call_log."""
    for log in call_log_rows:
        conn.execute(
            """
            INSERT INTO llm_call_log
                (call_id, prompt_hash, model,
                 tokens_in, tokens_out, latency_ms, cost_usd,
                 caller_service, finding_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                log["call_id"],
                log["prompt_hash"],
                log["model"],
                log["tokens_in"],
                log["tokens_out"],
                log["latency_ms"],
                log["cost_usd"],
                log["caller_service"],
                log.get("finding_id"),
            ),
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the drafter driver script."""
    parser = argparse.ArgumentParser(
        description="Run CommentDrafterAgent on all findings for a project + round."
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help="UUID of the project. Defaults to fixture permit B25-2734.",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=1,
        help="Review round number (default: 1).",
    )
    args = parser.parse_args()

    database_url: str | None = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)

    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    conn: psycopg.Connection = psycopg.connect(
        database_url, row_factory=psycopg.rows.dict_row
    )

    try:
        project_id: str = _resolve_project_id(conn, args.project_id)
        review_round: int = args.round

        print(f"project_id   = {project_id}")
        print(f"review_round = {review_round}")
        print()

        # --- Fetch all findings for this project + round ---
        findings = _fetch_findings(conn, project_id, review_round)
        if not findings:
            print("No findings found for this project + round. Nothing to draft.")
            return

        # --- Skip findings already drafted (idempotent) ---
        already_drafted = _fetch_existing_draft_finding_ids(conn, project_id, review_round)
        pending = [
            f for f in findings if str(f["finding_id"]) not in already_drafted
        ]

        print(
            f"Findings total: {len(findings)} | already drafted: {len(already_drafted)} "
            f"| to draft: {len(pending)}"
        )
        print()

        if not pending:
            print("All findings for this round already have polished drafts. Done.")
            return

        # --- Run the drafter ---
        agent = CommentDrafterAgent(api_key=anthropic_api_key)
        call_log_rows: list[dict] = []
        total_cost: float = 0.0
        drafted_count: int = 0
        error_count: int = 0

        for finding in pending:
            finding_id = str(finding["finding_id"])
            try:
                result = agent.draft(finding, call_log_rows)
            except RuntimeError as exc:
                print(f"  WARN: skipping finding {finding_id}: {exc}")
                error_count += 1
                continue

            _insert_comment_draft(
                conn,
                finding_id=finding_id,
                project_id=project_id,
                review_round=review_round,
                result_polished_text=result.polished_text,
                prompt_hash=result.prompt_hash,
                model=result.model,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
            )
            total_cost += result.cost_usd
            drafted_count += 1
            print(
                f"  [{drafted_count}/{len(pending)}] finding={finding_id} "
                f"discipline={finding.get('discipline')} "
                f"latency={result.latency_ms}ms cost=${result.cost_usd:.6f}"
            )

        # --- Persist LLM call log rows ---
        _insert_llm_call_log_rows(conn, call_log_rows)

        conn.commit()

        print()
        print(
            f"Summary: {drafted_count} finding(s) drafted"
            + (f", {error_count} error(s) skipped" if error_count else "")
            + f", total cost ${total_cost:.6f}"
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
