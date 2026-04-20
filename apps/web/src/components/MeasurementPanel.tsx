"use client";

import { useState, useEffect, useCallback } from "react";

type TraceEntry = {
  layer: string;
  confidence?: number;
  [key: string]: unknown;
};

type Measurement = {
  measurement_id: string;
  type: string;
  value: number;
  unit: string;
  confidence: number;
  trace: {
    sublayers?: TraceEntry[];
    formula?: string;
    composed_confidence?: number;
  };
  override_history: Array<{
    overridden_at: string;
    previous_value: number;
    override_value: number;
    rationale: string;
  }>;
  bbox: number[] | null;
  entity_id: string | null;
  tag: string | null;
};

type Props = {
  projectId: string;
  sheetId: string;
  onMeasurementClick?: (bbox: number[]) => void;
};

function confidenceBadgeClass(confidence: number): string {
  if (confidence >= 0.85) return "bg-green-100 text-green-800";
  if (confidence >= 0.7) return "bg-yellow-100 text-yellow-800";
  return "bg-red-100 text-red-800";
}

function groupByType(measurements: Measurement[]): Map<string, Measurement[]> {
  const groups = new Map<string, Measurement[]>();
  for (const m of measurements) {
    const existing = groups.get(m.type) ?? [];
    existing.push(m);
    groups.set(m.type, existing);
  }
  return groups;
}

