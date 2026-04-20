import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export async function GET(
  _req: Request,
  { params }: { params: { id: string } }
) {
  const sheets = await query(
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
       d.filename
     FROM sheets s
     JOIN documents d ON d.document_id = s.document_id
     JOIN submittals sub ON sub.submittal_id = d.submittal_id
     WHERE sub.project_id = $1
     ORDER BY s.page`,
    [params.id]
  );

  // Enrich with title-block fields from entities
  const entityMap = new Map<string, Record<string, unknown>>();
  if (sheets.length > 0) {
    const sheetIds = sheets.map((s) => (s as Record<string, unknown>).sheet_id as string);
    const entities = await query(
      `SELECT sheet_id, payload, confidence, source_track
       FROM entities
       WHERE sheet_id = ANY($1) AND type = 'title_block'`,
      [sheetIds]
    );
    for (const ent of entities as Record<string, unknown>[]) {
      entityMap.set(ent.sheet_id as string, ent);
    }
  }

  const enriched = (sheets as Record<string, unknown>[]).map((s) => ({
    ...s,
    title_block: entityMap.get(s.sheet_id as string) ?? null,
  }));

  return NextResponse.json(enriched);
}
