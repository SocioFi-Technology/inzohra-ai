"""Provider-agnostic embedder.

Two backends, selected per request:

- ``openai`` — ``text-embedding-3-large`` (1536 dims via ``dimensions`` arg).
- ``hash``  — deterministic hash-bag fallback (NEVER use in prod). Its output
  is a length-1536 bag-of-hashed-tokens vector. Only exists so that
  ``kb:seed`` runs in local dev when no OpenAI key is configured — the
  embeddings are then re-generated once a real key is provided.

Every section's embedding is stored in the ``code_sections.embedding``
``vector(1536)`` column. The dimensionality is fixed; choosing a different
embedding model requires a migration.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Protocol

EMBED_DIM = 1536


class Embedder(Protocol):
    model_id: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class HashEmbedder:
    """Deterministic bag-of-tokens hash embedder for local dev only.

    Not semantic. Good enough to exercise the vector pipeline end-to-end when
    no OpenAI key is available. All rules that depend on retrieval *recall*
    should be tested against the OpenAI backend at least once.
    """

    dim: int = EMBED_DIM
    model_id: str = "hash-bag:1536"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"[A-Za-z0-9]+", text.lower()):
            if len(tok) < 3:
                continue
            h = hashlib.sha256(tok.encode()).digest()
            # Multiple hash buckets for a single token to reduce collisions.
            for off in (0, 8, 16, 24):
                idx = int.from_bytes(h[off:off + 4], "big") % self.dim
                # Sign from a separate byte → symmetric positive/negative updates
                sign = 1.0 if h[off + 4] & 1 else -1.0
                v[idx] += sign
        # L2 normalise
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


@dataclass
class OpenAIEmbedder:
    """OpenAI ``text-embedding-3-large`` at 1536 dims."""

    api_key: str
    dim: int = EMBED_DIM
    model_id: str = "openai:text-embedding-3-large:1536"

    def embed(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI  # deferred import

        client = OpenAI(api_key=self.api_key)
        resp = client.embeddings.create(
            model="text-embedding-3-large",
            input=texts,
            dimensions=self.dim,
        )
        return [d.embedding for d in resp.data]


def get_embedder() -> Embedder:
    """Pick the best embedder given the current environment.

    Priority: OpenAI (if ``OPENAI_API_KEY`` looks real) → HashEmbedder.
    """
    key = os.environ.get("OPENAI_API_KEY", "")
    if key and not key.startswith("sk-xxx") and len(key) > 20:
        return OpenAIEmbedder(api_key=key)
    return HashEmbedder()