export function MeasurementPanel({ projectId, sheetId, onMeasurementClick }: Props) {
  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeMeasId, setActiveMeasId] = useState<string | null>(null);
  const [overrideState, setOverrideState] = useState<{
    measId: string;
    value: string;
    rationale: string;
  } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMeasurements = useCallback(() => {
    setLoading(true);
    fetch(`/api/projects/${projectId}/sheets/${sheetId}/measurements`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Measurement[]>;
      })
      .then((data) => {
        setMeasurements(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load measurements");
        setLoading(false);
      });
  }, [projectId, sheetId]);

  useEffect(() => {
    fetchMeasurements();
  }, [fetchMeasurements]);

  async function handleOverride(measId: string, overrideValueStr: string, rationale: string) {
    const overrideValue = parseFloat(overrideValueStr);
    if (isNaN(overrideValue)) {
      setError("Override value must be a number.");
      return;
    }
    if (!rationale.trim()) {
      setError("Rationale is required.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch(
        `/api/projects/${projectId}/measurements/${measId}/override`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ override_value: overrideValue, rationale }),
        }
      );
      if (!res.ok) {
        const body = (await res.json()) as { error?: string };
        throw new Error(body.error ?? `HTTP ${res.status}`);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Override failed");
      setSubmitting(false);
      return;
    }
    setSubmitting(false);
    setOverrideState(null);
    fetchMeasurements();
  }

  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500">Loading measurements…</div>
    );
  }

  if (measurements.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-400">
        No measurements for this sheet.
      </div>
    );
  }

  const groups = groupByType(measurements);

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="text-base font-semibold text-gray-800">Measurements</h2>

      {error && (
        <div className="rounded bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {Array.from(groups.entries()).map(([type, items]) => (
        <section key={type}>
          <h3 className="text-xs font-medium uppercase tracking-wide text-gray-500 mb-1">
            {type.replace(/_/g, " ")}
          </h3>
          <div className="flex flex-col gap-1">
            {items.map((m) => {
              const isActive = activeMeasId === m.measurement_id;
              const isOverriding = overrideState?.measId === m.measurement_id;
              const wasOverridden = m.override_history.length > 0;

              return (
                <div
                  key={m.measurement_id}
                  className="rounded border border-gray-200 bg-white shadow-sm"
                >
                  {/* Row */}
                  <div
                    className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50"
                    onClick={() => {
                      setActiveMeasId(isActive ? null : m.measurement_id);
                      if (m.bbox && onMeasurementClick) {
                        onMeasurementClick(m.bbox);
                      }
                    }}
                  >
                    {/* Tag */}
                    {m.tag && (
                      <span className="text-xs font-mono bg-gray-100 text-gray-600 rounded px-1">
                        {m.tag}
                      </span>
                    )}

                    {/* Value + unit */}
                    <span className="flex-1 text-sm text-gray-800">
                      <span className="font-medium">{m.value}</span>{" "}
                      <span className="text-gray-500">{m.unit}</span>
                    </span>

                    {/* Confidence badge */}
                    <span
                      className={`text-xs rounded px-1.5 py-0.5 font-medium ${confidenceBadgeClass(m.confidence)}`}
                    >
                      {Math.round(m.confidence * 100)}%
                    </span>

                    {/* Overridden badge */}
                    {wasOverridden && (
                      <span className="text-xs bg-purple-100 text-purple-700 rounded px-1.5 py-0.5 font-medium">
                        Overridden
                      </span>
                    )}

                    {/* Expand chevron */}
                    <span className="text-gray-400 text-xs">
                      {isActive ? "▲" : "▼"}
                    </span>
                  </div>

                  {/* Expanded: trace + override */}
                  {isActive && (
                    <div className="border-t border-gray-100 px-3 py-3 flex flex-col gap-3">
                      {/* Derivation trace */}
                      {m.trace.sublayers && m.trace.sublayers.length > 0 && (
                        <div>
                          <p className="text-xs font-medium text-gray-500 mb-1">
                            Derivation trace
                          </p>
                          <table className="w-full text-xs border-collapse">
                            <thead>
                              <tr className="bg-gray-50">
                                <th className="text-left px-2 py-1 font-medium text-gray-600 border border-gray-200">
                                  Layer
                                </th>
                                <th className="text-right px-2 py-1 font-medium text-gray-600 border border-gray-200">
                                  Confidence
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {m.trace.sublayers.map((sl, i) => (
                                <tr key={i} className="even:bg-gray-50">
                                  <td className="px-2 py-1 border border-gray-200 text-gray-700">
                                    {sl.layer}
                                  </td>
                                  <td className="px-2 py-1 border border-gray-200 text-right text-gray-700">
                                    {sl.confidence !== undefined
                                      ? `${Math.round(sl.confidence * 100)}%`
                                      : "—"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {m.trace.formula && (
                            <p className="mt-1 text-xs text-gray-400 font-mono">
                              {m.trace.formula}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Override history */}
                      {wasOverridden && (
                        <div>
                          <p className="text-xs font-medium text-gray-500 mb-1">
                            Override history
                          </p>
                          <div className="flex flex-col gap-1">
                            {m.override_history.map((h, i) => (
                              <div
                                key={i}
                                className="text-xs text-gray-600 bg-purple-50 rounded px-2 py-1"
                              >
                                <span className="font-medium">
                                  {h.previous_value} → {h.override_value}{" "}
                                  {m.unit}
                                </span>{" "}
                                — {h.rationale}
                                <span className="text-gray-400 ml-1">
                                  ({new Date(h.overridden_at).toLocaleString()})
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Override form */}
                      {isOverriding ? (
                        <div className="flex flex-col gap-2">
                          <p className="text-xs font-medium text-gray-700">
                            Override value
                          </p>
                          <input
                            type="number"
                            step="any"
                            value={overrideState.value}
                            onChange={(e) =>
                              setOverrideState((s) =>
                                s ? { ...s, value: e.target.value } : null
                              )
                            }
                            placeholder={`New value (${m.unit})`}
                            className="border border-gray-300 rounded px-2 py-1 text-sm w-full focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                          <textarea
                            value={overrideState.rationale}
                            onChange={(e) =>
                              setOverrideState((s) =>
                                s ? { ...s, rationale: e.target.value } : null
                              )
                            }
                            placeholder="Rationale (required)"
                            rows={2}
                            className="border border-gray-300 rounded px-2 py-1 text-sm w-full resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                          <div className="flex gap-2">
                            <button
                              disabled={submitting}
                              onClick={() =>
                                handleOverride(
                                  m.measurement_id,
                                  overrideState.value,
                                  overrideState.rationale
                                )
                              }
                              className="flex-1 bg-blue-600 text-white text-xs rounded px-3 py-1.5 disabled:opacity-50 hover:bg-blue-700"
                            >
                              {submitting ? "Saving…" : "Save override"}
                            </button>
                            <button
                              disabled={submitting}
                              onClick={() => setOverrideState(null)}
                              className="flex-1 border border-gray-300 text-gray-600 text-xs rounded px-3 py-1.5 hover:bg-gray-50"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          onClick={() =>
                            setOverrideState({
                              measId: m.measurement_id,
                              value: String(m.value),
                              rationale: "",
                            })
                          }
                          className="self-start text-xs border border-gray-300 text-gray-600 rounded px-3 py-1 hover:bg-gray-50"
                        >
                          Override
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
