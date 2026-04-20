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

// Rules that fire correctly on general-practice issues not individually cited in
// the BV letter. Show them separately — they are NOT false positives.
// Keep in sync with ACCEPTED_GENERAL_RULES in services/review/app/comparison/compare.py.
const ACCEPTED_GENERAL_RULES = new Set<string>([
  "PI-DATE-001", "PI-TITLE-001", "PI-PERMIT-001", "PI-NORTH-001", "PI-SCALE-001",
  "STR-SHEAR-CALLOUT-001", "STR-HOLDOWN-001", "STR-FASTENER-001", "STR-LOAD-PATH-001",
  "PLMB-BACKFLOW-001", "PLMB-WH-ELEVATION-001",
  "MECH-DUCT-INSUL-001",
  "ELEC-GFCI-001", "ELEC-AFCI-001", "ELEC-ACCESSIBLE-CTRL-001",
  "CALG-WATER-FIXTURES-001", "CALG-RECYCLE-001", "CALG-EV-READY-001",
  "CALG-INDOOR-AIR-001", "CALG-MANDATORY-NOTE-001",
  "EN-CLIMATE-ZONE-001", "EN-HERS-DECL-001", "EN-PRESCRIPTIVE-001",
  "FIRE-CO-ALARM-001",
]);

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
}

const TRIAGE_ACTIONS = [
  "Add rule",
  "Tune threshold",
  "Add exception",
  "Promote to skill gotcha",
] as const;

function confidenceBadge(confidence: number): {
  label: string;
  className: string;
} {
  if (confidence >= 0.85) {
    return {
      label: `${Math.round(confidence * 100)}%`,
      className:
        "bg-green-100 text-green-800 border border-green-200",
    };
  }
  if (confidence >= 0.7) {
    return {
      label: `${Math.round(confidence * 100)}%`,
      className:
        "bg-yellow-100 text-yellow-800 border border-yellow-200",
    };
  }
  return {
    label: `${Math.round(confidence * 100)}%`,
    className: "bg-red-100 text-red-800 border border-red-200",
  };
}

export default async function TriageFalsePositivesPage({
  searchParams,
}: {
  searchParams: { project?: string; round?: string };
}) {
  const projectId = searchParams.project;
  const round = parseInt(searchParams.round ?? "1", 10);

  if (!projectId) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-4">
          Triage — Potential False Positives
        </h1>
        <p className="text-gray-500">
          Provide a project_id query parameter: ?project=&lt;uuid&gt;
        </p>
      </div>
    );
  }

  const [findingsRes, bvRes] = await Promise.all([
    db.query<FindingRow>(
      `SELECT finding_id, rule_id, discipline, draft_comment_text, confidence, severity
         FROM findings WHERE project_id = $1 AND review_round = $2`,
      [projectId, round]
    ),
    db.query<BvRow>(
      `SELECT comment_number FROM external_review_comments
        WHERE project_id = $1`,
      [projectId]
    ),
  ]);

  const bvNums = new Set(bvRes.rows.map((r) => r.comment_number));
  const matchedFindingIds = new Set<string>();

  for (const f of findingsRes.rows) {
    const mapped = RULE_TO_BV[f.rule_id] ?? [];
    for (const n of mapped) {
      if (bvNums.has(n)) {
        matchedFindingIds.add(f.finding_id);
      }
    }
  }

  const unmatchedFindings = findingsRes.rows.filter(
    (f) => !matchedFindingIds.has(f.finding_id)
  );

  // True FPs: unmatched AND not a known general-practice rule
  const falsePositives = unmatchedFindings
    .filter((f) => !ACCEPTED_GENERAL_RULES.has(f.rule_id))
    .sort((a, b) => a.confidence - b.confidence); // lowest confidence first

  // Extra-value: unmatched but correct general-practice findings
  const acceptedGeneral = unmatchedFindings.filter((f) =>
    ACCEPTED_GENERAL_RULES.has(f.rule_id)
  );

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">
        Triage — Potential False Positives
      </h1>
      <p className="text-gray-500 mb-6">
        {falsePositives.length} true FPs of {findingsRes.rows.length} total
        findings (round {round}).{" "}
        {acceptedGeneral.length > 0 && (
          <span className="text-blue-600">
            {acceptedGeneral.length} additional general-practice findings
            (accepted — not in BV letter but correct).
          </span>
        )}{" "}
        Sorted by ascending confidence — lowest confidence first.
      </p>
      {falsePositives.length === 0 ? (
        <div className="bg-green-50 border border-green-200 rounded p-4 text-green-800">
          All findings match a BV comment. No potential false positives.
        </div>
      ) : (
        <ul className="space-y-4">
          {falsePositives.map((f) => {
            const badge = confidenceBadge(f.confidence);
            const truncated =
              (f.draft_comment_text ?? "").substring(0, 150) +
              ((f.draft_comment_text ?? "").length > 150 ? "…" : "");
            return (
              <li
                key={f.finding_id}
                className="border rounded p-4 bg-white shadow-sm"
              >
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className="font-mono text-sm bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                    {f.rule_id}
                  </span>
                  <span className="text-sm text-gray-500">{f.discipline}</span>
                  <span className="text-sm text-gray-400 uppercase">
                    {f.severity}
                  </span>
                  <span
                    className={`font-mono text-xs px-2 py-0.5 rounded ${badge.className}`}
                  >
                    {badge.label}
                  </span>
                  <span className="text-sm text-orange-600 ml-auto">
                    UNMATCHED
                  </span>
                </div>
                <p className="text-sm text-gray-800 mb-3">{truncated}</p>
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
            );
          })}
        </ul>
      )}
    </div>
  );
}
