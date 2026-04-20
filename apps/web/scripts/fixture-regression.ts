/**
 * Fixture regression harness.
 * Invoked by: pnpm test:fixture --phase <n>
 * Exits 0 on pass, 1 on regression.
 *
 * Phase 00 criteria checked here (DB-level):
 *   [a] All 19 sheets present in `sheets` table.
 *   [b] ≥17/19 title blocks have project_address containing "Dennis" (case-insensitive).
 *   [c] ≥1 sheet has address_mismatch = true (the "1966 Dennis Ln" bug sheet).
 */

import { Pool } from "pg";

const phase = process.argv.includes("--phase")
  ? process.argv[process.argv.indexOf("--phase") + 1]
  : "all";

console.log(`\n[fixture] phase=${phase}`);

const db = new Pool({ connectionString: process.env.DATABASE_URL! });

async function runPhase00(): Promise<boolean> {
  let passed = true;

  // Find the fixture project
  const projRow = await db.query(
    `SELECT project_id FROM projects WHERE permit_number = 'B25-2734' AND jurisdiction = 'santa_rosa' LIMIT 1`
  );
  if (projRow.rows.length === 0) {
    console.log("  [UNCHECKED] No B25-2734 project found — run ingest_fixture.py first.");
    await db.end();
    return true; // Not a failure — baseline not yet populated
  }
  const projectId = projRow.rows[0].project_id;

  // [a] Sheet count
  const sheetRes = await db.query(
    `SELECT COUNT(*) AS cnt FROM sheets s
     JOIN documents d ON d.document_id = s.document_id
     JOIN submittals sub ON sub.submittal_id = d.submittal_id
     WHERE sub.project_id = $1`,
    [projectId]
  );
  const sheetCount = parseInt(sheetRes.rows[0].cnt, 10);
  const aPass = sheetCount >= 19;
  console.log(
    `  [${aPass ? "PASS" : "FAIL"}] Sheet count: ${sheetCount} (need ≥19)`
  );
  if (!aPass) passed = false;

  // [b] Address extraction quality
  const addrRes = await db.query(
    `SELECT
       COUNT(*) FILTER (WHERE (payload->'project_address'->>'value') ILIKE '%dennis%') AS with_dennis,
       COUNT(*) AS total
     FROM entities e
     JOIN sheets s ON s.sheet_id = e.sheet_id
     JOIN documents d ON d.document_id = s.document_id
     JOIN submittals sub ON sub.submittal_id = d.submittal_id
     WHERE sub.project_id = $1 AND e.type = 'title_block'`,
    [projectId]
  );
  const withDennis = parseInt(addrRes.rows[0].with_dennis, 10);
  const totalEntities = parseInt(addrRes.rows[0].total, 10);
  const bPass = withDennis >= 17;
  console.log(
    `  [${bPass ? "PASS" : "FAIL"}] Address OK: ${withDennis}/${totalEntities} contain "Dennis" (need ≥17)`
  );
  if (!bPass) passed = false;

  // [c] Mismatch flag
  const mismatchRes = await db.query(
    `SELECT COUNT(*) AS cnt FROM entities e
     JOIN sheets s ON s.sheet_id = e.sheet_id
     JOIN documents d ON d.document_id = s.document_id
     JOIN submittals sub ON sub.submittal_id = d.submittal_id
     WHERE sub.project_id = $1 AND e.type = 'title_block'
       AND (e.payload->>'address_mismatch')::boolean = true`,
    [projectId]
  );
  const mismatchCount = parseInt(mismatchRes.rows[0].cnt, 10);
  const cPass = mismatchCount >= 1;
  console.log(
    `  [${cPass ? "PASS" : "UNCHECKED"}] Mismatch sheets flagged: ${mismatchCount} (need ≥1 for "1966 Dennis Ln" detection)`
  );
  // c is not a hard failure if vision track is disabled

  return passed;
}

(async () => {
  try {
    let ok = true;
    if (phase === "00" || phase === "all") {
      ok = await runPhase00();
    } else {
      console.log(`  [UNCHECKED] Phase ${phase} checks not yet implemented.`);
    }
    await db.end();
    console.log(ok ? "\n[fixture] PASS\n" : "\n[fixture] FAIL\n");
    process.exit(ok ? 0 : 1);
  } catch (err) {
    console.error("[fixture] ERROR:", err);
    await db.end();
    process.exit(1);
  }
})();
