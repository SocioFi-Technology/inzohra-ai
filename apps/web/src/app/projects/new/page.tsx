"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

type JurisdictionOption = {
  value: string;
  label: string;
};

const JURISDICTION_OPTIONS: JurisdictionOption[] = [
  { value: "santa_rosa", label: "Santa Rosa, CA" },
  { value: "oakland", label: "Oakland, CA" },
  { value: "san_jose", label: "San Jose, CA" },
  { value: "los_angeles", label: "Los Angeles, CA" },
  { value: "other", label: "Other" },
];

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function NewProjectPage() {
  const router = useRouter();

  const [address, setAddress] = useState("");
  const [permitNumber, setPermitNumber] = useState("");
  const [jurisdiction, setJurisdiction] = useState(JURISDICTION_OPTIONS[0].value);
  const [occupancyClass, setOccupancyClass] = useState("");
  const [constructionType, setConstructionType] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(todayISO());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address,
          permit_number: permitNumber,
          jurisdiction,
          occupancy_class: occupancyClass || undefined,
          construction_type: constructionType || undefined,
          effective_date: effectiveDate,
        }),
      });

      const data = (await res.json()) as { project_id?: string; error?: string };

      if (!res.ok) {
        setError(data.error ?? `Server error ${res.status}`);
        return;
      }

      if (!data.project_id) {
        setError("Unexpected response from server.");
        return;
      }

      router.push(`/projects/${data.project_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header bar */}
      <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3">
        <Link
          href="/"
          className="text-sm text-gray-500 hover:text-indigo-600 transition-colors"
        >
          ← Projects
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-sm font-semibold text-gray-900">New Project</h1>
      </div>

      {/* Centered card */}
      <div className="max-w-lg mx-auto px-6 py-8">
        <form
          onSubmit={(e) => void handleSubmit(e)}
          className="bg-white border border-gray-200 rounded-xl p-6 space-y-5"
        >
          {/* Project Address */}
          <div>
            <label
              htmlFor="address"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Project Address <span className="text-red-500">*</span>
            </label>
            <input
              id="address"
              type="text"
              required
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="2008 Dennis Ln, Santa Rosa, CA"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          {/* Permit Number */}
          <div>
            <label
              htmlFor="permitNumber"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Permit Number <span className="text-red-500">*</span>
            </label>
            <input
              id="permitNumber"
              type="text"
              required
              value={permitNumber}
              onChange={(e) => setPermitNumber(e.target.value)}
              placeholder="B25-2734"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          {/* Jurisdiction */}
          <div>
            <label
              htmlFor="jurisdiction"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Jurisdiction <span className="text-red-500">*</span>
            </label>
            <select
              id="jurisdiction"
              required
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
            >
              {JURISDICTION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Effective Date */}
          <div>
            <label
              htmlFor="effectiveDate"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Effective Date <span className="text-red-500">*</span>
            </label>
            <input
              id="effectiveDate"
              type="date"
              required
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          {/* Occupancy Class (optional) */}
          <div>
            <label
              htmlFor="occupancyClass"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Occupancy Class{" "}
              <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              id="occupancyClass"
              type="text"
              value={occupancyClass}
              onChange={(e) => setOccupancyClass(e.target.value)}
              placeholder="R-3, B, A-2 …"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          {/* Construction Type (optional) */}
          <div>
            <label
              htmlFor="constructionType"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Construction Type{" "}
              <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              id="constructionType"
              type="text"
              value={constructionType}
              onChange={(e) => setConstructionType(e.target.value)}
              placeholder="V-B, III-A …"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          {/* Error box */}
          {error !== null && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-indigo-600 text-white font-medium text-sm rounded-lg px-4 py-2.5 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "Creating…" : "Create Project"}
          </button>
        </form>

        {/* Info note */}
        <div className="mt-6 p-4 bg-blue-50 rounded-lg text-sm text-blue-700">
          <strong>Note:</strong> Creating a project here registers it in the
          database. To ingest plan drawings, run the ingestion pipeline:{" "}
          <code className="bg-blue-100 px-1.5 py-0.5 rounded font-mono text-xs">
            uv run scripts/ingest/ingest_fixture.py
          </code>
        </div>
      </div>
    </div>
  );
}
