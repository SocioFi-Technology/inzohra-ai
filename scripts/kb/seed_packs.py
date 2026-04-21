#!/usr/bin/env python
"""Seed jurisdictional packs into the Inzohra-ai database.

Reads pack data from ``packs/<city>/`` directories and inserts records into the
``jurisdictional_packs``, ``amendments``, ``agency_policies``,
``submittal_checklists``, and ``drafter_examples`` tables.

All inserts are ON CONFLICT DO NOTHING (idempotent). Safe to run multiple times.

Usage::

    python scripts/seed_packs.py --database-url $DATABASE_URL
    python scripts/seed_packs.py --database-url $DATABASE_URL --city santa-rosa
    python scripts/seed_packs.py --database-url $DATABASE_URL --city santa-rosa --city oakland

Reads ``DATABASE_URL`` from the environment or ``.env`` at the repo root when
``--database-url`` is not supplied.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import psycopg
import psycopg.rows
import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PACKS_DIR = _REPO_ROOT / "packs"

load_dotenv(_REPO_ROOT / ".env", override=False)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PackManifest = dict[str, Any]
Amendment = dict[str, Any]
ChecklistItem = dict[str, Any]
DrafterExample = dict[str, str]

# ---------------------------------------------------------------------------
# YAML / JSON helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise TypeError(f"Expected a YAML mapping in {path}, got {type(data).__name__}")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise TypeError(f"Expected a JSON object in {path}, got {type(data).__name__}")
    return data


# ---------------------------------------------------------------------------
# Drafter-example parser
# ---------------------------------------------------------------------------

_EXAMPLE_HEADER_RE = re.compile(r"^#{1,3}\s+Example\s+\d+", re.IGNORECASE | re.MULTILINE)


def _parse_drafter_examples(md_path: Path, pack_id: str) -> list[DrafterExample]:
    """Split drafter-examples.md into one dict per ``### Example NN`` block."""
    text = md_path.read_text(encoding="utf-8")
    # Split on any heading that starts with "Example NN"
    chunks = _EXAMPLE_HEADER_RE.split(text)
    headers = _EXAMPLE_HEADER_RE.findall(text)

    examples: list[DrafterExample] = []
    for header, chunk in zip(headers, chunks[1:], strict=False):
        # First non-empty line of the chunk after the header is the title suffix
        title_suffix = header.strip().lstrip("#").strip()
        body = chunk.strip()
        # Extract draft input / polished output if present
        input_match = re.search(r"\*\*Draft input:\*\*\s*(.+?)(?=\*\*Polished output|\Z)", body, re.DOTALL)
        output_match = re.search(r"\*\*Polished output:\*\*\s*(.+?)(?=\Z)", body, re.DOTALL)
        draft_input = input_match.group(1).strip() if input_match else ""
        polished_output = output_match.group(1).strip() if output_match else body

        # Derive discipline from heading context by scanning backwards for ## heading
        discipline = _infer_discipline(title_suffix, body)

        examples.append(
            {
                "pack_id": pack_id,
                "title": title_suffix,
                "discipline": discipline,
                "draft_input": draft_input,
                "polished_output": polished_output,
                "raw_markdown": f"### {title_suffix}\n{body}",
            }
        )
    return examples


