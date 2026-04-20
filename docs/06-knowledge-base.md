# § 06 — Knowledge base: codes, amendments, policies, standards

Inzohra-ai's knowledge base is a structured, retrievable store of every code section the system cites, every amendment layered on top of it, every agency policy, and every referenced standard.

## Scope

Initial coverage (2022 California cycle):

- **CBC** — California Building Code
- **CRC** — California Residential Code
- **CEC** — California Electrical Code
- **CMC** — California Mechanical Code
- **CPC** — California Plumbing Code
- **CFC** — California Fire Code
- **CEnC** — California Energy Code (Title 24 Part 6)
- **CalGreen** — California Green Building Standards Code (Title 24 Part 11)
- **HSC** — Health & Safety Code, §13131.x for R-2.1
- **NFPA 13R** (sprinklers), **NFPA 72** (fire alarm) referenced standards

## Data model

Each section is versioned with `effective_date` and `superseded_by_id`:

```
code_sections(
  id, code, section_number, canonical_id, jurisdiction_scope,
  title, body_text, tables_json, figures_json,
  effective_date, superseded_by_id,
  embedding vector(1536),
  cross_references[], referenced_standards[]
)

amendments(
  id, base_section_id, jurisdiction_id,
  amendment_text, operation (replace|append|override),
  effective_date, superseded_by_id
)

agency_policies(
  id, jurisdiction_id, title, body_text, source_url,
  applies_to_sections[], effective_date
)

referenced_standards(
  id, standard_code (e.g. "NFPA 13R-2022"), title, summary,
  full_text_uri, applies_to_sections[]
)
```

## Retrieval

Resolution is always against `(jurisdiction, effective_date)`:

1. **Canonical ID resolution** — `resolve_citation("Table 716.1(2)")` → a stable, unambiguous ID.
2. **State section lookup** — fetch the base text.
3. **Amendment application** — apply any matching amendment for that jurisdiction, in order.
4. **Agency policy layering** — attach any relevant agency policy as supplementary context.
5. **Return** — the resolved applicable text, the unamended text for reference, and the full precedence chain.

## Retrieval signature

```
lookup_section(code, section, jurisdiction, effective_date)
  → {applicable_text, unamended_text, amendments[], agency_policies[], cross_refs[], tables[], figures[]}

search_code(query, code_filter?, jurisdiction, effective_date)
  → [{section_id, score, snippet, canonical_id}]

get_table(table_id, jurisdiction, effective_date)
  → {rows, headers, rendered_image_uri}

resolve_citation(citation_string) → canonical_id

get_amendments(state_section_id, jurisdiction_id)
  → [amendment_records]

get_referenced_standards(section_id) → [standard_records]

check_effective_date(section_id, project_date)
  → {applicable: bool, superseded_by?, effective_from}
```

A top match is returned with full resolution; related sections are returned as drill-down candidates.

## Jurisdictional packs

Every city/county is a **pack**. A pack contains:

- Jurisdiction's amendments.
- Agency policies (memos, interpretations).
- Submittal checklists.
- Reviewer dialect (few-shot examples of comment phrasing).
- Preferred comment-letter template.
- Fee and timing conventions.

**Packs are data, not code.** Adding a city is a data-engineering task: source the municipal code, extract amendments, catalogue memos, collect sample review letters, validate against known projects.

Target effort: ~100 hours for city 1 (Santa Rosa); drops to ~20–30 hours by city 5 as tooling matures.

## Update cadence and versioning

California adopts a new Title 24 every three years; intermediate updates within each cycle; cities amend continuously. The KB is versioned at the section level. A project permitted on `2025-03-15` is forever reviewed against the text in effect on that date.

When a code updates, ingestion re-runs for affected sections, new versions are added, and affected projects in active cycles are flagged for re-review. Closed projects are **not** retroactively re-reviewed.

## What we do not fine-tune

We do not fine-tune the model on code text. Fine-tuning compresses text and breaks pointer fidelity — the system needs section IDs intact for citation. Retrieval-first absorbs updates; fine-tuning freezes a snapshot. The narrow case for fine-tuning is style (jurisdictional dialect for the comment drafter), and even that is better handled with few-shot prompting.
