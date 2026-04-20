import Link from "next/link";
import { pool } from "@/lib/db";

interface PackRow {
  pack_id: string;
  jurisdiction: string;
  version: string;
  effective_date: string;
  superseded_by: string | null;
  created_at: string;
  amendment_count: number;
}

async function fetchPacks(): Promise<PackRow[]> {
  try {
    const res = await pool.query<PackRow>(`
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
    return res.rows;
  } catch {
    return [];
  }
}

export default async function PacksListPage() {
  const packs = await fetchPacks();

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Jurisdictional Packs</h2>
          <p className="text-sm text-gray-500 mt-1">
            Code amendment packs and agency policies by jurisdiction.
          </p>
        </div>
        <Link
          href="/admin/packs/upload"
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
        >
          Upload new pack →
        </Link>
      </div>

      {packs.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500 mb-2">No jurisdictional packs found.</p>
          <p className="text-sm text-gray-400">
            Run{" "}
            <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono text-xs">
              python scripts/seed_packs.py
            </code>{" "}
            or upload a pack above.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm border-collapse border border-gray-200 bg-white rounded-lg overflow-hidden">
            <thead className="bg-gray-50">
              <tr>
                {["Pack ID", "Jurisdiction", "Version", "Effective Date", "Amendments", "Status", "Created"].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-2.5 text-left border border-gray-200 font-medium text-gray-700 text-xs uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {packs.map((pack) => (
                <tr key={pack.pack_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5 border border-gray-200">
                    <Link
                      href={`/admin/packs/${encodeURIComponent(pack.pack_id)}`}
                      className="font-mono text-xs text-blue-600 hover:underline"
                    >
                      {pack.pack_id}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 border border-gray-200">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                      {pack.jurisdiction}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 border border-gray-200 font-mono text-xs">
                    {pack.version}
                  </td>
                  <td className="px-4 py-2.5 border border-gray-200 text-gray-600">
                    {pack.effective_date
                      ? new Date(pack.effective_date).toLocaleDateString("en-US", {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                          timeZone: "UTC",
                        })
                      : "—"}
                  </td>
                  <td className="px-4 py-2.5 border border-gray-200 text-center text-gray-700">
                    {pack.amendment_count}
                  </td>
                  <td className="px-4 py-2.5 border border-gray-200">
                    {pack.superseded_by == null ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                        Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-400">
                        Superseded
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 border border-gray-200 text-xs text-gray-400">
                    {new Date(pack.created_at).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                      timeZone: "UTC",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
