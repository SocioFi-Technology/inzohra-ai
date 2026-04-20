import { query, queryOne } from "@/lib/db";
import Link from "next/link";

interface QueryRow {
  item_id: string;
  description: string;
  code_ref: string;
  threshold_value: number | null;
  threshold_unit: string | null;
  status: string | null;
  measured_value: number | null;
  unit: string | null;
  answer_text: string | null;
  confidence: number | null;
}

interface AnswerRow {
  item_id: string;
  description: string;
  code_ref: string;
  threshold_value: number | null;
  threshold_unit: string | null;
  status: string | null;
  measured_value: number | null;
  unit: string | null;
  answer_text: string | null;
  confidence: number | null;
  evidence_entity_ids: string[] | null;
  target_entity_class: string | null;
}

interface ReportMeta {
  report_id: string;
  project_id: string;
  status: string;
  pdf_path: string | null;
  query_count: number;
  green_count: number;
  amber_count: number;
  red_count: number;
  address: string;
  permit_number: string;
}

function StatusChip({ status }: { status: string | null }) {
  const variants: Record<string, string> = {
    green: "bg-green-100 text-green-800 border-green-200",
    amber: "bg-yellow-100 text-yellow-800 border-yellow-200",
    red: "bg-red-100 text-red-800 border-red-200",
    unknown: "bg-gray-100 text-gray-600 border-gray-200",
  };
  const key = status ?? "unknown";
  const cls = variants[key] ?? variants["unknown"];
  return (
    <span className={`inline-block px-2 py-0.5 rounded border text-xs font-medium ${cls}`}>
      {key}
    </span>
  );
}

const REMEDIATION_BY_CLASS: Record<string, string> = {
  window: "Revise window specifications to increase NCO",
  door: "Provide wider door or verify clear width measurement",
  room: "Revise room dimensions or ceiling height per plans",
  egress_path: "Verify travel distance or provide alternative egress",
};

type Props = {
  params: { reportId: string };
  searchParams: { view?: string };
};

