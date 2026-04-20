"""Energy reviewer — Phase 05.

Deterministic rules:
  EN-MIXED-OCC-T24-001   Separate T24 docs not provided for mixed occupancy — BV #43
  EN-DECL-SIGNED-001     Responsible Person Declaration not signed — BV #44
  EN-WALL-INSUL-001      Wall insulation R-value not specified per T24 — BV #56
  EN-CLIMATE-ZONE-001    Climate zone not declared on plans
  EN-HERS-DECL-001       HERS measures not declared on plans
  EN-PRESCRIPTIVE-001    T24 compliance path not declared (prescriptive vs performance)
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import anthropic
import psycopg
import psycopg.rows

from app.reviewers._context import (
    ArchAccessRuleContext,
    FindingPayload,
    emit_findings_aa,
    get_citation_aa,
    load_arch_access_context,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skill — loaded once at import time.
# ---------------------------------------------------------------------------

_SKILL_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "skills"
    / "energy"
    / "SKILL.md"
)


def _load_skill() -> str:
    try:
        return _SKILL_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Energy skill file not found at %s", _SKILL_PATH)
        return ""


_SKILL_TEXT: str = _load_skill()


# ---------------------------------------------------------------------------
# Rule version stamps
# ---------------------------------------------------------------------------

_RULE_VERSIONS: dict[str, str] = {
    "EN-MIXED-OCC-T24-001": "1.0.0",
    "EN-DECL-SIGNED-001":   "1.0.0",
    "EN-WALL-INSUL-001":    "1.0.0",
    "EN-CLIMATE-ZONE-001":  "1.0.0",
    "EN-HERS-DECL-001":     "1.0.0",
    "EN-PRESCRIPTIVE-001":  "1.0.0",
    "EN-LLM-001":           "1.0.0",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _project_ref() -> dict[str, Any]:
    return {"sheet_id": None, "detail": "Project-wide"}


def _sheet_ref(sheet_id: str | None, detail: str | None = None) -> dict[str, Any]:
    return {"sheet_id": sheet_id, "detail": detail}


def _fallback_citation(code: str, section: str) -> dict[str, Any]:
    """Return a sentinel citation when the KB has no live text for this section.

    NEVER invents frozen_text. The ``note`` field signals that the KB seed
    must be updated before the citation resolves.
    """
    return {
        "code": code,
        "section": section,
        "canonical_id": f"{code}-{section}",
        "frozen_text": None,
        "note": "Section not yet in KB — seed required",
    }


def _get_citations(
    ctx: ArchAccessRuleContext, *canonical_ids: str
) -> list[dict[str, Any]]:
    """Fetch citations from the KB; fall back gracefully when absent.

    Returns a non-empty list in all cases so findings always carry at least
    a reference stub.
    """
    result: list[dict[str, Any]] = []
    for cid in canonical_ids:
        cit = get_citation_aa(ctx, cid)
        if cit is not None:
            result.append(cit)
        else:
            # Parse the canonical_id into code + section for the fallback.
            code, _, section = cid.partition("-")
            result.append(_fallback_citation(code, section))
    return result


def _has_entity_type(ctx: ArchAccessRuleContext, etype: str) -> bool:
    return any(e.entity_type == etype for e in ctx.floor_plan_entities)


def _has_code_note_keyword(ctx: ArchAccessRuleContext, *keywords: str) -> bool:
    """True if any code_note OR title24_form entity mentions any of the keywords."""
    kws = [k.lower() for k in keywords]
    for e in ctx.floor_plan_entities:
        if e.entity_type not in ("code_note", "title24_form"):
            continue
        label = (e.room_label or "").lower()
        notes = (e.geometry_notes or "").lower()
        combined = label + " " + notes
        if any(kw in combined for kw in kws):
            return True
    return False


def _has_title24_form(ctx: ArchAccessRuleContext) -> bool:
    """True if any title24_form entity exists in the project."""
    return _has_entity_type(ctx, "title24_form")


def _has_plan_set_code_note_keyword(ctx: ArchAccessRuleContext, *keywords: str) -> bool:
    """True if any code_note entity (NOT title24_form) mentions any of the keywords."""
    kws = [k.lower() for k in keywords]
    for e in ctx.floor_plan_entities:
        if e.entity_type != "code_note":
            continue
        label = (e.room_label or "").lower()
        notes = (e.geometry_notes or "").lower()
        combined = label + " " + notes
        if any(kw in combined for kw in kws):
            return True
    return False


# ---------------------------------------------------------------------------
# EN-MIXED-OCC-T24-001 — Separate T24 docs not provided for mixed occupancy
# ---------------------------------------------------------------------------


def rule_en_mixed_occ_t24_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """BV #43: mixed R-3 + R-2.1 occupancies need separate T24 compliance docs.

    Fires when R-2.1 indicators are present but no code_note or title24_form
    entity mentions "R-2.1" or "separate" T24 compliance.
    """
    # Check whether any entity signals R-2.1 occupancy on the project.
    has_r21_indicator = _has_code_note_keyword(ctx, "r-2.1", "r2.1", "r 2.1")
    if not has_r21_indicator:
        return []

    # R-2.1 indicator found — check whether separate T24 compliance is addressed.
    has_separate_t24 = _has_code_note_keyword(ctx, "r-2.1", "separate") and (
        _has_code_note_keyword(ctx, "separate") or _has_title24_form(ctx)
    )
    # More precise: both an R-2.1 mention AND a "separate" mention in T24 context
    has_separate_t24 = _has_code_note_keyword(ctx, "separate") and _has_code_note_keyword(
        ctx, "r-2.1", "r2.1", "r 2.1"
    )

    if has_separate_t24:
        return []

    citations = _get_citations(ctx, "CEnC-100.0-f")
    return [
        FindingPayload(
            rule_id="EN-MIXED-OCC-T24-001",
            rule_version=_RULE_VERSIONS["EN-MIXED-OCC-T24-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                "The project contains both Group R-3 and Group R-2.1 occupancies. "
                "Provide separate Title 24 Part 6 energy compliance documentation "
                "(CF1R forms) for each occupancy classification. Each occupancy shall "
                "independently comply with the applicable energy requirements. "
                "(CEnC \u00a7100.0(f))"
            ),
            confidence=0.85,
        )
    ]


# ---------------------------------------------------------------------------
# EN-DECL-SIGNED-001 — Responsible Person Declaration not signed
# ---------------------------------------------------------------------------


def rule_en_decl_signed_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """BV #44: T24 Responsible Person's Declaration Statement must be signed.

    Fires when a title24_form entity exists but no code_note mentions "signed"
    or "responsible person declaration". Also fires when no title24_form exists.
    """
    has_t24 = _has_title24_form(ctx)

    # If no T24 form entity at all, emit (can't confirm it was submitted signed).
    if not has_t24:
        citations = _get_citations(ctx, "CEnC-150.1-a")
        return [
            FindingPayload(
                rule_id="EN-DECL-SIGNED-001",
                rule_version=_RULE_VERSIONS["EN-DECL-SIGNED-001"],
                severity="provide",
                sheet_reference=_project_ref(),
                evidence=[],
                citations=citations,
                draft_comment_text=(
                    "The Responsible Person\u2019s Declaration Statement on the Title 24 "
                    "energy compliance documentation must be signed and dated by the "
                    "responsible person of record (not the energy consultant who prepared "
                    "the forms). Provide signed CF1R forms with the permit submittal. "
                    "(CEnC \u00a7100.0)"
                ),
                confidence=0.80,
                requires_licensed_review=True,
            )
        ]

    # T24 form exists — check if signed declaration is noted.
    has_signed_note = _has_code_note_keyword(ctx, "signed", "responsible person declaration")
    if has_signed_note:
        return []

    citations = _get_citations(ctx, "CEnC-150.1-a")
    return [
        FindingPayload(
            rule_id="EN-DECL-SIGNED-001",
            rule_version=_RULE_VERSIONS["EN-DECL-SIGNED-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                "The Responsible Person\u2019s Declaration Statement on the Title 24 "
                "energy compliance documentation must be signed and dated by the "
                "responsible person of record (not the energy consultant who prepared "
                "the forms). Provide signed CF1R forms with the permit submittal. "
                "(CEnC \u00a7100.0)"
            ),
            confidence=0.82,
            requires_licensed_review=True,
        )
    ]


# ---------------------------------------------------------------------------
# EN-WALL-INSUL-001 — Wall insulation R-value not specified per T24
# ---------------------------------------------------------------------------


def rule_en_wall_insul_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """BV #56: T24 specifies R-19 batt insulation with 2x6 framing — plans must match.

    Fires when a title24_form or code_note mentions "R-19" or "2x6" wall
    insulation, but no plan-set code_note (type != 'title24_form') confirms R-19.
    """
    # Check if T24 documentation or any entity signals R-19 / 2x6 wall insulation.
    t24_or_note_mentions_r19 = _has_code_note_keyword(ctx, "r-19", "r19", "2x6")
    if not t24_or_note_mentions_r19:
        # No T24 requirement detected — rule does not fire.
        return []

    # R-19 requirement found — check if plan-set code_notes (not title24_form) confirm it.
    plan_set_confirms = _has_plan_set_code_note_keyword(ctx, "r-19", "r19", "2x6")
    if plan_set_confirms:
        return []

    citations = _get_citations(ctx, "CEnC-150.1-a")
    return [
        FindingPayload(
            rule_id="EN-WALL-INSUL-001",
            rule_version=_RULE_VERSIONS["EN-WALL-INSUL-001"],
            severity="revise",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                'The Title 24 energy documentation specifies R-19 batt insulation with '
                '2x6 framing at exterior walls. Provide a note on the wall framing plan '
                'specifying \u201c2x6 studs at 16\u2033 o.c. with R-19 batt insulation\u201d '
                'for all exterior walls to match the approved Title 24 compliance '
                "documentation. (CEnC \u00a7150.1(a))"
            ),
            confidence=0.87,
        )
    ]


# ---------------------------------------------------------------------------
# EN-CLIMATE-ZONE-001 — Climate zone not declared
# ---------------------------------------------------------------------------


def rule_en_climate_zone_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when climate zone is not declared on plans or T24 forms."""
    if _has_code_note_keyword(ctx, "climate zone", "cz", "zone 2"):
        return []

    citations = _get_citations(ctx, "CEnC-100.0-f")
    return [
        FindingPayload(
            rule_id="EN-CLIMATE-ZONE-001",
            rule_version=_RULE_VERSIONS["EN-CLIMATE-ZONE-001"],
            severity="clarify",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                "Confirm the climate zone on the energy compliance forms matches the "
                "project location. The City of Santa Rosa is in Climate Zone 2. The "
                "climate zone shall be clearly stated on all Title 24 compliance "
                "documentation."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# EN-HERS-DECL-001 — HERS measures not declared
# ---------------------------------------------------------------------------


def rule_en_hers_decl_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Provide finding when a T24 form exists but HERS measures are not mentioned."""
    if not _has_title24_form(ctx):
        return []

    if _has_code_note_keyword(ctx, "hers", "duct test", "infiltration", "hers measure"):
        return []

    citations = _get_citations(ctx, "CEnC-150.1-a")
    return [
        FindingPayload(
            rule_id="EN-HERS-DECL-001",
            rule_version=_RULE_VERSIONS["EN-HERS-DECL-001"],
            severity="provide",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                "If the Title 24 compliance path includes any HERS-required measures "
                "(high-efficiency HVAC, duct testing, infiltration testing), list all "
                "required HERS measures on the plans or T24 forms and specify which "
                "HERS verification tests are required prior to final inspection."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# EN-PRESCRIPTIVE-001 — T24 compliance path not declared
# ---------------------------------------------------------------------------


def rule_en_prescriptive_001(ctx: ArchAccessRuleContext) -> list[FindingPayload]:
    """Clarify finding when neither 'prescriptive' nor 'performance' is noted."""
    if _has_code_note_keyword(ctx, "prescriptive", "performance"):
        return []

    citations = _get_citations(ctx, "CEnC-150.1-a")
    return [
        FindingPayload(
            rule_id="EN-PRESCRIPTIVE-001",
            rule_version=_RULE_VERSIONS["EN-PRESCRIPTIVE-001"],
            severity="clarify",
            sheet_reference=_project_ref(),
            evidence=[],
            citations=citations,
            draft_comment_text=(
                "Indicate on the plans or Title 24 documentation whether the project "
                "is using the prescriptive or performance compliance path for each "
                "occupancy. Label each set of Title 24 forms accordingly."
            ),
            confidence=0.80,
        )
    ]


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_RULES = [
    rule_en_mixed_occ_t24_001,
    rule_en_decl_signed_001,
    rule_en_wall_insul_001,
    rule_en_climate_zone_001,
    rule_en_hers_decl_001,
    rule_en_prescriptive_001,
]


# ---------------------------------------------------------------------------
# LLM residue pass — EN-LLM-001
# ---------------------------------------------------------------------------


def _build_project_summary(
    ctx: ArchAccessRuleContext,
    deterministic_findings: list[FindingPayload],
) -> str:
    """Construct a compact text summary of the project for the LLM prompt."""
    code_note_count = sum(
        1 for e in ctx.floor_plan_entities if e.entity_type == "code_note"
    )
    t24_form_count = sum(
        1 for e in ctx.floor_plan_entities if e.entity_type == "title24_form"
    )
    sheet_titles = ", ".join(
        f"{s.canonical_id or s.sheet_id}: {s.canonical_title or '(no title)'}"
        for s in ctx.sheets[:12]
    )
    already_flagged = [fp.rule_id for fp in deterministic_findings]

    return (
        f"Project: {ctx.project_address} | jurisdiction: {ctx.jurisdiction} | "
        f"effective_date: {ctx.effective_date}\n"
        f"Sheets ({len(ctx.sheets)}): {sheet_titles}\n"
        f"Title 24 form entities: {t24_form_count}\n"
        f"Code note entities: {code_note_count}\n"
        f"Deterministic rules already fired: {', '.join(already_flagged) or 'none'}"
    )


def _hash_prompt(system: str, user: str, model: str) -> str:
    content = f"{model}|{system}|{user}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _run_llm_residue(
    ctx: ArchAccessRuleContext,
    anthropic_api_key: str,
    deterministic_findings: list[FindingPayload],
) -> list[FindingPayload]:
    """Run a single LLM call (temperature=0) to catch energy residue issues.

    Returns a (possibly empty) list of additional FindingPayloads.
    Every citation is retrieved live from the KB; if not found the citation
    stub is included with frozen_text=None rather than hallucinated text.
    """
    if not _SKILL_TEXT:
        logger.warning(
            "EN-LLM-001 skipped: energy skill text is empty (file missing?)."
        )
        return []

    project_summary = _build_project_summary(ctx, deterministic_findings)
    already_fired = [fp.rule_id for fp in deterministic_findings]

    user_prompt = (
        "You are reviewing a residential building permit plan set for compliance with "
        "the 2022 California Energy Code (Title 24, Part 6).\n\n"
        f"Project summary:\n{project_summary}\n\n"
        "The following deterministic rule IDs have already been emitted and must NOT "
        f"be duplicated: {', '.join(already_fired) or 'none'}.\n\n"
        "Identify any additional ENERGY code compliance issues not already covered by "
        "those rules. Focus on: mandatory measures, envelope insulation, window "
        "performance (U-factor, SHGC), lighting (JA8), water heating, mechanical "
        "ventilation, and CF1R/CF2R/CF3R documentation completeness.\n\n"
        "Respond with a JSON array only — no prose before or after. Each element:\n"
        "{\n"
        '  "rule_id": "EN-LLM-001",\n'
        '  "severity": "revise" | "provide" | "clarify" | "reference_only",\n'
        '  "draft_comment_text": "<specific, non-hallucinated comment>",\n'
        '  "sheet_id": "<sheet_id or null>",\n'
        '  "citations": [{"code": "<CEnC|CBC>", "section": "<section>"}],\n'
        '  "confidence": <0.70 to 0.80>\n'
        "}\n"
        "If no additional issues are found, respond with an empty array: []"
    )

    model = "claude-sonnet-4-6"
    prompt_hash = _hash_prompt(_SKILL_TEXT, user_prompt, model)
    t0 = time.monotonic()

    try:
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=0,
            system=_SKILL_TEXT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw_text = response.content[0].text if response.content else "[]"
        usage = response.usage

        logger.info(
            "EN-LLM-001 call complete: model=%s prompt_hash=%s "
            "input_tokens=%d output_tokens=%d latency_ms=%d",
            model,
            prompt_hash,
            usage.input_tokens,
            usage.output_tokens,
            latency_ms,
        )
    except Exception as exc:  # pragma: no cover
        logger.error("EN-LLM-001 Anthropic API call failed: %s", exc)
        return []

    # Parse the JSON response.
    try:
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        llm_items: list[dict[str, Any]] = json.loads(stripped)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("EN-LLM-001 JSON parse failed (%s). Raw: %r", exc, raw_text[:300])
        return []

    if not isinstance(llm_items, list):
        logger.warning("EN-LLM-001 unexpected JSON type: %s", type(llm_items))
        return []

    findings: list[FindingPayload] = []
    for item in llm_items:
        if not isinstance(item, dict):
            continue

        severity = item.get("severity", "clarify")
        if severity not in ("revise", "provide", "clarify", "reference_only"):
            severity = "clarify"

        confidence = float(item.get("confidence", 0.73))
        confidence = max(0.60, min(0.85, confidence))  # clamp to LLM range

        sheet_id: str | None = item.get("sheet_id") or None
        draft_text: str = str(item.get("draft_comment_text", "")).strip()

        # Retrieve citations from the KB; never use LLM-supplied frozen text.
        raw_citations: list[dict[str, Any]] = item.get("citations", [])
        retrieved_citations: list[dict[str, Any]] = []
        for rc in raw_citations:
            if not isinstance(rc, dict):
                continue
            code = rc.get("code", "")
            section = rc.get("section", "")
            if not code or not section:
                continue
            canonical_id = f"{code.upper()}-{section}"
            live = get_citation_aa(ctx, canonical_id)
            if live is not None:
                retrieved_citations.append(live)
            else:
                retrieved_citations.append(_fallback_citation(code, section))

        if not draft_text:
            continue  # skip empty findings

        findings.append(
            FindingPayload(
                rule_id="EN-LLM-001",
                rule_version=_RULE_VERSIONS["EN-LLM-001"],
                severity=severity,
                sheet_reference=_sheet_ref(sheet_id),
                evidence=[],
                citations=retrieved_citations,
                draft_comment_text=draft_text,
                confidence=confidence,
                llm_reasoner_id=model,
                prompt_hash=prompt_hash,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# EnergyReviewer — orchestrator
# ---------------------------------------------------------------------------


class EnergyReviewer:
    """Two-pass energy reviewer (Title 24 Part 6 / CEnC).

    Pass 1: deterministic rules (no LLM).
    Pass 2: LLM residue (EN-LLM-001) — only when ``anthropic_api_key`` is provided.

    Call ``run()`` once per submittal round.  It fetches all needed data from
    the database, runs every rule, and bulk-inserts findings.  The connection
    is not committed here — the caller owns the transaction.
    """

    DISCIPLINE = "energy"

    def run(
        self,
        conn: psycopg.Connection,  # type: ignore[type-arg]
        *,
        project_id: str,
        submittal_id: str,
        review_round: int,
        database_url: str,
        anthropic_api_key: str | None = None,
        extractor_versions_used: list[str] | None = None,
    ) -> list[str]:
        """Run all energy rules and persist findings.

        Returns the list of created finding IDs.  The caller must commit.
        """
        ctx: ArchAccessRuleContext = load_arch_access_context(
            conn,
            project_id=project_id,
            submittal_id=submittal_id,
            review_round=review_round,
            database_url=database_url,
        )

        all_findings: list[FindingPayload] = []

        # --- Pass 1: deterministic rules ---
        for rule_fn in _RULES:
            rule_findings = rule_fn(ctx)
            all_findings.extend(rule_findings)

        logger.info(
            "EnergyReviewer: %d deterministic finding(s) for project %s",
            len(all_findings),
            project_id,
        )

        # --- Pass 2: LLM residue ---
        if anthropic_api_key:
            llm_findings = _run_llm_residue(ctx, anthropic_api_key, all_findings)
            if llm_findings:
                logger.info(
                    "EnergyReviewer: EN-LLM-001 produced %d additional finding(s).",
                    len(llm_findings),
                )
            all_findings.extend(llm_findings)
        else:
            logger.warning(
                "EnergyReviewer: anthropic_api_key not provided — "
                "EN-LLM-001 residue pass skipped."
            )

        if not all_findings:
            return []

        return emit_findings_aa(
            conn,
            ctx,
            all_findings,
            self.DISCIPLINE,
            extractor_versions_used,
        )
