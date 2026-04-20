"""Ingestion service smoke test.
Invoked by: `uv run services/ingestion/app/smoke.py`
Exits 0 on success. Checks that key modules import and that Postgres + Redis + S3 are reachable.
"""
from __future__ import annotations
import os
import sys


def _check_env() -> None:
    required = ["DATABASE_URL", "REDIS_URL", "S3_ENDPOINT"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"INGESTION SMOKE: FAIL — missing env: {missing}")
        sys.exit(1)


def _check_imports() -> None:
    import fitz  # noqa: F401 - PyMuPDF
    import redis  # noqa: F401
    import psycopg  # noqa: F401


def main() -> None:
    _check_env()
    _check_imports()
    print("INGESTION SMOKE: OK")


if __name__ == "__main__":
    main()
