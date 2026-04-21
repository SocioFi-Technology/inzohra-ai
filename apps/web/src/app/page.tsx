import Link from "next/link";
import { pool } from "@/lib/db";

type ProjectRow = {
  project_id: string;
  address: string;
  permit_number: string;
  jurisdiction: string;
  created_at: string;
};

type PipelineStatus = {
  ingest: boolean;
  extract: boolean;
  review_ext: boolean;
  measure: boolean;
  findings: boolean;
  all_disc: boolean;
  letter: boolean;
  counts: {
    sheets: number;
    entities: number;
    ext_comments: number;
    measurements: number;
    findings: number;
    disciplines: number;
  };
};

/** Check pipeline phase completions for a single project. */
async function getPipelineStatus(projectId: string): Promise<PipelineStatus> {
  const checks = await Promise.allSettled([
    // 0 — sheets (ingest)
    pool.query(
      `SELECT COUNT(*)::int AS n
       FROM sheets s
       JOIN documents d ON d.document_id = s.document_id
       JOIN submittals sub ON sub.submittal_id = d.submittal_id
       WHERE sub.project_id = $1`,
      [projectId],
    ),
    // 1 — entities (extract)
    pool.query(
      `SELECT COUNT(*)::int AS n
       FROM entities e
       JOIN sheets s ON s.sheet_id = e.sheet_id
       JOIN documents d ON d.document_id = s.document_id
       JOIN submittals sub ON sub.submittal_id = d.submittal_id
       WHERE sub.project_id = $1`,
      [projectId],
    ),
    // 2 — external review comments
    pool.query(
      `SELECT COUNT(*)::int AS n FROM external_review_comments WHERE project_id = $1`,
      [projectId],
    ),
    // 3 — measurements (table may not exist yet — caught by allSettled)
    pool.query(
      `SELECT COUNT(*)::int AS n FROM measurements WHERE project_id = $1`,
      [projectId],
    ),
    // 4 — findings
    pool.query(
      `SELECT COUNT(*)::int AS n FROM findings WHERE project_id = $1`,
      [projectId],
    ),
    // 5 — distinct disciplines in findings
    pool.query(
      `SELECT COUNT(DISTINCT discipline)::int AS n FROM findings WHERE project_id = $1`,
      [projectId],
    ),
    // 6 — letter renders
    pool.query(
      `SELECT COUNT(*)::int AS n FROM letter_renders WHERE project_id = $1`,
      [projectId],
    ),
  ]);

  const n = (idx: number): number => {
    const r = checks[idx];
    return r.status === "fulfilled" ? ((r.value.rows[0]?.n as number) ?? 0) : 0;
  };

  return {
    ingest:     n(0) > 0,
    extract:    n(1) > 0,
    review_ext: n(2) > 0,
    measure:    n(3) > 0,
    findings:   n(4) > 0,
    all_disc:   n(5) >= 7,
    letter:     n(6) > 0,
    counts: {
      sheets:       n(0),
      entities:     n(1),
      ext_comments: n(2),
      measurements: n(3),
      findings:     n(4),
      disciplines:  n(5),
    },
  };
}

const PIPELINE_PHASES = [
  { key: "ingest",   label: "Ingest"   },
  { key: "extract",  label: "Extract"  },
  { key: "measure",  label: "Measure"  },
  { key: "findings", label: "Review"   },
  { key: "all_disc", label: "All disc" },
  { key: "letter",   label: "Letter"   },
] as const;

type PhaseKey = (typeof PIPELINE_PHASES)[number]["key"];

