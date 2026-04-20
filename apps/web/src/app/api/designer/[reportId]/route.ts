import { NextRequest, NextResponse } from "next/server";
import { queryOne, query } from "@/lib/db";

interface ReportRow {
  report_id: string;
  project_id: string;
  report_type: string;
  status: string;
  pdf_path: string | null;
  json_path: string | null;
  query_count: number;
  green_count: number;
  amber_count: number;
  red_count: number;
  created_at: string;
  address: string;
  permit_number: string;
}

interface AnswerRow {
  query_id: string;
  item_id: string;
  description: string;
  code_ref: string;
  threshold_value: number | null;
  threshold_unit: string | null;
  target_entity_class: string | null;
  answer_id: string | null;
  status: string | null;
  measured_value: number | null;
  unit: string | null;
  required_value: number | null;
  code_citation: Record<string, unknown> | null;
  evidence_entity_ids: string[] | null;
  confidence: number | null;
  answer_text: string | null;
  answer_created_at: string | null;
}

type RouteContext = { params: { reportId: string } };

export async function GET(
  _req: NextRequest,
  { params }: RouteContext
): Promise<NextResponse> {
  const { reportId } = params;

  let report: ReportRow | null = null;
  try {
    report = await queryOne<ReportRow>(
      `SELECT
         dr.report_id,
         dr.project_id,
         dr.report_type,
         dr.status,
         dr.pdf_path,
         dr.json_path,
         dr.query_count,
         dr.green_count,
         dr.amber_count,
         dr.red_count,
         dr.created_at,
         p.address,
         p.permit_number
       FROM designer_reports dr
       JOIN projects p ON p.project_id = dr.project_id
       WHERE dr.report_id = $1`,
      [reportId]
    );
  } catch {
    return NextResponse.json(
      { error: "Database not available" },
      { status: 503 }
    );
  }

  if (!report) {
    return NextResponse.json({ error: "Report not found" }, { status: 404 });
  }

  let answers: AnswerRow[] = [];
  try {
    answers = await query<AnswerRow>(
      `SELECT
         cq.query_id,
         cq.item_id,
         cq.description,
         cq.code_ref,
         cq.threshold_value,
         cq.threshold_unit,
         cq.target_entity_class,
         ca.answer_id,
         ca.status,
         ca.measured_value,
         ca.unit,
         ca.required_value,
         ca.code_citation,
         ca.evidence_entity_ids,
         ca.confidence,
         ca.answer_text,
         ca.created_at AS answer_created_at
       FROM checklist_queries cq
       LEFT JOIN checklist_answers ca ON ca.query_id = cq.query_id
       WHERE cq.project_id = $1
       ORDER BY cq.created_at, cq.item_id`,
      [report.project_id]
    );
  } catch {
    // answers table may not exist — return report without answers
  }

  return NextResponse.json({ report, answers });
}
