import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

interface ParsedQuery {
  itemId: string;
  description: string;
  targetEntityClass: string;
  codeRef: string;
  thresholdValue: number | null;
  thresholdUnit: string | null;
}

interface ParseRequestBody {
  address: string;
  permitNumber: string;
  jurisdiction: string;
  occupancyClass: string;
  checklistText: string;
}

interface PatternRule {
  pattern: RegExp;
  targetEntityClass: string;
  codeRef: string;
  thresholdValue: number | null;
  thresholdUnit: string | null;
}

/**
 * Simple JS pattern matcher mirroring the Python QCA parser.
 * Patterns are tried in order; the first match wins for entity-class assignment.
 * Numeric thresholds are extracted from the pattern match groups when available.
 */
const PATTERN_RULES: PatternRule[] = [
  {
    pattern: /egress\s+window|NCO|net\s+clear\s+opening/i,
    targetEntityClass: "window",
    codeRef: "CRC-R310.2.1",
    thresholdValue: 5.7,
    thresholdUnit: "sqft",
  },
  {
    pattern: /sill\s+height|window\s+sill/i,
    targetEntityClass: "window",
    codeRef: "CRC-R310.1",
    thresholdValue: 44,
    thresholdUnit: "inches",
  },
  {
    pattern: /door\s+width|exit\s+door|egress\s+door|clear\s+width/i,
    targetEntityClass: "door",
    codeRef: "CBC-1010.1.1",
    thresholdValue: 32,
    thresholdUnit: "inches",
  },
  {
    pattern: /ceiling\s+height|minimum\s+height|room\s+height/i,
    targetEntityClass: "room",
    codeRef: "CRC-R305.1",
    thresholdValue: 7,
    thresholdUnit: "feet",
  },
  {
    pattern: /travel\s+distance|egress\s+path|exit\s+travel/i,
    targetEntityClass: "egress_path",
    codeRef: "CBC-1006.3.3",
    thresholdValue: 200,
    thresholdUnit: "feet",
  },
  {
    pattern: /accessible\s+route|accessibility|ADA|wheelchair|path\s+of\s+travel/i,
    targetEntityClass: "egress_path",
    codeRef: "CBC-11B-402.5",
    thresholdValue: 36,
    thresholdUnit: "inches",
  },
  {
    pattern: /\bstair|riser|tread\b/i,
    targetEntityClass: "egress_path",
    codeRef: "CRC-R311.7",
    thresholdValue: null,
    thresholdUnit: null,
  },
  {
    pattern: /smoke\s+alarm|smoke\s+detector/i,
    targetEntityClass: "room",
    codeRef: "CRC-R314",
    thresholdValue: null,
    thresholdUnit: null,
  },
  {
    pattern: /occupant\s+load|occupancy\s+load/i,
    targetEntityClass: "room",
    codeRef: "CBC-1004.1",
    thresholdValue: null,
    thresholdUnit: null,
  },
  {
    pattern: /handrail|guard\s+rail|guardrail/i,
    targetEntityClass: "egress_path",
    codeRef: "CRC-R311.7.8",
    thresholdValue: null,
    thresholdUnit: null,
  },
];

/** Extract a numeric threshold from the line if one is present (e.g. ">= 5.7"). */
function extractThreshold(line: string): { value: number | null; unit: string | null } {
  // Match patterns like: >= 5.7 sqft | minimum 32 inches | at least 7 feet | < 44 in
  const numMatch = line.match(
    /(?:>=?|<=?|minimum|min\.?|at\s+least|not\s+exceed(?:ing)?|maximum|max\.?)\s*([\d.]+)\s*(sqft|sq\s*ft|feet|ft|inches|in\.?|meters?|m)/i
  );
  if (numMatch) {
    const raw = numMatch[2].toLowerCase().replace(/\s+/g, "");
    const unitMap: Record<string, string> = {
      sqft: "sqft",
      "sq ft": "sqft",
      feet: "feet",
      ft: "feet",
      inches: "inches",
      "in.": "inches",
      in: "inches",
      meters: "meters",
      meter: "meters",
      m: "meters",
    };
    return {
      value: parseFloat(numMatch[1]),
      unit: unitMap[raw] ?? raw,
    };
  }
  return { value: null, unit: null };
}

