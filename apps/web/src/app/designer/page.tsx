import { query } from "@/lib/db";
import Link from "next/link";

interface ReportRow {
  report_id: string;
  created_at: string;
  status: string;
  query_count: number;
  green_count: number;
  amber_count: number;
  red_count: number;
  address: string;
  permit_number: string;
}

function StatusChip({ status }: { status: string }) {
  const variants: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    complete: "bg-green-100 text-green-800",
    error: "bg-red-100 text-red-800",
  };
  const cls = variants[status] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

export default async function DesignerReportsPage() {
  let reports: ReportRow[] = [];

  try {
    reports = (await query<ReportRow>(`
      SELECT
        dr.report_id,
        dr.created_at,
        dr.status,
        dr.query_count,
        dr.green_count,
        dr.amber_count,
        dr.red_count,
        p.address,
        p.permit_number
      FROM designer_reports dr
      JOIN projects p ON p.project_id = dr.project_id
      ORDER BY dr.created_at DESC
      LIMIT 50
    `));
  } catch {
    // Table may not exist yet in this environment — render empty state.
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">My Reports</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Checklist analysis results for submitted plan sets.
          </p>
        </div>
        <Link
          href="/designer/upload"
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          New upload
        </Link>
      </div>

      {reports.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500 mb-2">No reports yet.</p>
          <p className="text-sm text-gray-400">
            Upload a plan set and checklist to generate your first report.
          </p>
          <Link
            href="/designer/upload"
            className="inline-block mt-4 text-sm text-blue-600 hover:underline"
          >
            Start upload &rarr;
          </Link>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Project</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Permit #</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Date</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-center px-4 py-3 font-medium text-green-700">Pass</th>
                <th className="text-center px-4 py-3 font-medium text-yellow-700">Warn</th>
                <th className="text-center px-4 py-3 font-medium text-red-700">Fail</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {reports.map((r) => (
                <tr key={r.report_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">{r.address}</td>
                  <td className="px-4 py-3 text-gray-600">{r.permit_number}</td>
                  <td className="px-4 py-3 text-gray-500">
                    {new Date(r.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip status={r.status} />
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-green-700 font-medium">{r.green_count ?? 0}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-yellow-700 font-medium">{r.amber_count ?? 0}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-red-700 font-medium">{r.red_count ?? 0}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/designer/${r.report_id}`}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      View report &rarr;
                    </Link>
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
