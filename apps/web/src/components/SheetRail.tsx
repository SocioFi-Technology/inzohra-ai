"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

type Sheet = {
  sheet_id: string;
  page: number;
  discipline_letter: string | null;
  sheet_number: string | null;
  canonical_id: string | null;
  title_block: {
    payload: {
      sheet_identifier_raw?: { value: string | null };
      sheet_title?: { value: string | null };
      address_mismatch?: boolean;
    };
  } | null;
};

type Props = { sheets: Sheet[]; projectId: string };

export function SheetRail({ sheets, projectId }: Props) {
  const params = useParams<{ sheetId: string }>();
  const activeSheetId = params?.sheetId
    ? decodeURIComponent(params.sheetId)
    : null;

  // Group by discipline letter
  const grouped: Record<string, Sheet[]> = {};
  for (const s of sheets) {
    const disc = s.discipline_letter ?? "—";
    (grouped[disc] ??= []).push(s);
  }

  return (
    <nav className="w-56 shrink-0 border-r border-gray-200 bg-gray-50 overflow-y-auto">
      <div className="px-3 py-3 border-b border-gray-200">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Sheets ({sheets.length})
        </p>
      </div>
      {Object.entries(grouped)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([disc, discSheets]) => (
          <div key={disc}>
            <p className="px-3 pt-2 pb-1 text-xs font-bold text-gray-400 uppercase tracking-widest">
              {disc}
            </p>
            {discSheets.map((s) => {
              const tbPayload = s.title_block?.payload;
              const label =
                tbPayload?.sheet_identifier_raw?.value ??
                `p${String(s.page).padStart(3, "0")}`;
              const title = tbPayload?.sheet_title?.value ?? "";
              const mismatch = tbPayload?.address_mismatch ?? false;
              const isActive = s.sheet_id === activeSheetId;

              return (
                <Link
                  key={s.sheet_id}
                  href={`/projects/${projectId}/sheets/${encodeURIComponent(s.sheet_id)}`}
                  className={[
                    "flex items-start gap-2 px-3 py-2 text-sm leading-tight transition-colors",
                    isActive
                      ? "bg-blue-100 text-blue-800 font-semibold"
                      : "text-gray-700 hover:bg-gray-100",
                  ].join(" ")}
                >
                  <span className="shrink-0 font-mono text-xs mt-0.5">
                    {label}
                  </span>
                  <span className="truncate text-gray-500 text-xs">{title}</span>
                  {mismatch && (
                    <span
                      title="Title-block address mismatch detected"
                      className="shrink-0 text-amber-500"
                    >
                      ⚠
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
    </nav>
  );
}
