"""EgressRouter — Phase 09.

Builds a graph of occupiable spaces and doorways from the entities DB,
then finds the shortest path from any point to the nearest exit using
Dijkstra's algorithm (via heapq — no external graph library).

Invariants:
  - All distances in INCHES (pre-converted from pixels using sheet scale).
  - Provenance: every result carries the full entity_id chain of the path.
  - No LLM calls. Read-only access to entities + sheets.
"""
from __future__ import annotations

import heapq
import logging
import math
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row

from pdf_quality import apply_quality_penalty

logger = logging.getLogger(__name__)

# Tolerance in pixels for considering two entity bboxes "adjacent"
ADJACENCY_TOLERANCE_PX: float = 24.0

# Fallback pixels-per-inch when sheet scale is unavailable
DEFAULT_PX_PER_INCH: float = 72.0

# Entity types considered traversable nodes in the egress graph
TRAVERSABLE_TYPES: frozenset[str] = frozenset({
    "room",
    "door",
    "window",
    "stair",
    "corridor",
})


@dataclass
class Node:
    entity_id: str
    node_type: str  # 'room' | 'door' | 'corridor' | 'exit'
    centroid_x: float  # inches from sheet origin
    centroid_y: float  # inches
    is_exit: bool


@dataclass
class EgressPath:
    start_entity_id: str
    end_entity_id: str  # the exit door/stair
    path_entity_ids: list[str]  # ordered chain
    distance_inches: float
    confidence: float
    pdf_quality_class: str
    trace: list[str]  # human-readable derivation steps


def _bboxes_adjacent(
    bbox_a: list[float],
    bbox_b: list[float],
    tolerance: float = ADJACENCY_TOLERANCE_PX,
) -> bool:
    """Return True if two bboxes overlap or are within `tolerance` pixels of each other.

    Each bbox is [x1, y1, x2, y2] in pixel coordinates.
    """
    ax1, ay1, ax2, ay2 = bbox_a[0], bbox_a[1], bbox_a[2], bbox_a[3]
    bx1, by1, bx2, by2 = bbox_b[0], bbox_b[1], bbox_b[2], bbox_b[3]

    # Expand each box by tolerance before testing overlap
    ax1 -= tolerance
    ay1 -= tolerance
    ax2 += tolerance
    ay2 += tolerance

    bx1 -= tolerance
    by1 -= tolerance
    bx2 += tolerance
    by2 += tolerance

    # Overlap test (AABB)
    return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)


def _euclidean_inches(
    node_a: Node,
    node_b: Node,
) -> float:
    """Euclidean distance between two node centroids in inches."""
    dx = node_a.centroid_x - node_b.centroid_x
    dy = node_a.centroid_y - node_b.centroid_y
    return math.sqrt(dx * dx + dy * dy)


