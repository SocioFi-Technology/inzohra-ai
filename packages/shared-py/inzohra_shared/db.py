"""Async psycopg connection helpers.

Usage::

    async with get_conn(database_url) as conn:
        row = await conn.fetchrow("SELECT ...")
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import psycopg
from psycopg.rows import dict_row


@asynccontextmanager
async def get_conn(database_url: str) -> AsyncGenerator[psycopg.AsyncConnection, None]:  # type: ignore[type-arg]
    """Yield an async psycopg connection with dict_row factory."""
    async with await psycopg.AsyncConnection.connect(
        database_url,
        row_factory=dict_row,
        autocommit=False,
    ) as conn:
        yield conn


@asynccontextmanager
async def get_autocommit_conn(database_url: str) -> AsyncGenerator[psycopg.AsyncConnection, None]:  # type: ignore[type-arg]
    """Yield an autocommit connection (for DDL or fire-and-forget inserts)."""
    async with await psycopg.AsyncConnection.connect(
        database_url,
        row_factory=dict_row,
        autocommit=True,
    ) as conn:
        yield conn
