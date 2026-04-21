"use client";

import { useState } from "react";

type Props = {
  commentId: string;
  commentText: string;
  discipline: string | null;
};

export function MissTriageActions({ commentId, commentText, discipline }: Props) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [action, setAction] = useState<string>("");

  async function doAction(act: "training_example" | "skill_note") {
    setState("loading");
    setAction(act);
    try {
      await fetch(`/api/triage/misses/${commentId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: act,
          discipline: discipline ?? "architectural",
          comment_text: commentText,
        }),
      });
      setState("done");
    } catch {
      setState("error");
    }
  }

  if (state === "done") {
    return (
      <span className="px-2 py-1 text-xs rounded border border-green-300 text-green-700 bg-green-50">
        ✓ {action === "training_example" ? "Added as example" : "Noted"}
      </span>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 flex-shrink-0">
      <button
        onClick={() => doAction("training_example")}
        disabled={state === "loading"}
        className="px-2 py-1 text-xs rounded border border-indigo-300 text-indigo-700 hover:bg-indigo-50 disabled:opacity-50 text-center"
      >
        {state === "loading" && action === "training_example" ? "…" : "Add as example"}
      </button>
      <button
        onClick={() => doAction("skill_note")}
        disabled={state === "loading"}
        className="px-2 py-1 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50 text-center"
      >
        {state === "loading" && action === "skill_note" ? "…" : "Mark noted"}
      </button>
    </div>
  );
}
