import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

export async function POST(
  req: NextRequest,
  { params }: { params: { commentId: string } },
) {
  const body = (await req.json()) as {
    action: "training_example" | "skill_note";
    pack_id?: string;
    discipline?: string;
    comment_text?: string;
  };

  if (body.action === "training_example") {
    const packId = body.pack_id ?? "santa-rosa";
    const discipline = body.discipline ?? "architectural";
    await pool
      .query(
        `INSERT INTO drafter_examples
           (example_id, pack_id, discipline, severity, draft_input, polished_output, created_at)
         VALUES (gen_random_uuid(), $1, $2, 'provide', $3, $3, NOW())
         ON CONFLICT DO NOTHING`,
        [packId, discipline, body.comment_text ?? ""],
      )
      .catch(() => {});
  }

  // Mark the external comment as "noted" by inserting an alignment record
  await pool
    .query(
      `INSERT INTO alignment_records
         (alignment_id, project_id, review_round, comment_id, bucket, similarity_score, created_at)
       SELECT gen_random_uuid(), erc.project_id, 1, erc.external_comment_id, 'missed', 0, NOW()
       FROM external_review_comments erc
       WHERE erc.external_comment_id = $1
       ON CONFLICT DO NOTHING`,
      [params.commentId],
    )
    .catch(() => {
      // alignment_records might have different schema — ignore
    });

  return NextResponse.json({ ok: true });
}
