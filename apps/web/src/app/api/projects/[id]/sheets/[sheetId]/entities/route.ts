import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export async function GET(
  _req: Request,
  { params }: { params: { id: string; sheetId: string } }
) {
  const entities = await query(
    `SELECT
       entity_id,
       type,
       payload,
       bbox,
       page,
       extractor_version,
       confidence,
       source_track,
       created_at
     FROM entities
     WHERE sheet_id = $1
     ORDER BY created_at`,
    [params.sheetId]
  );
  return NextResponse.json(entities);
}
