import Link from "next/link";
import { query } from "@/lib/db";

type Project = {
  project_id: string;
  address: string;
  permit_number: string;
  jurisdiction: string;
  sheet_count: string;
  created_at: string;
};

export default async function Home() {
  let projects: Project[] = [];
  try {
    projects = (await query(`
      SELECT
        p.project_id,
        p.address,
        p.permit_number,
        p.jurisdiction,
        p.created_at,
        COUNT(DISTINCT s.sheet_id)::text AS sheet_count
      FROM projects p
      LEFT JOIN submittals sub ON sub.project_id = p.project_id
      LEFT JOIN documents d ON d.submittal_id = sub.submittal_id
      LEFT JOIN sheets s ON s.document_id = d.document_id
      GROUP BY p.project_id
      ORDER BY p.created_at DESC
    `)) as Project[];
  } catch {
    // DB might not be reachable at build time
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Inzohra-ai</h1>
        <p className="text-sm text-gray-500 mb-8">
          Retrieval-grounded plan review · Phase 00
        </p>

        {projects.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center">
            <p className="text-gray-500 mb-3">No projects yet.</p>
            <p className="text-sm text-gray-400">
              Run{" "}
              <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono text-xs">
                uv run scripts/ingest_fixture.py
              </code>{" "}
              to ingest the 2008 Dennis Ln fixture.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {projects.map((p) => (
              <div
                key={p.project_id}
                className="bg-white rounded-lg border border-gray-200 p-4 hover:border-blue-300 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-semibold text-gray-900">{p.address}</p>
                    <p className="text-sm text-gray-500 mt-0.5">
                      Permit {p.permit_number} · {p.jurisdiction}
                    </p>
                  </div>
                  <span className="text-xs text-gray-400 mt-1">
                    {p.sheet_count} sheets
                  </span>
                </div>
                <div className="mt-3">
                  <Link
                    href={`/projects/${p.project_id}/sheets/`}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    View sheets →
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
