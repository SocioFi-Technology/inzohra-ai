# Authoring a new jurisdictional pack

## Overview

A jurisdictional pack is the complete configuration bundle that tells Inzohra-ai how to review a permit submittal under a specific city's rules. Every finding the system emits is resolved against the pack for the project's jurisdiction and effective date — so getting the pack right is what makes the output legally defensible.

A pack contains five artifacts:

| Artifact | Path inside pack | Purpose |
|---|---|---|
| Pack manifest | `pack.yaml` | Identity, code cycle, contacts, formatting defaults |
| Amendment files | `amendments/*.yaml` | Overrides to state-level CBC/CRC/CMC/CEC/CPC/CFC sections |
| Agency policies | `policies/*.yaml` | Administrative rules that are not code amendments (fee schedules, submittal hours, deferred-submittal policies) |
| Submittal checklists | `checklists/sfr.json`, `checklists/comm.json` | Required documents and plan items by occupancy type |
| Drafter examples | `drafter-examples.md` | Few-shot comment examples in the jurisdiction's voice |
| Letter template | `letter_template.json` | Typography, letterhead, signature block |

When a review runs, the `JurisdictionResolver` in `services/review/app/codekb/resolver.py` loads the pack, applies amendments to the base code KB, and hands the merged section set to the review workers. The `seed_packs.py` script writes the pack rows to `jurisdictional_packs` and `amendments` in Postgres. The drafter examples are loaded into `drafter_examples` and are retrieved at comment-draft time via embedding similarity.

**Target:** a subject-matter expert (building official, ICC-certified plans examiner, or senior permit tech) should be able to author a complete, passing pack in under 30 hours by the fifth jurisdiction they work on. The first pack takes 3-4x longer because you are learning the toolchain; expect that.

---

## Prerequisites

**DB access**

You need read-write access to the staging Postgres instance. Request credentials from the ops team; they will be provided as `STAGING_DATABASE_URL`. Never seed to production directly — the pack-promotion runbook (`ops/runbooks/pack-promotion.md`) covers that flow.

**Python environment**

```bash
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e packages/shared-py
uv pip install psycopg pyyaml rich click
```

The `scripts/seed_packs.py` script and its dry-run validator require this environment.

**Source materials you must collect before starting**

