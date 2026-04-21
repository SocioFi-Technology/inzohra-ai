"use client";

import { useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CitationRecord = {
  code: string;
  section: string;
  canonical_id: string;
  jurisdiction: string;
  effective_date: string;
  title: string | null;
  frozen_text: string;
  amendments: unknown[];
  agency_policies: unknown[];
  retrieval_chain: string[];
  confidence: number;
};

export type Finding = {
  finding_id: string;
  discipline: string;
  rule_id: string | null;
  rule_version: string | null;
  severity: "revise" | "provide" | "clarify" | "reference_only";
  requires_licensed_review: boolean;
  sheet_reference: { sheet_id: string | null; detail: string | null };
  evidence: unknown[];
  citations: CitationRecord[];
  draft_comment_text: string;
  polished_text: string | null;
  confidence: number;
  approval_state: string;
  review_round: number;
};

type Props = {
  findings: Finding[];
  /** The sheet_id currently shown in the viewer (to highlight relevant findings). */
  activeSheetId?: string | null;
  /** Called when user clicks a finding that has an evidence bbox. */
  onHighlightRequest?: (findingId: string, bbox: [number, number, number, number] | null) => void;
  /** Project ID for API calls. */
  projectId?: string;
};

// ---------------------------------------------------------------------------
// Severity styling
// ---------------------------------------------------------------------------

const SEVERITY_STYLES: Record<string, string> = {
  revise:         "bg-red-100 text-red-700 border border-red-200",
  provide:        "bg-amber-100 text-amber-700 border border-amber-200",
  clarify:        "bg-yellow-100 text-yellow-700 border border-yellow-200",
  reference_only: "bg-gray-100 text-gray-500 border border-gray-200",
};

const SEVERITY_ORDER: Finding["severity"][] = [
  "revise", "provide", "clarify", "reference_only",
];

// ---------------------------------------------------------------------------
// Approval state badge styling
// ---------------------------------------------------------------------------

const APPROVAL_STATE_STYLES: Record<string, string> = {
  pending:  "bg-gray-100 text-gray-500 border border-gray-200",
  approved: "bg-green-100 text-green-700 border border-green-200",
  rejected: "bg-red-100 text-red-600 border border-red-200",
  edited:   "bg-blue-100 text-blue-700 border border-blue-200",
};

function SeverityChip({ severity }: { severity: string }) {
  const cls = SEVERITY_STYLES[severity] ?? "bg-gray-100 text-gray-500";
  return (
    <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${cls}`}>
      {severity.replace("_", " ")}
    </span>
  );
}

function ApprovalBadge({ state }: { state: string }) {
  const cls = APPROVAL_STATE_STYLES[state] ?? "bg-gray-100 text-gray-500 border border-gray-200";
  return (
    <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${cls}`}>
      {state}
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const colour = value >= 0.9 ? "bg-green-500" : value >= 0.6 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${colour} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 font-mono">{pct}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Citation Drawer — overlays the right side when a citation is selected
// ---------------------------------------------------------------------------

function CitationDrawer({
  citation,
  onClose,
}: {
  citation: CitationRecord;
  onClose: () => void;
}) {
  return (
    <div className="absolute inset-0 bg-white z-10 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 shrink-0">
        <div>
          <span className="font-semibold text-gray-800 text-sm">
            {citation.code} §{citation.section}
          </span>
          {citation.title && (
            <p className="text-xs text-gray-400 mt-0.5">{citation.title}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-700 text-lg leading-none"
          aria-label="Close citation"
        >
          ×
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {/* Effective date + confidence */}
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <span>{citation.jurisdiction}</span>
          <span>·</span>
          <span>effective {citation.effective_date}</span>
          <span>·</span>
          <ConfidenceBar value={citation.confidence} />
        </div>

        {/* Frozen text */}
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Statutory Text (frozen)
          </p>
          <blockquote className="text-xs text-gray-700 leading-relaxed border-l-2 border-blue-300 pl-3 italic">
            {citation.frozen_text}
          </blockquote>
        </div>

        {/* Amendments */}
        {Array.isArray(citation.amendments) && citation.amendments.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Amendments
            </p>
            {(citation.amendments as Record<string, unknown>[]).map((a, i) => (
              <div key={i} className="text-xs bg-amber-50 border border-amber-200 rounded p-2 mb-1">
                <span className="font-semibold">{String(a.operation)}</span>
                {" · "}
                <span className="text-gray-500">{String(a.effective_date)}</span>
                <p className="mt-1 text-gray-700 italic">{String(a.text)}</p>
              </div>
            ))}
          </div>
        )}

        {/* Retrieval chain */}
        {citation.retrieval_chain.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Retrieval Chain
            </p>
            <ol className="text-xs text-gray-400 space-y-0.5 list-decimal list-inside">
              {citation.retrieval_chain.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FindingCard
// ---------------------------------------------------------------------------

function FindingCard({
  finding,
  isActive,
  isCurrentSheet,
  onSelect,
  onCitationClick,
  projectId,
  onApprovalStateChange,
}: {
  finding: Finding;
  isActive: boolean;
  isCurrentSheet: boolean;
  onSelect: () => void;
  onCitationClick: (cit: CitationRecord) => void;
  projectId?: string;
  onApprovalStateChange?: (findingId: string, newState: string, newPolishedText?: string) => void;
}) {
  const [editMode, setEditMode] = useState(false);
  const [editText, setEditText] = useState(finding.polished_text ?? finding.draft_comment_text);
  const [actionPending, setActionPending] = useState(false);

  const displayText = finding.polished_text ?? finding.draft_comment_text;

  async function postAction(action: "approve" | "reject" | "edit", text?: string) {
    if (!projectId) return;
    setActionPending(true);
    try {
      const body: { action: string; text?: string } = { action };
      if (text !== undefined) body.text = text;
      const res = await fetch(
        `/api/projects/${projectId}/findings/${finding.finding_id}/approve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );
      if (res.ok) {
        const data = (await res.json()) as { state: string };
        onApprovalStateChange?.(
          finding.finding_id,
          data.state,
          action === "edit" ? text : undefined
        );
        if (action === "edit") setEditMode(false);
      }
    } finally {
      setActionPending(false);
    }
  }

  return (
    <div
      onClick={onSelect}
      className={[
        "px-3 py-2.5 cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors",
        isActive ? "bg-blue-50" : "",
        isCurrentSheet ? "border-l-2 border-l-blue-400" : "border-l-2 border-l-transparent",
      ].join(" ")}
    >
      {/* Row 1: severity + rule_id + licensed flag */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <SeverityChip severity={finding.severity} />
        {finding.rule_id && (
          <span className="text-xs font-mono text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
            {finding.rule_id}
          </span>
        )}
        {finding.requires_licensed_review && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 border border-purple-200">
            ⚖ licensed
          </span>
        )}
        <span className="ml-auto">
          <ApprovalBadge state={finding.approval_state ?? "pending"} />
        </span>
      </div>

      {/* Row 2: discipline */}
      <p className="mt-0.5 text-xs text-indigo-600 font-mono">
        {finding.discipline}
      </p>

      {/* Row 3: sheet reference */}
      {finding.sheet_reference?.detail && (
        <p className="mt-0.5 text-xs text-gray-400 truncate">
          {finding.sheet_reference.sheet_id && (
            <span className="font-mono mr-1">{finding.sheet_reference.sheet_id.split(":")[1]}</span>
          )}
          {finding.sheet_reference.detail}
        </p>
      )}

      {/* Row 4: comment text preview */}
      {!isActive && (
        <p className="mt-1 text-xs text-gray-700 line-clamp-3">
          {displayText}
        </p>
      )}

      {/* Expanded view */}
      {isActive && (
        <div className="mt-2 space-y-2" onClick={(e) => e.stopPropagation()}>
          {/* Comment text — polished or draft */}
          {finding.polished_text ? (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-0.5">
                Polished text
              </p>
              <p className="text-xs text-gray-700 leading-relaxed">
                {finding.polished_text}
              </p>
            </div>
          ) : (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-0.5">
                Draft comment
              </p>
              <p className="text-xs text-gray-700 leading-relaxed">
                {finding.draft_comment_text}
              </p>
            </div>
          )}

          {/* Citations */}
          {finding.citations.map((cit, i) => (
            <button
              key={i}
              onClick={(e) => { e.stopPropagation(); onCitationClick(cit); }}
              className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 hover:underline"
            >
              <span className="font-mono">{cit.code} §{cit.section}</span>
              <span className="text-blue-400">→ view text</span>
            </button>
          ))}

          {/* Confidence */}
          <div className="flex items-center justify-between">
            <ConfidenceBar value={finding.confidence} />
          </div>

          {/* Inline edit textarea */}
          {editMode && (
            <div className="space-y-1">
              <textarea
                className="w-full text-xs border border-gray-300 rounded p-1.5 resize-none focus:outline-none focus:ring-1 focus:ring-blue-400"
                rows={5}
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                onClick={(e) => e.stopPropagation()}
              />
              <div className="flex gap-1">
                <button
                  disabled={actionPending}
                  onClick={(e) => { e.stopPropagation(); void postAction("edit", editText); }}
                  className="bg-blue-600 hover:bg-blue-700 text-white text-xs px-2 py-1 rounded disabled:opacity-50"
                >
                  Save
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setEditMode(false); }}
                  className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs px-2 py-1 rounded"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Action buttons */}
          {!editMode && (
            <div className="flex gap-1 pt-0.5">
              <button
                disabled={actionPending}
                onClick={(e) => { e.stopPropagation(); void postAction("approve"); }}
                className="bg-green-600 hover:bg-green-700 text-white text-xs px-2 py-1 rounded disabled:opacity-50"
              >
                ✓ Approve
              </button>
              <button
                disabled={actionPending}
                onClick={(e) => { e.stopPropagation(); void postAction("reject"); }}
                className="bg-red-600 hover:bg-red-700 text-white text-xs px-2 py-1 rounded disabled:opacity-50"
              >
                ✗ Reject
              </button>
              <button
                disabled={actionPending}
                onClick={(e) => { e.stopPropagation(); setEditText(finding.polished_text ?? finding.draft_comment_text); setEditMode(true); }}
                className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs px-2 py-1 rounded disabled:opacity-50"
              >
                ✏ Edit
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FindingsPanel
// ---------------------------------------------------------------------------

export function FindingsPanel({ findings: initialFindings, activeSheetId, onHighlightRequest, projectId }: Props) {
  const [findings, setFindings] = useState<Finding[]>(initialFindings);
  const [activeFindingId, setActiveFindingId] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<CitationRecord | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>("all");
  const [filterDiscipline, setFilterDiscipline] = useState<string>("all");

  if (findings.length === 0) {
    return (
      <aside className="w-72 shrink-0 border-l border-gray-200 bg-white flex flex-col">
        <div className="px-4 py-3 border-b border-gray-200">
          <span className="font-semibold text-gray-700 text-sm">Findings</span>
        </div>
        <div className="flex-1 flex items-center justify-center text-sm text-gray-400">
          No findings yet — run the reviewer.
        </div>
      </aside>
    );
  }

  // Sort: revise first, then provide, then clarify, then reference_only
  const sorted = [...findings].sort((a, b) => {
    const ai = SEVERITY_ORDER.indexOf(a.severity);
    const bi = SEVERITY_ORDER.indexOf(b.severity);
    return ai - bi;
  });

  // Build unique discipline list preserving severity-sort order
  const disciplines = Array.from(new Set(sorted.map((f) => f.discipline)));

  const filtered = sorted
    .filter((f) => filterSeverity === "all" || f.severity === filterSeverity)
    .filter((f) => filterDiscipline === "all" || f.discipline === filterDiscipline);

  // Counts per severity for tab badges
  const counts = findings.reduce<Record<string, number>>((acc, f) => {
    acc[f.severity] = (acc[f.severity] ?? 0) + 1;
    return acc;
  }, {});

  function handleSelect(finding: Finding) {
    const nextId = activeFindingId === finding.finding_id ? null : finding.finding_id;
    setActiveFindingId(nextId);
    if (nextId && onHighlightRequest) {
      const ev = finding.evidence[0] as Record<string, unknown> | undefined;
      const bbox = ev?.bbox as [number, number, number, number] | undefined;
      onHighlightRequest(finding.finding_id, bbox ?? null);
    }
  }

  function handleApprovalStateChange(findingId: string, newState: string, newPolishedText?: string) {
    setFindings((prev) =>
      prev.map((f) => {
        if (f.finding_id !== findingId) return f;
        return {
          ...f,
          approval_state: newState,
          ...(newPolishedText !== undefined ? { polished_text: newPolishedText } : {}),
        };
      })
    );
  }

  return (
    <aside className="w-72 shrink-0 border-l border-gray-200 bg-white flex flex-col relative overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 shrink-0">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-gray-700 text-sm">
            Findings
            <span className="ml-1.5 text-xs font-normal text-gray-400">
              ({findings.length})
            </span>
          </span>
        </div>

        {/* Discipline filter pills */}
        <div className="flex gap-1 mt-2 flex-wrap">
          <button
            onClick={() => setFilterDiscipline("all")}
            className={`text-xs px-1.5 py-0.5 rounded border ${
              filterDiscipline === "all"
                ? "bg-indigo-700 text-white border-indigo-700"
                : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
            }`}
          >
            All
          </button>
          {disciplines.map((disc) => (
            <button
              key={disc}
              onClick={() => setFilterDiscipline(disc)}
              className={`text-xs px-1.5 py-0.5 rounded border ${
                filterDiscipline === disc
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
              }`}
            >
              {disc.replace(/_/g, " ")}
            </button>
          ))}
        </div>

        {/* Severity filter chips */}
        <div className="flex gap-1 mt-1.5 flex-wrap">
          <button
            onClick={() => setFilterSeverity("all")}
            className={`text-xs px-1.5 py-0.5 rounded border ${
              filterSeverity === "all"
                ? "bg-gray-800 text-white border-gray-800"
                : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
            }`}
          >
            All
          </button>
          {SEVERITY_ORDER.filter((s) => counts[s]).map((sev) => (
            <button
              key={sev}
              onClick={() => setFilterSeverity(sev)}
              className={`text-xs px-1.5 py-0.5 rounded ${
                filterSeverity === sev
                  ? SEVERITY_STYLES[sev]
                  : "bg-white text-gray-500 border border-gray-200 hover:bg-gray-50"
              }`}
            >
              {sev.replace("_", " ")} ({counts[sev]})
            </button>
          ))}
        </div>
      </div>

      {/* Finding list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.map((f) => (
          <FindingCard
            key={f.finding_id}
            finding={f}
            isActive={activeFindingId === f.finding_id}
            isCurrentSheet={f.sheet_reference?.sheet_id === activeSheetId}
            onSelect={() => handleSelect(f)}
            onCitationClick={(cit) => setActiveCitation(cit)}
            projectId={projectId}
            onApprovalStateChange={handleApprovalStateChange}
          />
        ))}
      </div>

      {/* Citation drawer — overlays the panel */}
      {activeCitation && (
        <CitationDrawer
          citation={activeCitation}
          onClose={() => setActiveCitation(null)}
        />
      )}
    </aside>
  );
}
