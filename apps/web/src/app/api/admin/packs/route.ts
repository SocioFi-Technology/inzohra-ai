// GET  /api/admin/packs → list all packs with amendment count
// POST /api/admin/packs  body: {action: 'validate', manifest: string}
//                      → validate the manifest YAML structure (basic key checks)
//                      OR body: {action: 'list_diff', pack_id: string}
//                      → compare pack vs base state (list all amendments)
import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

interface PackSummary {
  pack_id: string;
  jurisdiction: string;
  version: string;
  effective_date: string;
  superseded_by: string | null;
  created_at: string;
  amendment_count: number;
}

interface ValidationResponse {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

interface AmendmentDiff {
  amendment_id: string;
  base_section_id: string;
  operation: string;
  amendment_text: string;
  effective_date: string;
}

type PostResponseBody = ValidationResponse | AmendmentDiff[];

const REQUIRED_KEYS = ["pack_id", "jurisdiction", "version", "effective_date"] as const;

function validateManifest(manifest: string): ValidationResponse {
  const errors: string[] = [];
  const warnings: string[] = [];

  for (const key of REQUIRED_KEYS) {
    // Accept YAML key pattern: "key:" or "key :" at start of a line
    const pattern = new RegExp(`^\\s*${key}\\s*:`, "m");
    if (!pattern.test(manifest)) {
      errors.push(`Missing required key: "${key}"`);
    }
  }

  // Warn if amendments or agency_policies keys are absent
  if (!/^\s*amendments\s*:/m.test(manifest)) {
    warnings.push('No "amendments" block found — pack will have zero amendments.');
  }
  if (!/^\s*agency_policies\s*:/m.test(manifest)) {
    warnings.push('No "agency_policies" block found.');
  }

  return { valid: errors.length === 0, errors, warnings };
}

export async function GET(): Promise<NextResponse<PackSummary[]>> {
  try {
    const res = await pool.query<PackSummary>(`
      SELECT
        p.pack_id,
        p.jurisdiction,
        p.version,
        p.effective_date,
        p.superseded_by,
        p.created_at,
        COUNT(a.amendment_id)::int AS amendment_count
      FROM jurisdictional_packs p
      LEFT JOIN amendments a ON a.pack_id = p.pack_id
      GROUP BY p.pack_id, p.jurisdiction, p.version, p.effective_date,
               p.superseded_by, p.created_at
      ORDER BY p.jurisdiction, p.effective_date DESC
    `);
    return NextResponse.json(res.rows);
  } catch {
    return NextResponse.json([]);
  }
}

export async function POST(
  req: NextRequest,
): Promise<NextResponse<PostResponseBody | { error: string }>> {
  let body: Record<string, string>;
  try {
    body = (await req.json()) as Record<string, string>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const { action } = body;

  if (action === "validate") {
    const { manifest } = body;
    if (typeof manifest !== "string" || manifest.trim() === "") {
      return NextResponse.json(
        { error: "manifest field is required and must be a non-empty string." },
        { status: 400 },
      );
    }
    const result = validateManifest(manifest);
    return NextResponse.json(result);
  }

  if (action === "list_diff") {
    const { pack_id } = body;
    if (typeof pack_id !== "string" || pack_id.trim() === "") {
      return NextResponse.json(
        { error: "pack_id field is required." },
        { status: 400 },
      );
    }
    try {
      const res = await pool.query<AmendmentDiff>(
        `SELECT amendment_id, base_section_id, operation, amendment_text, effective_date
         FROM amendments WHERE pack_id = $1 ORDER BY effective_date DESC`,
        [pack_id],
      );
      return NextResponse.json(res.rows);
    } catch {
      return NextResponse.json([]);
    }
  }

  if (action === "load") {
    // Actual loading is handled by the seed script server-side.
    // The UI calls this to signal intent; respond OK without writing.
    return NextResponse.json({
      valid: true,
      errors: [],
      warnings: [
        "Direct DB load via UI is not yet implemented. " +
          "Run `python scripts/seed_packs.py` to load packs.",
      ],
    });
  }

  return NextResponse.json({ error: `Unknown action: "${action}"` }, { status: 400 });
}