export default async function Home() {
  let projects: ProjectRow[] = [];
  try {
    const res = await pool.query(
      `SELECT project_id, address, permit_number, jurisdiction, created_at
       FROM projects
       ORDER BY created_at DESC`,
    );
    projects = res.rows as ProjectRow[];
  } catch {
    // DB not reachable at build time
  }

  // Fetch pipeline status for all projects in parallel
  const statuses = await Promise.all(
    projects.map((p) => getPipelineStatus(p.project_id)),
  );

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Top nav */}
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-6">
        <span className="font-bold text-gray-900 text-lg">Inzohra-ai</span>
        <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
          Plan Review System
        </span>
        <div className="ml-auto flex items-center gap-4 text-sm">
          <Link href="/metrics" className="text-gray-600 hover:text-indigo-600">
            Metrics
          </Link>
          <Link href="/triage" className="text-gray-600 hover:text-indigo-600">
            Triage
          </Link>
          <Link
            href="/admin/packs"
            className="text-gray-600 hover:text-indigo-600"
          >
            Packs
          </Link>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-6 py-8">
        <h1 className="text-xl font-bold text-gray-900 mb-1">Projects</h1>
        <p className="text-sm text-gray-500 mb-6">
          Active plan-check submittals. Click a project to open the reviewer
          workspace.
        </p>

        {projects.length === 0 ? (
          <div className="rounded-xl border-2 border-dashed border-gray-300 p-16 text-center">
            <p className="text-gray-500 text-lg mb-2">No projects yet.</p>
            <p className="text-sm text-gray-400">
              Run{" "}
              <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono text-xs">
                uv run scripts/ingest_fixture.py
              </code>{" "}
              to ingest the 2008 Dennis Ln fixture.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {projects.map((p, i) => {
              const status = statuses[i];
              const allDone = PIPELINE_PHASES.every(
                (ph) => status[ph.key as PhaseKey] as boolean,
              );
              return (
                <div
                  key={p.project_id}
                  className="bg-white rounded-xl border border-gray-200 hover:border-indigo-300 transition-colors overflow-hidden"
                >
                  {/* Card header */}
                  <div className="px-5 py-4 flex items-start gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h2 className="font-semibold text-gray-900">
                          {p.address}
                        </h2>
                        {allDone && (
                          <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                            Ready
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-500 mt-0.5">
                        Permit {p.permit_number} &middot;{" "}
                        {p.jurisdiction.replace(/_/g, " ")}
                      </p>
                      {/* Stats row */}
                      <div className="flex gap-4 mt-2 text-xs text-gray-400">
                        <span>{status.counts.sheets} sheets</span>
                        {status.counts.findings > 0 && (
                          <span>{status.counts.findings} findings</span>
                        )}
                        {status.counts.disciplines > 0 && (
                          <span>{status.counts.disciplines} disciplines</span>
                        )}
                        {status.counts.ext_comments > 0 && (
                          <span>
                            {status.counts.ext_comments} BV comments
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="text-xs text-gray-300 mt-1">
                      {new Date(p.created_at).toLocaleDateString()}
                    </span>
                  </div>

                  {/* Pipeline progress bar */}
                  <div className="px-5 pb-3">
                    <div className="flex items-center gap-1 flex-wrap">
                      {PIPELINE_PHASES.map((ph, phIdx) => {
                        const done = status[ph.key as PhaseKey] as boolean;
                        return (
                          <div key={ph.key} className="flex items-center gap-1">
                            <div
                              className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                                done
                                  ? "bg-indigo-100 text-indigo-700"
                                  : "bg-gray-100 text-gray-400"
                              }`}
                            >
                              {done ? "\u2713" : "\u25CB"} {ph.label}
                            </div>
                            {phIdx < PIPELINE_PHASES.length - 1 && (
                              <div className="w-3 h-px bg-gray-200"></div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Action links */}
                  <div className="border-t border-gray-100 px-5 py-2.5 flex gap-4 bg-gray-50">
                    <Link
                      href={`/projects/${p.project_id}/sheets`}
                      className="text-xs text-blue-600 hover:underline font-medium"
                    >
                      Reviewer Workspace &rarr;
                    </Link>
                    {status.letter && (
                      <Link
                        href={`/projects/${p.project_id}/letter`}
                        className="text-xs text-indigo-600 hover:underline font-medium"
                      >
                        View Letter &rarr;
                      </Link>
                    )}
                    <Link
                      href="/metrics"
                      className="text-xs text-gray-500 hover:underline"
                    >
                      Metrics
                    </Link>
                    <Link
                      href="/triage"
                      className="text-xs text-gray-500 hover:underline"
                    >
                      Triage
                    </Link>
                    {status.findings && (
                      <Link
                        href="/designer"
                        className="text-xs text-gray-500 hover:underline"
                      >
                        Designer
                      </Link>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
