"use client";

import { useState } from "react";

type BBoxField = {
  value: string | null;
  bbox: [number, number, number, number];
  confidence: number;
  source_track: "text" | "vision" | "merged";
  text_raw?: string | null;
  vision_raw?: string | null;
};

type TitleBlockPayload = {
  project_name?: BBoxField;
  project_address?: BBoxField;
  apn?: BBoxField;
  permit_number?: BBoxField;
  sheet_identifier_raw?: BBoxField;
  sheet_title?: BBoxField;
  designer_of_record?: BBoxField;
  stamp_present?: boolean;
  date_issued?: BBoxField;
  scale_declared?: BBoxField;
  north_arrow_bbox?: [number, number, number, number] | null;
  address_mismatch?: boolean;
};

type Entity = {
  entity_id: string;
  type: string;
  payload: TitleBlockPayload;
  bbox: number[];
  confidence: number;
  source_track: string;
};

type Props = {
  entity: Entity | null;
  onShowSource: (fieldId: string, bbox: [number, number, number, number]) => void;
  activeFieldId?: string | null;
};

const FIELD_LABELS: [keyof TitleBlockPayload, string][] = [
  ["project_address", "Address"],
  ["project_name", "Project Name"],
  ["permit_number", "Permit No."],
  ["apn", "APN"],
  ["sheet_identifier_raw", "Sheet ID"],
  ["sheet_title", "Sheet Title"],
  ["designer_of_record", "Designer"],
  ["date_issued", "Date Issued"],
  ["scale_declared", "Scale"],
];

function confidenceBadge(conf: number) {
  const pct = Math.round(conf * 100);
  const colour =
    conf >= 0.9
      ? "bg-green-100 text-green-700"
      : conf >= 0.6
      ? "bg-yellow-100 text-yellow-700"
      : "bg-red-100 text-red-700";
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${colour}`}>
      {pct}%
    </span>
  );
}

function trackBadge(track: string) {
  const colour =
    track === "merged"
      ? "bg-blue-100 text-blue-600"
      : track === "vision"
      ? "bg-purple-100 text-purple-600"
      : "bg-gray-100 text-gray-500";
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${colour}`}>{track}</span>
  );
}

export function TitleBlockPanel({ entity, onShowSource, activeFieldId }: Props) {
  const [expanded, setExpanded] = useState(true);

  if (!entity) {
    return (
      <aside className="w-72 shrink-0 border-l border-gray-200 bg-white p-4 text-sm text-gray-400">
        No title-block entity found for this sheet.
      </aside>
    );
  }

  const payload = entity.payload;
  const mismatch = payload.address_mismatch;

  return (
    <aside className="w-72 shrink-0 border-l border-gray-200 bg-white overflow-y-auto text-sm">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-gray-200 cursor-pointer select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="font-semibold text-gray-700">Title Block</span>
        <span className="text-gray-400">{expanded ? "▲" : "▼"}</span>
      </div>

      {mismatch && (
        <div className="mx-3 mt-2 px-3 py-2 bg-amber-50 border border-amber-300 rounded text-amber-700 text-xs">
          ⚠ Address mismatch detected on this sheet.
        </div>
      )}

      {expanded && (
        <div className="divide-y divide-gray-100">
          {FIELD_LABELS.map(([key, label]) => {
            const field = payload[key] as BBoxField | undefined;
            if (!field) return null;
            const fieldId = `${entity.entity_id}:${key}`;
            const isActive = fieldId === activeFieldId;
            const hasBbox =
              field.bbox &&
              (field.bbox[2] - field.bbox[0] > 1 || field.bbox[3] - field.bbox[1] > 1);

            return (
              <div
                key={key}
                className={[
                  "px-4 py-2.5",
                  isActive ? "bg-blue-50" : "",
                ].join(" ")}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                    {label}
                  </span>
                  <div className="flex items-center gap-1">
                    {confidenceBadge(field.confidence)}
                    {trackBadge(field.source_track)}
                  </div>
                </div>

                <div className="flex items-start justify-between gap-2">
                  <span
                    className={[
                      "font-medium break-words",
                      field.value ? "text-gray-900" : "text-gray-300 italic",
                    ].join(" ")}
                  >
                    {field.value ?? "—"}
                  </span>

                  {hasBbox && (
                    <button
                      onClick={() =>
                        onShowSource(
                          fieldId,
                          field.bbox as [number, number, number, number]
                        )
                      }
                      className="shrink-0 text-xs text-blue-500 hover:text-blue-700 hover:underline"
                    >
                      locate
                    </button>
                  )}
                </div>

                {/* Disagreement detail */}
                {field.source_track === "merged" &&
                  field.text_raw &&
                  field.vision_raw &&
                  field.text_raw !== field.vision_raw &&
                  field.confidence < 0.6 && (
                    <div className="mt-1 text-xs text-gray-400 space-y-0.5">
                      <div>
                        <span className="font-medium">Text:</span> {field.text_raw}
                      </div>
                      <div>
                        <span className="font-medium">Vision:</span> {field.vision_raw}
                      </div>
                    </div>
                  )}
              </div>
            );
          })}

          {/* Stamp */}
          <div className="px-4 py-2.5">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              Stamp
            </span>
            <p className="mt-0.5 font-medium text-gray-900">
              {payload.stamp_present ? "Present" : "Not detected"}
            </p>
          </div>

          {/* Overall entity confidence */}
          <div className="px-4 py-2.5 bg-gray-50">
            <span className="text-xs text-gray-400">
              Entity confidence: {Math.round(entity.confidence * 100)}% ·{" "}
              {entity.source_track}
            </span>
          </div>
        </div>
      )}
    </aside>
  );
}
