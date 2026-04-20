"""Thin LLM-call wrapper with prompt-hash logging.

Wraps anthropic.AsyncAnthropic. Enforces:
  - temperature = 0 everywhere.
  - Prompt hash logged on every call.
  - Model selection from MODEL_PRIMARY / MODEL_ESCALATION / MODEL_CLASSIFIER env.
  - Every call returns an LLMCallLog which callers persist to `llm_call_log`.
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID, uuid4


ModelRole = Literal["primary", "escalation", "classifier"]


def _model_for(role: ModelRole) -> str:
    env_key = {
        "primary": "MODEL_PRIMARY",
        "escalation": "MODEL_ESCALATION",
        "classifier": "MODEL_CLASSIFIER",
    }[role]
    default = {
        "primary": "claude-sonnet-4-5",
        "escalation": "claude-opus-4-5",
        "classifier": "claude-haiku-4-5-20251001",
    }[role]
    return os.getenv(env_key, default)


def _hash_prompt(system: str, messages: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    h.update(system.encode("utf-8"))
    for m in messages:
        h.update(str(m).encode("utf-8"))
    return h.hexdigest()[:16]


@dataclass
class LLMCallLog:
    call_id: UUID
    prompt_hash: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float
    caller_service: str
    finding_id: UUID | None = None
    retrieved_context_ids: list[UUID] = field(default_factory=list)


class LLMClient:
    """Provider-agnostic LLM client. Current impl: Anthropic."""

    def __init__(self, caller_service: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._caller = caller_service

    async def call(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        role: ModelRole = "primary",
        max_tokens: int = 4096,
        finding_id: UUID | None = None,
        retrieved_context_ids: list[UUID] | None = None,
    ) -> tuple[str, LLMCallLog]:
        model = _model_for(role)
        prompt_hash = _hash_prompt(system, messages)
        t0 = time.perf_counter()

        response = await self._client.messages.create(
            model=model,
            system=system,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=0,
        )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )

        log = LLMCallLog(
            call_id=uuid4(),
            prompt_hash=prompt_hash,
            model=model,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            latency_ms=latency_ms,
            cost_usd=0.0,  # filled by a pricing lookup in the persist step
            caller_service=self._caller,
            finding_id=finding_id,
            retrieved_context_ids=retrieved_context_ids or [],
        )
        return text, log
