"""Code-RAG: retrieval layer for the 2022 California code cycle."""
from .citations import format_section_number, resolve_citation
from .embedder import EMBED_DIM, Embedder, HashEmbedder, OpenAIEmbedder, get_embedder
from .tools import (
    Citation,
    SearchHit,
    check_effective_date,
    lookup_canonical,
    lookup_section,
    search_code,
)

__all__ = [
    "EMBED_DIM",
    "Embedder",
    "HashEmbedder",
    "OpenAIEmbedder",
    "get_embedder",
    "Citation",
    "SearchHit",
    "check_effective_date",
    "lookup_canonical",
    "lookup_section",
    "search_code",
    "resolve_citation",
    "format_section_number",
]