function parseChecklistText(text: string): ParsedQuery[] {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#") && !l.startsWith("//"));

  return lines.map((line, index): ParsedQuery => {
    const itemId = `Q${String(index + 1).padStart(3, "0")}`;

    for (const rule of PATTERN_RULES) {
      if (rule.pattern.test(line)) {
        const extracted = extractThreshold(line);
        return {
          itemId,
          description: line,
          targetEntityClass: rule.targetEntityClass,
          codeRef: rule.codeRef,
          thresholdValue: extracted.value ?? rule.thresholdValue,
          thresholdUnit: extracted.unit ?? rule.thresholdUnit,
        };
      }
    }

    // Fallback — unclassified item
    return {
      itemId,
      description: line,
      targetEntityClass: "room",
      codeRef: "CBC-GENERAL",
      thresholdValue: null,
      thresholdUnit: null,
    };
  });
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: ParseRequestBody;
  try {
    body = (await req.json()) as ParseRequestBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { address, permitNumber, jurisdiction, occupancyClass, checklistText } = body;

  if (!address || !permitNumber || !jurisdiction || !checklistText) {
    return NextResponse.json(
      { error: "address, permitNumber, jurisdiction, and checklistText are required" },
      { status: 400 }
    );
  }

  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    // Upsert project by permit_number + jurisdiction
    const upsertProject = await client.query(
      `INSERT INTO projects (project_id, address, permit_number, jurisdiction, occupancy_class, effective_date, created_at)
       VALUES (gen_random_uuid(), $1, $2, $3, $4, CURRENT_DATE, NOW())
       ON CONFLICT (permit_number, jurisdiction) DO UPDATE
         SET address = EXCLUDED.address,
             occupancy_class = EXCLUDED.occupancy_class
       RETURNING project_id`,
      [address, permitNumber, jurisdiction, occupancyClass ?? "R-3"]
    );

    const projectId: string = upsertProject.rows[0].project_id as string;

    const queries = parseChecklistText(checklistText);

    // Insert parsed queries with confirmed_by_user = false
    for (const q of queries) {
      await client.query(
        `INSERT INTO checklist_queries
           (query_id, project_id, item_id, description, target_entity_class,
            code_ref, threshold_value, threshold_unit, confirmed_by_user, created_at)
         VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, false, NOW())`,
        [
          projectId,
          q.itemId,
          q.description,
          q.targetEntityClass,
          q.codeRef,
          q.thresholdValue,
          q.thresholdUnit,
        ]
      );
    }

    // Return the inserted query_ids so Step 3 can reference them
    const insertedRows = await client.query(
      `SELECT query_id, item_id, description, target_entity_class, code_ref,
              threshold_value, threshold_unit
       FROM checklist_queries
       WHERE project_id = $1
       ORDER BY created_at, item_id`,
      [projectId]
    );

    await client.query("COMMIT");

    const responseQueries: ParsedQuery[] = (
      insertedRows.rows as Array<{
        query_id: string;
        item_id: string;
        description: string;
        target_entity_class: string;
        code_ref: string;
        threshold_value: number | null;
        threshold_unit: string | null;
      }>
    ).map((r) => ({
      itemId: r.item_id,
      description: r.description,
      targetEntityClass: r.target_entity_class,
      codeRef: r.code_ref,
      thresholdValue: r.threshold_value,
      thresholdUnit: r.threshold_unit,
    }));

    return NextResponse.json({ projectId, queries: responseQueries });
  } catch (err) {
    await client.query("ROLLBACK");
    console.error("[api/designer/parse] DB error:", err);
    return NextResponse.json(
      { error: "Database error — tables may not exist yet" },
      { status: 503 }
    );
  } finally {
    client.release();
  }
}
