"use client";

import { useState } from "react";
import Link from "next/link";

interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

type UploadState = "idle" | "validating" | "validated" | "loading" | "loaded" | "error";

export default function UploadPackPage() {
  const [fileText, setFileText] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [jurisdiction, setJurisdiction] = useState<string>("santa_rosa");
  const [state, setState] = useState<UploadState>("idle");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>("");

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setState("idle");
    setValidation(null);
    setErrorMessage("");

    const reader = new FileReader();
    reader.onload = (ev) => {
      setFileText((ev.target?.result as string) ?? "");
    };
    reader.readAsText(file);
  }

  async function handleValidate() {
    if (!fileText) {
      setErrorMessage("No file selected or file is empty.");
      setState("error");
      return;
    }
    setState("validating");
    setValidation(null);
    setErrorMessage("");

    try {
      const res = await fetch("/api/admin/packs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "validate", manifest: fileText }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Server error ${res.status}: ${text}`);
      }
      const result = (await res.json()) as ValidationResult;
      setValidation(result);
      setState("validated");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setState("error");
    }
  }

  async function handleLoad() {
    if (!fileText || !validation?.valid) return;
    setState("loading");
    setErrorMessage("");

    try {
      const res = await fetch("/api/admin/packs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "load",
          manifest: fileText,
          jurisdiction,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Server error ${res.status}: ${text}`);
      }
      setState("loaded");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setState("error");
    }
  }

  const validationPassed = validation?.valid === true;

  return (
    <div className="max-w-2xl">
      <div className="mb-4">
        <Link href="/admin/packs" className="text-sm text-blue-600 hover:underline">
          ← Back to packs
        </Link>
      </div>

      <h2 className="text-xl font-bold text-gray-900 mb-2">Upload New Pack</h2>
      <p className="text-sm text-gray-500 mb-6">
        Upload a <code className="bg-gray-100 px-1 rounded text-xs">.yaml</code> or{" "}
        <code className="bg-gray-100 px-1 rounded text-xs">.tar.gz</code> jurisdictional pack.
        Validate first, then load into the database.
      </p>

      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-5">
        {/* File input */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Pack file
          </label>
          <input
            type="file"
            accept=".yaml,.yml,.tar.gz"
            onChange={handleFileChange}
            className="block w-full text-sm text-gray-600
                       file:mr-4 file:py-2 file:px-4
                       file:rounded file:border file:border-gray-300
                       file:text-sm file:font-medium file:bg-gray-50
                       file:text-gray-700 hover:file:bg-gray-100
                       cursor-pointer"
          />
          {fileName && (
            <p className="text-xs text-gray-400 mt-1">Selected: {fileName}</p>
          )}
        </div>

        {/* Jurisdiction select */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Jurisdiction
          </label>
          <select
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
            className="block w-full rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="santa_rosa">Santa Rosa</option>
            <option value="oakland">Oakland</option>
            <option value="other">Other</option>
          </select>
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 pt-1">
          <button
            onClick={handleValidate}
            disabled={!fileText || state === "validating" || state === "loading"}
            className="px-4 py-2 text-sm font-medium rounded border border-gray-300
                       bg-white text-gray-700 hover:bg-gray-50
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {state === "validating" ? "Validating…" : "Validate"}
          </button>

          <button
            onClick={handleLoad}
            disabled={!validationPassed || state === "loading" || state === "loaded"}
            className="px-4 py-2 text-sm font-medium rounded
                       bg-blue-600 text-white hover:bg-blue-700
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {state === "loading" ? "Loading…" : "Load into DB"}
          </button>
        </div>

        {/* Validation result */}
        {validation && state === "validated" && (
          <div
            className={`rounded-lg p-4 text-sm ${
              validation.valid
                ? "bg-green-50 border border-green-200"
                : "bg-red-50 border border-red-200"
            }`}
          >
            <p className={`font-semibold mb-2 ${validation.valid ? "text-green-700" : "text-red-700"}`}>
              {validation.valid ? "Validation passed" : "Validation failed"}
            </p>
            {validation.errors.length > 0 && (
              <div className="mb-2">
                <p className="text-red-600 font-medium text-xs mb-1">Errors:</p>
                <ul className="list-disc list-inside space-y-0.5">
                  {validation.errors.map((e, i) => (
                    <li key={i} className="text-red-600 text-xs">{e}</li>
                  ))}
                </ul>
              </div>
            )}
            {validation.warnings.length > 0 && (
              <div>
                <p className="text-amber-600 font-medium text-xs mb-1">Warnings:</p>
                <ul className="list-disc list-inside space-y-0.5">
                  {validation.warnings.map((w, i) => (
                    <li key={i} className="text-amber-600 text-xs">{w}</li>
                  ))}
                </ul>
              </div>
            )}
            {validation.errors.length === 0 && validation.warnings.length === 0 && (
              <p className="text-green-600 text-xs">No issues found. Ready to load.</p>
            )}
          </div>
        )}

        {/* Success */}
        {state === "loaded" && (
          <div className="rounded-lg p-4 text-sm bg-green-50 border border-green-200">
            <p className="font-semibold text-green-700">Pack loaded successfully.</p>
            <Link href="/admin/packs" className="text-sm text-blue-600 hover:underline mt-1 inline-block">
              View all packs →
            </Link>
          </div>
        )}

        {/* Error */}
        {state === "error" && errorMessage && (
          <div className="rounded-lg p-4 text-sm bg-red-50 border border-red-200">
            <p className="font-semibold text-red-700 mb-1">Error</p>
            <p className="text-red-600 text-xs">{errorMessage}</p>
          </div>
        )}
      </div>
    </div>
  );
}
