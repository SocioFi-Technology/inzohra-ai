# § 04 — Data model and the provenance chain

Three principles:

1. **Immutability.** Every artefact is versioned. Re-runs produce new rows.
2. **Provenance.** Every artefact carries the evidence chain back to the pixel it came from.
3. **Queryability.** Every artefact is retrievable by a reviewer months or years after the permit closed.

## Entity classes

### `projects`
The long-lived unit. Identified by address, APN, jurisdiction. Persists across submittals, rounds, deferred permits, agency responses. Everything ultimately roots to a project.

### `submittals`
A point-in-time delivery of documents. An initial permit application, a resubmittal, a deferred submittal — each is its own submittal, linked to a parent where appropriate, with a `round_number` within its cycle.

### `documents`
A single file within a submittal. Fields: classified type, content hash (SHA-256), S3 URI, page count, authoring organization, extractor version. **Immutable once ingested.**

### `sheets`
For plan-set documents, one row per page with: parsed sheet identifier, declared scale, calibrated scale, discipline (G/A/S/M/E/P/T/F), sheet type (`floor_plan`, `elevation`, `schedule`, `details`, `code_notes`, `site_plan`, etc.). The primary addressable unit in the reviewer UI.

### `entities`
Everything extracted from a sheet or document — a room, a door, a window, a schedule row, a code note, a dimension, a fixture, a shear-wall callout, a holdown, a detail bubble. Fields: type, payload (JSONB), bbox, page, source sheet, extractor version.

### `measurements`
A special class of derived entities. Fields: value, unit, confidence interval, derivation trace (scale → calibration → geometry → computation, with bbox at every step), override history.

### `cross_doc_claims`
Aggregated facts asserted across multiple documents. Example: an occupancy claim of "R-2.1" with sources on the plan title block, the Title 24 cover, the narrative, and the fire review — one claim with four source entities.

### `findings`
Output of the review engine. Each finding carries discipline, severity, cited code sections (with retrieved text frozen at finding time), evidence entities, draft comment text, confidence, reviewer-approval state.

### `external_review_comments`
Parsed comments from incoming plan-check letters. Used for round-tracking, the learning loop, and direct comparison against AI-generated findings.

### `reviewer_actions`
Every approve / edit / merge / split / reject / override a human reviewer performs. Logged with timestamp, reviewer ID, rationale, before/after state. **Single most valuable training signal in the system.**

### `llm_call_log`
Every LLM call: `prompt_hash`, model, tokens_in/out, latency, cost, retrieved_context_ids. Used for reproducibility and cost tracking.

### `retrieval_log`
Every code-RAG call: query, jurisdiction, effective_date, matched section IDs, scores, retrieval_chain.

## The provenance chain, end-to-end

Consider a finding:
> "Bedroom 2 egress window net clear opening is 4.2 sqft, below the 5.7 sqft required by CRC §R310.2.1."

The chain:

1. `finding_id` → `evidence` → `measurement_id` (NCO = 4.2 sqft, confidence 0.88).
2. `measurement_id` → `derivation_trace`:
   - Scale from title block, `sheet_id=A-1.2`, bbox of scale notation.
   - Calibration via known-dimension check, bbox of reference dim.
   - Window entity `window_W4`, bbox of window symbol + tag.
   - Geometry extraction (width, height, sill) from vision pass, bboxes per field.
   - NCO computation: width × height after sash adjustment.
3. `finding.citations[0]` → `retrieval_log_id`:
   - Query "CRC §R310.2.1 egress window net clear opening residential", jurisdiction=`santa_rosa`, effective_date=`2025-03-15`.
   - Matched state section + any Santa Rosa amendment.
   - Frozen text attached to the finding.
4. `finding.rule_id` → `ARCH-EGRESS-010 v1.2.1`, code in `services/review/app/rules/architectural/egress_010.py`, fixture test passing.

Every link in this chain is clickable in the reviewer UI.
