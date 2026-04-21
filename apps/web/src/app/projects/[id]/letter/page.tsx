import Link from "next/link";
import { pool } from "@/lib/db";
import * as fs from "fs";
import * as path from "path";
import { notFound } from "next/navigation";
import { TopNav } from "@/components/TopNav";

// Severity colors matching the BV palette
const SEVERITY_COLOR: Record<string, string> = {
  revise:         "border-l-4 border-l-red-500",
  provide:        "border-l-4 border-l-amber-500",
  clarify:        "border-l-4 border-l-yellow-400",
  reference_only: "border-l-4 border-l-gray-300",
};
const SEVERITY_BADGE: Record<string, string> = {
  revise:         "bg-red-100 text-red-700",
  provide:        "bg-amber-100 text-amber-700",
  clarify:        "bg-yellow-100 text-yellow-700",
  reference_only: "bg-gray-100 text-gray-500",
};

const DISCIPLINE_LABEL: Record<string, string> = {
  plan_integrity:   "Plan Integrity",
  architectural:    "Architectural",
  accessibility:    "Accessibility",
  energy:           "Energy (Title 24)",
  electrical:       "Electrical",
  mechanical:       "Mechanical",
  plumbing:         "Plumbing",
  structural:       "Structural",
  fire_life_safety: "Fire & Life Safety",
  calgreen:         "CALGreen",
};

type LetterRenderRow = {
  render_id: string;
  pdf_path: string;
  docx_path: string;
  json_path: string;
  review_round: number;
  created_at: string;
  finding_count: number;
};

type FindingEntry = {
  finding_id: string;
  discipline: string;
  severity: string;
  rule_id?: string;
  requires_licensed_review?: boolean;
  comment_number?: number;
  display_text?: string;
  sheet_reference?: { sheet_id?: string; detail?: string };
};

type ProjectBlock = {
  permit_number?: string;
  address?: string;
};

type SignatureBlock = {
  reviewer_name?: string;
  title?: string;
};

type LetterBundle = {
  findings?: FindingEntry[];
  jurisdiction?: string;
  project_block?: ProjectBlock;
  generated_at?: string;
  general_instructions?: string;
  signature_block?: SignatureBlock;
};

const DISC_ORDER = [
  "plan_integrity",
  "architectural",
  "accessibility",
  "energy",
  "electrical",
  "mechanical",
  "plumbing",
  "structural",
  "fire_life_safety",
  "calgreen",
] as const;

