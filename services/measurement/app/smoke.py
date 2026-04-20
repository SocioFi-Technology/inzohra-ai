"""Measurement service smoke test."""
from __future__ import annotations
import os
import sys


def main() -> None:
    required = ["DATABASE_URL", "REDIS_URL"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"MEASUREMENT SMOKE: FAIL — missing env: {missing}")
        sys.exit(1)

    import cv2  # noqa: F401
    import numpy as np  # noqa: F401
    import shapely  # noqa: F401
    import fitz  # noqa: F401

    print("MEASUREMENT SMOKE: OK")


if __name__ == "__main__":
    main()
