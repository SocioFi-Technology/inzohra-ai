"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface ParsedQuery {
  itemId: string;
  description: string;
  targetEntityClass: string;
  codeRef: string;
  thresholdValue: number | null;
  thresholdUnit: string | null;
}

interface ParseResponse {
  projectId: string;
  queries: ParsedQuery[];
}

interface AnswerResponse {
  reportId: string;
  status: string;
}

type Step = 1 | 2 | 3 | 4;

interface ProjectForm {
  address: string;
  permitNumber: string;
  jurisdiction: string;
  occupancyClass: string;
}

interface ConfirmRow extends ParsedQuery {
  confirmed: boolean;
}

const SAMPLE_CHECKLIST = `Verify egress window NCO >= 5.7 sqft
Confirm all exit doors are minimum 32 inches clear width
Check that bedroom ceiling height is at least 7 feet
Verify egress travel distance does not exceed 200 feet
Confirm accessible route width is minimum 36 inches
Verify bathroom door is minimum 32 inches clear width`;

export default function UploadPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [projectForm, setProjectForm] = useState<ProjectForm>({
    address: "",
    permitNumber: "",
    jurisdiction: "santa_rosa",
    occupancyClass: "R-3",
  });

  const [checklistText, setChecklistText] = useState("");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [confirmRows, setConfirmRows] = useState<ConfirmRow[]>([]);

  // Step 1 → Step 2: validate project fields
  function goToStep2() {
    if (!projectForm.address.trim() || !projectForm.permitNumber.trim()) {
      setError("Address and permit number are required.");
      return;
    }
    setError(null);
    setStep(2);
  }

  // Step 2 → Step 3: parse checklist
  async function parseChecklist() {
    if (!checklistText.trim()) {
      setError("Paste or upload a checklist before continuing.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/designer/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: projectForm.address,
          permitNumber: projectForm.permitNumber,
          jurisdiction: projectForm.jurisdiction,
          occupancyClass: projectForm.occupancyClass,
          checklistText,
        }),
      });
      if (!res.ok) {
        const body = (await res.json()) as { error?: string };
        throw new Error(body.error ?? "Parse failed");
      }
      const data = (await res.json()) as ParseResponse;
      setProjectId(data.projectId);
      setConfirmRows(data.queries.map((q) => ({ ...q, confirmed: true })));
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  // Step 3 → Step 4: run analysis
  async function runAnalysis() {
    if (!projectId) return;
    const confirmedQueryIds = confirmRows
      .filter((r) => r.confirmed)
      .map((r) => r.itemId);
    if (confirmedQueryIds.length === 0) {
      setError("Select at least one query to confirm.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/designer/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId, confirmedQueryIds }),
      });
      if (!res.ok) {
        const body = (await res.json()) as { error?: string };
        throw new Error(body.error ?? "Answer request failed");
      }
      const data = (await res.json()) as AnswerResponse;
      setStep(4);
      // Redirect after a short delay
      setTimeout(() => {
        router.push(`/designer/${data.reportId}`);
      }, 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setLoading(false);
    }
  }

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setChecklistText((ev.target?.result as string) ?? "");
    };
    reader.readAsText(file);
  }

  function toggleRow(itemId: string) {
    setConfirmRows((rows) =>
      rows.map((r) => (r.itemId === itemId ? { ...r, confirmed: !r.confirmed } : r))
    );
  }

  return (
    <div className="max-w-2xl">
      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-8">
        {([1, 2, 3, 4] as Step[]).map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${
                step === s
                  ? "bg-blue-600 text-white"
                  : step > s
                  ? "bg-green-500 text-white"
                  : "bg-gray-200 text-gray-500"
              }`}
            >
              {s}
            </div>
            {s < 4 && <div className="w-8 h-px bg-gray-300" />}
          </div>
        ))}
        <span className="ml-2 text-sm text-gray-500">
          {step === 1 && "Project details"}
          {step === 2 && "Upload checklist"}
          {step === 3 && "Confirm queries"}
          {step === 4 && "Processing"}
        </span>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Step 1 — Project */}
      {step === 1 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-900">Step 1 — Project details</h2>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Project address
            </label>
            <input
              type="text"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="2008 Dennis Ln, Santa Rosa, CA"
              value={projectForm.address}
              onChange={(e) =>
                setProjectForm((f) => ({ ...f, address: e.target.value }))
              }
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Permit number
            </label>
            <input
              type="text"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="B25-2734"
              value={projectForm.permitNumber}
              onChange={(e) =>
                setProjectForm((f) => ({ ...f, permitNumber: e.target.value }))
              }
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Jurisdiction
            </label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={projectForm.jurisdiction}
              onChange={(e) =>
                setProjectForm((f) => ({ ...f, jurisdiction: e.target.value }))
              }
            >
              <option value="santa_rosa">Santa Rosa</option>
              <option value="oakland">Oakland</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Occupancy class
            </label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={projectForm.occupancyClass}
              onChange={(e) =>
                setProjectForm((f) => ({ ...f, occupancyClass: e.target.value }))
              }
            >
              <option value="R-3">R-3</option>
              <option value="R-2">R-2</option>
              <option value="A-2">A-2</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div className="pt-2">
            <button
              onClick={goToStep2}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {/* Step 2 — Checklist */}
      {step === 2 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-900">Step 2 — Checklist</h2>
          <p className="text-sm text-gray-500">
            Paste checklist items or upload a <code>.json</code>, <code>.txt</code>, or{" "}
            <code>.pdf</code> file. One item per line.
          </p>

          <div className="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2 text-xs text-gray-500 font-mono">
            <p className="font-semibold text-gray-600 mb-1">Sample:</p>
            <p>Verify egress window NCO &ge; 5.7 sqft</p>
          </div>

          <textarea
            className="w-full h-44 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder={SAMPLE_CHECKLIST}
            value={checklistText}
            onChange={(e) => setChecklistText(e.target.value)}
          />

          <div className="flex items-center gap-3">
            <label className="cursor-pointer text-sm text-blue-600 hover:underline">
              Upload file
              <input
                type="file"
                accept=".json,.txt,.pdf"
                className="hidden"
                onChange={handleFileUpload}
              />
            </label>
            {checklistText && (
              <span className="text-xs text-gray-400">
                {checklistText.split("\n").filter((l) => l.trim()).length} lines loaded
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={() => setStep(1)}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Back
            </button>
            <button
              onClick={parseChecklist}
              disabled={loading}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {loading ? "Parsing..." : "Parse checklist"}
            </button>
          </div>
        </div>
      )}

      {/* Step 3 — Confirm queries */}
      {step === 3 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-900">Step 3 — Confirm queries</h2>
          <p className="text-sm text-gray-500">
            Review the parsed queries. Uncheck any you want to skip.
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-600 w-8"></th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Item</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Description</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Entity</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Code ref</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Threshold</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {confirmRows.map((row) => (
                  <tr
                    key={row.itemId}
                    className={`${row.confirmed ? "" : "opacity-50"} cursor-pointer hover:bg-gray-50`}
                    onClick={() => toggleRow(row.itemId)}
                  >
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={row.confirmed}
                        onChange={() => toggleRow(row.itemId)}
                        onClick={(e) => e.stopPropagation()}
                        className="rounded"
                      />
                    </td>
                    <td className="px-3 py-2 font-mono text-gray-700">{row.itemId}</td>
                    <td className="px-3 py-2 text-gray-600 max-w-xs truncate">
                      {row.description}
                    </td>
                    <td className="px-3 py-2">
                      <span className="bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded text-xs">
                        {row.targetEntityClass}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-gray-500">{row.codeRef}</td>
                    <td className="px-3 py-2 text-gray-600">
                      {row.thresholdValue != null
                        ? `${row.thresholdValue} ${row.thresholdUnit ?? ""}`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {confirmRows.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-4">
              No queries were parsed. Check your checklist format.
            </p>
          )}

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={() => setStep(2)}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Back
            </button>
            <button
              onClick={runAnalysis}
              disabled={loading || confirmRows.filter((r) => r.confirmed).length === 0}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {loading
                ? "Submitting..."
                : `Run analysis (${confirmRows.filter((r) => r.confirmed).length} queries)`}
            </button>
          </div>
        </div>
      )}

      {/* Step 4 — Processing */}
      {step === 4 && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center space-y-4">
          <div className="flex justify-center">
            <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
          <h2 className="text-base font-semibold text-gray-900">Analysis in progress</h2>
          <p className="text-sm text-gray-500">
            Queuing measurement lookups and code retrievals&hellip;
          </p>
          <p className="text-xs text-gray-400">
            Redirecting to your report in a moment.
          </p>
        </div>
      )}
    </div>
  );
}
