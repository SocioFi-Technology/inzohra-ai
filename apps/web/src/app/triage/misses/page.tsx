import { Pool } from "pg";

const db = new Pool({ connectionString: process.env.DATABASE_URL! });

// Complete rule-to-BV map covering all phases.
// Keep in sync with RULE_TO_BV_COMMENT in services/review/app/comparison/compare.py.
const RULE_TO_BV: Record<string, number[]> = {
  // Plan integrity
  "PI-STAMP-001": [4],
  "PI-INDEX-003": [1],
  // Architectural
  "AR-EGRESS-WIN-001": [2], "AR-WIN-NCO-001": [2], "AR-WIN-HEIGHT-001": [2],
  "AR-WIN-WIDTH-001": [2], "AR-WIN-SILL-001": [2],
  "AR-CODE-ANALYSIS-001": [10], "AR-SHOWER-001": [12], "AR-RESTROOM-001": [13],
  "AR-EXIT-SEP-001": [14], "AR-TRAVEL-001": [15], "AR-EXIT-DISC-001": [16],
  "AR-SMOKE-001": [17],
  // Accessibility
  "AC-TRIGGER-001": [22], "AC-PATH-001": [27, 28], "AC-DOOR-WIDTH-001": [31, 38],
  "AC-TURN-001": [29, 34], "AC-KITCHEN-001": [28, 29, 30, 31],
  "AC-TOILET-001": [31, 32, 38], "AC-TP-DISP-001": [40],
  "AC-GRAB-001": [35, 36], "AC-REACH-001": [33, 37, 38],
  "AC-SIGN-001": [42], "AC-PARKING-001": [25, 26],
  "AC-SURFACE-001": [27, 41], "AC-HTG-001": [30],
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

interface BvRow {
  comment_number: number;
  comment_text: string;
}

interface FindingRow {
  finding_id: string;
  rule_id: string;
  discipline: string;
  draft_comment_text: string;
  confidence: number;
}

const TRIAGE_ACTIONS = [
  "Add rule",
  "Tune threshold",
  "Add exception",
  "Promote to skill gotcha",
] as const;

export default async function TriageMissesPage({
  searchParams,
}: {
  searchParams: { project?: string; round?: string };
}) {
  const projectId = searchParams.project;
  const round = parseInt(searchParams.round ?? "1", 10);

  if (!projectId) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-4">Triage — Missed Comments</h1>
        <p className="text-gray-500">
          Provide a project_id query parameter: ?project=&lt;uuid&gt;
        </p>
      </div>
    );
  }

  const [findingsRes, bvRes] = await Promise.all([
    db.query<FindingRow>(
      `SELECT finding_id, rule_id, discipline, draft_comment_text, confidence
         FROM findings WHERE project_id = $1 AND review_round = $2`,
      [projectId, round]
    ),
    db.query<BvRow>(
      `SELECT comment_number, comment_text FROM external_review_comments
        WHERE project_id = $1 ORDER BY comment_number`,
      [projectId]
    ),
  ]);

  // De-duplicate by comment_number (DB may have duplicate rows for same comment)
  const bvByNum = new Map(bvRes.rows.map((r) => [r.comment_number, r.comment_text]));

  const matchedBvNums = new Set<number>();
  for (const f of findingsRes.rows) {
    const mapped = RULE_TO_BV[f.rule_id] ?? [];
    for (const n of mapped) {
      if (bvByNum.has(n)) matchedBvNums.add(n);
    }
  }

  const misses = Array.from(bvByNum.entries())
    .filter(([num]) => !matchedBvNums.has(num))
    .map(([num, text]) => ({ comment_number: num, comment_text: text }))
    .sort((a, b) => a.comment_number - b.comment_number);

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Triage — Missed BV Comments</h1>
      <p className="text-gray-500 mb-6">
        {misses.length} of {bvByNum.size} unique BV comments not matched by any
        finding (round {round}).
      </p>
      {misses.length === 0 ? (
        <div className="bg-green-50 border border-green-200 rounded p-4 text-green-800">
          All BV comments are covered by findings. No misses.
        </div>
      ) : (
        <ul className="space-y-4">
          {misses.map((m) => (
            <li
              key={m.comment_number}
              className="border rounded p-4 bg-white shadow-sm"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="font-mono text-sm bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded">
                  BV #{m.comment_number}
                </span>
                <span className="text-sm text-gray-400">MISSED</span>
              </div>
              <p className="text-sm text-gray-800 mb-3">{m.comment_text}</p>
              <div className="flex gap-2 flex-wrap">
                {TRIAGE_ACTIONS.map((action) => (
                  <button
                    key={action}
                    className="text-xs px-3 py-1 rounded border border-gray-300 hover:bg-gray-50"
                  >
                    {action}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
