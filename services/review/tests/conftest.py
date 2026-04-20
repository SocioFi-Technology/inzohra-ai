"""Pytest conftest for the review service.

Adds ``services/review`` to ``sys.path`` so tests can import ``app.*``
without the package being installed editably.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The review service root is two levels up from this file.
_SVC_ROOT = Path(__file__).resolve().parent.parent
if str(_SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SVC_ROOT))

# Also ensure inzohra_shared (packages/shared-py) is importable.
_SHARED_ROOT = _SVC_ROOT.parent.parent / "packages" / "shared-py"
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))