1. The current municipal code (or the city's web portal with amendments on file)
2. The state base codes for the applicable cycle (2022 CBC, 2022 CRC, 2022 CMC, 2022 CEC, 2022 CPC, 2022 CFC — all available at dgs.ca.gov)
3. Any local ordinances that amend Title 24 (search the city's municipal code under "building" or "Title 24")
4. At least three real comment letters from that jurisdiction (redacted if needed) — these calibrate the drafter examples
5. The jurisdiction's submittal checklist if they publish one (most cities post a PDF checklist on their permits portal)

---

## Step 1 — Source materials

**Finding municipal code amendments**

California cities adopt the state codes with local amendments through ordinances. Typical sources:

- The city's online municipal code portal (Municode, American Legal, or a city-hosted Legistar instance). Search for "building code" in the ordinance index.
- The city's Building and Safety department webpage — many post a "local amendments" PDF alongside the permit application forms.
- Phone call to the counter supervisor: ask "do you have a written list of your local amendments to the 2022 CBC?" Most offices will email a PDF.

**Santa Rosa example:** Santa Rosa's 2022 CBC amendments were adopted by Ordinance 4157 (2023). The ordinance PDF is hosted at srcity.org/DocumentCenter. Key amendments include a 1-hour fire-resistive construction trigger for R-2 occupancies in the WUI overlay, and a stricter egress window sill height of 40 inches for sleeping rooms in new SFR (vs. the state 44-inch sill exception).

**Oakland example:** Oakland amended CFC §903.2.8 via OMC Title 15, requiring NFPA 13 (not 13R) sprinklers in all new R-2 construction regardless of building height — stricter than the state code trigger of four stories. Oakland also amended CBC §1006.3.3 to require a second exit from any sleeping loft exceeding 200 sq ft.

**Agency memos and interpretations**

Some amendments are never codified — they live as department memos or counter policies. Collect these from:

- Public records requests (CPRA in California) to the Building Department
- ICC chapter meeting minutes for the local chapter
- The plan-check supervisor directly (call, don't email — they rarely respond to cold email)

Flag any policy that comes only from a memo as `source_type: agency_memo` in the policy YAML; this triggers the `requires_licensed_review` flag on any finding derived from it.

**Sample review letters**

You need a minimum of 30 comment examples across at least six disciplines for the drafter-examples file. Sources:

- Applicants who have received comment letters (often willing to share after permit is resolved)
- The jurisdiction's public records portal — issued comment letters may be public records
- A reviewing engineer or architect who works regularly in that city

---

## Step 2 — Create the pack manifest

Every pack lives at `packs/<jurisdiction-slug>/pack.yaml`. The slug is lowercase, hyphenated, no spaces: `santa-rosa`, `oakland`, `san-jose`.

```yaml
# packs/oakland/pack.yaml
schema_version: "1"
jurisdiction_id: oakland
display_name: "City of Oakland"
state: CA
county: Alameda
code_cycle: "2022"
effective_date: "2023-01-01"        # Date this pack's amendments took effect
base_codes:
  - CBC                              # California Building Code
  - CRC                              # California Residential Code
  - CMC                              # California Mechanical Code
  - CEC                              # California Electrical Code
  - CPC                              # California Plumbing Code
  - CFC                              # California Fire Code
  - CalGreen                         # CALGreen Mandatory Measures
contacts:
  building_dept_phone: "510-238-3444"
  building_dept_email: "ceda-building@oaklandca.gov"
  building_dept_url: "https://www.oaklandca.gov/departments/building"
letter_defaults:
  font_family: "Times New Roman"
  date_format: "MMMM D, YYYY"
  jurisdiction_label: "City of Oakland – Bureau of Building"
```

**Naming conventions:**

- `jurisdiction_id` must match the slug in `projects.jurisdiction` column exactly — mismatches cause the resolver to fall back to state defaults silently, which is a hard-to-diagnose bug.
- `effective_date` is the date the *local amendments* took effect, not the state code adoption date. When the city adopts amendments mid-cycle, create a second pack YAML with a later `effective_date` and add both to the DB. The resolver picks the pack whose `effective_date` is closest to (but not after) the project's `effective_date`.
- `code_cycle` must be a 4-digit year string matching the state code cycle: `"2019"`, `"2022"`, `"2025"`.

---

## Step 3 — Amendment files

Amendments go in `packs/<slug>/amendments/`. One YAML file per base code is conventional but not required; splitting by topic is fine for complex jurisdictions.

```yaml
# packs/oakland/amendments/cfc-amendments.yaml
schema_version: "1"
jurisdiction_id: oakland
base_code: CFC
effective_date: "2023-01-01"
source_url: "https://www.oaklandca.gov/documents/title-15-buildings-and-construction"
source_description: "Oakland Municipal Code Title 15, Chapter 15.12, adopted 2022-11-15"
amendments:
  - section_id: CFC-903.2.8
    operation: replace
    amended_text: |
      903.2.8 Group R. An automatic sprinkler system installed in accordance with
      NFPA 13 shall be provided throughout all new buildings of Group R occupancy,
      regardless of height or number of stories.
    rationale: "Oakland requires NFPA 13 (not 13R) in all new R occupancies due to
      historic fire risk in the flatlands. State threshold of 4 stories does not apply."
    amendment_type: more_restrictive

  - section_id: CBC-1006.3.3
    operation: add_condition
    condition_text: |
      Exception 4 (Oakland only): A sleeping loft exceeding 200 square feet in area
      shall be provided with not fewer than two approved means of egress.
    rationale: "Loft egress clarification adopted by Oakland after 2016 Ghost Ship fire."
    amendment_type: more_restrictive
```

**Operation types:**

| Operation | When to use |
|---|---|
| `replace` | The entire section text is replaced. Use when Oakland's text contradicts the state text. |
| `add_condition` | Additional condition appended to the state section. Use when Oakland adds an exception or sub-condition without replacing the base text. |
| `delete_exception` | A state exception is removed (city is more restrictive). Identify the exception by number or text snippet. |
| `insert_before` | New paragraph inserted before a specified subsection marker. |
| `numeric_override` | A numeric threshold changes (e.g., 40-inch sill vs. 44-inch). Specify `field`, `state_value`, and `amended_value`. |

**Finding base section IDs**

Section IDs use the format `<CODE>-<SECTION>` where `<CODE>` is the abbreviated code name and `<SECTION>` is the dotted section number from the printed code. Examples:

- `CBC-1006.3.3` — California Building Code section 1006.3.3
- `CRC-R310.2.1` — California Residential Code section R310.2.1
- `CFC-903.2.8` — California Fire Code section 903.2.8

To find the canonical ID for a section, query the code KB: `SELECT section_id FROM code_sections WHERE code = 'CFC' AND section = '903.2.8'`. If the section is not in the KB, add it via the `kb-seed.ts` script before referencing it in amendments.

**Handling effective-date windows**

When a city adopts new amendments mid-cycle (e.g., Oakland updated its sprinkler rule in 2024), create a second amendment file with the new `effective_date`. The resolver evaluates amendments in date order and applies only those on or before the project date. Never delete or overwrite an existing amendment file — append a new one with the new effective date. This preserves immutability for projects already reviewed under the old rule.

**Precedence chain behavior**

The resolver applies amendments in this order: state base code → city amendment → county overlay (if any) → agency memo. Later layers override earlier layers. If two amendments both target the same `section_id` with the same `effective_date`, the resolver logs a conflict and uses the more restrictive value, then emits a warning. Resolve conflicts before production seeding.

---

## Step 4 — Agency policies

Policies are administrative rules that are not code amendments — they do not change the legal text of CBC/CRC etc., but they affect how the review is conducted. Examples:

- "Oakland requires a geotechnical report for all new R-2 construction in Alquist-Priolo zones."
- "Santa Rosa requires a separate Fire Department application for sprinkler systems."
- "Oakland's Building Department accepts deferred submittals for structural calculations only if a licensed engineer stamps the deferred-submittal log on the title sheet."

```yaml
# packs/oakland/policies/submittal-policies.yaml
schema_version: "1"
jurisdiction_id: oakland
policies:
  - policy_id: OAK-POL-GEOTECH-001
    title: "Geotechnical report required in AP zones"
    description: |
      All new construction in Alquist-Priolo Earthquake Fault Zones requires a
      geotechnical investigation report stamped by a licensed geotechnical engineer.
      The report must be submitted with the initial permit application.
    applies_to_sections:
      - CBC-1803.5.12
    severity: provide
    source_url: "https://www.oaklandca.gov/documents/building-division-policies"
    source_type: agency_policy
    requires_licensed_review: true

  - policy_id: OAK-POL-DEFSUB-001
    title: "Deferred submittal log must be engineer-stamped"
    description: |
      Oakland requires the deferred submittal log on the title sheet to bear the
      engineer-of-record's stamp and signature. A list without a stamp will be
      rejected at counter.
    applies_to_sections:
      - CBC-107.3.4.1
    severity: provide
    source_url: "https://www.oaklandca.gov/documents/building-division-policies"
    source_type: agency_policy
    requires_licensed_review: false
```

**What counts as a policy vs an amendment:** If the text changes what a code section says, it is an amendment. If it adds a procedural requirement that does not appear in any code section, it is a policy. When in doubt, ask the building official; using the wrong classification causes the resolver to apply the wrong precedence chain.

**`source_url` requirements:** All `source_url` values must point to publicly accessible documents. Do not use internal share links, Dropbox, or non-public city intranet URLs. If a policy exists only as a memo obtained via CPRA, upload the memo to the project's S3 bucket and use the S3 URL.

---

## Step 5 — Submittal checklists

Checklists tell the `QuestionChecklistAgent` what to look for in the submittal package. They live at `packs/<slug>/checklists/sfr.json` (single-family residential) and `packs/<slug>/checklists/comm.json` (commercial/multi-family).

```json
{
  "schema_version": "1",
  "jurisdiction_id": "oakland",
  "occupancy_type": "R-2",
  "checklist_id": "OAK-CL-R2-2023",
  "effective_date": "2023-01-01",
  "items": [
    {
      "item_id": "OAK-CL-R2-2023-001",
      "description": "Completed building permit application (Form B-1)",
      "required": true,
      "code_ref": "CBC-107.1",
      "notes": "Must be signed by the property owner or authorized agent."
    },
    {
      "item_id": "OAK-CL-R2-2023-002",
      "description": "Two sets of plans drawn to scale (min 1/8\" = 1'-0\")",
      "required": true,
      "code_ref": "CBC-107.2.1",
      "notes": null
    },
    {
      "item_id": "OAK-CL-R2-2023-003",
      "description": "NFPA 13 sprinkler system drawings (deferred submittal accepted with stamped log)",
      "required": true,
      "code_ref": "CFC-903.2.8",
      "notes": "Oakland local amendment: NFPA 13, not 13R, required for all new R-2."
    },
    {
      "item_id": "OAK-CL-R2-2023-004",
      "description": "Title 24 Part 6 energy compliance forms (CF1R, CF2R, CF3R)",
      "required": true,
      "code_ref": "CEC-10-103(a)",
      "notes": null
    },
    {
      "item_id": "OAK-CL-R2-2023-005",
      "description": "Geotechnical report (AP zone projects only)",
      "required": false,
      "code_ref": "CBC-1803.5.12",
      "notes": "Required per OAK-POL-GEOTECH-001 when site is in Alquist-Priolo zone."
    }
  ]
}
```

**Item ID naming convention:** `<JURISDICTION_ABBREV>-CL-<OCC>-<YEAR>-<3-DIGIT-SEQ>`. Never reuse an `item_id` — if you update a checklist item, create a new item with the new year and increment the sequence.

**`required` vs `recommended`:** `required: true` means a hard stop; the system will flag `provide` severity if the item is absent. `required: false` means a soft check; the system emits `clarify` severity.

**`code_ref` format:** Use the same canonical section ID format as amendments: `CBC-107.2.1`. Do not use free-text strings like "CBC Section 107.2.1" — the resolver needs the canonical form to link the checklist item to the KB.

---

## Step 6 — Drafter examples

The comment-drafter agent (Layer 9) uses few-shot retrieval from `drafter_examples` to match the jurisdiction's voice. The file lives at `packs/<slug>/drafter-examples.md`.

**Minimum 30 examples, covering at least these disciplines:** architectural, accessibility, structural, mechanical, electrical, plumbing, energy, fire/life-safety, CalGreen, and plan integrity. Aim for 3-5 examples per discipline.

**BV-dialect rules (these are non-negotiable):**

1. Present tense, active voice: "Plans show..." not "It was noted that plans showed..."
2. Sheet reference first: "Sheet A2.1, Door 101 —" not "Door 101 on Sheet A2.1"
3. Inline citation immediately after the finding: "...clear width of 2'-10" (CBC §1010.1.1 requires 3'-0" minimum)."
4. Severity keyword in the header: **REVISE**, **PROVIDE**, **CLARIFY**, or **REFERENCE ONLY**
5. No passive constructions, no hedging ("it appears that", "it seems"), no first-person.

```markdown
## Example 23 — Accessibility (Oakland)

**REVISE** Sheet A3.1, Unit 101 – Accessible route: The kitchen counter height shown
at 36" does not provide the required 34" maximum work surface height for the
accessible unit. Revise to comply with CBC §11B-804.3 and ANSI A117.1 §804.3.
One Type A fully accessible unit is required per CBC §11B-233.3.1 for this 18-unit
R-2 building.

---

## Example 24 — Fire/Life Safety (Oakland local amendment)

**PROVIDE** Sheet A0.1, General Notes – Sprinkler system: Plans reference NFPA 13R
sprinkler system throughout. Oakland Municipal Code Title 15 §15.12.100 (local
amendment to CFC §903.2.8) requires NFPA 13 (full-coverage) sprinklers for all new
Group R occupancies regardless of height. Revise general notes and deferred-submittal
log to reference NFPA 13. Stamped deferred-submittal log required on title sheet per
OAK-POL-DEFSUB-001.
```

---

## Step 7 — Letter template

The letter template controls the visual output of the generated comment letter PDF and DOCX. It lives at `packs/<slug>/letter_template.json`.

```json
{
  "schema_version": "1",
  "jurisdiction_id": "oakland",
  "font_family": "Times New Roman",
  "font_size_body": 11,
  "font_size_heading": 12,
  "margins": {
    "top_in": 1.0,
    "bottom_in": 1.0,
    "left_in": 1.25,
    "right_in": 1.0
  },
  "letterhead_text": "City of Oakland\nBuilding Services Division\n250 Frank H. Ogawa Plaza, Suite 2340\nOakland, CA 94612\n(510) 238-3444",
  "subject_line_template": "Plan Check Comment Letter — {permit_number} — Round {review_round}",
  "signature_block": "Inzohra AI Review System\nOn behalf of Oakland Building Services\nThis letter is a system-generated draft for reviewer approval.",
  "page_number_position": "bottom_center",
  "finding_header_style": "bold_uppercase",
  "citation_style": "inline"
}
```

All fields are required. `letterhead_text` accepts `\n` line breaks. `page_number_position` must be one of `bottom_center`, `bottom_right`, `top_right`. `finding_header_style` must be `bold_uppercase` or `bold_title_case`.

---

## Step 8 — Validate the pack

Run the dry-run validator before seeding anything to the DB:

```bash
python3 scripts/seed_packs.py --dry-run --city oakland
```

The validator checks:

- All required files are present (manifest, at least one amendment file, at least one checklist, drafter-examples, letter template)
- All section IDs in amendments and policies exist in the code KB
- All `effective_date` values parse as ISO 8601 dates
- The `jurisdiction_id` in every YAML matches the pack directory slug
- Amendment operations are valid enum values
- No `source_url` is a non-public URL pattern (localhost, 192.168.x.x, etc.)

Fix all errors the validator reports before proceeding. The validator will also warn (not error) if:

- Fewer than 30 drafter examples are present
- A discipline has zero examples
- Any amendment references a section ID not in the canonical section ID format

Check the amendment resolution output by running:

```bash
python3 scripts/seed_packs.py --dry-run --city oakland --show-resolution
```

This prints every amendment and the state text it targets, so you can visually confirm the replacements are correct.

The admin UI at `/admin/packs/upload` provides a browser-based version of the same validation. Upload the pack directory as a zip file; the UI returns the same validation report. This is useful if you do not have local DB access.

---

## Step 9 — Seed into staging DB

```bash
export STAGING_DATABASE_URL="postgresql://inzohra:..."
python3 scripts/seed_packs.py --city oakland --db-url "$STAGING_DATABASE_URL"
```

The script writes to three tables:

- `jurisdictional_packs` — one row per pack manifest (upserts on `jurisdiction_id` + `effective_date`)
- `amendments` — one row per amendment entry (upserts on `section_id` + `jurisdiction_id` + `effective_date`)
- `drafter_examples` — one row per example (inserts only; never updates existing examples — new examples get new rows)

Verify the rows were written:

```sql
SELECT jurisdiction_id, display_name, effective_date, created_at
FROM jurisdictional_packs
WHERE jurisdiction_id = 'oakland';

SELECT COUNT(*) FROM amendments WHERE jurisdiction_id = 'oakland';

SELECT COUNT(*) FROM drafter_examples WHERE jurisdiction_id = 'oakland';
```

You should see at least 1 pack row, as many amendment rows as you have amendment entries, and at least 30 drafter example rows.

---

## Step 10 — Run fixture tests

```bash
pnpm test:fixture --phase 08
```

Phase 08 checks that the structural prerequisites for multi-jurisdiction support are in place: the `submittal_checklists` and `drafter_examples` tables exist, the `rule_metrics_live` view has a `jurisdiction` column, and the key source files exist on disk. It also runs soft checks (warn-only) that verify at least 2 packs and 20 amendments exist in the DB.

If the test fails on a file-existence check (e.g., `[FAIL] [h] packs/santa-rosa/pack.yaml exists`), the file is genuinely missing — create it. If it fails on a DB structure check, the migration has not been applied — run `db/scripts/migrate.sh`.

---

## Step 11 — Promote to production

1. Open a pull request from your working branch to `main`. Title format: `feat(packs): add <city> jurisdictional pack`.
2. The CI pipeline runs `pnpm test:fixture --phase 08` and the full regression suite.
3. A second reviewer (ops or senior eng) reviews the amendment YAMLs for accuracy. For any amendment marked `amendment_type: more_restrictive`, the reviewer confirms the source ordinance is cited.
4. After approval, ops runs `scripts/seed_packs.py --city <slug> --db-url "$PROD_DATABASE_URL"` from a secure terminal — never in CI.
5. Tag the commit: `git tag packs/<slug>/v1.0.0`.
6. Announce to the reviewer team in #plan-review Slack: "Oakland pack v1 is live. Effective 2023-01-01. 14 amendments, 38 drafter examples. Contact @you with questions."

See `ops/runbooks/pack-promotion.md` for the full promotion checklist.

---

## Appendix A — Amendment operation reference

| Operation | Description | Example |
|---|---|---|
| `replace` | The full section text is replaced with `amended_text`. The state text is no longer used for this section in this jurisdiction. | Oakland CFC §903.2.8: replace state threshold language with NFPA 13 mandate |
| `add_condition` | A new condition, exception, or paragraph is appended to the state text. The state text is preserved and shown first. | Oakland CBC §1006.3.3: add loft-egress condition without replacing base section |
| `delete_exception` | A numbered or named exception in the state section is suppressed. Identify the exception by number (`exception_number: 2`) or by a unique text snippet (`exception_match: "not more than two stories"`). | Santa Rosa CRC §R302.2: delete Exception 2 (zero-lot-line allowance) |
| `insert_before` | A new paragraph is inserted before a specified subsection marker. Use `before_marker` to identify the insertion point. | CBC §107.3: insert deferred-submittal log requirement before "107.3.1 Deferred Submittals" |
| `numeric_override` | Changes a single numeric threshold. Specify `field`, `state_value`, and `amended_value`. | Santa Rosa CRC §R310.2.1: sill height override from 44" to 40" |

---

## Appendix B — Section ID format

Section IDs use the format `<CODE>-<SECTION>` with no spaces.

| Code abbreviation | Full name |
|---|---|
| `CBC` | California Building Code (Title 24, Part 2) |
| `CRC` | California Residential Code (Title 24, Part 2.5) |
| `CMC` | California Mechanical Code (Title 24, Part 4) |
| `CEC` | California Electrical Code (Title 24, Part 3) |
| `CPC` | California Plumbing Code (Title 24, Part 5) |
| `CFC` | California Fire Code (Title 19 / Part 9) |
| `CalGreen` | CALGreen Building Standards Code (Title 24, Part 11) |

Examples:

- `CBC-R310.2.1` — residential egress window opening requirements
- `CRC-R337.1` — WUI construction requirements (note: CRC uses R-prefixed section numbers)
- `CFC-903.2.8` — automatic sprinkler system requirements for Group R
- `CBC-11B-804.3` — accessible kitchen work surface (Part 2, Chapter 11B)
- `CalGreen-4.106.3` — stormwater management

When a section does not appear in the canonical list returned by `SELECT section_id FROM code_sections`, add it via `apps/web/scripts/kb-seed.ts` before referencing it in an amendment.

---

## Appendix C — Known gotchas

**WUI / Fire Hazard Severity Zone pitfalls**

Santa Rosa lies almost entirely within the Very High Fire Hazard Severity Zone (VHFHSZ) designated by CAL FIRE. This triggers CRC Chapter R337 (WUI construction requirements) for all new SFR and ADU construction. When authoring a Santa Rosa amendment, always check whether a section is modified by R337 before writing the amendment — many CBC/CRC sections have WUI exceptions that are not obvious from the main section text.

Oakland's WUI overlay applies only to the Oakland Hills (ZIP codes 94611, 94618, 94619). The pack must flag this as a geographic condition, not a blanket amendment. Use `applies_to_zone: WUI_overlay` in the amendment YAML and document that the resolver checks project parcel against the overlay shapefile.

**Oakland R-2 sprinkler vs. Santa Rosa ADU sprinkler**

These are different rules with different triggers and different standards:

- Oakland R-2: NFPA 13 (full-coverage) for all new R-2, any size. Local amendment to CFC §903.2.8.
- Santa Rosa ADU: NFPA 13D (single-family equivalent) required for detached ADUs over 500 sq ft. This is a local amendment to CRC §R313.1 and is only triggered for detached ADUs, not attached ADUs.

Do not conflate these. If an Oakland project has an ADU, both rules apply (NFPA 13 governs because it is more restrictive).

**Effective date windows when codes change mid-cycle**

California re-adopts the state codes roughly every 3 years, but cities often adopt local amendments at different times — sometimes before the state code takes effect (to pre-adopt), sometimes a year after (because the council cycle is slow). The resolver handles this by date-range matching, but you must enter the correct `effective_date` in each amendment file.

Common mistake: an author sets `effective_date: "2022-01-01"` (the nominal cycle start) for an amendment that was actually adopted in 2023 via an ordinance. The resolver then applies the amendment to projects from 2022, which is wrong and potentially illegal. Always verify the ordinance adoption date, not just the code cycle year.

When a city is mid-transition (e.g., some projects are reviewed under 2019 codes, others under 2022), create two separate pack directories: `packs/oakland-2019/` and `packs/oakland-2022/`. The `ProjectMatcher` uses the project's `effective_date` to select the correct pack.

**Code sections with no state text (Oakland-only sections)**

Some Oakland sections are numbered locally and do not correspond to any CBC/CRC section. These use the `insert_standalone` operation (a special case of `insert_before` without a `before_marker`). Example: Oakland's deferred-submittal log requirement is numbered as a local section with no CBC analog. In this case, use `source_section_id: null` and `operation: insert_standalone`. The resolver will create a synthetic section in the KB for this jurisdiction only.
