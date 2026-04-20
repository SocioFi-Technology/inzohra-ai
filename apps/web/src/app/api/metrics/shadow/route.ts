// GET /api/metrics/shadow — recent shadow runs for comparison UI
// POST /api/metrics/shadow — promote a shadow version to default
import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export interface ShadowRunRow {
  run_id: string;
  prompt_key: string;
  control_version: string;
  shadow_version: string;
  control_preview: string;
  shadow_preview: string;
  winner: string | null;
  created_at: string;
}

export async function GET(): Promise<NextResponse<ShadowRunRow[]>> {
  try {
    const res = await pool.query<ShadowRunRow>(`
      SELECT run_id, prompt_key, control_version, shadow_version,
             LEFT(control_output, 200) AS control_preview,
             LEFT(shadow_output, 200)  AS shadow_preview,
             winner, created_at
      FROM shadow_runs
      ORDER BY created_at DESC
      LIMIT 50
    `);
    return NextResponse.json(res.rows);
  } catch {
    // shadow_runs table not yet created — return empty list gracefully
    return NextResponse.json([]);
  }
}

interface PromoteBody {
  prompt_key: string;
  version_tag: string;
}

export async function POST(
  req: Request,
): Promise<NextResponse<{ ok: true } | { error: string }>> {
  const body = (await req.json()) as PromoteBody;
  const { prompt_key, version_tag } = body;

  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(
      "UPDATE prompt_versions SET is_default = false WHERE prompt_key = $1",
      [prompt_key],
    );
    await client.query(
      "UPDATE prompt_versions SET is_default = true, shadow = false WHERE prompt_key = $1 AND version_tag = $2",
      [prompt_key, version_tag],
    );
    await client.query("COMMIT");
    return NextResponse.json({ ok: true });
  } catch (e) {
    await client.query("ROLLBACK");
    return NextResponse.json({ error: String(e) }, { status: 500 });
  } finally {
    client.release();
  }
}
