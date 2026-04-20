// GET /api/admin/packs/[packId] → full pack detail with amendments + policies
import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

interface PackHeader {
  pack_id: string;
  jurisdiction: string;
  version: string;
  effective_date: string;
  superseded_by: string | null;
  created_at: string;
  manifest: Record<string, unknown> | null;
}

interface AmendmentRow {
  amendment_id: string;
  base_section_id: string;
  operation: string;
  amendment_text: string;
  effective_date: string;
  superseded_by_id: string | null;
}

interface PolicyRow {
  policy_id: string;
  title: string;
  body_text: string;
  source_url: string | null;
  applies_to_sections: string[];
  effective_date: string;
}

interface PackDetail {
  pack: PackHeader;
  amendments: AmendmentRow[];
  policies: PolicyRow[];
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ packId: string }> },
): Promise<NextResponse<PackDetail | { error: string }>> {
  const { packId } = await params;
  const decodedPackId = decodeURIComponent(packId);

  try {
    const packRes = await pool.query<PackHeader>(
      `SELECT pack_id, jurisdiction, version, effective_date,
              superseded_by, created_at, manifest
       FROM jurisdictional_packs WHERE pack_id = $1`,
      [decodedPackId],
    );

    if (packRes.rows.length === 0) {
      return NextResponse.json({ error: `Pack not found: ${decodedPackId}` }, { status: 404 });
    }

    const [amendmentsRes, policiesRes] = await Promise.all([
      pool
        .query<AmendmentRow>(
          `SELECT amendment_id, base_section_id, operation,
                  amendment_text, effective_date, superseded_by_id
           FROM amendments WHERE pack_id = $1 ORDER BY effective_date DESC`,
          [decodedPackId],
        )
        .catch(() => ({ rows: [] as AmendmentRow[] })),
      pool
        .query<PolicyRow>(
          `SELECT policy_id, title, body_text, source_url,
                  applies_to_sections, effective_date
           FROM agency_policies WHERE pack_id = $1 ORDER BY effective_date DESC`,
          [decodedPackId],
        )
        .catch(() => ({ rows: [] as PolicyRow[] })),
    ]);

    return NextResponse.json({
      pack: packRes.rows[0],
      amendments: amendmentsRes.rows,
      policies: policiesRes.rows,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
