import { NextRequest, NextResponse } from "next/server";
import { pool, query } from "@/lib/db";

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

// ---------------------------------------------------------------------------
// POST /api/projects — create a new project + initial submittal
// ---------------------------------------------------------------------------

type CreateProjectBody = {
  address: string;
  permit_number: string;
  jurisdiction: string;
  occupancy_class?: string;
  construction_type?: string;
  effective_date?: string;
};

type ProjectIdRow = {
  project_id: string;
};

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: CreateProjectBody;
  try {
    body = (await req.json()) as CreateProjectBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { address, permit_number, jurisdiction, occupancy_class, construction_type, effective_date } = body;

  if (!address?.trim() || !permit_number?.trim() || !jurisdiction?.trim()) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const effectiveDateValue = effective_date ?? new Date().toISOString().slice(0, 10);

  try {
    // 1. Bootstrap default tenant (idempotent)
    await pool.query(
      `INSERT INTO tenants (tenant_id, name, kind)
       VALUES ('00000000-0000-0000-0000-000000000001', 'Inzohra-ai (default)', 'reviewer_firm')
       ON CONFLICT (tenant_id) DO NOTHING`,
    );

    // 2. Insert project
    const projectResult = await pool.query<ProjectIdRow>(
      `INSERT INTO projects
         (project_id, tenant_id, address, permit_number, jurisdiction,
          effective_date, occupancy_class, construction_type)
       VALUES
         (gen_random_uuid(),
          '00000000-0000-0000-0000-000000000001',
          $1, $2, $3, $4, $5, $6)
       RETURNING project_id`,
      [
        address.trim(),
        permit_number.trim(),
        jurisdiction.trim(),
        effectiveDateValue,
        occupancy_class ?? null,
        construction_type ?? null,
      ],
    );

    const row = projectResult.rows[0];

    // 3. Insert initial submittal
    await pool.query(
      `INSERT INTO submittals (submittal_id, project_id, round_number, kind, received_at)
       VALUES (gen_random_uuid(), $1, 1, 'initial', NOW())`,
      [row.project_id],
    );

    return NextResponse.json({ project_id: row.project_id }, { status: 201 });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Internal server error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
