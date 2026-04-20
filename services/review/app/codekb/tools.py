"""Code-RAG retrieval tools.

Read-only access to ``code_sections`` + ``amendments`` + ``agency_policies``.
Every retrieval resolves against ``(jurisdiction, effective_date)``.

Public surface (used by reviewers):
- ``lookup_section(code, section_number, jurisdiction, effective_date)``
- ``search_code(query, code_filter, jurisdiction, effective_date, limit)``
- ``get_table(canonical_id, jurisdiction, effective_date)``
- ``resolve_citation(citation_string)``   — see ``citations.py``
- ``get_amendments(section_id, jurisdiction)``
- ``check_effective_date(canonical_id, project_date)``

Every successful retrieval produces a ``retrieval_chain`` — the ordered list
of steps the code took to arrive at the answer. Never paraphrase; return the
frozen body text from the DB.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .citations import format_section_number, resolve_citation
from .embedder import Embedder, get_embedder


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Citation:
    """A single code-retrieval result suitable for ``findings.citations``."""

    canonical_id: str
    code: str
    section_number: str
    title: str | None
    frozen_text: str
    jurisdiction: str
    effective_date: str
    amendments: list[dict[str, Any]] = field(default_factory=list)
    agency_policies: list[dict[str, Any]] = field(default_factory=list)
    cross_references: list[str] = field(default_factory=list)
    referenced_standards: list[str] = field(default_factory=list)
    retrieval_chain: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_finding_citation(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "section": self.section_number,
            "canonical_id": self.canonical_id,
            "jurisdiction": self.jurisdiction,
            "effective_date": self.effective_date,
            "title": self.title,
            "frozen_text": self.frozen_text,
            "amendments": self.amendments,
            "agency_policies": self.agency_policies,
            "cross_references": self.cross_references,
            "referenced_standards": self.referenced_standards,
            "retrieval_chain": self.retrieval_chain,
            "confidence": self.confidence,
        }


@dataclass
class SearchHit:
    canonical_id: str
    code: str
    section_number: str
    title: str | None
    snippet: str
    score: float


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def _conn(database_url: str) -> psycopg.Connection:  # type: ignore[type-arg]
    return psycopg.connect(database_url, row_factory=dict_row)


# ---------------------------------------------------------------------------
# lookup_section
# ---------------------------------------------------------------------------

def lookup_section(
    database_url: str,
    *,
    code: str,
    section_number: str,
    jurisdiction: str,
    effective_date: date | str,
) -> Citation | None:
    """Fetch a single section by (code, section_number) at effective_date.

    Returns ``None`` when no matching section exists.
    """
    eff = effective_date.isoformat() if isinstance(effective_date, date) else effective_date
    canonical_id = f"{code.upper()}-{section_number}"

    with _conn(database_url) as conn:
        # Pick the latest section with effective_date <= eff, not superseded before eff.
        row = conn.execute(
            """SELECT *
               FROM code_sections
               WHERE canonical_id = %s
                 AND effective_date <= %s
               ORDER BY effective_date DESC
               LIMIT 1""",
            (canonical_id, eff),
        ).fetchone()

        if row is None:
            return None

        amendments = _fetch_amendments(conn, row["section_id"], jurisdiction, eff)
        policies = _fetch_policies(conn, canonical_id, jurisdiction, eff)

    chain = [
        f"canonical_id={canonical_id}",
        f"lookup(effective_date<={eff})",
        f"found section_id={row['section_id']}",
    ]
    if amendments:
        chain.append(f"applied {len(amendments)} amendment(s) for {jurisdiction}")

    return Citation(
        canonical_id=canonical_id,
        code=row["code"],
        section_number=row["section_number"],
        title=row.get("title"),
        frozen_text=row["body_text"],
        jurisdiction=jurisdiction,
        effective_date=str(row["effective_date"]),
        amendments=amendments,
        agency_policies=policies,
        cross_references=list(row.get("cross_references") or []),
        referenced_standards=list(row.get("referenced_standards") or []),
        retrieval_chain=chain,
    )


def _fetch_amendments(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    section_id: str,
    jurisdiction: str,
    eff: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT a.*
             FROM amendments a
             JOIN jurisdictional_packs p ON p.pack_id = a.pack_id
            WHERE a.base_section_id = %s
              AND p.jurisdiction = %s
              AND a.effective_date <= %s
              AND (a.superseded_by_id IS NULL)
            ORDER BY a.effective_date""",
        (section_id, jurisdiction, eff),
    ).fetchall()
    return [
        {
            "amendment_id": str(r["amendment_id"]),
            "operation": r["operation"],
            "text": r["amendment_text"],
            "effective_date": str(r["effective_date"]),
        }
        for r in rows
    ]


