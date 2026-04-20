import { Pool } from "pg";
import Link from "next/link";

const db = new Pool({ connectionString: process.env.DATABASE_URL! });

async function fetchCounts(): Promise<{ findings: number; edits: number }> {
  const [findings, edits] = await Promise.allSettled([
    db.query("SELECT COUNT(*)::int AS n FROM findings"),
    db.query(
      "SELECT COUNT(*)::int AS n FROM reviewer_edits WHERE edit_ratio >= 0.25"
    ),
  ]);
  return {
    findings:
      findings.status === "fulfilled"
        ? (findings.value.rows[0]?.n ?? 0)
        : 0,
    edits:
      edits.status === "fulfilled" ? (edits.value.rows[0]?.n ?? 0) : 0,
  };
}

const QUEUES = [
  {
    href: "/triage/misses",
    label: "Misses",
    desc: "Authority comments the AI did not raise",
    color: "red",
  },
  {
    href: "/triage/false-positives",
    label: "False Positives",
    desc: "AI findings the authority did not raise",
    color: "orange",
  },
  {
    href: "/triage/edits",
    label: "High-Edit Findings",
    desc: "Drafter output with large reviewer edits \u2014 few-shot sources",
    color: "purple",
  },
  {
    href: "/triage/overrides",
    label: "Measurement Overrides",
    desc: "Manual measurement corrections grouped by type + PDF quality",
    color: "gray",
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
  // counts fetched but not currently displayed on cards — available for future use
  await fetchCounts();

  return (
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
          return (
            <Link
              key={q.href}
              href={q.href}
              className={`block p-5 rounded-xl border-2 ${c.border} ${c.bg} hover:shadow-sm transition-shadow`}
            >
              <div className={`text-base font-semibold ${c.text} mb-1`}>
                {q.label}
              </div>
              <div className="text-sm text-gray-600">{q.desc}</div>
            </Link>
          );
        })}
      </div>
    </main>
  );
}
