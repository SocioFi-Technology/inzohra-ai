import { NextResponse } from "next/server";
import { query, queryOne } from "@/lib/db";

interface OverrideBody {
  override_value: number;
  rationale: string;
  reviewer_id?: string; // optional for now — Phase 08 adds auth
}

interface MeasurementRow {
  measurement_id: string;
  value: number;
  unit: string;
  confidence: number;
  override_history: Array<unknown>;
}

export async function POST(
  req: Request,
  { params }: { params: { id: string; measurementId: string } }
) {
  let body: OverrideBody;
  try {
    body = (await req.json()) as OverrideBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { override_value, rationale } = body;

  if (typeof override_value !== "number" || !rationale) {
    return NextResponse.json(
      { error: "override_value (number) and rationale (string) required" },
      { status: 400 }
    );
  }

  // Load current measurement
  const measurement = await queryOne<MeasurementRow>(
    `SELECT measurement_id, value, unit, confidence, override_history
     FROM measurements WHERE measurement_id = $1 AND project_id = $2`,
    [params.measurementId, params.id]
  );

  if (!measurement) {
    return NextResponse.json({ error: "Measurement not found" }, { status: 404 });
  }

  const currentHistory = measurement.override_history ?? [];
  const newEntry = {
    overridden_at: new Date().toISOString(),
    previous_value: measurement.value,
    override_value,
    rationale,
    reviewer_id: body.reviewer_id ?? "anonymous",
  };

  // Append override to history, update value and confidence
  await query(
    `UPDATE measurements
     SET value = $1,
         confidence = 0.99,
         override_history = ($2)::jsonb
     WHERE measurement_id = $3 AND project_id = $4`,
    [
      override_value,
      JSON.stringify([...currentHistory, newEntry]),
      params.measurementId,
      params.id,
    ]
  );

  return NextResponse.json({
    measurement_id: params.measurementId,
    new_value: override_value,
    override_count: currentHistory.length + 1,
  });
}
