import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export async function GET(
  _req: Request,
  { params }: { params: { id: string; sheetId: string } }
) {
  const measurements = await query(
    `SELECT
       m.measurement_id,
       m.type,
       m.value,
       m.unit,
       m.confidence,
       m.trace,
       m.override_history,
       m.bbox,
       m.entity_id,
       m.tag,
       m.extractor_version,
       m.created_at
     FROM measurements m
     WHERE m.sheet_id = $1
       AND m.project_id = $2
     ORDER BY m.type, m.created_at`,
    [params.sheetId, params.id]
  );
  return NextResponse.json(measurements);
}
