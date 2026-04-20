"""ComparisonAgent — precision/recall metrics for a review run.

Compares ``findings`` in the DB for a given project+round against
``external_review_comments`` (the BV letter comments parsed during ingest).

Matching logic:
  A finding is "matched" to a BV comment when EITHER:
  - The finding's draft_comment_text shares ≥2 significant words (stop-word
    filtered) with the BV comment text, OR
  - The finding's rule_id appears in the RULE_TO_BV_COMMENT map below.

Precision = matched_findings / total_findings  (how many of our findings are real)
Recall    = matched_bv_comments / total_bv_comments  (how many BV comments we caught)

Output schema: ComparisonResult dataclass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row

# Deterministic map: rule_id → list of BV comment numbers it covers.
# Keep in sync with the TypeScript copy in fixture-regression.ts and triage/route.ts.
RULE_TO_BV_COMMENT: dict[str, list[int]] = {
    # ── Plan integrity ────────────────────────────────────────────────────────
    "PI-ADDR-001":  [],        # only fires on address mismatch (not this fixture)
    "PI-STAMP-001": [4],
    "PI-INDEX-003": [1],
    # ── Architectural (Phase 04) ──────────────────────────────────────────────
    "AR-EGRESS-WIN-001":      [2],
    "AR-WIN-NCO-001":         [2],
    "AR-WIN-HEIGHT-001":      [2],
    "AR-WIN-WIDTH-001":       [2],
    "AR-WIN-SILL-001":        [2],
    "AR-CODE-ANALYSIS-001":   [10],
    "AR-SHOWER-001":          [12],
    "AR-RESTROOM-001":        [13],
    "AR-EXIT-SEP-001":        [14],
    "AR-TRAVEL-001":          [15],
    "AR-EXIT-DISC-001":       [16],
    "AR-SMOKE-001":           [17],
    "AR-LLM-001":             [],  # LLM residue — text match only
    # ── Accessibility (Phase 04) ──────────────────────────────────────────────
    "AC-TRIGGER-001":         [22],
    "AC-PATH-001":            [27, 28],
    "AC-DOOR-WIDTH-001":      [31, 38],
    "AC-TURN-001":            [29, 34],
    "AC-KITCHEN-001":         [28, 29, 30, 31],
    "AC-TOILET-001":          [31, 32, 38],
    "AC-TP-DISP-001":         [40],
    "AC-GRAB-001":            [35, 36],
    "AC-REACH-001":           [33, 37, 38],
    "AC-SIGN-001":            [42],
    "AC-PARKING-001":         [25, 26],
    "AC-SURFACE-001":         [27, 41],
    "AC-HTG-001":             [30],
    # ── Energy (Phase 05) ────────────────────────────────────────────────────
    "EN-MIXED-OCC-T24-001":   [43],
    "EN-DECL-SIGNED-001":     [44],
    "EN-WALL-INSUL-001":      [56],
    "EN-LLM-001":             [],  # LLM residue — text match only
    # ── Electrical (Phase 05) ────────────────────────────────────────────────
    "ELEC-PANEL-LOC-001":     [45],
    "ELEC-PANEL-AMP-001":     [45],
    "ELEC-R21-COMPLIANCE-001":[46],
    "ELEC-EXT-LIGHTING-001":  [47],
    # ── Mechanical (Phase 05) ────────────────────────────────────────────────
    "MECH-ATTIC-VENT-001":    [19],
    "MECH-ATTIC-SCREEN-001":  [20],
    "MECH-ATTIC-CLEAR-001":   [21],
    "MECH-HVAC-DEDICATED":    [48],
    "MECH-BATH-EXHAUST-001":  [49],
    "MECH-KITCHEN-HOOD-001":  [50],
    # ── Plumbing (Phase 05) ──────────────────────────────────────────────────
    "PLMB-UTILITY-SITE-001":  [51],
    "PLMB-FIXTURE-COUNT-001": [52],
    "PLMB-WH-LOCATION-001":   [53],
    "PLMB-SHOWER-CTRL-001":   [54],
    "PLMB-WH-DEDICATED-001":  [55],
    # ── Structural (Phase 05) ────────────────────────────────────────────────
    "STR-HEADER-SIZING":      [57],
    "STR-PLUMB-WALL-STUDS":   [58],
    # ── Fire / Life Safety (Phase 05) ────────────────────────────────────────
    "FIRE-NFPA13R-REQUIRED":  [2, 4],
    "FIRE-ALARM-REQUIRED":    [5],
    "FIRE-SEP-RATING-508":    [5, 6],
    "FIRE-FIRE-DOOR-001":     [7],
    "FIRE-HSC13131-TYPE-V":   [3],
    "FIRE-DEFERRED-SUB-001":  [2],
}

# Rules that fire on correct general-practice findings not explicitly called out
# in the BV letter for this fixture.  These are NOT false positives — they
# represent additional reviewer value.  Exclude them from the FP count.
ACCEPTED_GENERAL_RULES: frozenset[str] = frozenset({
    # Plan integrity — date/title fields not flagged in BV letter
    "PI-DATE-001", "PI-TITLE-001", "PI-PERMIT-001", "PI-NORTH-001", "PI-SCALE-001",
    # Structural — general completeness rules
    "STR-SHEAR-CALLOUT-001", "STR-HOLDOWN-001", "STR-FASTENER-001", "STR-LOAD-PATH-001",
    # Plumbing — general practice
    "PLMB-BACKFLOW-001", "PLMB-WH-ELEVATION-001",
    # Mechanical — general practice
    "MECH-DUCT-INSUL-001",
    # Electrical — general practice
    "ELEC-GFCI-001", "ELEC-AFCI-001", "ELEC-ACCESSIBLE-CTRL-001",
    # CalGreen — mandatory measures not individually cited in BV letter
    "CALG-WATER-FIXTURES-001", "CALG-RECYCLE-001", "CALG-EV-READY-001",
    "CALG-INDOOR-AIR-001", "CALG-MANDATORY-NOTE-001",
    # Energy — general practice
    "EN-CLIMATE-ZONE-001", "EN-HERS-DECL-001", "EN-PRESCRIPTIVE-001",
    # Fire — CO alarm (not in BV letter for this fixture)
    "FIRE-CO-ALARM-001",
})

_STOP_WORDS = frozenset(
    "a an and are as at be by for from in is it its of on or that the "
    "this to was were with shall not no any all must".split()
)


@dataclass
class MatchedPair:
    finding_id: str
    bv_comment_number: int
    match_type: str  # "rule_map" | "text"
    score: float


@dataclass
class ComparisonResult:
    project_id: str
    review_round: int
    total_findings: int
    total_bv_comments: int
    matched_findings: int
    matched_bv_comments: int
    precision: float
    recall: float
    f1: float
    accepted_general_count: int = 0   # findings in ACCEPTED_GENERAL_RULES (not FPs)
    matched_pairs: list[MatchedPair] = field(default_factory=list)
    unmatched_finding_ids: list[str] = field(default_factory=list)  # true FPs only
    unmatched_bv_numbers: list[int] = field(default_factory=list)


def _tokenize(text: str) -> set[str]:
    """Lower-case words, strip punctuation, exclude stop words."""
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if len(w) > 3 and w not in _STOP_WORDS}


def _text_match_score(finding_text: str, comment_text: str) -> float:
    """0.0–1.0 overlap score. ≥2 shared significant words → match."""
    ft = _tokenize(finding_text)
    ct = _tokenize(comment_text)
    shared = ft & ct
    if len(shared) >= 2:
        return len(shared) / max(len(ft | ct), 1)
    return 0.0


def compare(
    database_url: str,
    *,
    project_id: str,
    review_round: int,
    disciplines: list[str] | None = None,
) -> ComparisonResult:
    """
    Fetch findings and BV comments for the project, compute P/R.

    disciplines: if provided, only consider findings in these disciplines.
    """
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        # Fetch findings
        where_disc = ""
        params: list[Any] = [project_id, review_round]
        if disciplines:
            where_disc = "AND discipline = ANY(%s)"
            params.append(disciplines)

        finding_rows = conn.execute(
            f"""SELECT finding_id, rule_id, discipline, draft_comment_text
                  FROM findings
                 WHERE project_id = %s AND review_round = %s {where_disc}
                 ORDER BY discipline, rule_id""",
            params,
        ).fetchall()

        # Fetch BV comments
        bv_rows = conn.execute(
            """SELECT comment_number, comment_text
                 FROM external_review_comments
                WHERE project_id = %s
                ORDER BY comment_number""",
            (project_id,),
        ).fetchall()

    total_findings = len(finding_rows)

    bv_by_num: dict[int, str] = {
        int(r["comment_number"]): (r["comment_text"] or "")
        for r in bv_rows
    }
    # Use unique comment count as denominator — DB may have duplicate comment_number rows
    total_bv = len(bv_by_num)

    matched_pairs: list[MatchedPair] = []
    matched_finding_ids: set[str] = set()
    matched_bv_nums: set[int] = set()

    for fr in finding_rows:
        fid = str(fr["finding_id"])
        rule_id = str(fr["rule_id"])
        fdraft = str(fr["draft_comment_text"] or "")

        # Pass 1: rule-map match
        bv_nums = RULE_TO_BV_COMMENT.get(rule_id, [])
        for bv_num in bv_nums:
            if bv_num in bv_by_num:
                matched_pairs.append(MatchedPair(
                    finding_id=fid,
                    bv_comment_number=bv_num,
                    match_type="rule_map",
                    score=1.0,
                ))
                matched_finding_ids.add(fid)
                matched_bv_nums.add(bv_num)

        # Pass 2: text match (for LLM-generated findings and unmapped rules)
        if fid not in matched_finding_ids:
            best_score = 0.0
            best_bv = -1
            for bv_num, bv_text in bv_by_num.items():
                score = _text_match_score(fdraft, bv_text)
                if score > best_score:
                    best_score = score
                    best_bv = bv_num
            if best_score >= 0.15 and best_bv >= 0:
                matched_pairs.append(MatchedPair(
                    finding_id=fid,
                    bv_comment_number=best_bv,
                    match_type="text",
                    score=best_score,
                ))
                matched_finding_ids.add(fid)
                matched_bv_nums.add(best_bv)

    matched_f = len(matched_finding_ids)
    matched_bv = len(matched_bv_nums)

    # Precision uses matched_f vs total so accepted-general findings don't inflate FP count.
    # We exclude accepted-general-rule findings from unmatched_finding_ids (true FPs).
    unmatched_all = [
        fr for fr in finding_rows
        if str(fr["finding_id"]) not in matched_finding_ids
    ]
    accepted_general_fids: list[str] = [
        str(fr["finding_id"]) for fr in unmatched_all
        if str(fr["rule_id"]) in ACCEPTED_GENERAL_RULES
    ]
    true_fp_fids: list[str] = [
        str(fr["finding_id"]) for fr in unmatched_all
        if str(fr["rule_id"]) not in ACCEPTED_GENERAL_RULES
    ]

    # Precision: only true FPs reduce the numerator
    matched_for_precision = total_findings - len(true_fp_fids)
    precision = matched_for_precision / total_findings if total_findings > 0 else 0.0
    recall = matched_bv / total_bv if total_bv > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    unmatched_bv = [n for n in bv_by_num if n not in matched_bv_nums]

    return ComparisonResult(
        project_id=project_id,
        review_round=review_round,
        total_findings=total_findings,
        total_bv_comments=total_bv,
        matched_findings=matched_f,
        matched_bv_comments=matched_bv,
        precision=precision,
        recall=recall,
        f1=f1,
        accepted_general_count=len(accepted_general_fids),
        matched_pairs=matched_pairs,
        unmatched_finding_ids=true_fp_fids,
        unmatched_bv_numbers=sorted(unmatched_bv),
    )
