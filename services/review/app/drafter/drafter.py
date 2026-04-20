"""CommentDrafterAgent — Phase 06.

Takes a single finding dict (all fields from the findings DB table) and calls
Claude Sonnet at temperature=0 to produce polished BV-dialect comment-letter
text.  The agent NEVER invents citations: it uses only the ``frozen_text``
already present in the finding's ``citations`` list.

Invariants upheld:
  - Temperature always 0.
  - Structured output: the model is constrained to return exactly one paragraph
    of plain text (no markdown, no bullet points).
  - Every call is logged via the ``call_log_rows`` accumulator passed in by the
    caller; the caller is responsible for persisting those rows.
  - Prompt hash is SHA-256 of (system_prompt + user_message + model).
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL: str = "claude-sonnet-4-5"
_MAX_TOKENS: int = 512
_COST_PER_INPUT_TOKEN: float = 3e-6
_COST_PER_OUTPUT_TOKEN: float = 15e-6

# Resolve the skills root relative to this file's location:
#   services/review/app/drafter/drafter.py
#   → ../../../../../skills
_SKILLS_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent.parent.parent / "skills"
)
_EXAMPLES_PATH: Path = (
    _SKILLS_ROOT / "jurisdiction-santa-rosa" / "drafter-examples.md"
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class DraftResult:
    """Polished BV-dialect comment text and associated call telemetry."""

    polished_text: str
    prompt_hash: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_examples() -> str:
    """Load few-shot drafter examples from the jurisdiction-santa-rosa skill.

    Returns an empty string if the file is missing; the agent degrades
    gracefully by omitting the few-shot block from the system prompt.
    """
    try:
        return _EXAMPLES_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(
            "Drafter examples file not found at %s; proceeding without few-shot block.",
            _EXAMPLES_PATH,
        )
        return ""


def _build_system_prompt(examples_text: str) -> str:
    """Compose the system prompt from role description and few-shot examples."""
    few_shot_block = (
        f"<FEW_SHOT_EXAMPLES>\n{examples_text}\n</FEW_SHOT_EXAMPLES>"
        if examples_text
        else ""
    )
    return (
        "You are a BV (Bureau Veritas) plan-check reviewer writing jurisdictional "
        "comment letters for Santa Rosa Building Division.\n\n"
        "Your task: rewrite the provided draft comment into polished BV dialect.\n\n"
        "Rules:\n"
        "1. Start with the sheet reference (e.g. \"Sheet A-1.2:\").\n"
        "2. State the observed condition (measured value if present).\n"
        "3. Cite the code section inline using the EXACT frozen_text provided — "
        "do not paraphrase.\n"
        "4. End with the severity keyword: \"Revise: …\", \"Provide: …\", "
        "\"Clarify: …\", or \"Reference only: …\".\n"
        "5. One paragraph. No bullet points. No markdown. Under 120 words.\n"
        "\n"
        + few_shot_block
    )


def _build_user_message(finding: dict[str, Any]) -> str:
    """Compose the user message from the finding's key fields.

    Citations are formatted using only their ``frozen_text`` field so the
    agent cannot hallucinate code language beyond what was already retrieved.
    """
    draft_text: str = finding.get("draft_comment_text") or ""
    severity: str = finding.get("severity") or "clarify"

    sheet_ref: dict[str, Any] = finding.get("sheet_reference") or {}
    sheet_id: str = sheet_ref.get("sheet_id") or "Project-wide"
    detail: str = sheet_ref.get("detail") or ""

    # Format citations — only the frozen_text travels to the prompt.
    citations_raw: list[Any] = finding.get("citations") or []
    citation_lines: list[str] = []
    for cit in citations_raw:
        if not isinstance(cit, dict):
            continue
        code = cit.get("code", "")
        section = cit.get("section", "")
        frozen = cit.get("frozen_text")
        if frozen:
            citation_lines.append(f"{code} §{section}: {frozen}")
        elif code and section:
            # Include the stub so the model knows a citation was attempted.
            citation_lines.append(
                f"{code} §{section}: [retrieved text not yet in KB — do not invent]"
            )
    formatted_citations = "\n".join(citation_lines) if citation_lines else "None"

    return (
        f"Draft: {draft_text}\n"
        f"Sheet: {sheet_id} {detail}".strip()
        + f"\nCitations:\n{formatted_citations}\n"
        f"Severity: {severity}"
    )


def _hash_prompt(system: str, user: str, model: str) -> str:
    """Return a 16-character SHA-256 hex prefix of (system + user + model)."""
    raw = f"{system}\x00{user}\x00{model}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def draft_fallback(finding: dict[str, Any]) -> str:
    """Return the raw draft_comment_text when the API produces empty content.

    This ensures we always store *something* for every finding rather than
    an empty row.
    """
    return (finding.get("draft_comment_text") or "").strip()


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class CommentDrafterAgent:
    """Polishes a single finding's draft_comment_text into BV-dialect prose.

    The agent is stateless: construct once and call ``draft()`` for each
    finding.  Few-shot examples are loaded once at construction time.
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the agent and load the jurisdiction-specific examples.

        Args:
            api_key: Anthropic API key. Must not be a placeholder.
        """
        self._api_key: str = api_key
        self._examples_text: str = _load_examples()
        self._system_prompt: str = _build_system_prompt(self._examples_text)

    def draft(
        self,
        finding: dict[str, Any],
        call_log_rows: list[dict[str, Any]],
    ) -> DraftResult:
        """Polish a single finding into BV-dialect comment-letter text.

        Args:
            finding: Dict of all columns from the ``findings`` table.
            call_log_rows: Accumulator list; one ``llm_call_log``-shaped dict
                will be appended on every successful API call.

        Returns:
            DraftResult with the polished text and full call telemetry.

        Raises:
            RuntimeError: If the Anthropic API call fails.
        """
        user_message = _build_user_message(finding)
        prompt_hash = _hash_prompt(self._system_prompt, user_message, _MODEL)

        t0 = time.monotonic()
        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            response = client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                temperature=0,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            raise RuntimeError(
                f"CommentDrafterAgent: Anthropic API call failed for "
                f"finding {finding.get('finding_id')}: {exc}"
            ) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)

        usage = response.usage
        tokens_in: int = usage.input_tokens
        tokens_out: int = usage.output_tokens
        cost_usd: float = (
            tokens_in * _COST_PER_INPUT_TOKEN + tokens_out * _COST_PER_OUTPUT_TOKEN
        )

        polished_text: str = (
            response.content[0].text.strip() if response.content else draft_fallback(finding)
        )

        logger.info(
            "CommentDrafterAgent: finding=%s model=%s prompt_hash=%s "
            "tokens_in=%d tokens_out=%d latency_ms=%d cost_usd=%.6f",
            finding.get("finding_id"),
            _MODEL,
            prompt_hash,
            tokens_in,
            tokens_out,
            latency_ms,
            cost_usd,
        )

        # Append the call log row so the caller can bulk-insert it.
        call_log_rows.append(
            {
                "call_id": str(uuid.uuid4()),
                "prompt_hash": prompt_hash,
                "model": _MODEL,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "cost_usd": round(cost_usd, 8),
                "caller_service": "drafter",
                "finding_id": str(finding.get("finding_id")) if finding.get("finding_id") else None,
            }
        )

        return DraftResult(
            polished_text=polished_text,
            prompt_hash=prompt_hash,
            model=_MODEL,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )
