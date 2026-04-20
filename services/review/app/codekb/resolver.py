"""JurisdictionResolver — Phase 08.

Walks the precedence chain:
  base code section → jurisdiction amendments (ordered by effective_date ASC)
  → agency policies

Returns the resolved (amended) text, the unamended base text, and the full
precedence chain so every finding can trace exactly which text was applied.

This module is intentionally independent from tools.py: it speaks directly to
the same database but does not import from that module.  Keeping layers
separate means the resolver can evolve (e.g. add caching) without coupling to
the reviewer tool surface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


@dataclass
class AmendmentApplication:
    """A single amendment that was applied during resolution."""

    amendment_id: str
    operation: str  # 'replace' | 'append' | 'override' | 'insert_before' | 'insert_after'
    text: str
    effective_date: str


@dataclass
class ResolvedSection:
    """The fully resolved section text plus the chain of evidence."""

    canonical_id: str
    jurisdiction: str
    effective_date: str
    base_text: str                              # unamended body_text from code_sections
    resolved_text: str                          # text after applying all amendments
    amendments_applied: list[AmendmentApplication]
    agency_policies: list[dict[str, Any]]
    precedence_chain: list[str]                 # human-readable ordered trace
    confidence: float                           # 1.0 = unambiguous; < 1.0 = conflict


# ---------------------------------------------------------------------------
# JurisdictionResolver
# ---------------------------------------------------------------------------


class JurisdictionResolver:
    """Resolve a code section through the full jurisdiction precedence chain.

    Precedence order (lowest → highest, last-write-wins):
      1. Base code section body_text
      2. Jurisdiction amendments in effective_date ASC order
      3. Agency policies are surfaced alongside the resolved text but do NOT
         further mutate resolved_text — they are advisory notes.

    Conflict handling:
      - Multiple ``replace`` or ``override`` amendments → confidence drops to
        0.7, the most-recent effective_date wins.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        *,
        code: str,
        section_number: str,
        jurisdiction: str,
        effective_date: date | str,
    ) -> ResolvedSection | None:
        """Return the resolved section or None if no matching section exists."""
        eff = (
            effective_date.isoformat()
            if isinstance(effective_date, date)
            else effective_date
        )
        canonical_id = f"{code.upper()}-{section_number}"

        with psycopg.connect(self._database_url, row_factory=dict_row) as conn:
            section_row = self._fetch_section(conn, canonical_id, eff)
            if section_row is None:
                return None

            raw_amendments = self._fetch_amendments(
                conn,
                section_id=str(section_row["section_id"]),
                jurisdiction=jurisdiction,
                eff=eff,
            )
            raw_policies = self._fetch_policies(
                conn,
                canonical_id=canonical_id,
                jurisdiction=jurisdiction,
                eff=eff,
            )

        base_text: str = section_row["body_text"]
        resolved_text, amendments_applied, confidence, chain = self._apply_amendments(
            base_text=base_text,
            raw_amendments=raw_amendments,
            canonical_id=canonical_id,
            jurisdiction=jurisdiction,
            eff=eff,
        )

        # Append policy notes to the chain (advisory, not text-mutating)
        for pol in raw_policies:
            chain.append(
                f"agency_policy(title={pol.get('title','')!r},"
                f" effective_date={pol.get('effective_date','')})"
            )

        return ResolvedSection(
            canonical_id=canonical_id,
            jurisdiction=jurisdiction,
            effective_date=eff,
            base_text=base_text,
            resolved_text=resolved_text,
            amendments_applied=amendments_applied,
            agency_policies=raw_policies,
            precedence_chain=chain,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers — DB queries (all parameterised, no f-string SQL)
    # ------------------------------------------------------------------

    def _fetch_section(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        canonical_id: str,
        eff: str,
    ) -> dict[str, Any] | None:
        """Return the most-recent code_sections row effective on or before *eff*."""
        return conn.execute(
            """
            SELECT section_id, canonical_id, code, section_number, title,
                   body_text, cross_references, referenced_standards, effective_date
              FROM code_sections
             WHERE canonical_id = %s
               AND effective_date <= %s
             ORDER BY effective_date DESC
             LIMIT 1
            """,
            (canonical_id, eff),
        ).fetchone()

    def _fetch_amendments(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        section_id: str,
        jurisdiction: str,
        eff: str,
    ) -> list[dict[str, Any]]:
        """Return all non-superseded amendments for *section_id* in *jurisdiction*.

        Ordered by effective_date ASC so that later amendments override earlier
        ones during the application pass.
        """
        rows = conn.execute(
            """
            SELECT a.amendment_id,
                   a.operation,
                   a.amendment_text,
                   a.effective_date
              FROM amendments a
              JOIN jurisdictional_packs p ON p.pack_id = a.pack_id
             WHERE a.base_section_id = %s
               AND p.jurisdiction    = %s
               AND a.effective_date  <= %s
               AND a.superseded_by_id IS NULL
             ORDER BY a.effective_date ASC
            """,
            (section_id, jurisdiction, eff),
        ).fetchall()
        return [dict(r) for r in rows]

    def _fetch_policies(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        canonical_id: str,
        jurisdiction: str,
        eff: str,
    ) -> list[dict[str, Any]]:
        """Return agency policies that apply to *canonical_id* in *jurisdiction*."""
        rows = conn.execute(
            """
            SELECT ap.policy_id,
                   ap.title,
                   ap.body_text,
                   ap.source_url,
                   ap.effective_date
              FROM agency_policies ap
              JOIN jurisdictional_packs p ON p.pack_id = ap.pack_id
             WHERE p.jurisdiction    = %s
               AND ap.effective_date <= %s
               AND %s               = ANY(ap.applies_to_sections)
             ORDER BY ap.effective_date ASC
            """,
            (jurisdiction, eff, canonical_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Amendment application logic
    # ------------------------------------------------------------------

    def _apply_amendments(
        self,
        *,
        base_text: str,
        raw_amendments: list[dict[str, Any]],
        canonical_id: str,
        jurisdiction: str,
        eff: str,
    ) -> tuple[str, list[AmendmentApplication], float, list[str]]:
        """Apply amendments in effective_date ASC order.

        Returns:
          (resolved_text, amendments_applied, confidence, precedence_chain)

        Amendment semantics:
          replace      → resolved_text = amendment_text
          override     → same as replace (different intent, identical behaviour)
          append       → resolved_text = current_text + "\\n\\n" + amendment_text
          insert_after → same as append
          insert_before→ resolved_text = amendment_text + "\\n\\n" + current_text
        """
        chain: list[str] = [
            f"base_section(canonical_id={canonical_id},"
            f" effective_date<={eff})",
        ]

        if not raw_amendments:
            chain.append("no_amendments_for_jurisdiction=" + jurisdiction)
            return base_text, [], 1.0, chain

        resolved_text = base_text
        amendments_applied: list[AmendmentApplication] = []
        replace_count = 0

        for row in raw_amendments:
            op: str = row["operation"]
            amendment_text: str = row["amendment_text"]
            amd_id: str = str(row["amendment_id"])
            amd_date: str = str(row["effective_date"])

            if op in ("replace", "override"):
                resolved_text = amendment_text
                replace_count += 1
                chain.append(
                    f"amendment(id={amd_id}, op={op},"
                    f" effective_date={amd_date}) → replace"
                )

            elif op in ("append", "insert_after"):
                resolved_text = resolved_text + "\n\n" + amendment_text
                chain.append(
                    f"amendment(id={amd_id}, op={op},"
                    f" effective_date={amd_date}) → append"
                )

            elif op == "insert_before":
                resolved_text = amendment_text + "\n\n" + resolved_text
                chain.append(
                    f"amendment(id={amd_id}, op={op},"
                    f" effective_date={amd_date}) → insert_before"
                )

            else:
                # Unknown operation — skip and note in chain.
                chain.append(
                    f"amendment(id={amd_id}, op={op!r},"
                    f" effective_date={amd_date}) → SKIPPED_UNKNOWN_OP"
                )
                continue

            amendments_applied.append(
                AmendmentApplication(
                    amendment_id=amd_id,
                    operation=op,
                    text=amendment_text,
                    effective_date=amd_date,
                )
            )

        # Confidence: multiple replace/override ops signal conflicting amendments.
        confidence = 0.7 if replace_count > 1 else 1.0
        if replace_count > 1:
            chain.append(
                f"CONFLICT: {replace_count} replace/override amendments found;"
                " most-recent effective_date wins; confidence=0.7"
            )

        return resolved_text, amendments_applied, confidence, chain