class EgressRouter:
    """Graph-based egress path router (Layer 4 — Measurement, no LLM)."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        *,
        project_id: str,
        sheet_id: str,
        start_entity_id: str,
    ) -> EgressPath | None:
        """Route from start_entity to nearest exit.

        Queries entities table for all doors/rooms/exits on the sheet.
        Builds an adjacency graph: two nodes are adjacent if their bboxes
        share an edge (within a tolerance of 24 pixels).
        Runs Dijkstra to find the shortest path to any exit.
        Returns None if no exit found or if sheet is low_quality_scan.
        """
        pdf_quality_class = self._fetch_pdf_quality(sheet_id)

        # Skip routing on low_quality_scan — egress_distance is disabled
        _adj_conf, skip_reason = apply_quality_penalty(
            "egress_distance", 1.0, pdf_quality_class
        )
        if skip_reason is not None:
            logger.warning(
                "EgressRouter.route skipped for sheet_id=%s: %s", sheet_id, skip_reason
            )
            return None

        px_per_inch = self._fetch_sheet_scale(sheet_id)
        entities = self._fetch_entities(sheet_id)

        if not entities:
            logger.info("EgressRouter: no traversable entities on sheet_id=%s", sheet_id)
            return None

        # Build Node objects
        nodes: dict[str, Node] = {}
        raw_bboxes: dict[str, list[float]] = {}

        for row in entities:
            entity_id: str = row["entity_id"]
            etype: str = row["type"]
            payload: dict[str, Any] = row["payload"] or {}
            bbox: list[float] = row["bbox"] or [0.0, 0.0, 0.0, 0.0]

            cx_px = (bbox[0] + bbox[2]) / 2.0
            cy_px = (bbox[1] + bbox[3]) / 2.0
            cx_in = cx_px / px_per_inch
            cy_in = cy_px / px_per_inch

            is_exit = (
                etype == "stair"
                or (etype == "door" and str(payload.get("is_exit", "")).lower() == "true")
            )

            node_type = "exit" if is_exit else etype
            nodes[entity_id] = Node(
                entity_id=entity_id,
                node_type=node_type,
                centroid_x=cx_in,
                centroid_y=cy_in,
                is_exit=is_exit,
            )
            raw_bboxes[entity_id] = bbox

        if start_entity_id not in nodes:
            logger.warning(
                "EgressRouter: start_entity_id=%s not found in sheet entities",
                start_entity_id,
            )
            return None

        # Build adjacency list (O(n^2) — acceptable for sheet-scale entity counts)
        entity_ids = list(nodes.keys())
        adjacency: dict[str, list[str]] = {eid: [] for eid in entity_ids}

        for i in range(len(entity_ids)):
            for j in range(i + 1, len(entity_ids)):
                eid_a = entity_ids[i]
                eid_b = entity_ids[j]
                if _bboxes_adjacent(raw_bboxes[eid_a], raw_bboxes[eid_b]):
                    adjacency[eid_a].append(eid_b)
                    adjacency[eid_b].append(eid_a)

        # Dijkstra from start_entity_id to nearest exit
        result = self._dijkstra(
            nodes=nodes,
            adjacency=adjacency,
            start_id=start_entity_id,
        )

        if result is None:
            logger.info(
                "EgressRouter: no exit reachable from entity_id=%s on sheet_id=%s",
                start_entity_id,
                sheet_id,
            )
            return None

        path_ids, distance_inches = result

        # Apply PDF quality confidence penalty
        raw_confidence = 0.90
        adjusted_confidence, _ = apply_quality_penalty(
            "egress_distance", raw_confidence, pdf_quality_class
        )

        trace: list[str] = [
            f"sheet_id={sheet_id}",
            f"pdf_quality_class={pdf_quality_class}",
            f"px_per_inch={px_per_inch:.4f}",
            f"start={start_entity_id}",
            f"path={' -> '.join(path_ids)}",
            f"distance_inches={distance_inches:.4f}",
            f"raw_confidence={raw_confidence}",
            f"adjusted_confidence={adjusted_confidence}",
        ]

        return EgressPath(
            start_entity_id=start_entity_id,
            end_entity_id=path_ids[-1],
            path_entity_ids=path_ids,
            distance_inches=distance_inches,
            confidence=adjusted_confidence,
            pdf_quality_class=pdf_quality_class,
            trace=trace,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _dijkstra(
        self,
        nodes: dict[str, Node],
        adjacency: dict[str, list[str]],
        start_id: str,
    ) -> tuple[list[str], float] | None:
        """Run Dijkstra's algorithm and return (path, distance) to nearest exit.

        Returns None if no exit is reachable.
        Uses stdlib heapq — no external graph library.
        """
        INF = float("inf")
        dist: dict[str, float] = {eid: INF for eid in nodes}
        dist[start_id] = 0.0
        prev: dict[str, str | None] = {eid: None for eid in nodes}

        # heap entries: (distance, entity_id)
        heap: list[tuple[float, str]] = [(0.0, start_id)]

        while heap:
            current_dist, current_id = heapq.heappop(heap)

            if current_dist > dist[current_id]:
                continue  # stale entry

            if nodes[current_id].is_exit and current_id != start_id:
                # Reconstruct path
                path: list[str] = []
                cursor: str | None = current_id
                while cursor is not None:
                    path.append(cursor)
                    cursor = prev[cursor]
                path.reverse()
                return path, current_dist

            for neighbor_id in adjacency.get(current_id, []):
                edge_weight = _euclidean_inches(nodes[current_id], nodes[neighbor_id])
                candidate = current_dist + edge_weight
                if candidate < dist[neighbor_id]:
                    dist[neighbor_id] = candidate
                    prev[neighbor_id] = current_id
                    heapq.heappush(heap, (candidate, neighbor_id))

        # Check if start_id itself is an exit (degenerate case — return it as trivial path)
        if nodes[start_id].is_exit:
            return [start_id], 0.0

        return None

    def _fetch_pdf_quality(self, sheet_id: str) -> str:
        """Read pdf_quality_class from sheets table; default 'vector'."""
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT pdf_quality_class FROM sheets WHERE sheet_id = %s",
                    (sheet_id,),
                )
                row = cur.fetchone()
        if row and row.get("pdf_quality_class"):
            return str(row["pdf_quality_class"])
        return "vector"

    def _fetch_sheet_scale(self, sheet_id: str) -> float:
        """Return calibrated pixels-per-inch for the sheet; default 72.0."""
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT calibrated_px_per_inch
                        FROM sheet_scales
                        WHERE sheet_id = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (sheet_id,),
                    )
                    row = cur.fetchone()
            if row and row.get("calibrated_px_per_inch"):
                val = float(row["calibrated_px_per_inch"])
                if val > 0:
                    return val
        except Exception as exc:
            logger.warning("_fetch_sheet_scale failed for sheet_id=%s: %s", sheet_id, exc)
        return DEFAULT_PX_PER_INCH

    def _fetch_entities(self, sheet_id: str) -> list[dict[str, Any]]:
        """Fetch all traversable entities on the sheet."""
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT entity_id, type, payload, bbox
                    FROM entities
                    WHERE sheet_id = %s
                      AND type IN ('room', 'door', 'window', 'stair', 'corridor')
                    """,
                    (sheet_id,),
                )
                return list(cur.fetchall())
