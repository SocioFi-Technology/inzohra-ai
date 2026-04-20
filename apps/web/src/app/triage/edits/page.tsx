import { Pool } from "pg";
import Link from "next/link";

const db = new Pool({ connectionString: process.env.DATABASE_URL! });

const EDIT_RATIO_THRESHOLD = 0.25; // 25% of text changed

interface EditRow {
  edit_id: string;
  finding_id: string;
  rule_id: string | null;
  draft_text: string;
  approved_text: string;
  edit_distance: number;
  edit_ratio: number;
  created_at: string;
}

async function fetchHighEditFindings(): Promise<EditRow[]> {
  try {
    const res = await db.query<EditRow>(`
      SELECT edit_id, finding_id, rule_id, draft_text, approved_text,
             edit_distance, edit_ratio, created_at
      FROM reviewer_edits
      WHERE edit_ratio >= ${EDIT_RATIO_THRESHOLD}
      ORDER BY edit_ratio DESC
      LIMIT 50
    `);
    return res.rows;
  } catch {
    return [];
  }
}

export default async function EditsPage() {
  const edits = await fetchHighEditFindings();

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <Link href="/metrics" className="text-sm text-blue-600 hover:underline">
          &larr; Metrics
        </Link>
        <h1 className="text-2xl font-bold">Triage: Reviewer Edits</h1>
        <span className="ml-auto bg-purple-100 text-purple-700 text-sm font-medium px-3 py-0.5 rounded-full">
          {edits.length} high-edit findings
        </span>
      </div>
      <p className="text-sm text-gray-500 mb-6">
        Findings where the reviewer changed &gt;
        {(EDIT_RATIO_THRESHOLD * 100).toFixed(0)}% of the drafter&rsquo;s text.
        These are strong candidates for few-shot drafter training examples.
      </p>

      {edits.length === 0 ? (
        <div className="text-sm text-gray-500 border border-dashed border-gray-300 rounded p-6 text-center">
          No high-edit findings yet. Reviewer edits are recorded when a reviewer
          saves a modified comment in the review UI.
        </div>
      ) : (
        <div className="space-y-4">
          {edits.map((e) => (
            <div
              key={e.edit_id}
              className="border border-purple-200 rounded-lg p-4 bg-white"
            >
              <div className="flex items-center gap-2 mb-3">
                {e.rule_id && (
                  <code className="text-xs bg-gray-100 border border-gray-200 px-1.5 py-0.5 rounded">
                    {e.rule_id}
                  </code>
                )}
                <span className="text-xs font-semibold text-purple-700 ml-auto">
                  edit ratio {(e.edit_ratio * 100).toFixed(0)}%
                </span>
                <span className="text-xs text-gray-400">
                  &Delta;{e.edit_distance} chars
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs font-medium text-gray-500 mb-1">
                    Draft
                  </div>
                  <div className="bg-red-50 border border-red-100 rounded p-2 text-xs text-gray-700 leading-relaxed">
                    {e.draft_text}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-500 mb-1">
                    Approved
                  </div>
                  <div className="bg-green-50 border border-green-100 rounded p-2 text-xs text-gray-700 leading-relaxed">
                    {e.approved_text}
                  </div>
                </div>
              </div>
              <div className="mt-2 flex justify-end">
                <span className="text-xs px-2 py-1 rounded border border-purple-200 text-purple-700 cursor-default">
                  Add as few-shot example
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
