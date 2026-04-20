import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export async function GET() {
  const projects = await query(`
    SELECT
      p.project_id,
      p.address,
      p.permit_number,
      p.jurisdiction,
      p.effective_date,
      p.occupancy_class,
      p.construction_type,
      p.created_at,
      COUNT(DISTINCT s.sheet_id) AS sheet_count
    FROM projects p
    LEFT JOIN documents d ON d.submittal_id IN (
      SELECT submittal_id FROM submittals WHERE project_id = p.project_id
    )
    LEFT JOIN sheets s ON s.document_id = d.document_id
    GROUP BY p.project_id
    ORDER BY p.created_at DESC
  `);
  return NextResponse.json(projects);
}
