"""
ComparisonAgent — Phase 07.

Aligns AI findings against authority (BV) external review comments for a
given project + round.  Produces alignment_records rows with buckets:
  matched        — AI finding and authority comment address the same issue
  missed         — authority comment has no AI counterpart
  false_positive — AI finding has no matching authority comment
  partial        — overlap but not full alignment (low similarity score)

Algorithm:
1. Build candidate pairs: (finding, comment) pairs that share a sheet_reference
   OR have overlapping citation section numbers.
2. Compute similarity scores:
   - Sheet match: +0.3 if same sheet label
   - Citation overlap: +0.3 per shared section number (capped at 0.4)
   - Text similarity: Levenshtein ratio of comment texts (0.0–0.4)
   Total possible: 1.0
3. Hungarian assignment on the cost matrix (1 - similarity) to find optimal
   bijective matching.
4. Classify each pair:
   - similarity >= 0.55 → matched
   - 0.3 <= similarity < 0.55 → partial
   - finding with no pair → false_positive
   - comment with no pair → missed
"""
from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

try:
    from scipy.optimize import linear_sum_assignment
    import numpy as np
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy not available; falling back to greedy alignment.")


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
MATCHED_THRESHOLD = 0.55
PARTIAL_THRESHOLD = 0.30


@dataclass
class AlignmentRecord:
    alignment_id: str
    project_id: str
    review_round: int
    finding_id: str | None
    comment_id: str | None
    bucket: str          # matched | missed | false_positive | partial
    similarity_score: float


# ---------------------------------------------------------------------------
# Similarity helpers
# ---------------------------------------------------------------------------

def _sheet_similarity(finding: dict[str, Any], comment: dict[str, Any]) -> float:
    """0.3 if the finding's resolved sheet label matches the comment's sheet_ref."""
    f_sheet = (finding.get("sheet_reference") or {})
    f_label = f_sheet.get("sheet_label") or f_sheet.get("sheet_id") or ""
    c_sheet = comment.get("sheet_ref") or ""
    if not f_label or not c_sheet:
        return 0.0
    # Normalise: upper-case, strip spaces
    f_norm = f_label.upper().replace(" ", "")
    c_norm = c_sheet.upper().replace(" ", "")
    if f_norm == c_norm or f_norm in c_norm or c_norm in f_norm:
        return 0.3
    return 0.0


def _citation_similarity(finding: dict[str, Any], comment: dict[str, Any]) -> float:
    """Up to 0.4 based on overlapping citation section numbers."""
    citations = finding.get("citations") or []
    f_sections: set[str] = set()
    for cit in citations:
        if isinstance(cit, dict):
            sec = cit.get("section") or ""
            # Normalise section: "R310.2.1" → "R310.2.1"
            f_sections.add(sec.strip().upper())

    c_text = (comment.get("comment_text") or "").upper()
    matches = sum(1 for s in f_sections if s and s in c_text)
    return min(0.4, matches * 0.2)


def _text_similarity(text_a: str, text_b: str) -> float:
    """Levenshtein ratio mapped to 0.0–0.4 range."""
    if not text_a or not text_b:
        return 0.0
    # Simple character-level Levenshtein ratio (no external deps)
    a, b = text_a[:300].lower(), text_b[:300].lower()
    if a == b:
        return 0.4
    len_a, len_b = len(a), len(b)
    # DP Levenshtein
    prev = list(range(len_b + 1))
    for i, ca in enumerate(a):
        curr = [i + 1] + [0] * len_b
        for j, cb in enumerate(b):
            curr[j + 1] = min(
                curr[j] + 1,
                prev[j + 1] + 1,
                prev[j] + (0 if ca == cb else 1),
            )
        prev = curr
    distance = prev[len_b]
    ratio = 1.0 - distance / max(len_a, len_b)
    return round(ratio * 0.4, 4)


def _compute_similarity(finding: dict[str, Any], comment: dict[str, Any]) -> float:
    score = (
        _sheet_similarity(finding, comment)
        + _citation_similarity(finding, comment)
        + _text_similarity(
            finding.get("draft_comment_text") or "",
            comment.get("comment_text") or "",
        )
    )
    return min(1.0, round(score, 4))


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