def _infer_discipline(title: str, body: str) -> str:
    """Heuristically infer the discipline from the example title and body text."""
    combined = (title + " " + body).lower()
    mapping: list[tuple[list[str], str]] = [
        (["accessibility", "accessible", "acc-"], "accessibility"),
        (["structural", "hold-down", "shear wall", "anchor bolt", "st-"], "structural"),
        (["mechanical", "hvac", "combustion air", "dryer duct", "me-"], "mechanical"),
        (["electrical", "panel", "afci", "ev charg", "el-"], "electrical"),
        (["plumbing", "water heater", "fixture flow", "prv", "pl-"], "plumbing"),
        (["energy", "cf-1r", "insulation", "solar", "title 24", "en-"], "energy"),
        (["fire", "smoke alarm", "sprinkler", "wui", "fl-", "nfpa"], "fire_life_safety"),
        (["calgreen", "waste management", "cwmp", "cg-"], "calgreen"),
        (["plan integrity", "sheet index", "dimension conflict", "pi-"], "plan_integrity"),
    ]
    for keywords, discipline in mapping:
        if any(kw in combined for kw in keywords):
            return discipline
    return "architectural"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _ensure_tables(conn: psycopg.Connection[dict[str, Any]]) -> None:
    """Create the submittal_checklists and drafter_examples tables if absent.

    These tables are not in the baseline migration yet. The seed script creates
    them idempotently so it can run on any environment.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS submittal_checklists (
            checklist_id   TEXT PRIMARY KEY,
            pack_id        TEXT NOT NULL,
            occupancy_class TEXT NOT NULL,
            version        TEXT NOT NULL,
            effective_date DATE NOT NULL,
            description    TEXT,
            items          JSONB NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drafter_examples (
            example_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pack_id        TEXT NOT NULL,
            title          TEXT NOT NULL,
            discipline     TEXT NOT NULL,
            draft_input    TEXT NOT NULL,
            polished_output TEXT NOT NULL,
            raw_markdown   TEXT NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _upsert_pack_manifest(
    conn: psycopg.Connection[dict[str, Any]], manifest: PackManifest
) -> None:
    """Insert a jurisdictional pack manifest. ON CONFLICT DO NOTHING."""
    conn.execute(
        """
        INSERT INTO jurisdictional_packs
            (pack_id, jurisdiction, version, effective_date, superseded_by, manifest)
        VALUES
            (%(pack_id)s, %(jurisdiction)s, %(version)s, %(effective_date)s::date,
             %(superseded_by)s, %(manifest)s::jsonb)
        ON CONFLICT (pack_id) DO NOTHING
        """,
        {
            "pack_id": manifest["pack_id"],
            "jurisdiction": manifest["jurisdiction"],
            "version": manifest["version"],
            "effective_date": manifest["effective_date"],
            "superseded_by": manifest.get("superseded_by"),
            "manifest": json.dumps(manifest),
        },
    )


def _upsert_amendments(
    conn: psycopg.Connection[dict[str, Any]],
    amendments_data: dict[str, Any],
) -> tuple[int, int]:
    """Insert amendments from one amendments YAML file.

    Returns (inserted, skipped) counts.

    Note: the ``amendments`` table references ``base_section_id`` (UUID FK to
    ``code_sections``). For seeding purposes, we store amendments in a staging
    approach — we insert them only if the base code section already exists.
    When the code section does not yet exist (code KB not seeded), we skip with
    a warning. This keeps the seed idempotent and non-destructive.
    """
    pack_id: str = amendments_data["pack_id"]
    items: list[dict[str, Any]] = amendments_data.get("amendments", [])
    inserted = 0
    skipped = 0

    for item in items:
        base_section: str = item["base_section"]  # e.g. "CBC-R337.1"
        # Derive code and section_number from the base_section string
        # Format: <CODE>-<SECTION>
        dash_idx = base_section.index("-")
        code_str = base_section[:dash_idx]
        section_num = base_section[dash_idx + 1:]

        # Look up the code_section row
        row = conn.execute(
            """
            SELECT section_id
              FROM code_sections
             WHERE code            = %(code)s
               AND section_number  = %(section_num)s
             ORDER BY effective_date DESC
             LIMIT 1
            """,
            {"code": code_str, "section_num": section_num},
        ).fetchone()

        if row is None:
            print(
                f"    SKIP amendment for {base_section} — section not in code_sections table "
                f"(run seed_kb.py first to populate base sections)",
                file=sys.stderr,
            )
            skipped += 1
            continue

        base_section_id: str = str(row["section_id"])
        result = conn.execute(
            """
            INSERT INTO amendments
                (base_section_id, pack_id, operation, amendment_text, effective_date)
            SELECT
                %(base_section_id)s::uuid,
                %(pack_id)s,
                %(operation)s,
                %(text)s,
                %(effective_date)s::date
            WHERE NOT EXISTS (
                SELECT 1
                  FROM amendments
                 WHERE base_section_id = %(base_section_id)s::uuid
                   AND pack_id         = %(pack_id)s
                   AND operation       = %(operation)s
            )
            """,
            {
                "base_section_id": base_section_id,
                "pack_id": pack_id,
                "operation": item["operation"],
                "text": item["text"],
                "effective_date": item["effective_date"],
            },
        )
        if result.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    return inserted, skipped


def _upsert_checklist(
    conn: psycopg.Connection[dict[str, Any]],
    checklist: dict[str, Any],
) -> bool:
    """Insert a submittal checklist. Returns True if inserted, False if skipped."""
    result = conn.execute(
        """
        INSERT INTO submittal_checklists
            (checklist_id, pack_id, occupancy_class, version, effective_date, description, items)
        VALUES
            (%(checklist_id)s, %(pack_id)s, %(occupancy_class)s, %(version)s,
             %(effective_date)s::date, %(description)s, %(items)s::jsonb)
        ON CONFLICT (checklist_id) DO NOTHING
        """,
        {
            "checklist_id": checklist["checklist_id"],
            "pack_id": checklist["pack_id"],
            "occupancy_class": checklist["occupancy_class"],
            "version": checklist["version"],
            "effective_date": checklist["effective_date"],
            "description": checklist.get("description", ""),
            "items": json.dumps(checklist.get("items", [])),
        },
    )
    return result.rowcount == 1


def _upsert_fee_schedule(
    conn: psycopg.Connection[dict[str, Any]],
    fees: dict[str, Any],
    pack_id: str,
) -> bool:
    """Store fee schedule as an agency_policy record. Returns True if inserted."""
    title = f"Fee Schedule — {pack_id}"
    body_text = json.dumps(fees, indent=2)
    effective_date = fees.get("effective_date", "2023-01-01")

    result = conn.execute(
        """
        INSERT INTO agency_policies
            (pack_id, title, body_text, source_url, applies_to_sections, effective_date)
        SELECT
            %(pack_id)s,
            %(title)s,
            %(body_text)s,
            %(source_url)s,
            %(applies_to)s,
            %(effective_date)s::date
        WHERE NOT EXISTS (
            SELECT 1
              FROM agency_policies
             WHERE pack_id = %(pack_id)s
               AND title   = %(title)s
        )
        """,
        {
            "pack_id": pack_id,
            "title": title,
            "body_text": body_text,
            "source_url": fees.get("source"),
            "applies_to": [],
            "effective_date": effective_date,
        },
    )
    return result.rowcount == 1


def _upsert_letter_template(
    conn: psycopg.Connection[dict[str, Any]],
    template: dict[str, Any],
    pack_id: str,
) -> bool:
    """Store letter template as an agency_policy record. Returns True if inserted."""
    title = f"Letter Template — {pack_id}"
    body_text = json.dumps(template, indent=2)
    effective_date = template.get("effective_date", "2023-01-01")

    result = conn.execute(
        """
        INSERT INTO agency_policies
            (pack_id, title, body_text, source_url, applies_to_sections, effective_date)
        SELECT
            %(pack_id)s,
            %(title)s,
            %(body_text)s,
            %(source_url)s,
            %(applies_to)s,
            %(effective_date)s::date
        WHERE NOT EXISTS (
            SELECT 1
              FROM agency_policies
             WHERE pack_id = %(pack_id)s
               AND title   = %(title)s
        )
        """,
        {
            "pack_id": pack_id,
            "title": title,
            "body_text": body_text,
            "source_url": None,
            "applies_to": [],
            "effective_date": effective_date,
        },
    )
    return result.rowcount == 1


def _upsert_drafter_examples(
    conn: psycopg.Connection[dict[str, Any]],
    examples: list[DrafterExample],
) -> tuple[int, int]:
    """Insert drafter examples. Skip duplicates by (pack_id, title). Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0
    for ex in examples:
        result = conn.execute(
            """
            INSERT INTO drafter_examples
                (pack_id, title, discipline, draft_input, polished_output, raw_markdown)
            SELECT
                %(pack_id)s,
                %(title)s,
                %(discipline)s,
                %(draft_input)s,
                %(polished_output)s,
                %(raw_markdown)s
            WHERE NOT EXISTS (
                SELECT 1
                  FROM drafter_examples
                 WHERE pack_id = %(pack_id)s
                   AND title   = %(title)s
            )
            """,
            ex,
        )
        if result.rowcount == 1:
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


