// GET /api/metrics/disciplines
// Returns per-discipline rollup: total rules, avg precision, avg confidence.
import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export interface DisciplineMetricRow {
  discipline: string;
  rule_count: number;
  finding_count: number;
  avg_confidence: number | null;
  last_activity: string | null;
}

export async function GET(): Promise<NextResponse<DisciplineMetricRow[]>> {
  const res = await pool.query<DisciplineMetricRow>(`
    SELECT
      discipline,
      COUNT(DISTINCT rule_id)::int                           AS rule_count,
      COUNT(DISTINCT finding_id)::int                        AS finding_count,
      ROUND(AVG(confidence)::numeric, 3)                     AS avg_confidence,
      MAX(created_at)                                        AS last_activity
    FROM findings
    WHERE discipline IS NOT NULL
    GROUP BY discipline
    ORDER BY discipline
  `);
  return NextResponse.json(res.rows);
}
