import { Pool } from "pg";
import Link from "next/link";

const db = new Pool({ connectionString: process.env.DATABASE_URL! });

interface MissedComment {
  comment_id: string;
  comment_number: number;
  sheet_ref: string | null;
  comment_text: string;
  discipline: string | null;
  suggested_rule: string | null;
}

// Very simple keyword → discipline + rule prefix mapping.
// A proper version would use embedding similarity to existing rules.
function suggestRule(text: string): string {
  const t = text.toLowerCase();
  if (t.includes("door") && (t.includes("fire") || t.includes("rated"))) return "FIRE-FIRE-DOOR-002";
  if (t.includes("window") && t.includes("egress")) return "AR-EGRESS-WIN-002";
  if (t.includes("accessible") || t.includes("11b")) return "AC-NEW-001";
  if (t.includes("sprinkler") || t.includes("nfpa")) return "FIRE-SPRINKLER-002";
  if (t.includes("smoke") || t.includes("alarm")) return "FIRE-CO-ALARM-002";
  if (t.includes("energy") || t.includes("title 24")) return "EN-NEW-001";
  if (t.includes("electrical") || t.includes("panel")) return "ELEC-NEW-001";
  if (t.includes("plumb") || t.includes("water heater")) return "PLMB-NEW-001";
  if (t.includes("structural") || t.includes("shear")) return "STR-NEW-001";
  if (t.includes("mechanical") || t.includes("hvac")) return "MECH-NEW-001";
  return "AR-NEW-001";
}

async function fetchMissed(): Promise<MissedComment[]> {
  // Try to use alignment_records if available
  try {
    const res = await db.query<{
      comment_id: string;
      comment_number: number;
      sheet_ref: string | null;
      comment_text: string;
      discipline: string | null;
    }>(`
      SELECT erc.comment_id, erc.comment_number, erc.sheet_ref,
             erc.comment_text, erc.discipline
      FROM external_review_comments erc
      WHERE NOT EXISTS (
        SELECT 1 FROM alignment_records ar
        WHERE ar.comment_id = erc.comment_id AND ar.bucket IN ('matched','partial')
      )
      ORDER BY erc.comment_number
    `);
    return res.rows.map((r) => ({
      ...r,
      suggested_rule: suggestRule(r.comment_text),
    }));
  } catch {
    // alignment_records table doesn't exist yet — show all external comments
    try {
      const res = await db.query<{
        comment_id: string;
        comment_number: number;
        sheet_ref: string | null;
        comment_text: string;
        discipline: string | null;
      }>(`
        SELECT comment_id, comment_number, sheet_ref, comment_text, discipline
        FROM external_review_comments
        ORDER BY comment_number
      `);
      return res.rows.map((r) => ({
        ...r,
        suggested_rule: suggestRule(r.comment_text),
      }));
    } catch {
      return [];
    }
  }
}

export default async function MissesPage() {
  const missed = await fetchMissed();

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <Link href="/metrics" className="text-sm text-blue-600 hover:underline">
          &larr; Metrics
        </Link>
        <h1 className="text-2xl font-bold">Triage: Misses</h1>
        <span className="ml-auto bg-red-100 text-red-700 text-sm font-medium px-3 py-0.5 rounded-full">
          {missed.length} missed
        </span>
      </div>
      <p className="text-sm text-gray-500 mb-6">
        Authority BV comments the AI did not raise. For each: add a rule, or
        promote the pattern as a skill gotcha for the discipline reviewer.
      </p>

      {missed.length === 0 ? (
        <div className="text-sm text-gray-500 border border-dashed border-gray-300 rounded p-6 text-center">
          No missed comments! Run{" "}
          <code className="bg-gray-100 px-1 rounded">
            uv run scripts/run_comparison.py
          </code>{" "}
          to populate.
        </div>
      ) : (
        <div className="space-y-3">
          {missed.map((c) => (
            <div
              key={c.comment_id}
              className="border border-gray-200 rounded-lg p-4 bg-white hover:border-gray-300"
            >
              <div className="flex items-start gap-3">
                <span className="flex-shrink-0 w-7 h-7 bg-red-100 text-red-700 rounded-full flex items-center justify-center text-xs font-bold">
                  {c.comment_number}
                </span>
                <div className="flex-1 min-w-0">
                  {c.sheet_ref && (
                    <span className="inline-block text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded mb-1">
                      {c.sheet_ref}
                    </span>
                  )}
                  <p className="text-sm text-gray-800 leading-relaxed">
                    {c.comment_text}
                  </p>
                  {c.suggested_rule && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
                      <span>Suggested rule:</span>
                      <code className="bg-yellow-50 text-yellow-800 px-2 py-0.5 rounded border border-yellow-200">
                        {c.suggested_rule}
                      </code>
                    </div>
                  )}
                </div>
                <div className="flex flex-col gap-1.5 flex-shrink-0">
                  <span className="px-2 py-1 text-xs rounded border border-gray-200 text-gray-600 cursor-default text-center">
                    Add rule
                  </span>
                  <span className="px-2 py-1 text-xs rounded border border-gray-200 text-gray-600 cursor-default text-center">
                    Skill gotcha
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