def _fetch_policies(
    conn: psycopg.Connection,  # type: ignore[type-arg]
    canonical_id: str,
    jurisdiction: str,
    eff: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT ap.title, ap.body_text, ap.source_url, ap.effective_date
             FROM agency_policies ap
             JOIN jurisdictional_packs p ON p.pack_id = ap.pack_id
            WHERE p.jurisdiction = %s
              AND ap.effective_date <= %s
              AND %s = ANY(ap.applies_to_sections)
            ORDER BY ap.effective_date""",
        (jurisdiction, eff, canonical_id),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# search_code (vector similarity)
# ---------------------------------------------------------------------------

def search_code(
    database_url: str,
    *,
    query: str,
    jurisdiction: str,
    effective_date: date | str,
    code_filter: list[str] | None = None,
    limit: int = 5,
    embedder: Embedder | None = None,
) -> list[SearchHit]:
    """Vector-similarity search; returns top-k hits."""
    eff = effective_date.isoformat() if isinstance(effective_date, date) else effective_date
    emb = embedder or get_embedder()
    vec = emb.embed([query])[0]
    # Format as pgvector literal
    vec_literal = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"

    where = ["effective_date <= %s"]
    params: list[Any] = [eff]
    if code_filter:
        where.append("code = ANY(%s)")
        params.append([c.upper() for c in code_filter])

    params.append(vec_literal)
    params.append(limit)

    sql = f"""
        SELECT canonical_id, code, section_number, title, body_text,
               1 - (embedding <=> %s::vector) AS score
          FROM code_sections
         WHERE {' AND '.join(where)}
         ORDER BY embedding <=> %s::vector
         LIMIT %s
    """
    # We need vec_literal twice (in SELECT and ORDER BY)
    params_final = params[:-2] + [vec_literal, vec_literal, limit]

    with _conn(database_url) as conn:
        rows = conn.execute(sql, params_final).fetchall()

    hits: list[SearchHit] = []
    for r in rows:
        snippet = (r["body_text"] or "")[:240].replace("\n", " ")
        hits.append(SearchHit(
            canonical_id=r["canonical_id"],
            code=r["code"],
            section_number=r["section_number"],
            title=r.get("title"),
            snippet=snippet,
            score=float(r["score"]),
        ))
    return hits


# ---------------------------------------------------------------------------
# check_effective_date
# ---------------------------------------------------------------------------

def check_effective_date(
    database_url: str,
    *,
    canonical_id: str,
    project_date: date | str,
) -> dict[str, Any]:
    """Return {applicable: bool, effective_from?, superseded_by?}."""
    pd = project_date.isoformat() if isinstance(project_date, date) else project_date
    with _conn(database_url) as conn:
        row = conn.execute(
            """SELECT section_id, effective_date, superseded_by_id
                 FROM code_sections
                WHERE canonical_id = %s
                  AND effective_date <= %s
                ORDER BY effective_date DESC
                LIMIT 1""",
            (canonical_id, pd),
        ).fetchone()
    if row is None:
        return {"applicable": False, "reason": "section_not_found"}
    return {
        "applicable": True,
        "effective_from": str(row["effective_date"]),
        "superseded_by": str(row["superseded_by_id"]) if row["superseded_by_id"] else None,
    }


# ---------------------------------------------------------------------------
# Convenience: lookup by pre-resolved canonical_id
# ---------------------------------------------------------------------------

def lookup_canonical(
    database_url: str,
    *,
    canonical_id: str,
    jurisdiction: str,
    effective_date: date | str,
) -> Citation | None:
    """Shortcut when the caller already has a canonical_id."""
    code, _, section_number = canonical_id.partition("-")
    if not section_number:
        return None
    # Handle the CBC-TBL-xxx / CRC-Rxxx / CBC-11B-xxx special cases by
    # reconstructing the "section_number" as stored.
    if section_number.startswith("TBL-"):
        # stored as section_number="Table <rest>"? we store canonical only; do direct lookup
        return _lookup_by_canonical(database_url, canonical_id, jurisdiction, effective_date)
    if canonical_id.startswith("CBC-11B-") or canonical_id.startswith("CRC-R"):
        return _lookup_by_canonical(database_url, canonical_id, jurisdiction, effective_date)
    return lookup_section(
        database_url,
        code=code,
        section_number=section_number,
        jurisdiction=jurisdiction,
        effective_date=effective_date,
    )


def _lookup_by_canonical(
    database_url: str,
    canonical_id: str,
    jurisdiction: str,
    effective_date: date | str,
) -> Citation | None:
    eff = effective_date.isoformat() if isinstance(effective_date, date) else effective_date
    with _conn(database_url) as conn:
        row = conn.execute(
            """SELECT *
                 FROM code_sections
                WHERE canonical_id = %s
                  AND effective_date <= %s
                ORDER BY effective_date DESC
                LIMIT 1""",
            (canonical_id, eff),
        ).fetchone()
        if row is None:
            return None
        amendments = _fetch_amendments(conn, row["section_id"], jurisdiction, eff)
        policies = _fetch_policies(conn, canonical_id, jurisdiction, eff)

    return Citation(
        canonical_id=canonical_id,
        code=row["code"],
        section_number=row["section_number"],
        title=row.get("title"),
        frozen_text=row["body_text"],
        jurisdiction=jurisdiction,
        effective_date=str(row["effective_date"]),
        amendments=amendments,
        agency_policies=policies,
        cross_references=list(row.get("cross_references") or []),
        referenced_standards=list(row.get("referenced_standards") or []),
        retrieval_chain=[
            f"canonical_id={canonical_id}",
            f"lookup(effective_date<={eff})",
            f"found section_id={row['section_id']}",
        ],
    )
