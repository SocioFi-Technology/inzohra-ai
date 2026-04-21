import { pool as db } from "@/lib/db";
import Link from "next/link";

interface OverrideRow {
  measurement_type: string;
  pdf_quality_class: string | null;
  override_count: number;
  avg_confidence: number;
  last_override: string;
}

async function fetchOverrides(): Promise<OverrideRow[]> {
  try {
    // Try with pdf_quality_class column
    const res = await db.query<OverrideRow>(`
      SELECT measurement_type,
             pdf_quality_class,
             COUNT(*)::int      AS override_count,
             AVG(confidence)    AS avg_confidence,
             MAX(created_at)    AS last_override
      FROM measurements
      WHERE overridden = true
      GROUP BY measurement_type, pdf_quality_class
      ORDER BY override_count DESC
    `);
    return res.rows;
  } catch {
    try {
      // Fallback: without pdf_quality_class or overridden columns
      const res = await db.query<OverrideRow>(`
        SELECT measurement_type,
               NULL::text       AS pdf_quality_class,
               COUNT(*)::int    AS override_count,
               AVG(confidence)  AS avg_confidence,
               MAX(created_at)  AS last_override
        FROM measurements
        GROUP BY measurement_type
        ORDER BY override_count DESC
        LIMIT 20
      `);
      return res.rows;
    } catch {
      return [];
    }
  }
}

export default async function OverridesPage() {
  const overrides = await fetchOverrides();

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <Link href="/metrics" className="text-sm text-blue-600 hover:underline">
          &larr; Metrics
        </Link>
        <h1 className="text-2xl font-bold">Triage: Measurement Overrides</h1>
        <span className="ml-auto bg-gray-100 text-gray-700 text-sm font-medium px-3 py-0.5 rounded-full">
          {overrides.reduce((s, r) => s + r.override_count, 0)} total overrides
        </span>
      </div>
      <p className="text-sm text-gray-500 mb-6">
        Measurement values that a reviewer manually overrode. High override counts
        on a measurement type + PDF quality class indicate the extractor needs
        tuning.
      </p>

      {overrides.length === 0 ? (
        <div className="text-sm text-gray-500 border border-dashed border-gray-300 rounded p-6 text-center">
          No measurement overrides recorded yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm border-collapse border border-gray-200">
            <thead className="bg-gray-50">
              <tr>
                {[
                  "Measurement Type",
                  "PDF Quality",
                  "Override Count",
                  "Avg Confidence",
                  "Last Override",
                ].map((h) => (
                  <th
                    key={h}
                    className="px-3 py-2 text-left border border-gray-200 font-medium text-xs"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {overrides.map((r, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-3 py-2 border border-gray-200 font-mono text-xs">
                    {r.measurement_type}
                  </td>
                  <td className="px-3 py-2 border border-gray-200 text-xs">
                    {r.pdf_quality_class ?? "\u2014"}
                  </td>
                  <td className="px-3 py-2 border border-gray-200 font-semibold">
                    {r.override_count}
                  </td>
                  <td className="px-3 py-2 border border-gray-200">
                    {r.avg_confidence != null
                      ? (Number(r.avg_confidence) * 100).toFixed(0) + "%"
                      : "\u2014"}
                  </td>
                  <td className="px-3 py-2 border border-gray-200 text-xs text-gray-500">
                    {new Date(r.last_override).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
