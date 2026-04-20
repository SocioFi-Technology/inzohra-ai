"""Review service smoke test."""
from __future__ import annotations
import os
import sys


def main() -> None:
    required = ["DATABASE_URL", "REDIS_URL", "ANTHROPIC_API_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"REVIEW SMOKE: FAIL — missing env: {missing}")
        sys.exit(1)

    import anthropic  # noqa: F401
    import psycopg  # noqa: F401
    import redis  # noqa: F401

    print("REVIEW SMOKE: OK")


if __name__ == "__main__":
    main()
