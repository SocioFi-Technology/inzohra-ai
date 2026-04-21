import Link from "next/link";
import { query, queryOne } from "@/lib/db";
import { notFound } from "next/navigation";

type SheetCard = {
  sheet_id: string;
  page: number;
  canonical_id: string | null;
  sheet_number: string | null;
  discipline_letter: string | null;
  thumb_uri: string | null;
  finding_count: number;
};

const DISCIPLINE_COLORS: Record<string, string> = {
  A: "bg-blue-100 text-blue-700",
  S: "bg-orange-100 text-orange-700",
  M: "bg-green-100 text-green-700",
  E: "bg-yellow-100 text-yellow-700",
  P: "bg-cyan-100 text-cyan-700",
  G: "bg-gray-100 text-gray-700",
  C: "bg-purple-100 text-purple-700",
};

export default async function SheetsGalleryPage({ params }: { params: { id: string } }) {
  const project = await queryOne(
    `SELECT address, permit_number, jurisdiction FROM projects WHERE project_id = $1`,
    [params.id],
  ) as Record<string, string> | null;

  if (!project) notFound();

  const sheets = await query<SheetCard>(`
    SELECT
      s.sheet_id,
      s.page,
      s.canonical_id,
      s.sheet_number,
      s.discipline_letter,
      s.thumb_uri,
      COUNT(DISTINCT f.finding_id)::int AS finding_count
    FROM sheets s
    JOIN documents d ON d.document_id = s.document_id
    JOIN submittals sub ON sub.submittal_id = d.submittal_id
    LEFT JOIN findings f ON f.project_id = sub.project_id
      AND f.sheet_reference->>'sheet_id' = s.sheet_id
    WHERE sub.project_id = $1
    GROUP BY s.sheet_id, s.page, s.canonical_id, s.sheet_number, s.discipline_letter, s.thumb_uri
    ORDER BY s.page
  `, [params.id]).catch(() => [] as SheetCard[]);

  if (sheets.length === 0) {
    return (
      <main className="p-8 text-gray-500">
        <Link href="/" className="text-sm text-blue-600 hover:underline">← Home</Link>
        <p className="mt-4">No sheets yet — run the ingestion pipeline first.</p>
      </main>
    );
  }

  // Collect unique discipline letters for the filter bar
  const disciplines = [...new Set(sheets.map((s) => s.discipline_letter).filter(Boolean))] as string[];

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-3 sticky top-0 z-10 flex items-center gap-4">
        <Link href="/" className="text-sm text-blue-600 hover:underline">← Home</Link>
        <div>
          <span className="font-semibold text-gray-900">{project.address}</span>
          <span className="text-sm text-gray-400 ml-2">Permit {project.permit_number}</span>
        </div>
        <span className="ml-auto text-sm text-gray-400">{sheets.length} sheets</span>
      </div>

      {/* Discipline filter pills (server-rendered; client-side filtering would need "use client") */}
      <div className="bg-white border-b border-gray-100 px-6 py-2 flex items-center gap-2 overflow-x-auto">
        <span className="text-xs text-gray-400 shrink-0">Filter:</span>
        <Link
          href={`/projects/${params.id}/sheets`}
          className="shrink-0 px-2.5 py-1 rounded text-xs font-medium bg-indigo-600 text-white"
        >
          All ({sheets.length})
        </Link>
        {disciplines.map((d) => {
          const count = sheets.filter((s) => s.discipline_letter === d).length;
          const cls = DISCIPLINE_COLORS[d] ?? "bg-gray-100 text-gray-600";
          return (
            <span key={d} className={`shrink-0 px-2.5 py-1 rounded text-xs font-medium ${cls}`}>
              {d} ({count})
            </span>
          );
        })}
      </div>

      {/* Thumbnail grid */}
      <div className="p-6 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        {sheets.map((sheet) => {
          const label = sheet.canonical_id ?? sheet.sheet_number ?? `p${sheet.page}`;
          const thumbUrl = sheet.thumb_uri
            ? `/api/assets/${sheet.thumb_uri.replace(/^s3:\/\/[^/]+\//, "")}`
            : null;
          const discColor = DISCIPLINE_COLORS[sheet.discipline_letter ?? ""] ?? "bg-gray-100 text-gray-600";
          return (
            <Link
              key={sheet.sheet_id}
              href={`/projects/${params.id}/sheets/${encodeURIComponent(sheet.sheet_id)}`}
              className="group bg-white border border-gray-200 rounded-lg overflow-hidden hover:border-indigo-400 hover:shadow-sm transition-all"
            >
              {/* Thumbnail */}
              <div className="aspect-[3/4] bg-gray-100 relative overflow-hidden">
                {thumbUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={thumbUrl}
                    alt={label}
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-300 text-3xl">
                    📄
                  </div>
                )}
                {/* Finding count badge */}
                {sheet.finding_count > 0 && (
                  <span className="absolute top-1.5 right-1.5 bg-red-500 text-white text-xs font-bold w-5 h-5 rounded-full flex items-center justify-center shadow">
                    {sheet.finding_count > 9 ? "9+" : sheet.finding_count}
                  </span>
                )}
              </div>
              {/* Label row */}
              <div className="px-2 py-1.5 flex items-center gap-1.5">
                {sheet.discipline_letter && (
                  <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${discColor}`}>
                    {sheet.discipline_letter}
                  </span>
                )}
                <span className="text-xs font-medium text-gray-700 truncate group-hover:text-indigo-700">
                  {label}
                </span>
                <span className="text-xs text-gray-300 ml-auto">p{sheet.page}</span>
              </div>
            </Link>
          );
        })}
      </div>
    </main>
  );
}
