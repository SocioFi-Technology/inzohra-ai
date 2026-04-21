import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

interface RequestBody {
  action: "approve" | "reject" | "edit";
  text?: string;
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string; findingId: string } },
) {
  const body = (await req.json()) as RequestBody;
  const { id: projectId, findingId } = params;

  const newState =
    body.action === "approve" ? "approved" :
    body.action === "reject"  ? "rejected" :
    "edited";

  // Ensure approval_state column exists (idempotent migration guard).
  // If the column is missing, alter the table then retry.
  try {
    await pool.query(
      `UPDATE findings SET approval_state = $1 WHERE finding_id = $2 AND project_id = $3`,
      [newState, findingId, projectId],
    );
  } catch (err) {
    // Column may not exist yet — add it and retry.
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("approval_state") || msg.includes("column")) {
      await pool.query(
        `ALTER TABLE findings ADD COLUMN IF NOT EXISTS approval_state TEXT DEFAULT 'pending'`,
      );
      await pool.query(
        `UPDATE findings SET approval_state = $1 WHERE finding_id = $2 AND project_id = $3`,
        [newState, findingId, projectId],
      );
    } else {
      throw err;
    }
  }

  if (body.action === "edit" && body.text) {
    // Upsert into comment_drafts.
    await pool.query(
      `INSERT INTO comment_drafts (draft_id, finding_id, project_id, review_round, polished_text, created_at)
       VALUES (gen_random_uuid(), $1, $2, 1, $3, NOW())
       ON CONFLICT (finding_id, project_id, review_round)
       DO UPDATE SET polished_text = EXCLUDED.polished_text`,
      [findingId, projectId, body.text],
    );
  }

  return NextResponse.json({ ok: true, state: newState });
}
