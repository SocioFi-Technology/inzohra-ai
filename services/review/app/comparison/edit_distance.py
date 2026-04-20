"""
Edit-distance tracker — Phase 07.

Records Levenshtein distance between the drafter's polished_text and the
human reviewer's final approved text.  Called when a reviewer saves an edit
in the UI; persists to reviewer_edits table.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class EditRecord:
    finding_id: str
    rule_id: str | None
    draft_text: str
    approved_text: str
    edit_distance: int
    edit_ratio: float   # edit_distance / max(len(draft), len(approved))


def levenshtein(a: str, b: str) -> int:
    """Pure-Python Levenshtein distance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for ca in a:
        curr = [prev[0] + 1] + [0] * len(b)
        for j, cb in enumerate(b):
            curr[j + 1] = min(
                curr[j] + 1,
                prev[j + 1] + 1,
                prev[j] + (0 if ca == cb else 1),
            )
        prev = curr
    return prev[len(b)]


def compute_edit_record(
    finding_id: str,
    rule_id: str | None,
    draft_text: str,
    approved_text: str,
) -> EditRecord:
    dist = levenshtein(draft_text, approved_text)
    denom = max(len(draft_text), len(approved_text), 1)
    return EditRecord(
        finding_id=finding_id,
        rule_id=rule_id,
        draft_text=draft_text,
        approved_text=approved_text,
        edit_distance=dist,
        edit_ratio=round(dist / denom, 4),
    )
