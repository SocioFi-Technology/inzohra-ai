// GET /api/metrics/rules?jurisdiction=<value>
// Returns per-rule metrics from rule_metrics_live view, with graceful fallback
// when alignment data doesn't exist yet (returns findings-only stats).
// Optional ?jurisdiction= filters to a specific jurisdiction.
import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

export interface RuleMetricRow {
  rule_id: string;
  discipline: string;
  total_findings: number;
  matched: number;
  false_positives: number;
  missed: number;
  precision: number | null;
  avg_confidence: number | null;
  last_evaluated_at: string | null;
}

export async function GET(req: NextRequest): Promise<NextResponse<RuleMetricRow[]>> {
  const { searchParams } = new URL(req.url);
  const jurisdiction = searchParams.get("jurisdiction") ?? "";

  try {
    // Try rule_metrics_live first (post migration 0013 includes jurisdiction in GROUP BY)
    if (jurisdiction) {
      const res = await pool.query<RuleMetricRow>(
        `SELECT
          rule_id,
          discipline,
          COALESCE(total_findings, 0)::int  AS total_findings,
          COALESCE(matched, 0)::int          AS matched,
          COALESCE(false_positives, 0)::int  AS false_positives,
          COALESCE(missed, 0)::int           AS missed,
          precision,
          avg_confidence,
          last_evaluated_at
        FROM rule_metrics_live
        WHERE jurisdiction = $1
        ORDER BY discipline, rule_id`,
        [jurisdiction],
      );
      return NextResponse.json(res.rows);
    }

    const res = await pool.query<RuleMetricRow>(`
      SELECT
        rule_id,
        discipline,
        COALESCE(total_findings, 0)::int  AS total_findings,
        COALESCE(matched, 0)::int          AS matched,
        COALESCE(false_positives, 0)::int  AS false_positives,
        COALESCE(missed, 0)::int           AS missed,
        precision,
        avg_confidence,
        last_evaluated_at
      FROM rule_metrics_live
      ORDER BY discipline, rule_id
    `);
    return NextResponse.json(res.rows);
  } catch {
    // Fallback: rule_metrics_live view doesn't exist yet — query findings directly
    if (jurisdiction) {
      const res = await pool.query<RuleMetricRow>(
        `SELECT
          f.rule_id,
          f.discipline,
          COUNT(*)::int          AS total_findings,
          0                      AS matched,
          0                      AS false_positives,
          0                      AS missed,
          NULL::numeric          AS precision,
          AVG(f.confidence)      AS avg_confidence,
          MAX(f.created_at)      AS last_evaluated_at
        FROM findings f
        JOIN projects p ON p.project_id = f.project_id
        WHERE f.rule_id IS NOT NULL AND p.jurisdiction = $1
        GROUP BY f.rule_id, f.discipline
        ORDER BY f.discipline, f.rule_id`,
        [jurisdiction],
      );
      return NextResponse.json(res.rows as RuleMetricRow[]);
    }

    const res = await pool.query<RuleMetricRow>(`
      SELECT
        rule_id,
        discipline,
        COUNT(*)::int          AS total_findings,
        0                      AS matched,
        0                      AS false_positives,
        0                      AS missed,
        NULL::numeric          AS precision,
        AVG(confidence)        AS avg_confidence,
        MAX(created_at)        AS last_evaluated_at
      FROM findings
      WHERE rule_id IS NOT NULL
      GROUP BY rule_id, discipline
      ORDER BY discipline, rule_id
    `);
    return NextResponse.json(res.rows as RuleMetricRow[]);
  }
}
