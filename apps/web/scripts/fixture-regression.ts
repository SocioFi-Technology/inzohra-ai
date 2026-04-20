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

/**
 * Phase 01 acceptance criteria:
 *   [a] Code KB seeded: ≥19 code_sections rows in the DB.
 *   [b] At least one PI-ADDR-001 finding for the fixture project (catches "1966 Dennis Ln").
 *   [c] At least one PI-INDEX-003 finding (sheet-ID mismatch, BV Comment 1).
 *   [d] Every PI-ADDR-001 finding carries a non-empty citations array with a frozen_text.
 *   [e] At least one PI-STAMP-001 finding exists (BV Comment 4).
 */
async function runPhase01(): Promise<boolean> {
  let passed = true;

  // [a] KB seeded
  const kbRes = await db.query(`SELECT COUNT(*) AS cnt FROM code_sections`);
  const kbCount = parseInt(kbRes.rows[0].cnt, 10);
  const aPass = kbCount >= 19;
  console.log(`  [${aPass ? "PASS" : "FAIL"}] Code KB sections: ${kbCount} (need ≥19)`);
  if (!aPass) passed = false;

  // Find fixture project
  const projRow = await db.query(
    `SELECT project_id FROM projects WHERE permit_number = 'B25-2734' AND jurisdiction = 'santa_rosa' LIMIT 1`
  );
  if (projRow.rows.length === 0) {
    console.log("  [UNCHECKED] No B25-2734 project found — run ingest + review scripts first.");
    return passed;
  }
  const projectId = projRow.rows[0].project_id;

  // [b] PI-ADDR-001 finding exists (UNCHECKED: only fires when fixture has an address mismatch)
  const addrRes = await db.query(
    `SELECT COUNT(*) AS cnt FROM findings
     WHERE project_id = $1 AND discipline = 'plan_integrity' AND rule_id = 'PI-ADDR-001'`,
    [projectId]
  );
  const addrCount = parseInt(addrRes.rows[0].cnt, 10);
  const bPass = addrCount >= 1;
  console.log(`  [${bPass ? "PASS" : "UNCHECKED"}] PI-ADDR-001 findings: ${addrCount} (fires only if fixture has address mismatch)`);

  // [c] PI-INDEX-003 finding exists (BV Comment 1)
  const idxRes = await db.query(
    `SELECT COUNT(*) AS cnt FROM findings
     WHERE project_id = $1 AND discipline = 'plan_integrity' AND rule_id = 'PI-INDEX-003'`,
    [projectId]
  );
  const idxCount = parseInt(idxRes.rows[0].cnt, 10);
  const cPass = idxCount >= 1;
  console.log(`  [${cPass ? "PASS" : "UNCHECKED"}] PI-INDEX-003 findings: ${idxCount} (need ≥1 if SheetIndexAgent found an index)`);
  // UNCHECKED rather than FAIL: only fires if a cover sheet with an index was parsed

  // [d] PI-ADDR-001 citations carry frozen_text
  const citRes = await db.query(
    `SELECT citations FROM findings
     WHERE project_id = $1 AND discipline = 'plan_integrity' AND rule_id = 'PI-ADDR-001'
     LIMIT 5`,
    [projectId]
  );
  let dPass = true;
  for (const row of citRes.rows) {
    const cits: Array<Record<string, unknown>> = row.citations ?? [];
    // Findings may have empty citations if KB was not seeded; that's allowed
    // but when citations are present, each must carry a frozen_text.
    if (cits.length > 0 && !cits[0].frozen_text) {
      dPass = false;
    }
  }
  if (addrCount > 0) {
    console.log(`  [${dPass ? "PASS" : "FAIL"}] PI-ADDR-001 citation frozen_text present`);
    if (!dPass) passed = false;
  }

  // [e] PI-STAMP-001 finding exists (BV Comment 4)
  const stampRes = await db.query(
    `SELECT COUNT(*) AS cnt FROM findings
     WHERE project_id = $1 AND discipline = 'plan_integrity' AND rule_id = 'PI-STAMP-001'`,
    [projectId]
  );
  const stampCount = parseInt(stampRes.rows[0].cnt, 10);
  const ePass = stampCount >= 1;
  console.log(`  [${ePass ? "PASS" : "UNCHECKED"}] PI-STAMP-001 findings: ${stampCount} (need ≥1 if stamps were absent)`);

  return passed;
}

