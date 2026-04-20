"use client";

import { useState } from "react";
import { SheetRail } from "@/components/SheetRail";
import { SheetViewer } from "@/components/SheetViewer";
import { TitleBlockPanel } from "@/components/TitleBlockPanel";
import { FindingsPanel, type Finding } from "@/components/FindingsPanel";

type Props = {
  sheet: Record<string, unknown>;
  allSheets: Record<string, unknown>[];
  entities: Record<string, unknown>[];
  projectId: string;
  findings: Finding[];
};

export function SheetViewerWrapper({
  sheet,
  allSheets,
  entities,
  projectId,
  findings,
}: Props) {
  const [activeFieldId, setActiveFieldId] = useState<string | null>(null);
  const [highlights, setHighlights] = useState<
    { id: string; bbox: [number, number, number, number]; label: string; color?: string }[]
  >([]);
  const [rightTab, setRightTab] = useState<"title_block" | "findings">("title_block");

  const titleBlockEntity =
    (entities.find((e) => e.type === "title_block") as Record<string, unknown>) ?? null;

  function handleShowSource(
    fieldId: string,
    bbox: [number, number, number, number]
  ) {
    setActiveFieldId(fieldId);
    setHighlights([{ id: fieldId, bbox, label: fieldId.split(":")[1] ?? fieldId }]);
  }

  function handleHighlightClick(id: string) {
    setActiveFieldId(id);
  }

  // Shape allSheets for SheetRail
  const railSheets = allSheets.map((s) => ({
    sheet_id: s.sheet_id as string,
    page: s.page as number,
    discipline_letter: s.discipline_letter as string | null,
    sheet_number: s.sheet_number as string | null,
    canonical_id: s.canonical_id as string | null,
    title_block: s.title_block_payload
      ? { payload: s.title_block_payload as Record<string, unknown> }
      : null,
  }));

  // Count findings on the current sheet for badge
  const sheetId = sheet.sheet_id as string;
  const sheetFindingCount = findings.filter(
    (f) => f.sheet_reference?.sheet_id === sheetId
  ).length;

  return (
    <div className="flex h-screen overflow-hidden bg-white">
      {/* Left rail */}
      <SheetRail sheets={railSheets as never} projectId={projectId} />

      {/* Center — PDF viewer */}
      <main className="flex-1 overflow-hidden flex flex-col">
        {/* Top bar */}
        <div className="h-10 border-b border-gray-200 flex items-center px-4 gap-3 shrink-0">
          <span className="text-sm font-semibold text-gray-700">
            {(titleBlockEntity?.payload as Record<string, unknown>)?.sheet_identifier_raw
              ? (
                  (titleBlockEntity?.payload as Record<string, unknown>)
                    ?.sheet_identifier_raw as Record<string, unknown>
                )?.value as string
              : `Page ${sheet.page as number}`}
          </span>
          <span className="text-sm text-gray-400">
            {(titleBlockEntity?.payload as Record<string, unknown>)?.sheet_title
              ? (
                  (titleBlockEntity?.payload as Record<string, unknown>)
                    ?.sheet_title as Record<string, unknown>
                )?.value as string
              : ""}
          </span>
        </div>

        <div className="flex-1 overflow-hidden">
          <SheetViewer
            documentS3Uri={sheet.document_s3_uri as string}
            pageNumber={sheet.page as number}
            pageWidthPts={(sheet.page_width_pts as number) ?? 612}
            pageHeightPts={(sheet.page_height_pts as number) ?? 792}
            highlights={highlights}
            onHighlightClick={handleHighlightClick}
            activeHighlightId={activeFieldId}
          />
        </div>
      </main>

      {/* Right panel — tabbed */}
      <div className="w-72 shrink-0 border-l border-gray-200 flex flex-col bg-white overflow-hidden">
        {/* Tab header */}
        <div className="flex border-b border-gray-200 shrink-0">
          <button
            onClick={() => setRightTab("title_block")}
            className={[
              "flex-1 py-2 text-xs font-semibold transition-colors",
              rightTab === "title_block"
                ? "border-b-2 border-blue-500 text-blue-600"
                : "text-gray-500 hover:text-gray-700",
            ].join(" ")}
          >
            Title Block
          </button>
          <button
            onClick={() => setRightTab("findings")}
            className={[
              "flex-1 py-2 text-xs font-semibold transition-colors flex items-center justify-center gap-1",
              rightTab === "findings"
                ? "border-b-2 border-blue-500 text-blue-600"
                : "text-gray-500 hover:text-gray-700",
            ].join(" ")}
          >
            Findings
            {findings.length > 0 && (
              <span
                className={`text-xs px-1.5 py-0.5 rounded-full font-mono ${
                  sheetFindingCount > 0
                    ? "bg-red-100 text-red-600"
                    : "bg-gray-100 text-gray-400"
                }`}
              >
                {findings.length}
              </span>
            )}
          </button>
        </div>

        {/* Tab content — no border since the tab strip already provides it */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {rightTab === "title_block" ? (
            <TitleBlockPanel
              entity={
                titleBlockEntity
                  ? {
                      entity_id: titleBlockEntity.entity_id as string,
                      type: titleBlockEntity.type as string,
                      payload: titleBlockEntity.payload as never,
                      bbox: titleBlockEntity.bbox as number[],
                      confidence: titleBlockEntity.confidence as number,
                      source_track: titleBlockEntity.source_track as string,
                    }
                  : null
              }
              onShowSource={handleShowSource}
              activeFieldId={activeFieldId}
              embedded
            />
          ) : (
            <FindingsPanel
              findings={findings}
              activeSheetId={sheetId}
            />
          )}
        </div>
      </div>
    </div>
  );
}
