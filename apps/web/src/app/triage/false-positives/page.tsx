import { pool } from "@/lib/db";
import Link from "next/link";
import { FpTriageActions } from "@/components/FpTriageActions";

interface FalsePositiveFinding {
  finding_id: string;
  rule_id: string | null;
  discipline: string;
  severity: string;
  sheet_id: string | null;
  draft_comment_text: string;
  confidence: number;
}

async function fetchFalsePositives(): Promise<FalsePositiveFinding[]> {
  try {
    const res = await pool.query<FalsePositiveFinding>(`
      SELECT f.finding_id, f.rule_id, f.discipline, f.severity,
             f.sheet_reference->>'sheet_id' AS sheet_id,
             f.draft_comment_text,
             f.confidence
      FROM findings f
      JOIN alignment_records ar ON ar.finding_id = f.finding_id AND ar.bucket = 'false_positive'
      ORDER BY f.confidence DESC, f.discipline
      LIMIT 100
    `);
    return res.rows;
  } catch {
    // No alignment yet — show all findings sorted by low confidence
    try {
      const res = await pool.query<FalsePositiveFinding>(`
        SELECT finding_id, rule_id, discipline, severity,
               sheet_reference->>'sheet_id' AS sheet_id,
               draft_comment_text, confidence
        FROM findings
        WHERE rule_id IS NOT NULL
        ORDER BY confidence ASC
        LIMIT 100
      `);
      return res.rows;
    } catch {
      return [];
    }
  }
}

const ACCEPTED_GENERAL_RULES = new Set([
  "PI-DATE-001",
  "PI-TITLE-001",
  "PI-PERMIT-001",
  "PI-NORTH-001",
  "PI-SCALE-001",
  "STR-SHEAR-CALLOUT-001",
  "STR-HOLDOWN-001",
  "STR-FASTENER-001",
  "STR-LOAD-PATH-001",
  "PLMB-BACKFLOW-001",
  "PLMB-WH-ELEVATION-001",
  "MECH-DUCT-INSUL-001",
  "ELEC-GFCI-001",
  "ELEC-AFCI-001",
  "ELEC-ACCESSIBLE-CTRL-001",
  "CALG-WATER-FIXTURES-001",
  "CALG-RECYCLE-001",
  "CALG-EV-READY-001",
  "CALG-INDOOR-AIR-001",
  "CALG-MANDATORY-NOTE-001",
  "EN-CLIMATE-ZONE-001",
  "EN-HERS-DECL-001",
  "EN-PRESCRIPTIVE-001",
  "FIRE-CO-ALARM-001",
]);

export default async function FalsePositivesPage() {
  const fps = await fetchFalsePositives();
  const trueFPs = fps.filter((f) => !ACCEPTED_GENERAL_RULES.has(f.rule_id ?? ""));
  const accepted = fps.filter((f) => ACCEPTED_GENERAL_RULES.has(f.rule_id ?? ""));

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <Link href="/metrics" className="text-sm text-blue-600 hover:underline">
          &larr; Metrics
        </Link>
        <h1 className="text-2xl font-bold">Triage: False Positives</h1>
        <span className="ml-auto bg-orange-100 text-orange-700 text-sm font-medium px-3 py-0.5 rounded-full">
          {trueFPs.length} to review
        </span>
      </div>
      <p className="text-sm text-gray-500 mb-6">
        AI findings the authority didn&apos;t raise. True FPs need threshold tuning or
        rule deprecation. Accepted-practice findings (general-code reminders) are
        expected and shown separately.
      </p>

      {trueFPs.length === 0 && (
        <div className="text-sm text-gray-500 border border-dashed border-gray-300 rounded p-6 text-center mb-6">
          No false positives detected. Run{" "}
          <code className="bg-gray-100 px-1 rounded">
            uv run scripts/run_comparison.py
          </code>{" "}
          to populate.
        </div>
      )}

      {trueFPs.length > 0 && (
        <div className="space-y-2 mb-8">
          {trueFPs.map((f) => (
            <div
              key={f.finding_id}
              className="border border-orange-200 rounded-lg p-4 bg-orange-50"
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {f.rule_id && (
                      <code className="text-xs bg-white border border-gray-200 px-1.5 py-0.5 rounded">
                        {f.rule_id}
                      </code>
                    )}
                    <span className="text-xs text-gray-500">{f.discipline}</span>
                    <span className="text-xs text-gray-400 ml-auto">
                      confidence {(f.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-sm text-gray-800 leading-relaxed line-clamp-3">
                    {f.draft_comment_text}
                  </p>
                </div>
                <FpTriageActions findingId={f.finding_id} />
              </div>
            </div>
          ))}
        </div>
      )}

      {accepted.length > 0 && (
        <details className="border border-gray-200 rounded-lg p-3">
          <summary className="text-sm font-medium cursor-pointer text-gray-600">
            {accepted.length} accepted-practice findings (general-code reminders
            &mdash; not true FPs)
          </summary>
          <div className="mt-3 space-y-1">
            {accepted.map((f) => (
              <div
                key={f.finding_id}
                className="flex items-center gap-2 text-xs text-gray-500 py-1"
              >
                <code className="bg-gray-100 px-1 rounded">{f.rule_id}</code>
                <span className="text-gray-400">{f.discipline}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </main>
  );
}
