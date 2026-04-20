"""
Shadow-deploy infrastructure — Phase 07.

When a prompt_version has shadow=True, both the control (default) and shadow
versions run on the same input.  Outputs are stored in shadow_runs for later
comparison and promotion.

Usage:
    shadow = ShadowRunner(api_key=os.environ["ANTHROPIC_API_KEY"], conn=conn)
    result = shadow.run(
        prompt_key="drafter_system",
        user_message=user_msg,
        finding_id=str(finding_id),
        project_id=str(project_id),
    )
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-5"
_MAX_TOKENS = 512


@dataclass
class ShadowRunResult:
    run_id: str
    control_version: str
    shadow_version: str
    control_output: str
    shadow_output: str
    winner: str | None     # 'control' | 'shadow' | 'tie' | None (not yet judged)


class ShadowRunner:
    """Runs both control and shadow prompt versions and stores the comparison."""

    def __init__(self, api_key: str, conn: Any) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._conn = conn

    def _fetch_versions(self, prompt_key: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Return (control_row, shadow_row | None)."""
        rows = self._conn.execute(
            """
            SELECT version_id, version_tag, prompt_text, is_default, shadow
            FROM prompt_versions
            WHERE prompt_key = %s
            ORDER BY created_at DESC
            """,
            (prompt_key,),
        ).fetchall()

        control = next((r for r in rows if r["is_default"]), None)
        shadow = next((r for r in rows if r["shadow"] and not r["is_default"]), None)
        if control is None and rows:
            control = rows[0]
        return control, shadow

    def _call(self, system_prompt: str, user_message: str) -> str:
        resp = self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text.strip() if resp.content else ""

    def run(
        self,
        prompt_key: str,
        user_message: str,
        finding_id: str | None = None,
        project_id: str | None = None,
    ) -> ShadowRunResult:
        control, shadow = self._fetch_versions(prompt_key)
        if control is None:
            raise RuntimeError(f"No prompt version found for key {prompt_key!r}")

        control_output = self._call(control["prompt_text"], user_message)

        shadow_output = ""
        shadow_version = ""
        if shadow is not None:
            shadow_output = self._call(shadow["prompt_text"], user_message)
            shadow_version = shadow["version_tag"]
        else:
            shadow_version = control["version_tag"]

        run_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT INTO shadow_runs
                (run_id, project_id, finding_id, prompt_key,
                 control_version, shadow_version, control_output, shadow_output)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                project_id,
                finding_id,
                prompt_key,
                control["version_tag"],
                shadow_version,
                control_output,
                shadow_output,
            ),
        )

        return ShadowRunResult(
            run_id=run_id,
            control_version=control["version_tag"],
            shadow_version=shadow_version,
            control_output=control_output,
            shadow_output=shadow_output,
            winner=None,
        )

    def promote(self, prompt_key: str, version_tag: str) -> None:
        """Mark version_tag as the new default; clear shadow flag."""
        self._conn.execute(
            "UPDATE prompt_versions SET is_default = false WHERE prompt_key = %s",
            (prompt_key,),
        )
        self._conn.execute(
            "UPDATE prompt_versions SET is_default = true, shadow = false "
            "WHERE prompt_key = %s AND version_tag = %s",
            (prompt_key, version_tag),
        )
        logger.info("Promoted %s → %s as default", prompt_key, version_tag)