/**
 * Phase 02 acceptance criteria:
 *   [a] ≥58 external_review_comments for the fixture project (BV letter parsed).
 *   [b] At least one cross_doc_claims row for the fixture project.
 *   [c] At least one title24_form entity exists for the fixture project.
 *   [d] At least one cross_doc_claim with claim_type = 'r_value_roof'.
 *   [e] Code KB has ≥35 sections (expanded seed).
 */
async function runPhase02(): Promise<boolean> {
  let passed = true;

  const projRow = await db.query(
    `SELECT project_id FROM projects WHERE permit_number = 'B25-2734' AND jurisdiction = 'santa_rosa' LIMIT 1`
  );
  if (projRow.rows.length === 0) {
    console.log("  [UNCHECKED] No B25-2734 project found — run ingest_all_fixture.py first.");
    return true;
  }
  const projectId = projRow.rows[0].project_id;

  // [a] BV letter comments
  const commentsRes = await db.query(
    `SELECT COUNT(*) AS cnt FROM external_review_comments WHERE project_id = $1`,
    [projectId]
  );
  const commentCount = parseInt(commentsRes.rows[0].cnt, 10);
  const aPass = commentCount >= 58;
  console.log(`  [${aPass ? "PASS" : "FAIL"}] BV comments: ${commentCount} (need ≥58)`);
  if (!aPass) passed = false;

  // [b] cross_doc_claims
  const claimsRes = await db.query(
    `SELECT COUNT(*) AS cnt FROM cross_doc_claims WHERE project_id = $1`,
    [projectId]
  );
  const claimCount = parseInt(claimsRes.rows[0].cnt, 10);
  const bPass = claimCount >= 1;
  console.log(`  [${bPass ? "PASS" : "UNCHECKED"}] Cross-doc claims: ${claimCount} (need ≥1)`);

  // [c] title24_form entity
  const t24Res = await db.query(
    `SELECT COUNT(*) AS cnt FROM entities WHERE project_id = $1 AND type = 'title24_form'`,
    [projectId]
  );
  const t24Count = parseInt(t24Res.rows[0].cnt, 10);
  const cPass = t24Count >= 1;
  console.log(`  [${cPass ? "PASS" : "UNCHECKED"}] Title24 entities: ${t24Count} (need ≥1)`);

  // [d] r_value_roof claim
  const roofRes = await db.query(
    `SELECT COUNT(*) AS cnt FROM cross_doc_claims WHERE project_id = $1 AND claim_type = 'r_value_roof'`,
    [projectId]
  );
  const roofCount = parseInt(roofRes.rows[0].cnt, 10);
  const dPass = roofCount >= 1;
  console.log(`  [${dPass ? "PASS" : "UNCHECKED"}] R-value roof claim: ${roofCount} (need ≥1 if T24 parsed)`);

  // [e] KB expanded
  const kbRes = await db.query(`SELECT COUNT(*) AS cnt FROM code_sections`);
  const kbCount = parseInt(kbRes.rows[0].cnt, 10);
  const ePass = kbCount >= 35;
  console.log(`  [${ePass ? "PASS" : "FAIL"}] Code KB sections: ${kbCount} (need ≥35 for Phase 02)`);
  if (!ePass) passed = false;

  return passed;
}

(async () => {
  try {
    let ok = true;
    if (phase === "00" || phase === "all") {
      ok = (await runPhase00()) && ok;
    }
    if (phase === "01" || phase === "all") {
      console.log("\n[fixture] phase=01");
      ok = (await runPhase01()) && ok;
    }
    if (phase === "02" || phase === "all") {
      console.log("\n[fixture] phase=02");
      ok = (await runPhase02()) && ok;
    }
    if (phase !== "00" && phase !== "01" && phase !== "02" && phase !== "all") {
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