export default async function LetterPage({
  params,
}: {
  params: { id: string };
}) {
  // 1. Find latest render
  let render: LetterRenderRow | null = null;
  try {
    const res = await pool.query(
      `SELECT render_id, pdf_path, docx_path, json_path, review_round, created_at, finding_count
       FROM letter_renders
       WHERE project_id = $1
       ORDER BY created_at DESC LIMIT 1`,
      [params.id],
    );
    render = (res.rows[0] as LetterRenderRow) ?? null;
  } catch {
    render = null;
  }

  if (!render) {
    return (
      <>
        <TopNav />
        <main className="p-8 max-w-3xl mx-auto">
          <Link href="/" className="text-sm text-blue-600 hover:underline">
            &larr; Home
          </Link>
          <h1 className="text-2xl font-bold mt-4 mb-2">Comment Letter</h1>
          <div className="border border-dashed border-gray-300 rounded-lg p-12 text-center text-gray-500">
            No letter rendered yet. Run:
            <code className="block mt-2 bg-gray-100 px-3 py-1 rounded text-xs font-mono">
              pnpm --filter @inzohra/rendering render --project {params.id} --round 1
            </code>
          </div>
        </main>
      </>
    );
  }

  // 2. Read JSON bundle — try stored path first, then rendering-service output dir
  let bundle: LetterBundle | null = null;
  try {
    const jsonRaw = fs.readFileSync(render.json_path, "utf8");
    bundle = JSON.parse(jsonRaw) as LetterBundle;
  } catch {
    const altPath = path.join(
      process.cwd(),
      "..",
      "..",
      "services",
      "rendering",
      "inzohra-output",
      path.basename(render.json_path),
    );
    try {
      bundle = JSON.parse(fs.readFileSync(altPath, "utf8")) as LetterBundle;
    } catch {
      notFound();
    }
  }

  if (!bundle) notFound();

  // 3. Group findings by discipline
  const findings: FindingEntry[] = bundle.findings ?? [];
  const byDiscipline = new Map<string, FindingEntry[]>();
  for (const f of findings) {
    if (!byDiscipline.has(f.discipline)) byDiscipline.set(f.discipline, []);
    byDiscipline.get(f.discipline)!.push(f);
  }

  return (
    <>
      <TopNav />
      <main className="min-h-screen bg-gray-50">
      {/* Header bar */}
      <div className="sticky top-12 z-10 bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Link href="/" className="hover:text-indigo-600">Projects</Link>
          <span>/</span>
          <Link href={`/projects/${params.id}`} className="hover:text-indigo-600">Project</Link>
          <span>/</span>
          <Link href={`/projects/${params.id}/sheets`} className="hover:text-indigo-600">Sheets</Link>
          <span>/</span>
          <span className="text-gray-900 font-medium">Letter</span>
        </div>
        <h1 className="font-bold text-gray-900">
          Comment Letter &mdash; Round {render.review_round}
        </h1>
        <span className="text-sm text-gray-400">{render.finding_count} comments</span>
        <span className="text-xs text-gray-400 ml-2">
          Generated {new Date(render.created_at).toLocaleDateString()}
        </span>
        <div className="ml-auto flex gap-2">
          <a
            href={`/api/projects/${params.id}/letter/download?type=pdf`}
            className="px-3 py-1.5 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700 font-medium"
          >
            &darr; PDF
          </a>
          <a
            href={`/api/projects/${params.id}/letter/download?type=docx`}
            className="px-3 py-1.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300 font-medium"
          >
            &darr; DOCX
          </a>
        </div>
      </div>

      {/* Letter body */}
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Project block */}
        <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
          <div className="text-center mb-4">
            <div className="text-sm font-bold text-gray-700 uppercase tracking-wide">
              Bureau Veritas &mdash; Plan Check
            </div>
            <div className="text-xs text-gray-400 mt-0.5">
              {bundle.jurisdiction ?? ""}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
            <div>
              <span className="text-gray-400">Permit:</span>{" "}
              <span className="font-medium">
                {bundle.project_block?.permit_number}
              </span>
            </div>
            <div>
              <span className="text-gray-400">Address:</span>{" "}
              <span className="font-medium">
                {bundle.project_block?.address}
              </span>
            </div>
            <div>
              <span className="text-gray-400">Round:</span>{" "}
              <span className="font-medium">{render.review_round}</span>
            </div>
            <div>
              <span className="text-gray-400">Generated:</span>{" "}
              <span className="font-medium">
                {bundle.generated_at?.slice(0, 10)}
              </span>
            </div>
          </div>
          {bundle.general_instructions && (
            <p className="mt-4 text-xs text-gray-500 italic border-t border-gray-100 pt-3">
              {bundle.general_instructions}
            </p>
          )}
        </div>

        {/* Findings by discipline — canonical order */}
        {DISC_ORDER.map((disc) => {
          const group = byDiscipline.get(disc);
          if (!group || group.length === 0) return null;
          return (
            <section key={disc} className="mb-8">
              <h2 className="text-sm font-bold text-gray-800 uppercase tracking-wide mb-3 flex items-center gap-2">
                <span className="flex-1 border-t border-gray-200"></span>
                <span>{DISCIPLINE_LABEL[disc] ?? disc}</span>
                <span className="text-xs font-normal text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                  {group.length}
                </span>
                <span className="flex-1 border-t border-gray-200"></span>
              </h2>
              <div className="space-y-2">
                {group.map((f) => (
                  <div
                    key={f.finding_id}
                    className={`bg-white border border-gray-200 rounded-lg p-4 ${SEVERITY_COLOR[f.severity] ?? ""}`}
                  >
                    <div className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 bg-gray-100 text-gray-600 rounded-full flex items-center justify-center text-xs font-bold">
                        {f.comment_number}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`text-xs px-1.5 py-0.5 rounded font-medium ${SEVERITY_BADGE[f.severity] ?? "bg-gray-100 text-gray-500"}`}
                          >
                            {f.severity?.replace("_", " ")}
                          </span>
                          {f.rule_id && (
                            <code className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                              {f.rule_id}
                            </code>
                          )}
                          {f.requires_licensed_review && (
                            <span className="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">
                              licensed
                            </span>
                          )}
                          {f.sheet_reference?.sheet_id && (
                            <a
                              href={`/projects/${params.id}/sheets/${encodeURIComponent(f.sheet_reference.sheet_id)}`}
                              className="ml-auto text-xs text-blue-500 hover:underline"
                            >
                              View on sheet &rarr;
                            </a>
                          )}
                        </div>
                        <p className="text-sm text-gray-800 leading-relaxed">
                          {f.display_text}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          );
        })}

        {/* Any disciplines not in canonical order */}
        {Array.from(byDiscipline.entries())
          .filter(([d]) => !(DISC_ORDER as readonly string[]).includes(d))
          .map(([disc, group]) => (
            <section key={disc} className="mb-8">
              <h2 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-3">
                {disc}
              </h2>
              <div className="space-y-2">
                {group.map((f) => (
                  <div
                    key={f.finding_id}
                    className="bg-white border border-gray-200 rounded-lg p-4"
                  >
                    <span className="text-sm text-gray-700">{f.display_text}</span>
                  </div>
                ))}
              </div>
            </section>
          ))}

        {/* Signature */}
        <div className="mt-10 pt-6 border-t border-gray-200 text-sm text-gray-600">
          <p>Sincerely,</p>
          <p className="font-semibold mt-2">
            {bundle.signature_block?.reviewer_name}
          </p>
          <p className="text-gray-400">{bundle.signature_block?.title}</p>
        </div>
      </div>
    </main>
    </>
  );
}
