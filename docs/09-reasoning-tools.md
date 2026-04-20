# § 09 — Reasoning tools and the tool-use surface

Three tool families, collectively **the callable API for reviewer agents**. Every tool call returns provenance along with its result. Every tool is read-only; writes go through emit_* helpers owned by the review commander.

## Measurement tools

```python
def get_sheet_scale(sheet_id: str) -> SheetScale:
    """{declared: "1/4\" = 1'-0\"", calibrated_ratio: 48.0, confidence: 0.97,
        calibration_source: entity_id, bbox: [...]}"""

def measure_distance(sheet_id: str, point_a: Point, point_b: Point) -> Measurement:
    """Straight-line inches between two points on a sheet, using calibrated scale."""

def get_room_dimensions(sheet_id: str, room_id: str) -> RoomDims:
    """{width_in, length_in, area_sqft, height_ft (if known), confidence, trace}"""

def get_door_specs(sheet_id: str, door_tag: str) -> DoorSpecs:
    """{width_in, height_in, type (swing/slide/bifold), rating (min), swing_side,
        schedule_source, geometry_source, confidence}"""

def get_window_specs(sheet_id: str, window_tag: str) -> WindowSpecs:
    """{width_in, height_in, sill_height_in, NCO_sqft, operable (bool),
        schedule_source, geometry_source, confidence}"""

def measure_egress_path(sheet_id: str, start: Point, end: Point) -> EgressPath:
    """{distance_ft, path (list of segments with bbox), confidence, trace}"""

def measure_between(sheet_id: str, entity_a: str, entity_b: str) -> Measurement:
    """Center-to-center or edge-to-edge between two entities."""

def get_accessible_route(sheet_id: str, from_: str, to: str) -> AccessibleRoute:
    """{width_min_in, slope_pct, x_slope_pct, clearances, turning_spaces, confidence}"""

def verify_dimension(sheet_id: str, bbox: BBox) -> DimVerification:
    """{text_val_in, geom_val_in, match: bool, delta_pct}"""
```

## Code-RAG tools

Every return includes the resolved applicable text, the unamended text for reference, and the precedence chain.

```python
def lookup_section(code: str, section: str, jurisdiction: str, effective_date: date) -> SectionResult:
    """{applicable_text, unamended_text, amendments[], agency_policies[],
        cross_refs[], tables[], figures[], canonical_id}"""

def search_code(query: str, code_filter: list[str]|None, jurisdiction: str, effective_date: date) -> list[SearchHit]:
    """Ranked sections with snippets and similarity scores."""

def get_table(table_id: str, jurisdiction: str, effective_date: date) -> TableResult:
    """{rows, headers, rendered_image_uri}"""

def resolve_citation(citation_string: str) -> str:
    """Parses 'Table 716.1(2)', '§11B-805.2.1', 'CRC R310.2.1', etc. to canonical_id."""

def get_amendments(state_section_id: str, jurisdiction_id: str) -> list[Amendment]:
    """Amendment records with effective_date windows."""

def get_referenced_standards(section_id: str) -> list[ReferencedStandard]:
    """NFPA / ASTM / ASHRAE / etc. with metadata."""

def check_effective_date(section_id: str, project_date: date) -> EffectiveCheck:
    """{applicable: bool, superseded_by?, effective_from}"""
```

## Entity-query tools

Read-only access to the extracted store. Common projections optimized for reviewer workflows.

```python
def get_entity(entity_id: str) -> Entity: ...
def get_sheet(sheet_id: str) -> Sheet: ...
def list_rooms(project_id: str, sheet_filter: list[str]|None = None) -> list[Room]: ...
def list_doors(project_id: str) -> list[Door]: ...
def list_windows(project_id: str) -> list[Window]: ...
def list_fixtures(project_id: str, type_filter: list[str]|None = None) -> list[Fixture]: ...
def get_schedule(sheet_id: str, schedule_type: str) -> Schedule: ...
def find_by_tag(project_id: str, tag: str) -> list[Entity]: ...
def cross_doc_claim(project_id: str, claim_type: str) -> CrossDocClaim:
    """{value, sources[], conflicts[], confidence}"""
```

## Tool-use patterns (canonical rule shape)

```python
def ARCH_EGRESS_010(ctx: RuleContext) -> list[Finding]:
    """Egress window NCO ≥ 5.7 sqft (CRC R310.2.1)."""
    findings = []
    bedrooms = [r for r in ctx.list_rooms() if r.use == "bedroom" and r.is_new]
    section = ctx.lookup_section("CRC", "R310.2.1", ctx.jurisdiction, ctx.effective_date)
    for bedroom in bedrooms:
        windows = [w for w in ctx.list_windows() if w.room_id == bedroom.id]
        for w in windows:
            specs = ctx.get_window_specs(w.sheet_id, w.tag)
            if specs.NCO_sqft < 5.7:
                findings.append(ctx.emit_finding(
                    discipline="architectural",
                    rule_id="ARCH-EGRESS-010", rule_version="1.0.0",
                    severity="revise",
                    sheet_reference={"sheet_id": w.sheet_id},
                    evidence=[
                        {"entity_id": w.id, "bbox": w.bbox},
                        {"measurement_id": specs.measurement_id,
                         "value": specs.NCO_sqft, "unit": "sqft",
                         "confidence": specs.confidence, "trace": specs.trace},
                    ],
                    citations=[section.as_citation()],
                    draft_comment_text=f"Window {w.tag} in {bedroom.label} has NCO of "
                                       f"{specs.NCO_sqft:.1f} sqft; CRC §R310.2.1 requires ≥ 5.7 sqft.",
                    confidence=min(specs.confidence, section.confidence),
                ))
    return findings
```

LLM-reasoning passes follow the same shape with an additional step: the agent constructs a reasoning chain over tool outputs and emits a narrative finding. The chain is logged. The retrieved sections are frozen into the finding. **The model never paraphrases code text — it cites what it retrieved.**
