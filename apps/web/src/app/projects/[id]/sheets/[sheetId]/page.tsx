/**
 * Sheet viewer — /projects/[id]/sheets/[sheetId]
 *
 * Server component: fetches sheet + entities from DB.
 * Renders client components for interactive parts.
 */
import { notFound } from "next/navigation";
import { query, queryOne } from "@/lib/db";
import { SheetViewerWrapper } from "./SheetViewerWrapper";

type Props = {
  params: { id: string; sheetId: string };
};

export async function generateMetadata({ params }: Props) {
  const sheet = await queryOne(
    `SELECT sheet_id, page, canonical_id FROM sheets WHERE sheet_id = $1`,
    [decodeURIComponent(params.sheetId)]
  ) as Record<string, unknown> | null;
  const label = (sheet?.canonical_id as string) ?? `Page ${sheet?.page ?? "?"}`;
  return { title: `${label} — Inzohra-ai` };
}

export default async function SheetPage({ params }: Props) {
  const sheetId = decodeURIComponent(params.sheetId);
  const projectId = params.id;

  // Load sheet
  const sheet = await queryOne(
    `SELECT
       s.sheet_id, s.page, s.discipline_letter, s.sheet_number,
       s.canonical_id, s.sheet_type, s.declared_scale,
       s.thumb_uri, s.extract_raster_uri,
       s.page_width_pts, s.page_height_pts,
       d.document_id, d.s3_uri AS document_s3_uri
     FROM sheets s
     JOIN documents d ON d.document_id = s.document_id
     JOIN submittals sub ON sub.submittal_id = d.submittal_id
     WHERE s.sheet_id = $1 AND sub.project_id = $2`,
    [sheetId, projectId]
  ) as Record<string, unknown> | null;

  if (!sheet) notFound();

  // Load all sheets for the rail
  const allSheets = await query(
    `SELECT
       s.sheet_id, s.page, s.discipline_letter, s.sheet_number,
       s.canonical_id, s.sheet_type,
       e.payload AS title_block_payload
     FROM sheets s
     JOIN documents d ON d.document_id = s.document_id
     JOIN submittals sub ON sub.submittal_id = d.submittal_id
     LEFT JOIN entities e ON e.sheet_id = s.sheet_id AND e.type = 'title_block'
     WHERE sub.project_id = $1
     ORDER BY s.page`,
    [projectId]
  ) as Record<string, unknown>[];

  // Load entities for this sheet
  const entities = await query(
    `SELECT entity_id, type, payload, bbox, confidence, source_track
     FROM entities WHERE sheet_id = $1 ORDER BY created_at`,
    [sheetId]
  ) as Record<string, unknown>[];

  return (
    <SheetViewerWrapper
      sheet={sheet}
      allSheets={allSheets}
      entities={entities}
      projectId={projectId}
    />
  );
}