export default async function ReportDetailPage({ params, searchParams }: Props) {
  const view = searchParams.view ?? "questions";
  const { reportId } = params;

  let report: ReportMeta | null = null;
  let rows: AnswerRow[] = [];

  try {
    report = await queryOne<ReportMeta>(`
      SELECT
        dr.report_id,
        dr.project_id,
        dr.status,
        dr.pdf_path,
        dr.query_count,
        dr.green_count,
        dr.amber_count,
        dr.red_count,
        p.address,
        p.permit_number
      FROM designer_reports dr
      JOIN projects p ON p.project_id = dr.project_id
      WHERE dr.report_id = $1
    `, [reportId]);
  } catch {
    // table may not exist yet
  }

  if (!report) {
    return (
      <div className="text-center py-16 text-gray-500">
        <p>Report not found or database not yet available.</p>
        <Link href="/designer" className="text-blue-600 hover:underline text-sm mt-2 inline-block">
          &larr; Back to reports
        </Link>
      </div>
    );
  }

  try {
    rows = await query<AnswerRow>(`
      SELECT
        cq.item_id,
        cq.description,
        cq.code_ref,
        cq.threshold_value,
        cq.threshold_unit,
        cq.target_entity_class,
        ca.status,
        ca.measured_value,
        ca.unit,
        ca.answer_text,
        ca.confidence,
        ca.evidence_entity_ids
      FROM checklist_queries cq
      LEFT JOIN checklist_answers ca ON ca.query_id = cq.query_id
      WHERE cq.project_id = $1
      ORDER BY cq.created_at, cq.item_id
    `, [report.project_id]);
  } catch {
    // answers table may not exist yet
  }

  const viewLinks = [
    { key: "questions", label: "Questions" },
    { key: "plan", label: "Plan" },
    { key: "remediation", label: "Remediation" },
  ];

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <Link href="/designer" className="text-sm text-blue-600 hover:underline">
            &larr; My Reports
          </Link>
        </div>
        <h2 className="text-xl font-semibold text-gray-900">{report.address}</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Permit {report.permit_number} &middot; Report{" "}
          <code className="font-mono text-xs">{reportId.slice(0, 8)}&hellip;</code>
        </p>

        {/* Summary counts */}
        <div className="flex gap-4 mt-3">
          <span className="text-sm text-green-700 font-medium">
            {report.green_count ?? 0} pass
          </span>
          <span className="text-sm text-yellow-700 font-medium">
            {report.amber_count ?? 0} warn
          </span>
          <span className="text-sm text-red-700 font-medium">
            {report.red_count ?? 0} fail
          </span>
          <span className="text-sm text-gray-500">
            of {report.query_count ?? 0} queries
          </span>
        </div>
      </div>

      {/* View switcher */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {viewLinks.map((vl) => (
          <Link
            key={vl.key}
            href={`/designer/${reportId}?view=${vl.key}`}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              view === vl.key
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {vl.label}
          </Link>
        ))}
      </div>

      {/* View: Questions */}
      {view === "questions" && (
        <div className="space-y-3">
          {rows.length === 0 && (
            <div className="rounded-lg border border-dashed border-gray-300 p-10 text-center text-gray-400">
              No query answers yet. The analysis pipeline may still be running.
            </div>
          )}
          {rows.map((row) => (
            <div
              key={row.item_id}
              className="bg-white rounded-lg border border-gray-200 p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 inline-block bg-gray-100 text-gray-600 font-mono text-xs px-2 py-0.5 rounded shrink-0">
                    {row.item_id}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-gray-900">{row.description}</p>
                    <p className="text-xs text-gray-400 mt-0.5 font-mono">{row.code_ref}</p>
                  </div>
                </div>
                <StatusChip status={row.status} />
              </div>

              {(row.measured_value != null || row.threshold_value != null) && (
                <div className="mt-3 flex gap-6 text-xs text-gray-500">
                  {row.measured_value != null && (
                    <span>
                      Measured:{" "}
                      <strong className="text-gray-700">
                        {row.measured_value} {row.unit ?? ""}
                      </strong>
                    </span>
                  )}
                  {row.threshold_value != null && (
                    <span>
                      Required:{" "}
                      <strong className="text-gray-700">
                        {row.threshold_value} {row.threshold_unit ?? ""}
                      </strong>
                    </span>
                  )}
                  {row.confidence != null && (
                    <span>
                      Confidence:{" "}
                      <strong className="text-gray-700">
                        {Math.round(row.confidence * 100)}%
                      </strong>
                    </span>
                  )}
                </div>
              )}

              {row.answer_text && (
                <p className="mt-2 text-sm text-gray-600 bg-gray-50 rounded px-3 py-2">
                  {row.answer_text}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* View: Plan */}
      {view === "plan" && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <p className="text-sm text-gray-600 mb-4">
            Plan overlay coming in Phase 10. Evidence entity IDs from red and amber
            findings:
          </p>
          {(() => {
            const entityIds = rows
              .filter((r) => r.status === "red" || r.status === "amber")
              .flatMap((r) => r.evidence_entity_ids ?? [])
              .filter(Boolean);

            return entityIds.length > 0 ? (
              <pre className="text-xs font-mono bg-gray-50 rounded-lg p-4 border border-gray-200 overflow-x-auto whitespace-pre-wrap break-all">
                {entityIds.join("\n")}
              </pre>
            ) : (
              <p className="text-sm text-gray-400">
                No entity IDs available (no red or amber findings, or analysis pending).
              </p>
            );
          })()}
        </div>
      )}

      {/* View: Remediation */}
      {view === "remediation" && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-500">
              Red and amber findings only, sorted by severity.
            </p>
            <a
              href={report.pdf_path ?? `/api/designer/${reportId}/pdf`}
              className="text-sm text-blue-600 hover:underline border border-blue-200 rounded-lg px-3 py-1.5 hover:bg-blue-50 transition-colors"
            >
              Download PDF
            </a>
          </div>

          {(() => {
            const remediation = rows
              .filter((r) => r.status === "red" || r.status === "amber")
              .sort((a, b) => {
                const order: Record<string, number> = { red: 0, amber: 1 };
                return (order[a.status ?? ""] ?? 2) - (order[b.status ?? ""] ?? 2);
              });

            if (remediation.length === 0) {
              return (
                <div className="rounded-lg border border-dashed border-gray-300 p-10 text-center text-gray-400">
                  No remediation items — all queries passed or are pending.
                </div>
              );
            }

            return (
              <div className="space-y-3">
                {remediation.map((row) => {
                  const severityLabel = row.status === "red" ? "Attention" : "Recommend";
                  const severityCls =
                    row.status === "red"
                      ? "bg-red-50 border-red-200 text-red-800"
                      : "bg-yellow-50 border-yellow-200 text-yellow-800";
                  const remediationAction =
                    REMEDIATION_BY_CLASS[row.target_entity_class ?? ""] ??
                    "Review plans and correct the identified deficiency.";

                  return (
                    <div
                      key={row.item_id}
                      className={`rounded-lg border p-4 ${severityCls}`}
                    >
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div>
                          <span className="text-xs font-semibold uppercase tracking-wide">
                            {severityLabel}
                          </span>
                          <p className="text-sm font-medium mt-0.5">{row.description}</p>
                        </div>
                        <span className="font-mono text-xs shrink-0 opacity-70">
                          {row.code_ref}
                        </span>
                      </div>

                      {(row.measured_value != null || row.threshold_value != null) && (
                        <div className="flex gap-4 text-xs mb-2 opacity-80">
                          {row.measured_value != null && (
                            <span>
                              Measured: {row.measured_value} {row.unit ?? ""}
                            </span>
                          )}
                          {row.threshold_value != null && (
                            <span>
                              Required: {row.threshold_value} {row.threshold_unit ?? ""}
                            </span>
                          )}
                        </div>
                      )}

                      <div className="text-xs mt-2 bg-white bg-opacity-60 rounded px-3 py-2">
                        <strong>Action:</strong> {remediationAction}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