# ---------------------------------------------------------------------------
# City seeder
# ---------------------------------------------------------------------------


def seed_city(
    conn: psycopg.Connection[dict[str, Any]],
    city_dir: Path,
) -> None:
    city_name = city_dir.name
    print(f"\n{'='*60}")
    print(f"  Seeding city: {city_name}")
    print(f"{'='*60}")

    # --- pack manifest ---
    manifest_path = city_dir / "pack.yaml"
    if not manifest_path.exists():
        print(f"  ERROR: {manifest_path} not found — skipping city", file=sys.stderr)
        return
    manifest = _load_yaml(manifest_path)
    pack_id: str = manifest["pack_id"]
    print(f"  Pack ID : {pack_id}")

    with conn.transaction():
        _ensure_tables(conn)

    with conn.transaction():
        _upsert_pack_manifest(conn, manifest)
        print(f"  [pack manifest] {pack_id} — inserted/exists")

    # --- amendments ---
    amendments_dir = city_dir / "amendments"
    if amendments_dir.exists():
        for amend_file in sorted(amendments_dir.glob("*.yaml")):
            amend_data = _load_yaml(amend_file)
            with conn.transaction():
                ins, skp = _upsert_amendments(conn, amend_data)
            base_code = amend_data.get("base_code", amend_file.stem.upper())
            print(f"  [amendments/{amend_file.name}] {base_code}: {ins} inserted, {skp} skipped")
    else:
        print(f"  [amendments] directory not found — skipping")

    # --- checklists ---
    checklists_dir = city_dir / "checklists"
    if checklists_dir.exists():
        for cl_file in sorted(checklists_dir.glob("*.json")):
            checklist = _load_json(cl_file)
            with conn.transaction():
                ok = _upsert_checklist(conn, checklist)
            status = "inserted" if ok else "skipped (exists)"
            print(f"  [checklists/{cl_file.name}] {checklist['checklist_id']} — {status}")
    else:
        print(f"  [checklists] directory not found — skipping")

    # --- fees ---
    fees_path = city_dir / "fees.json"
    if fees_path.exists():
        fees = _load_json(fees_path)
        with conn.transaction():
            ok = _upsert_fee_schedule(conn, fees, pack_id)
        status = "inserted" if ok else "skipped (exists)"
        print(f"  [fees.json] {fees.get('fee_schedule_id', 'unknown')} — {status}")
    else:
        print(f"  [fees.json] not found — skipping")

    # --- letter template ---
    lt_path = city_dir / "letter_template.json"
    if lt_path.exists():
        template = _load_json(lt_path)
        with conn.transaction():
            ok = _upsert_letter_template(conn, template, pack_id)
        status = "inserted" if ok else "skipped (exists)"
        print(f"  [letter_template.json] {template.get('template_id', 'unknown')} — {status}")
    else:
        print(f"  [letter_template.json] not found — skipping")

    # --- drafter examples ---
    for candidate in [
        city_dir / "drafter-examples.md",
        _REPO_ROOT / "skills" / f"jurisdiction-{city_name}" / "drafter-examples.md",
    ]:
        if candidate.exists():
            examples = _parse_drafter_examples(candidate, pack_id)
            with conn.transaction():
                ins, skp = _upsert_drafter_examples(conn, examples)
            print(
                f"  [drafter-examples] {candidate.relative_to(_REPO_ROOT)}: "
                f"{ins} inserted, {skp} skipped"
            )
            break
    else:
        print(f"  [drafter-examples] not found — skipping")

    print(f"  Done: {city_name}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed jurisdictional packs into the Inzohra-ai database."
    )
    parser.add_argument(
        "--database-url",
        dest="database_url",
        default=None,
        help="PostgreSQL connection URL (overrides DATABASE_URL env var)",
    )
    parser.add_argument(
        "--city",
        action="append",
        dest="cities",
        metavar="CITY",
        help=(
            "City directory name under packs/ to seed (e.g. santa-rosa). "
            "Can be specified multiple times. Defaults to all cities found in packs/."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # Resolve database URL
    import os

    database_url: str = args.database_url or os.environ.get("DATABASE_URL", "")
    if not database_url:
        print(
            "ERROR: DATABASE_URL not set. Provide --database-url or set DATABASE_URL in environment.",
            file=sys.stderr,
        )
        return 1

    # Resolve city directories
    if not _PACKS_DIR.exists():
        print(f"ERROR: packs/ directory not found at {_PACKS_DIR}", file=sys.stderr)
        return 1

    if args.cities:
        city_dirs = [_PACKS_DIR / city for city in args.cities]
        missing = [d for d in city_dirs if not d.is_dir()]
        if missing:
            for m in missing:
                print(f"ERROR: city directory not found: {m}", file=sys.stderr)
            return 1
    else:
        city_dirs = [d for d in sorted(_PACKS_DIR.iterdir()) if d.is_dir()]

    if not city_dirs:
        print("No city directories found in packs/. Nothing to seed.", file=sys.stderr)
        return 1

    db_display = database_url.split("@")[-1] if "@" in database_url else database_url[:48]
    print(f"Pack seeder")
    print(f"  DB      : ...{db_display}")
    print(f"  Cities  : {[d.name for d in city_dirs]}")

    conn: psycopg.Connection[dict[str, Any]] = psycopg.connect(
        database_url, row_factory=psycopg.rows.dict_row
    )
    try:
        for city_dir in city_dirs:
            seed_city(conn, city_dir)
    finally:
        conn.close()

    print(f"\n[OK] Pack seed complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
