import { NextResponse } from "next/server";
import { queryOne } from "@/lib/db";

export async function GET(
  _req: Request,
  { params }: { params: { id: string; sheetId: string } }
) {
  const sheet = await queryOne(
    `SELECT
       s.sheet_id,
       s.page,
       s.discipline_letter,
       s.sheet_number,
       s.canonical_id,
       s.sheet_type,
       s.declared_scale,
       s.thumb_uri,
       s.extract_raster_uri,
       s.page_width_pts,
       s.page_height_pts,
       d.document_id,
       d.s3_uri
     FROM sheets s
     JOIN documents d ON d.document_id = s.document_id
     JOIN submittals sub ON sub.submittal_id = d.submittal_id
     WHERE s.sheet_id = $1 AND sub.project_id = $2`,
    [params.sheetId, params.id]
  );

  if (!sheet) {
    return NextResponse.json({ error: "Sheet not found" }, { status: 404 });
  }

  return NextResponse.json(sheet);
}
