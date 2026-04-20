import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

const db = new Pool({ connectionString: process.env.DATABASE_URL! });

// Complete rule-to-BV map covering all phases
const RULE_TO_BV: Record<string, number[]> = {
  // Plan integrity
  "PI-STAMP-001": [4],
  "PI-INDEX-003": [1],
  // Architectural
  "AR-EGRESS-WIN-001": [2], "AR-WIN-NCO-001": [2],
  "AR-CODE-ANALYSIS-001": [10], "AR-SHOWER-001": [12], "AR-RESTROOM-001": [13],
  "AR-EXIT-SEP-001": [14], "AR-TRAVEL-001": [15], "AR-EXIT-DISC-001": [16],
  "AR-SMOKE-001": [17],
  // Accessibility
  "AC-TRIGGER-001": [22], "AC-PATH-001": [27], "AC-DOOR-WIDTH-001": [38],
  "AC-TURN-001": [29], "AC-KITCHEN-001": [28, 30, 31],
  "AC-TOILET-001": [32, 38], "AC-TP-DISP-001": [40],
  "AC-GRAB-001": [35, 36], "AC-REACH-001": [33, 34, 37],
  "AC-SIGN-001": [42], "AC-PARKING-001": [25],
  // Energy
  "EN-MIXED-OCC-T24-001": [43], "EN-DECL-SIGNED-001": [44], "EN-WALL-INSUL-001": [56],
  // Electrical
  "ELEC-PANEL-LOC-001": [45], "ELEC-PANEL-AMP-001": [45],
  "ELEC-R21-COMPLIANCE-001": [46], "ELEC-EXT-LIGHTING-001": [47],
  // Mechanical
  "MECH-ATTIC-VENT-001": [19], "MECH-ATTIC-SCREEN-001": [20], "MECH-ATTIC-CLEAR-001": [21],
  "MECH-HVAC-DEDICATED": [48], "MECH-BATH-EXHAUST-001": [49], "MECH-KITCHEN-HOOD-001": [50],
  // Plumbing
  "PLMB-UTILITY-SITE-001": [51], "PLMB-FIXTURE-COUNT-001": [52],
  "PLMB-WH-LOCATION-001": [53], "PLMB-SHOWER-CTRL-001": [54], "PLMB-WH-DEDICATED-001": [55],
  // Structural
  "STR-HEADER-SIZING": [57], "STR-PLUMB-WALL-STUDS": [58],
  // Fire/Life Safety
  "FIRE-NFPA13R-REQUIRED": [2, 4], "FIRE-ALARM-REQUIRED": [5],
  "FIRE-SEP-RATING-508": [5, 6], "FIRE-FIRE-DOOR-001": [7],
  "FIRE-HSC13131-TYPE-V": [3], "FIRE-DEFERRED-SUB-001": [2],
};

interface FindingRow {
  finding_id: string;
  rule_id: string;
  discipline: string;
  draft_comment_text: string;
  confidence: number;
  severity: string;
}

interface BvRow {
  comment_number: number;
  comment_text: string;
}

const TRIAGE_ACTIONS = [
  "Add rule",
  "Tune threshold",
  "Add exception",
  "Promote to skill gotcha",
] as const;

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const projectId = params.id;
  const round = parseInt(request.nextUrl.searchParams.get("round") ?? "1", 10);

  try {
    const [findingsRes, bvRes] = await Promise.all([
      db.query<FindingRow>(
        `SELECT finding_id, rule_id, discipline, draft_comment_text, confidence, severity
           FROM findings WHERE project_id = $1 AND review_round = $2`,
        [projectId, round]
      ),
      db.query<BvRow>(
        `SELECT comment_number, comment_text FROM external_review_comments
          WHERE project_id = $1 ORDER BY comment_number`,
        [projectId]
      ),
    ]);

    const bvByNum = new Map(
      bvRes.rows.map((r) => [r.comment_number, r.comment_text])
    );
    const matchedFindingIds = new Set<string>();
    const matchedBvNums = new Set<number>();

    for (const f of findingsRes.rows) {
      const mapped = RULE_TO_BV[f.rule_id] ?? [];
      for (const n of mapped) {
        if (bvByNum.has(n)) {
          matchedFindingIds.add(f.finding_id);
          matchedBvNums.add(n);
        }
      }
    }

    // Misses: BV comments not matched by any finding
    const misses = bvRes.rows
      .filter((r) => !matchedBvNums.has(r.comment_number))
      .map((r) => ({
        comment_number: r.comment_number,
        comment_text: r.comment_text,
        triage_actions: [...TRIAGE_ACTIONS],
      }));

    // False positives: findings not matched to any BV comment
    const falsePositives = findingsRes.rows
      .filter((f) => !matchedFindingIds.has(f.finding_id))
      .map((f) => ({
        finding_id: f.finding_id,
        rule_id: f.rule_id,
        discipline: f.discipline,
        draft_comment_text: (f.draft_comment_text ?? "").substring(0, 200),
        confidence: f.confidence,
        severity: f.severity,
        triage_actions: [...TRIAGE_ACTIONS],
      }));

    return NextResponse.json({
      project_id: projectId,
      review_round: round,
      total_bv_comments: bvRes.rows.length,
      total_findings: findingsRes.rows.length,
      matched_bv_comments: matchedBvNums.size,
      matched_findings: matchedFindingIds.size,
      miss_count: misses.length,
      false_positive_count: falsePositives.length,
      misses,
      false_positives: falsePositives,
    });
  } catch (err) {
    console.error("triage error:", err);
    return NextResponse.json({ error: "internal" }, { status: 500 });
  }
}
