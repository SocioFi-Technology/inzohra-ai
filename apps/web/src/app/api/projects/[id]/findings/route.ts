/**
 * GET /api/projects/[id]/findings
 *
 * Returns all findings for the project, optionally filtered by
 * ?discipline=plan_integrity&round=1&severity=revise
 *
 * Response shape:
 * {
 *   total: number,
 *   by_discipline: Record<string, Finding[]>,
 *   findings: Finding[]
 * }
 */
import { NextResponse } from "next/server";
import { query } from "@/lib/db";

interface Finding {
  finding_id: string;
  discipline: string;
  rule_id: string | null;
  rule_version: string | null;
  severity: "revise" | "provide" | "clarify" | "reference_only";
  requires_licensed_review: boolean;
  sheet_reference: Record<string, unknown>;
  evidence: unknown[];
  citations: CitationRecord[];
  draft_comment_text: string;
  confidence: number;
  approval_state: string;
  review_round: number;
  created_at: string;
}

interface CitationRecord {
  code: string;
  section: string;
  canonical_id: string;
  jurisdiction: string;
  effective_date: string;
  title: string | null;
  frozen_text: string;
  amendments: unknown[];
  agency_policies: unknown[];
  retrieval_chain: string[];
  confidence: number;
}

export async function GET(
  req: Request,
  { params }: { params: { id: string } }
) {
  const { searchParams } = new URL(req.url);
  const discipline = searchParams.get("discipline");
  const round = searchParams.get("round");
  const severity = searchParams.get("severity");

  // Build WHERE clauses
  const conditions: string[] = ["f.project_id = $1"];
  const values: unknown[] = [params.id];
  let idx = 2;

  if (discipline) {
    conditions.push(`f.discipline = $${idx++}`);
    values.push(discipline);
  }
  if (round) {
    conditions.push(`f.review_round = $${idx++}`);
    values.push(parseInt(round, 10));
  }
  if (severity) {
    conditions.push(`f.severity = $${idx++}`);
    values.push(severity);
  }

  const where = conditions.join(" AND ");

  const rows = await query<Finding>(
    `SELECT
       f.finding_id,
       f.discipline,
       f.rule_id,
       f.rule_version,
       f.severity,
       f.requires_licensed_review,
       f.sheet_reference,
       f.evidence,
       f.citations,
       f.draft_comment_text,
       f.confidence,
       f.approval_state,
       f.review_round,
       f.created_at
     FROM findings f
     WHERE ${where}
     ORDER BY f.discipline, f.severity, f.created_at`,
    values
  );

  // Group by discipline
  const byDiscipline: Record<string, Finding[]> = {};
  for (const row of rows) {
    const disc = row.discipline;
    if (!byDiscipline[disc]) byDiscipline[disc] = [];
    byDiscipline[disc].push(row);
  }

  return NextResponse.json({
    total: rows.length,
    by_discipline: byDiscipline,
    findings: rows,
  });
}
