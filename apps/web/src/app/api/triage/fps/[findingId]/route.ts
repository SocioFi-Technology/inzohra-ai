import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

export async function POST(
  req: NextRequest,
  { params }: { params: { findingId: string } },
) {
  const body = (await req.json()) as {
    action: "confirm_fp" | "accept" | "deprecate";
  };

  if (body.action === "confirm_fp") {
    await pool
      .query(
        `UPDATE findings SET approval_state = 'rejected' WHERE finding_id = $1`,
        [params.findingId],
      )
      .catch(() => {});
  } else if (body.action === "accept") {
    await pool
      .query(
        `UPDATE findings SET approval_state = 'approved' WHERE finding_id = $1`,
        [params.findingId],
      )
      .catch(() => {});
  }

  return NextResponse.json({ ok: true });
}