def align(
    findings: list[dict[str, Any]],
    comments: list[dict[str, Any]],
    project_id: str,
    review_round: int,
) -> list[AlignmentRecord]:
    """
    Align findings against authority comments and return AlignmentRecord list.
    """
    records: list[AlignmentRecord] = []

    if not findings and not comments:
        return records

    if not findings:
        return [
            AlignmentRecord(
                alignment_id=str(uuid.uuid4()),
                project_id=project_id,
                review_round=review_round,
                finding_id=None,
                comment_id=str(c["comment_id"]),
                bucket="missed",
                similarity_score=0.0,
            )
            for c in comments
        ]

    if not comments:
        return [
            AlignmentRecord(
                alignment_id=str(uuid.uuid4()),
                project_id=project_id,
                review_round=review_round,
                finding_id=str(f["finding_id"]),
                comment_id=None,
                bucket="false_positive",
                similarity_score=0.0,
            )
            for f in findings
        ]

    n_f, n_c = len(findings), len(comments)

    # Build full similarity matrix (findings x comments)
    sim_matrix = [
        [_compute_similarity(f, c) for c in comments]
        for f in findings
    ]

    # Hungarian assignment on cost matrix
    assigned_f: set[int] = set()
    assigned_c: set[int] = set()
    pairs: list[tuple[int, int]] = []

    if HAS_SCIPY:
        import numpy as np  # noqa: PLC0415
        cost = np.array([[1.0 - s for s in row] for row in sim_matrix])
        row_ind, col_ind = linear_sum_assignment(cost)
        assigned_f = set(int(i) for i in row_ind)
        assigned_c = set(int(i) for i in col_ind)
        pairs = [(int(r), int(c)) for r, c in zip(row_ind, col_ind)]
    else:
        # Greedy fallback: sort by similarity desc, assign greedily
        candidates = sorted(
            [(i, j, sim_matrix[i][j]) for i in range(n_f) for j in range(n_c)],
            key=lambda x: -x[2],
        )
        for fi, ci, _ in candidates:
            if fi not in assigned_f and ci not in assigned_c:
                assigned_f.add(fi)
                assigned_c.add(ci)
                pairs.append((fi, ci))

    # Classify pairs — low-similarity pairs are discarded, freeing both sides
    low_sim_f: set[int] = set()
    low_sim_c: set[int] = set()

    for fi, ci in pairs:
        sim = sim_matrix[fi][ci]
        if sim >= MATCHED_THRESHOLD:
            bucket = "matched"
        elif sim >= PARTIAL_THRESHOLD:
            bucket = "partial"
        else:
            # Below both thresholds: treat both sides as unmatched
            low_sim_f.add(fi)
            low_sim_c.add(ci)
            continue
        records.append(AlignmentRecord(
            alignment_id=str(uuid.uuid4()),
            project_id=project_id,
            review_round=review_round,
            finding_id=str(findings[fi]["finding_id"]),
            comment_id=str(comments[ci]["comment_id"]),
            bucket=bucket,
            similarity_score=sim,
        ))

    # Findings not in any accepted pair → false_positive
    effective_assigned_f = assigned_f - low_sim_f
    for fi in range(n_f):
        if fi not in effective_assigned_f:
            records.append(AlignmentRecord(
                alignment_id=str(uuid.uuid4()),
                project_id=project_id,
                review_round=review_round,
                finding_id=str(findings[fi]["finding_id"]),
                comment_id=None,
                bucket="false_positive",
                similarity_score=0.0,
            ))

    # Comments not in any accepted pair → missed
    effective_assigned_c = assigned_c - low_sim_c
    for ci in range(n_c):
        if ci not in effective_assigned_c:
            records.append(AlignmentRecord(
                alignment_id=str(uuid.uuid4()),
                project_id=project_id,
                review_round=review_round,
                finding_id=None,
                comment_id=str(comments[ci]["comment_id"]),
                bucket="missed",
                similarity_score=0.0,
            ))

    return records
