import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

const db = new Pool({ connectionString: process.env.DATABASE_URL! });

interface FindingRow {
  finding_id: string;
  rule_id: string;
  discipline: string;
  draft_comment_text: string;
}

interface BvCommentRow {
  comment_number: number;
  comment_text: string;
}

// Rule → BV comment map (mirrors Python RULE_TO_BV_COMMENT)
const RULE_TO_BV: Record<string, number[]> = {
  "PI-STAMP-001":       [4],
  "PI-INDEX-003":       [1],
  "AR-EGRESS-WIN-001":  [2],
  "AR-WIN-NCO-001":     [2],
  "AR-CODE-ANALYSIS-001": [10],
  "AR-SHOWER-001":      [12],
  "AR-RESTROOM-001":    [13],
  "AR-EXIT-SEP-001":    [14],
  "AR-TRAVEL-001":      [15],
  "AR-EXIT-DISC-001":   [16],
  "AR-SMOKE-001":       [17],
  "AC-TRIGGER-001":     [22],
  "AC-PATH-001":        [28],
  "AC-DOOR-WIDTH-001":  [31],
  "AC-TURN-001":        [34],
  "AC-KITCHEN-001":     [29, 30],
  "AC-TOILET-001":      [31, 32],
  "AC-TP-DISP-001":     [40],
  "AC-GRAB-001":        [35, 36],
  "AC-REACH-001":       [37, 38],
  "AC-SIGN-001":        [42],
  "AC-PARKING-001":     [25],
};

function tokenize(text: string): Set<string> {
  const stopWords = new Set(
    "a an and are as at be by for from in is it its of on or that the this to was were with shall not no any all must"
      .split(" ")
  );
  return new Set(
    text.toLowerCase().match(/[a-z]+/g)?.filter(
      (w) => w.length > 3 && !stopWords.has(w)
    ) ?? []
  );
}

function textMatchScore(findingText: string, commentText: string): number {
  const ft = tokenize(findingText);
  const ct = tokenize(commentText);
  const shared = new Set([...ft].filter((w) => ct.has(w)));
  if (shared.size >= 2) {
    return shared.size / Math.max(new Set([...ft, ...ct]).size, 1);
  }
  return 0;
}

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const projectId = params.id;
  const round = parseInt(request.nextUrl.searchParams.get("round") ?? "1", 10);
  const discipline = request.nextUrl.searchParams.get("discipline") ?? null;

  try {
    let query = `
      SELECT finding_id, rule_id, discipline, draft_comment_text
        FROM findings
       WHERE project_id = $1 AND review_round = $2
    `;
    const queryParams: (string | number | string[])[] = [projectId, round];

    if (discipline) {
      queryParams.push([discipline]);
      query += ` AND discipline = ANY($${queryParams.length})`;
    }

    const [findingsRes, bvRes] = await Promise.all([
      db.query<FindingRow>(query, queryParams),
      db.query<BvCommentRow>(
        `SELECT comment_number, comment_text FROM external_review_comments WHERE project_id = $1 ORDER BY comment_number`,
        [projectId]
      ),
    ]);

    const findings = findingsRes.rows;
    const bvComments = bvRes.rows;
    const bvByNum = new Map(bvComments.map((r) => [r.comment_number, r.comment_text]));

    const matchedFindingIds = new Set<string>();
    const matchedBvNums = new Set<number>();

    for (const f of findings) {
      const mapped = RULE_TO_BV[f.rule_id] ?? [];
      for (const bvNum of mapped) {
        if (bvByNum.has(bvNum)) {
          matchedFindingIds.add(f.finding_id);
          matchedBvNums.add(bvNum);
        }
      }
      if (!matchedFindingIds.has(f.finding_id)) {
        let best = 0;
        let bestNum = -1;
        for (const [num, text] of bvByNum) {
          const score = textMatchScore(f.draft_comment_text, text);
          if (score > best) { best = score; bestNum = num; }
        }
        if (best >= 0.15 && bestNum >= 0) {
          matchedFindingIds.add(f.finding_id);
          matchedBvNums.add(bestNum);
        }
      }
    }

    const totalFindings = findings.length;
    const totalBv = bvComments.length;
    const matchedF = matchedFindingIds.size;
    const matchedBv = matchedBvNums.size;
    const precision = totalFindings > 0 ? matchedF / totalFindings : 0;
    const recall = totalBv > 0 ? matchedBv / totalBv : 0;
    const f1 = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;

    return NextResponse.json({
      project_id: projectId,
      review_round: round,
      total_findings: totalFindings,
      total_bv_comments: totalBv,
      matched_findings: matchedF,
      matched_bv_comments: matchedBv,
      precision: Math.round(precision * 1000) / 1000,
      recall: Math.round(recall * 1000) / 1000,
      f1: Math.round(f1 * 1000) / 1000,
      unmatched_bv_numbers: bvComments
        .map((r) => r.comment_number)
        .filter((n) => !matchedBvNums.has(n)),
    });
  } catch (err) {
    console.error("metrics error:", err);
    return NextResponse.json({ error: "internal" }, { status: 500 });
  }
}
