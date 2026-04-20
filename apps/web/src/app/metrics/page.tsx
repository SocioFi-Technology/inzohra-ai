import Link from "next/link";
import { pool } from "@/lib/db";

// ---- Colour scale: precision 0→1 mapped to red→yellow→green ----
function precisionColor(p: number | null): string {
  if (p === null) return "#e5e7eb"; // gray-200 = no data
  if (p >= 0.8) return "#86efac"; // green-300
  if (p >= 0.6) return "#fde68a"; // yellow-200
  if (p >= 0.4) return "#fca5a5"; // red-300
  return "#f87171"; // red-400
}

interface RuleRow {
  rule_id: string;
  discipline: string;
  total_findings: number;
  matched: number;
  false_positives: number;
  missed: number;
  precision: number | null;
  avg_confidence: number | null;
}

interface DisciplineRow {
  discipline: string;
  rule_count: number;
  finding_count: number;
  avg_confidence: number | null;
}

interface ShadowRow {
  run_id: string;
  prompt_key: string;
  control_version: string;
  shadow_version: string;
  control_preview: string;
  shadow_preview: string;
  winner: string | null;
  created_at: string;
}

const JURISDICTIONS = [
  { value: "", label: "All" },
  { value: "santa_rosa", label: "Santa Rosa" },
  { value: "oakland", label: "Oakland" },
] as const;

async function fetchRules(jurisdiction: string): Promise<RuleRow[]> {
  try {
    if (jurisdiction) {
      const res = await pool.query<RuleRow>(
        `SELECT rml.rule_id, rml.discipline,
                COALESCE(rml.total_findings, 0)::int  AS total_findings,
                COALESCE(rml.matched, 0)::int          AS matched,
                COALESCE(rml.false_positives, 0)::int  AS false_positives,
                COALESCE(rml.missed, 0)::int           AS missed,
                rml.precision, rml.avg_confidence
         FROM rule_metrics_live rml
         WHERE rml.jurisdiction = $1
         ORDER BY rml.discipline, rml.rule_id`,
        [jurisdiction],
      );
      return res.rows;
    }
    const res = await pool.query<RuleRow>(`
      SELECT rule_id, discipline,
             COALESCE(total_findings, 0)::int  AS total_findings,
             COALESCE(matched, 0)::int          AS matched,
             COALESCE(false_positives, 0)::int  AS false_positives,
             COALESCE(missed, 0)::int           AS missed,
             precision, avg_confidence
      FROM rule_metrics_live
      ORDER BY discipline, rule_id
    `);
    return res.rows;
  } catch {
    if (jurisdiction) {
      const res = await pool.query<RuleRow>(
        `SELECT f.rule_id, f.discipline, COUNT(*)::int AS total_findings,
                0 AS matched, 0 AS false_positives, 0 AS missed,
                NULL::numeric AS precision, AVG(f.confidence) AS avg_confidence
         FROM findings f
         JOIN projects p ON p.project_id = f.project_id
         WHERE f.rule_id IS NOT NULL AND p.jurisdiction = $1
         GROUP BY f.rule_id, f.discipline
         ORDER BY f.discipline, f.rule_id`,
        [jurisdiction],
      );
      return res.rows;
    }
    const res = await pool.query<RuleRow>(`
      SELECT rule_id, discipline, COUNT(*)::int AS total_findings,
             0 AS matched, 0 AS false_positives, 0 AS missed,
             NULL::numeric AS precision, AVG(confidence) AS avg_confidence
      FROM findings
      WHERE rule_id IS NOT NULL
      GROUP BY rule_id, discipline
      ORDER BY discipline, rule_id
    `);
    return res.rows;
  }
}

async function fetchDisciplines(jurisdiction: string): Promise<DisciplineRow[]> {
  if (jurisdiction) {
    const res = await pool.query<DisciplineRow>(
      `SELECT f.discipline,
              COUNT(DISTINCT f.rule_id)::int     AS rule_count,
              COUNT(DISTINCT f.finding_id)::int  AS finding_count,
              ROUND(AVG(f.confidence)::numeric, 3) AS avg_confidence
       FROM findings f
       JOIN projects p ON p.project_id = f.project_id
       WHERE f.discipline IS NOT NULL AND p.jurisdiction = $1
       GROUP BY f.discipline
       ORDER BY f.discipline`,
      [jurisdiction],
    );
    return res.rows;
  }
  const res = await pool.query<DisciplineRow>(`
    SELECT discipline,
           COUNT(DISTINCT rule_id)::int     AS rule_count,
           COUNT(DISTINCT finding_id)::int  AS finding_count,
           ROUND(AVG(confidence)::numeric, 3) AS avg_confidence
    FROM findings
    WHERE discipline IS NOT NULL
    GROUP BY discipline
    ORDER BY discipline
  `);
  return res.rows;
}

