"use client";

import { useState } from "react";

export function FpTriageActions({ findingId }: { findingId: string }) {
  const [state, setState] = useState<"idle" | "loading" | "done">("idle");
  const [label, setLabel] = useState("");

  async function act(action: "confirm_fp" | "accept" | "deprecate") {
    setState("loading");
    setLabel(
      action === "confirm_fp"
        ? "Confirmed FP"
        : action === "accept"
          ? "Accepted"
          : "Flagged",
    );
    await fetch(`/api/triage/fps/${findingId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }).catch(() => {});
    setState("done");
  }

  if (state === "done") {
    return (
      <span className="px-2 py-1 text-xs rounded border border-green-300 text-green-700 bg-green-50">
        ✓ {label}
      </span>
    );
  }

  return (
    <div className="flex flex-col gap-1 flex-shrink-0 text-xs">
      <button
        onClick={() => act("confirm_fp")}
        disabled={state === "loading"}
        className="px-2 py-1 rounded border border-orange-300 text-orange-700 hover:bg-orange-50 disabled:opacity-50"
      >
        Confirm FP
      </button>
      <button
        onClick={() => act("accept")}
        disabled={state === "loading"}
        className="px-2 py-1 rounded border border-green-300 text-green-700 hover:bg-green-50 disabled:opacity-50"
      >
        Accept (not FP)
      </button>
      <button
        onClick={() => act("deprecate")}
        disabled={state === "loading"}
        className="px-2 py-1 rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-50"
      >
        Deprecate rule
      </button>
    </div>
  );
}
