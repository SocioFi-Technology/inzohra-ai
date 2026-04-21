import { notFound } from "next/navigation";
import Link from "next/link";
import { query, queryOne } from "@/lib/db";
import { TopNav } from "@/components/TopNav";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ProjectRow = {
  project_id: string;
  address: string;
  permit_number: string;
  jurisdiction: string;
  effective_date: string | null;
  occupancy_class: string | null;
  construction_type: string | null;
  created_at: string;
};

type DisciplineCount = {
  discipline_letter: string;
  cnt: number;
};

type SeverityCount = {
  severity: string;
  cnt: number;
};

type ApprovalCount = {
  state: string;
  cnt: number;
};

type LetterRender = {
  render_id: string;
  review_round: number;
  created_at: string;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SEVERITY_STYLES: Record<string, string> = {
  revise: "bg-red-100 text-red-700",
  provide: "bg-amber-100 text-amber-700",
  clarify: "bg-yellow-100 text-yellow-700",
  reference_only: "bg-gray-100 text-gray-500",
};

const DISCIPLINE_STYLES: Record<string, string> = {
  A: "bg-blue-100 text-blue-700",
  S: "bg-orange-100 text-orange-700",
  M: "bg-green-100 text-green-700",
  E: "bg-yellow-100 text-yellow-700",
  P: "bg-cyan-100 text-cyan-700",
};

function severityLabel(s: string): string {
  const map: Record<string, string> = {
    revise: "Revise",
    provide: "Provide",
    clarify: "Clarify",
    reference_only: "Reference Only",
  };
  return map[s] ?? s;
}

function totalFindings(rows: SeverityCount[]): number {
  return rows.reduce((acc, r) => acc + r.cnt, 0);
}

function approvalTotal(rows: ApprovalCount[]): number {
  return rows.reduce((acc, r) => acc + r.cnt, 0);
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function ProjectOverviewPage({
  params,
}: {
  params: { id: string };
}) {
  const projectId = params.id;

  // Fetch project (required)
  const project = await queryOne<ProjectRow>(
    `SELECT project_id, address, permit_number, jurisdiction,
            effective_date, occupancy_class, construction_type, created_at
     FROM projects WHERE project_id = $1`,
    [projectId],
  );

  if (!project) notFound();

  // Parallel secondary fetches — all gracefully degrade
  const [disciplinesResult, severitiesResult, approvalsResult, letterResult] =
    await Promise.allSettled([
      query<DisciplineCount>(
        `SELECT discipline_letter, COUNT(*)::int AS cnt
         FROM sheets s
         JOIN documents d ON d.document_id = s.document_id
         JOIN submittals sub ON sub.submittal_id = d.submittal_id
         WHERE sub.project_id = $1
           AND discipline_letter IS NOT NULL
         GROUP BY discipline_letter
         ORDER BY discipline_letter`,
        [projectId],
      ),
      query<SeverityCount>(
        `SELECT severity, COUNT(*)::int AS cnt
         FROM findings WHERE project_id = $1
         GROUP BY severity`,
        [projectId],
      ),
      query<ApprovalCount>(
        `SELECT COALESCE(approval_state, 'pending') AS state,
                COUNT(*)::int AS cnt
         FROM findings WHERE project_id = $1
         GROUP BY approval_state`,
        [projectId],
      ),
      queryOne<LetterRender>(
        `SELECT render_id, review_round, created_at
         FROM letter_renders WHERE project_id = $1
         ORDER BY created_at DESC LIMIT 1`,
        [projectId],
      ),
    ]);

  const disciplines: DisciplineCount[] =
    disciplinesResult.status === "fulfilled" ? disciplinesResult.value : [];
  const severities: SeverityCount[] =
    severitiesResult.status === "fulfilled" ? severitiesResult.value : [];
  const approvals: ApprovalCount[] =
    approvalsResult.status === "fulfilled" ? approvalsResult.value : [];
  const letter: LetterRender | null =
    letterResult.status === "fulfilled" ? letterResult.value : null;

  const findingTotal = totalFindings(severities);
  const approvalTotalCount = approvalTotal(approvals);

  const approvedCount =
    approvals.find((a) => a.state === "approved")?.cnt ?? 0;
  const rejectedCount =
    approvals.find((a) => a.state === "rejected")?.cnt ?? 0;
  const editedCount = approvals.find((a) => a.state === "edited")?.cnt ?? 0;
  const pendingCount =
    approvals.find((a) => a.state === "pending")?.cnt ?? 0;

  const effectiveDateDisplay = project.effective_date
    ? new Date(project.effective_date).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "—";

  return (
    <>
      <TopNav />
      <main className="max-w-5xl mx-auto px-6 py-6">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1.5 text-sm text-gray-500 mb-4">
          <Link href="/" className="hover:text-indigo-600 transition-colors">
            ← Projects
          </Link>
          <span>/</span>
          <span className="text-gray-900 font-medium truncate">
            {project.address}
          </span>
        </nav>

        {/* Project header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">{project.address}</h1>
          <div className="flex flex-wrap gap-4 mt-1.5 text-sm text-gray-500">
            <span>
              Permit{" "}
              <span className="font-medium text-gray-700">
                {project.permit_number}
              </span>
            </span>
            <span>
              Jurisdiction{" "}
              <span className="font-medium text-gray-700">
                {project.jurisdiction.replace(/_/g, " ")}
              </span>
            </span>
            <span>
              Effective{" "}
              <span className="font-medium text-gray-700">
                {effectiveDateDisplay}
              </span>
            </span>
            {project.occupancy_class && (
              <span>
                Occupancy{" "}
                <span className="font-medium text-gray-700">
                  {project.occupancy_class}
                </span>
              </span>
            )}
            {project.construction_type && (
              <span>
                Construction{" "}
                <span className="font-medium text-gray-700">
                  {project.construction_type}
                </span>
              </span>
            )}
          </div>
        </div>

        {/* Action cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <Link
            href={`/projects/${projectId}/sheets`}
            className="bg-white border border-gray-200 rounded-xl px-5 py-4 hover:border-indigo-300 hover:shadow-sm transition-all group"
          >
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">
              Workspace
            </div>
            <div className="font-semibold text-gray-900 group-hover:text-indigo-700 transition-colors">
              Reviewer Workspace →
            </div>
            <div className="text-xs text-gray-500 mt-1">
              Sheets, findings, annotations
            </div>
          </Link>

          <Link
            href={`/projects/${projectId}/letter`}
            className={`bg-white border rounded-xl px-5 py-4 hover:shadow-sm transition-all group ${
              letter
                ? "border-gray-200 hover:border-indigo-300"
                : "border-dashed border-gray-300 opacity-70"
            }`}
          >
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">
              Letter
            </div>
            <div
              className={`font-semibold transition-colors ${
                letter
                  ? "text-gray-900 group-hover:text-indigo-700"
                  : "text-gray-400"
              }`}
            >
              {letter ? "Letter Preview →" : "Not generated yet"}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {letter
                ? `Round ${letter.review_round}`
                : "Run the review pipeline first"}
            </div>
          </Link>

          <Link
            href="/designer"
            className="bg-white border border-gray-200 rounded-xl px-5 py-4 hover:border-indigo-300 hover:shadow-sm transition-all group"
          >
            <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">
              Designer
            </div>
            <div className="font-semibold text-gray-900 group-hover:text-indigo-700 transition-colors">
              Designer Checklist →
            </div>
            <div className="text-xs text-gray-500 mt-1">
              Upload responses, view comments
            </div>
          </Link>
        </div>

        {/* Stats pills */}
        <div className="flex flex-wrap gap-3 mb-6">
          <span className="bg-white border border-gray-200 rounded-full px-3 py-1 text-sm text-gray-700">
            <span className="font-semibold">{disciplines.reduce((a, d) => a + d.cnt, 0)}</span>{" "}
            sheets
          </span>
          <span className="bg-white border border-gray-200 rounded-full px-3 py-1 text-sm text-gray-700">
            <span className="font-semibold">{findingTotal}</span> findings
          </span>
          <span className="bg-white border border-gray-200 rounded-full px-3 py-1 text-sm text-gray-700">
            <span className="font-semibold">{approvedCount}</span> approved
          </span>
          <span className="bg-white border border-gray-200 rounded-full px-3 py-1 text-sm text-gray-700">
            Letter:{" "}
            {letter ? (
              <span className="font-semibold">Round {letter.review_round}</span>
            ) : (
              <span className="text-gray-400">Pending</span>
            )}
          </span>
        </div>

        {/* Two-column grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
          {/* Severity breakdown */}
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              Findings by Severity
            </h2>
            {severities.length === 0 ? (
              <p className="text-sm text-gray-400">No findings yet.</p>
            ) : (
              <div className="space-y-2">
                {severities.map((row) => (
                  <div
                    key={row.severity}
                    className="flex items-center justify-between"
                  >
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded ${
                        SEVERITY_STYLES[row.severity] ??
                        "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {severityLabel(row.severity)}
                    </span>
                    <span className="text-sm font-semibold text-gray-900">
                      {row.cnt}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Discipline breakdown */}
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              Sheets by Discipline
            </h2>
            {disciplines.length === 0 ? (
              <p className="text-sm text-gray-400">No sheets ingested yet.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {disciplines.map((row) => (
                  <span
                    key={row.discipline_letter}
                    className={`inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full ${
                      DISCIPLINE_STYLES[row.discipline_letter] ??
                      "bg-gray-100 text-gray-600"
                    }`}
                  >
                    <span className="font-bold">{row.discipline_letter}</span>
                    <span className="opacity-75">{row.cnt}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Approval progress */}
        {approvalTotalCount > 0 && (
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              Approval Progress
            </h2>
            {/* Progress bar */}
            <div className="w-full h-2 rounded-full bg-gray-100 overflow-hidden flex mb-3">
              {approvedCount > 0 && (
                <div
                  className="bg-green-500 h-full"
                  style={{
                    width: `${(approvedCount / approvalTotalCount) * 100}%`,
                  }}
                />
              )}
              {editedCount > 0 && (
                <div
                  className="bg-blue-400 h-full"
                  style={{
                    width: `${(editedCount / approvalTotalCount) * 100}%`,
                  }}
                />
              )}
              {rejectedCount > 0 && (
                <div
                  className="bg-red-400 h-full"
                  style={{
                    width: `${(rejectedCount / approvalTotalCount) * 100}%`,
                  }}
                />
              )}
              {pendingCount > 0 && (
                <div
                  className="bg-gray-200 h-full"
                  style={{
                    width: `${(pendingCount / approvalTotalCount) * 100}%`,
                  }}
                />
              )}
            </div>
            <div className="flex flex-wrap gap-4 text-xs text-gray-600">
              {pendingCount > 0 && (
                <span>
                  <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300 mr-1 align-middle" />
                  Pending: <span className="font-medium">{pendingCount}</span>
                </span>
              )}
              {approvedCount > 0 && (
                <span>
                  <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500 mr-1 align-middle" />
                  Approved: <span className="font-medium">{approvedCount}</span>
                </span>
              )}
              {editedCount > 0 && (
                <span>
                  <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-400 mr-1 align-middle" />
                  Edited: <span className="font-medium">{editedCount}</span>
                </span>
              )}
              {rejectedCount > 0 && (
                <span>
                  <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-400 mr-1 align-middle" />
                  Rejected: <span className="font-medium">{rejectedCount}</span>
                </span>
              )}
            </div>
          </div>
        )}
      </main>
    </>
  );
}
