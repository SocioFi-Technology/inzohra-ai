import { pool } from "@/lib/db";
import Link from "next/link";
import { TopNav } from "@/components/TopNav";

async function fetchCounts(): Promise<{
  misses: number;
  fps: number;
  edits: number;
  overrides: number;
}> {
  const [misses, fps, edits, overrides] = await Promise.allSettled([
    pool.query(`
      SELECT COUNT(*)::int AS n FROM external_review_comments erc
      WHERE NOT EXISTS (
        SELECT 1 FROM alignment_records ar
        WHERE ar.comment_id = erc.external_comment_id AND ar.bucket IN ('matched','partial')
      )
    `),
    pool.query(`
      SELECT COUNT(*)::int AS n FROM findings f
      JOIN alignment_records ar ON ar.finding_id = f.finding_id AND ar.bucket = 'false_positive'
    `),
    pool.query(
      `SELECT COUNT(*)::int AS n FROM reviewer_edits WHERE edit_ratio >= 0.25`,
    ),
    pool.query(
      `SELECT COUNT(*)::int AS n FROM measurements WHERE override_value IS NOT NULL`,
    ),
  ]);

  return {
    misses:
      misses.status === "fulfilled" ? (misses.value.rows[0]?.n ?? 0) : 0,
    fps: fps.status === "fulfilled" ? (fps.value.rows[0]?.n ?? 0) : 0,
    edits:
      edits.status === "fulfilled" ? (edits.value.rows[0]?.n ?? 0) : 0,
    overrides:
      overrides.status === "fulfilled"
        ? (overrides.value.rows[0]?.n ?? 0)
        : 0,
  };
}

const QUEUES = [
  {
    href: "/triage/misses",
    label: "Misses",
    desc: "Authority comments the AI did not raise",
    color: "red",
    countKey: "misses",
  },
  {
    href: "/triage/false-positives",
    label: "False Positives",
    desc: "AI findings the authority did not raise",
    color: "orange",
    countKey: "fps",
  },
  {
    href: "/triage/edits",
    label: "High-Edit Findings",
    desc: "Drafter output with large reviewer edits — few-shot material",
    color: "purple",
    countKey: "edits",
  },
  {
    href: "/triage/overrides",
    label: "Measurement Overrides",
    desc: "Manual measurement corrections grouped by type + PDF quality",
    color: "gray",
    countKey: "overrides",
  },
] as const;

const COLOR_MAP = {
  red: {
    bg: "bg-red-50",
    border: "border-red-200",
    text: "text-red-700",
  },
  orange: {
    bg: "bg-orange-50",
    border: "border-orange-200",
    text: "text-orange-700",
  },
  purple: {
    bg: "bg-purple-50",
    border: "border-purple-200",
    text: "text-purple-700",
  },
  gray: {
    bg: "bg-gray-50",
    border: "border-gray-200",
    text: "text-gray-700",
  },
} as const;

export default async function TriagePage() {
  const counts = await fetchCounts();

  return (
    <>
      <TopNav />
      <main className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <Link href="/metrics" className="text-sm text-blue-600 hover:underline">
          &larr; Metrics
        </Link>
        <h1 className="text-2xl font-bold">Triage Queues</h1>
      </div>
      <p className="text-sm text-gray-500 mb-8">
        Review and action items from the learning loop. Run{" "}
        <code className="bg-gray-100 px-1 rounded text-xs">
          uv run scripts/run_comparison.py
        </code>{" "}
        to populate misses and false-positives.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {QUEUES.map((q) => {
          const c = COLOR_MAP[q.color];
          const count = counts[q.countKey as keyof typeof counts];
          return (
            <Link
              key={q.href}
              href={q.href}
              className={`block p-5 rounded-xl border-2 ${c.border} ${c.bg} hover:shadow-sm transition-shadow`}
            >
              <div className="flex items-start justify-between">
                <div className={`text-base font-semibold ${c.text} mb-1`}>
                  {q.label}
                </div>
                {count > 0 && (
                  <span
                    className={`text-sm font-bold px-2 py-0.5 rounded-full ${c.bg} ${c.text} border ${c.border}`}
                  >
                    {count}
                  </span>
                )}
              </div>
              <div className="text-sm text-gray-600">{q.desc}</div>
            </Link>
          );
        })}
      </div>
    </main>
    </>
  );
}
