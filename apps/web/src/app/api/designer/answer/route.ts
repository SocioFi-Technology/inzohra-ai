import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

interface AnswerRequestBody {
  projectId: string;
  confirmedQueryIds: string[];
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: AnswerRequestBody;
  try {
    body = (await req.json()) as AnswerRequestBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { projectId, confirmedQueryIds } = body;

  if (!projectId || !Array.isArray(confirmedQueryIds) || confirmedQueryIds.length === 0) {
    return NextResponse.json(
      { error: "projectId and a non-empty confirmedQueryIds array are required" },
      { status: 400 }
    );
  }

  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    // Create the designer_reports row with status='pending'
    const reportResult = await client.query(
      `INSERT INTO designer_reports
         (report_id, project_id, report_type, status,
          pdf_path, json_path, query_count,
          green_count, amber_count, red_count, created_at)
       VALUES (gen_random_uuid(), $1, 'checklist', 'pending',
               NULL, NULL, $2, 0, 0, 0, NOW())
       RETURNING report_id`,
      [projectId, confirmedQueryIds.length]
    );

    const reportId: string = reportResult.rows[0].report_id as string;

    // Mark confirmed queries
    // Use ANY($1::text[]) to match item_ids against confirmedQueryIds
    await client.query(
      `UPDATE checklist_queries
       SET confirmed_by_user = true
       WHERE project_id = $1
         AND item_id = ANY($2::text[])`,
      [projectId, confirmedQueryIds]
    );

    // Fetch the actual query_ids for the confirmed items
    const queryRows = await client.query(
      `SELECT query_id
       FROM checklist_queries
       WHERE project_id = $1
         AND item_id = ANY($2::text[])`,
      [projectId, confirmedQueryIds]
    );

    // Write stub checklist_answers — real pipeline would populate these
    for (const row of queryRows.rows as Array<{ query_id: string }>) {
      await client.query(
        `INSERT INTO checklist_answers
           (answer_id, query_id, project_id, status,
            measured_value, unit, required_value, code_citation,
            evidence_entity_ids, confidence, answer_text, created_at)
         VALUES (gen_random_uuid(), $1, $2, 'unknown',
                 NULL, NULL, NULL, '{}',
                 '{}', 0, 'Analysis queued — run answer pipeline', NOW())
         ON CONFLICT DO NOTHING`,
        [row.query_id, projectId]
      );
    }

    // Mark report complete (Phase 09 stub — real deployment would leave pending)
    await client.query(
      `UPDATE designer_reports
       SET status = 'complete',
           query_count = $2,
           green_count = 0,
           amber_count = 0,
           red_count = 0
       WHERE report_id = $1`,
      [reportId, confirmedQueryIds.length]
    );

    await client.query("COMMIT");

    return NextResponse.json({ reportId, status: "pending" });
  } catch (err) {
    await client.query("ROLLBACK");
    console.error("[api/designer/answer] DB error:", err);
    return NextResponse.json(
      { error: "Database error — tables may not exist yet" },
      { status: 503 }
    );
  } finally {
    client.release();
  }
}