async function fetchShadow(): Promise<ShadowRow[]> {
  try {
    const res = await pool.query<ShadowRow>(`
      SELECT run_id, prompt_key, control_version, shadow_version,
             LEFT(control_output, 200) AS control_preview,
             LEFT(shadow_output, 200)  AS shadow_preview,
             winner, created_at
      FROM shadow_runs
      ORDER BY created_at DESC
      LIMIT 20
    `);
    return res.rows;
  } catch {
    return [];
  }
}

const TRIAGE_QUEUES = [
  "misses",
  "false-positives",
  "edits",
  "overrides",
] as const;

export default async function MetricsPage({
  searchParams,
}: {
  searchParams: Promise<{ jurisdiction?: string }>;
}) {
  const { jurisdiction: rawJurisdiction } = await searchParams;
  const jurisdiction =
    rawJurisdiction === "santa_rosa" || rawJurisdiction === "oakland"
      ? rawJurisdiction
      : "";

  const [rules, disciplines, shadowRuns] = await Promise.all([
    fetchRules(jurisdiction),
    fetchDisciplines(jurisdiction),
    fetchShadow(),
  ]);

  // Group rules by discipline for heatmap
  const byDiscipline = new Map<string, RuleRow[]>();
  for (const r of rules) {
    if (!byDiscipline.has(r.discipline)) byDiscipline.set(r.discipline, []);
    byDiscipline.get(r.discipline)!.push(r);
  }

  return (
    <main className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Rule Metrics Dashboard</h1>
      <p className="text-sm text-gray-500 mb-4">
        Precision/recall per rule, computed from AI findings vs authority
        comments. Run{" "}
        <code className="bg-gray-100 px-1 rounded text-xs">
          uv run scripts/run_comparison.py
        </code>{" "}
        to refresh.
      </p>

      {/* Jurisdiction filter pills */}
      <div className="flex items-center gap-2 mb-6">
        <span className="text-xs text-gray-500 font-medium uppercase tracking-wide mr-1">
          Jurisdiction:
        </span>
        {JURISDICTIONS.map((j) => {
          const isActive = jurisdiction === j.value;
          const href = j.value ? `/metrics?jurisdiction=${j.value}` : "/metrics";
          return (
            <a
              key={j.value || "all"}
              href={href}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                isActive
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400 hover:text-indigo-600"
              }`}
            >
              {j.label}
            </a>
          );
        })}
        {jurisdiction && (
          <span className="ml-2 text-xs text-gray-400">
            Filtering by: <strong>{jurisdiction.replace("_", " ")}</strong>
          </span>
        )}
      </div>

      {/* Triage links */}
      <div className="flex gap-3 mb-8">
        {TRIAGE_QUEUES.map((q) => (
          <Link
            key={q}
            href={`/triage/${q}`}
            className="px-3 py-1.5 rounded border border-gray-300 text-sm hover:bg-gray-50 capitalize"
          >
            {q.replace("-", " ")}
          </Link>
        ))}
      </div>

      {/* Per-discipline summary */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-3">By Discipline</h2>
        {disciplines.length === 0 ? (
          <p className="text-sm text-gray-400">
            No findings recorded yet. Run a review to populate this table.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm border-collapse border border-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  {["Discipline", "Rules", "Findings", "Avg Confidence"].map(
                    (h) => (
                      <th
                        key={h}
                        className="px-3 py-2 text-left border border-gray-200 font-medium"
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {disciplines.map((d) => (
                  <tr key={d.discipline} className="hover:bg-gray-50">
                    <td className="px-3 py-1.5 border border-gray-200 font-mono text-xs">
                      {d.discipline}
                    </td>
                    <td className="px-3 py-1.5 border border-gray-200">
                      {d.rule_count}
                    </td>
                    <td className="px-3 py-1.5 border border-gray-200">
                      {d.finding_count}
                    </td>
                    <td className="px-3 py-1.5 border border-gray-200">
                      {d.avg_confidence != null
                        ? (Number(d.avg_confidence) * 100).toFixed(1) + "%"
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Rule precision heatmap */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-3">Rule Precision Heatmap</h2>
        <p className="text-xs text-gray-400 mb-3">
          Cell colour:{" "}
          <span style={{ background: "#86efac" }} className="px-2 rounded">
            ≥ 0.8
          </span>{" "}
          <span style={{ background: "#fde68a" }} className="px-2 rounded">
            0.6–0.8
          </span>{" "}
          <span style={{ background: "#fca5a5" }} className="px-2 rounded">
            0.4–0.6
          </span>{" "}
          <span style={{ background: "#f87171" }} className="px-2 rounded">
            &lt; 0.4
          </span>{" "}
          <span style={{ background: "#e5e7eb" }} className="px-2 rounded">
            no data
          </span>
        </p>
        {byDiscipline.size === 0 ? (
          <p className="text-sm text-gray-400">
            No rules with findings yet.
          </p>
        ) : (
          Array.from(byDiscipline.entries()).map(([disc, discRules]) => (
            <div key={disc} className="mb-6">
              <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-1 capitalize">
                {disc.replace(/_/g, " ")}
              </h3>
              <div className="overflow-x-auto">
                <table className="text-xs border-collapse">
                  <thead>
                    <tr>
                      <th className="px-2 py-1 text-left border border-gray-200 bg-gray-50 min-w-[160px]">
                        Rule
                      </th>
                      <th className="px-2 py-1 border border-gray-200 bg-gray-50">
                        Findings
                      </th>
                      <th className="px-2 py-1 border border-gray-200 bg-gray-50">
                        Matched
                      </th>
                      <th className="px-2 py-1 border border-gray-200 bg-gray-50">
                        FP
                      </th>
                      <th className="px-2 py-1 border border-gray-200 bg-gray-50">
                        Missed
                      </th>
                      <th className="px-2 py-1 border border-gray-200 bg-gray-50 min-w-[80px]">
                        Precision
                      </th>
                      <th className="px-2 py-1 border border-gray-200 bg-gray-50 min-w-[80px]">
                        Confidence
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {discRules.map((r) => (
                      <tr key={r.rule_id}>
                        <td className="px-2 py-1 border border-gray-200 font-mono">
                          {r.rule_id}
                        </td>
                        <td className="px-2 py-1 border border-gray-200 text-center">
                          {r.total_findings}
                        </td>
                        <td className="px-2 py-1 border border-gray-200 text-center">
                          {r.matched}
                        </td>
                        <td className="px-2 py-1 border border-gray-200 text-center">
                          {r.false_positives}
                        </td>
                        <td className="px-2 py-1 border border-gray-200 text-center">
                          {r.missed}
                        </td>
                        <td
                          className="px-2 py-1 border border-gray-200 text-center font-semibold"
                          style={{ background: precisionColor(r.precision) }}
                        >
                          {r.precision != null
                            ? (Number(r.precision) * 100).toFixed(0) + "%"
                            : "—"}
                        </td>
                        <td className="px-2 py-1 border border-gray-200 text-center">
                          {r.avg_confidence != null
                            ? (Number(r.avg_confidence) * 100).toFixed(0) + "%"
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))
        )}
      </section>

      {/* Shadow deploy section */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Shadow Deploy</h2>
        {shadowRuns.length === 0 ? (
          <div className="text-sm text-gray-500 border border-dashed border-gray-300 rounded p-4">
            No shadow runs yet. Set{" "}
            <code className="bg-gray-100 px-1 rounded text-xs">
              shadow = true
            </code>{" "}
            on a prompt_versions row to activate shadow mode.
          </div>
        ) : (
          <div className="space-y-3">
            {shadowRuns.map((run) => (
              <div
                key={run.run_id}
                className="border border-gray-200 rounded p-3 text-sm"
              >
                <div className="flex items-center gap-3 mb-2">
                  <span className="font-mono text-xs bg-gray-100 px-2 py-0.5 rounded">
                    {run.prompt_key}
                  </span>
                  <span className="text-gray-400 text-xs">
                    {run.control_version} → {run.shadow_version}
                  </span>
                  {run.winner != null && (
                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                      winner: {run.winner}
                    </span>
                  )}
                  <span className="text-gray-400 text-xs ml-auto">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-xs font-medium text-gray-500 mb-1">
                      Control ({run.control_version})
                    </div>
                    <div className="bg-gray-50 p-2 rounded text-xs text-gray-700 leading-relaxed">
                      {run.control_preview}&hellip;
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-gray-500 mb-1">
                      Shadow ({run.shadow_version})
                    </div>
                    <div className="bg-blue-50 p-2 rounded text-xs text-gray-700 leading-relaxed">
                      {run.shadow_preview}&hellip;
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
