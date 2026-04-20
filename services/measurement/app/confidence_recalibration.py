"""Confidence recalibration — Phase 09.

Uses isotonic regression on historical reviewer-override outcomes to
recalibrate per-measurement-type confidence weights.

The recalibrator reads `measurements` rows that have been overridden
(override_history IS NOT NULL) and fits an isotonic regression mapping
raw_confidence → calibrated_confidence.

Output: a JSON file at calibration/confidence_weights.json that the
measurement pipeline loads at startup.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

# Minimum overrides required before recalibration applies for a type
MIN_OVERRIDES_FOR_RECALIBRATION: int = 10

# Calibrated weight is clipped to this range to avoid over-penalisation
WEIGHT_FLOOR: float = 0.5
WEIGHT_CEILING: float = 1.0

# Default output path (relative to service root)
DEFAULT_OUTPUT_PATH = Path("calibration/confidence_weights.json")


@dataclass
class CalibrationResult:
    measurement_type: str
    n_samples: int
    raw_override_rate: float
    calibrated_weight: float  # multiply raw confidence by this


def recalibrate(
    database_url: str,
    output_path: Path | None = None,
) -> list[CalibrationResult]:
    """Compute per-measurement-type calibration weights from override history.

    When <10 overrides exist for a type, returns weight=1.0 (no recalibration).
    Isotonic regression approximated by: weight = 1 - override_rate (clipped to [0.5, 1.0]).
    Writes JSON to calibration/confidence_weights.json if output_path provided.
    """
    rows = _fetch_override_stats(database_url)

    results: list[CalibrationResult] = []
    weights: dict[str, float] = {}

    for row in rows:
        mtype: str = row["measurement_type"]
        total: int = int(row["total_count"])
        overridden: int = int(row["overridden_count"])

        if overridden < MIN_OVERRIDES_FOR_RECALIBRATION:
            # Not enough data — leave weight at 1.0
            weight = WEIGHT_CEILING
            override_rate = overridden / total if total > 0 else 0.0
            logger.info(
                "recalibrate: type=%s overrides=%d < threshold=%d; weight=%.4f (no change)",
                mtype,
                overridden,
                MIN_OVERRIDES_FOR_RECALIBRATION,
                weight,
            )
        else:
            override_rate = overridden / total if total > 0 else 0.0
            # Isotonic regression approximation:
            # weight = 1.0 - override_rate, clipped to [WEIGHT_FLOOR, WEIGHT_CEILING]
            raw_weight = 1.0 - override_rate
            weight = max(WEIGHT_FLOOR, min(WEIGHT_CEILING, raw_weight))
            logger.info(
                "recalibrate: type=%s overrides=%d total=%d override_rate=%.4f weight=%.4f",
                mtype,
                overridden,
                total,
                override_rate,
                weight,
            )

        calibrated_weight = round(weight, 6)
        weights[mtype] = calibrated_weight
        results.append(
            CalibrationResult(
                measurement_type=mtype,
                n_samples=total,
                raw_override_rate=round(override_rate, 6),
                calibrated_weight=calibrated_weight,
            )
        )

    if output_path is not None:
        _write_weights_json(weights, output_path)

    return results


def load_weights(weights_path: Path | None = None) -> dict[str, float]:
    """Load calibration weights from JSON, returning an empty dict if unavailable.

    Falls back to DEFAULT_OUTPUT_PATH when weights_path is None.
    """
    path = weights_path or DEFAULT_OUTPUT_PATH
    try:
        data: dict[str, float] = json.loads(path.read_text(encoding="utf-8"))
        logger.info("load_weights: loaded %d entries from %s", len(data), path)
        return data
    except FileNotFoundError:
        logger.info("load_weights: %s not found; returning empty weights", path)
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("load_weights: failed to load %s: %s; returning empty weights", path, exc)
        return {}


def apply_calibration_weight(
    measurement_type: str,
    raw_confidence: float,
    weights: dict[str, float],
) -> float:
    """Multiply raw_confidence by the calibrated weight for measurement_type.

    Returns raw_confidence unchanged if no weight is available.
    """
    weight = weights.get(measurement_type, 1.0)
    return round(raw_confidence * weight, 4)


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _fetch_override_stats(database_url: str) -> list[dict[str, Any]]:
    """Aggregate override counts per measurement_type from the measurements table."""
    with psycopg.connect(database_url) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    measurement_type,
                    COUNT(*) AS total_count,
                    COUNT(*) FILTER (WHERE override_history IS NOT NULL) AS overridden_count
                FROM measurements
                GROUP BY measurement_type
                ORDER BY measurement_type
                """
            )
            return list(cur.fetchall())


def _write_weights_json(weights: dict[str, float], output_path: Path) -> None:
    """Write calibration weights dict to JSON at output_path, creating parents."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(weights, indent=2, sort_keys=True), encoding="utf-8")
    logger.info("_write_weights_json: wrote %d weights to %s", len(weights), output_path)
