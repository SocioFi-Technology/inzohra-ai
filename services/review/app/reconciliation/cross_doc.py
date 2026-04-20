"""CrossDocClaimBuilder — build and persist cross-document claims.

Reads entities from the DB and compares values across document types:
- title_block (plan_set) vs title24_form — R-values, address, climate zone
- title24_form compliance result
- fire_review memo vs plan_set occupancy code notes

Invariants:
  - Append-only: re-running creates new rows, never updates existing.
  - Every claim carries resolved_value, sources, conflicts.
  - builder_version bumped on schema or logic change.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import psycopg
import psycopg.rows
from psycopg.types.json import Jsonb

VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class CrossDocResult:
    claims_inserted: int = 0
    conflicts_found: int = 0
    claim_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_address(addr: str) -> str:
    """Lowercase and strip all whitespace for address comparison."""
    return addr.lower().replace(" ", "").replace(",", "").strip()


def _upsert_claim(
    conn: psycopg.Connection,
    project_id: str,
    claim_type: str,
    resolved_value: dict,
    sources: list[dict],
    conflicts: list[dict],
    confidence: float,
) -> str:
    """Insert a new cross_doc_claims row (append-only — no ON CONFLICT).

    Returns the new claim_id (UUID string).
    The caller is responsible for committing.
    """
    claim_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO cross_doc_claims
          (claim_id, project_id, claim_type, resolved_value, confidence,
           sources, conflicts, claim_version, builder_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, '1.0.0', %s)
        """,
        (
            claim_id,
            project_id,
            claim_type,
            Jsonb(resolved_value),
            confidence,
            Jsonb(sources),
            Jsonb(conflicts),
            VERSION,
        ),
    )
    return claim_id


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_cross_doc_claims(
    conn: psycopg.Connection,
    *,
    project_id: str,
) -> CrossDocResult:
    """Build and persist cross-document claims for *project_id*.

    Reads entities from the DB (title24_form, title_block, code_note) and
    emits claims to ``cross_doc_claims``.  The caller is responsible for
    committing the transaction.

    Returns a :class:`CrossDocResult` with counts.
    """
    result = CrossDocResult()

    # -----------------------------------------------------------------------
    # 1. Fetch the most-recent title24_form entity
    # -----------------------------------------------------------------------
    t24_row = conn.execute(
        """
        SELECT entity_id, payload, confidence
        FROM entities
        WHERE project_id = %s AND type = 'title24_form'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()

    t24_payload: dict = {}
    t24_entity_id: str | None = None
    t24_confidence: float = 0.0
    if t24_row:
        t24_entity_id = str(t24_row["entity_id"])
        t24_payload = t24_row["payload"] if isinstance(t24_row["payload"], dict) else {}
        t24_confidence = float(t24_row["confidence"])

    # -----------------------------------------------------------------------
    # 2. Fetch the first title_block entity from the plan_set
    # -----------------------------------------------------------------------
    tb_row = conn.execute(
        """
        SELECT entity_id, payload, confidence
        FROM entities
        WHERE project_id = %s AND type = 'title_block'
        ORDER BY page
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()

    tb_payload: dict = {}
    tb_entity_id: str | None = None
    if tb_row:
        tb_entity_id = str(tb_row["entity_id"])
        tb_payload = tb_row["payload"] if isinstance(tb_row["payload"], dict) else {}

    # -----------------------------------------------------------------------
    # 3. Fetch all code_note entities
    # -----------------------------------------------------------------------
    code_note_rows = conn.execute(
        """
        SELECT entity_id, payload, confidence
        FROM entities
        WHERE project_id = %s AND type = 'code_note'
        ORDER BY created_at
        """,
        (project_id,),
    ).fetchall()

    # -----------------------------------------------------------------------
    # 4. Build claims
    # -----------------------------------------------------------------------

    if t24_entity_id:
        t24_source_entry: dict = {
            "doc_type": "title24_form",
            "entity_id": t24_entity_id,
        }

        # [A] climate_zone
        climate_zone = t24_payload.get("climate_zone")
        if climate_zone is not None:
            cid = _upsert_claim(
                conn,
                project_id,
                "climate_zone",
                resolved_value={"value": climate_zone, "source_doc_type": "title24_form"},
                sources=[{**t24_source_entry, "value": climate_zone}],
                conflicts=[],
                confidence=t24_confidence,
            )
            result.claims_inserted += 1
            result.claim_ids.append(cid)

        # [B] t24_compliance_result
        compliance_result = t24_payload.get("compliance_result")
        if compliance_result is not None:
            cid = _upsert_claim(
                conn,
                project_id,
                "t24_compliance_result",
                resolved_value={
                    "value": compliance_result,
                    "source_doc_type": "title24_form",
                },
                sources=[{**t24_source_entry, "value": compliance_result}],
                conflicts=[],
                confidence=t24_confidence,
            )
            result.claims_inserted += 1
            result.claim_ids.append(cid)

        # [C] conditioned_floor_area
        conditioned_floor_area = t24_payload.get("conditioned_floor_area")
        if conditioned_floor_area is not None:
            cid = _upsert_claim(
                conn,
                project_id,
                "conditioned_floor_area",
                resolved_value={
                    "value": conditioned_floor_area,
                    "unit": "sqft",
                    "source_doc_type": "title24_form",
                },
                sources=[{**t24_source_entry, "value": conditioned_floor_area}],
                conflicts=[],
                confidence=t24_confidence,
            )
            result.claims_inserted += 1
            result.claim_ids.append(cid)

        # [D] r_value_roof — compare against code_note entities
        envelope_surfaces: list[dict] = t24_payload.get("envelope_surfaces") or []
        roof_surfaces = [s for s in envelope_surfaces if s.get("surface_type") == "roof"]

        for surf in roof_surfaces:
            r_val = surf.get("r_value")
            if r_val is None:
                continue

            # Collect conflicts from code_note items referencing roof R-values
            roof_conflicts: list[dict] = []
            for cn_row in code_note_rows:
                cn_payload = (
                    cn_row["payload"]
                    if isinstance(cn_row["payload"], dict)
                    else {}
                )
                items: list[dict] = cn_payload.get("items") or []
                for item in items:
                    text = str(item.get("text") or item.get("value") or "").lower()
                    if "r-" in text and "roof" in text:
                        # Try to extract numeric R-value from the note text
                        import re
                        match = re.search(r"r-(\d+(?:\.\d+)?)", text)
                        if match:
                            cn_r_val: float | str = float(match.group(1))
                            if cn_r_val != r_val:
                                roof_conflicts.append(
                                    {
                                        "doc_type_a": "title24_form",
                                        "doc_type_b": "code_note",
                                        "entity_id_b": str(cn_row["entity_id"]),
                                        "value_a": r_val,
                                        "value_b": cn_r_val,
                                        "unit": "hr·ft²·°F/Btu",
                                    }
                                )

            if roof_conflicts:
                result.conflicts_found += len(roof_conflicts)

            cid = _upsert_claim(
                conn,
                project_id,
                "r_value_roof",
                resolved_value={
                    "value": r_val,
                    "unit": "hr·ft²·°F/Btu",
                    "source_doc_type": "title24_form",
                },
                sources=[{**t24_source_entry, "value": r_val, "unit": "hr·ft²·°F/Btu"}],
                conflicts=roof_conflicts,
                confidence=t24_confidence,
            )
            result.claims_inserted += 1
            result.claim_ids.append(cid)
            # Only emit one claim per project (first roof surface wins)
            break

        # [E] project_address_match — compare title24 address vs title_block
        t24_address: str | None = t24_payload.get("project_address")
        if t24_address and tb_entity_id:
            # title_block address stored under payload["project_address"]["value"]
            tb_addr_raw = tb_payload.get("project_address")
            tb_address: str | None = None
            if isinstance(tb_addr_raw, dict):
                tb_address = tb_addr_raw.get("value")
            elif isinstance(tb_addr_raw, str):
                tb_address = tb_addr_raw

            if tb_address:
                addresses_match = (
                    _normalise_address(tb_address) == _normalise_address(t24_address)
                )
                if addresses_match:
                    cid = _upsert_claim(
                        conn,
                        project_id,
                        "project_address_match",
                        resolved_value={
                            "match": True,
                            "plan_set": tb_address,
                            "title24": t24_address,
                        },
                        sources=[
                            {
                                "doc_type": "title_block",
                                "entity_id": tb_entity_id,
                                "value": tb_address,
                            },
                            {
                                "doc_type": "title24_form",
                                "entity_id": t24_entity_id,
                                "value": t24_address,
                            },
                        ],
                        conflicts=[],
                        confidence=0.95,
                    )
                else:
                    addr_conflict = {
                        "doc_type_a": "title_block",
                        "doc_type_b": "title24_form",
                        "value_a": tb_address,
                        "value_b": t24_address,
                    }
                    result.conflicts_found += 1
                    cid = _upsert_claim(
                        conn,
                        project_id,
                        "project_address_match",
                        resolved_value={
                            "match": False,
                            "plan_set": tb_address,
                            "title24": t24_address,
                        },
                        sources=[
                            {
                                "doc_type": "title_block",
                                "entity_id": tb_entity_id,
                                "value": tb_address,
                            },
                            {
                                "doc_type": "title24_form",
                                "entity_id": t24_entity_id,
                                "value": t24_address,
                            },
                        ],
                        conflicts=[addr_conflict],
                        confidence=0.9,
                    )
                result.claims_inserted += 1
                result.claim_ids.append(cid)

    return result


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def run_cross_doc_claims(database_url: str, project_id: str) -> CrossDocResult:
    """Convenience function: open connection, run, commit, return result."""
    with psycopg.connect(database_url, row_factory=psycopg.rows.dict_row) as conn:
        result = build_cross_doc_claims(conn, project_id=project_id)
        conn.commit()
    return result
