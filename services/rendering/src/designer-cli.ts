/**
 * Designer report render CLI — Phase 09.
 * Usage: tsx src/designer-cli.ts --report <uuid>
 *
 * The project_id is looked up from the designer_reports row.
 * DATABASE_URL must be set in the environment.
 */

import { assembleDesignerReport } from "./designer-report";
import * as fs from "fs";
import * as path from "path";

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const reportIdx = args.indexOf("--report");

  if (reportIdx === -1 || !args[reportIdx + 1]) {
    console.error("Usage: tsx src/designer-cli.ts --report <uuid>");
    process.exit(1);
  }

  const reportId = args[reportIdx + 1]!;

  // Ensure output directory exists
  const outDir = path.resolve(process.cwd(), "inzohra-output");
  fs.mkdirSync(outDir, { recursive: true });

  console.log(`[designer-render] report=${reportId}`);

  // Resolve project_id from DB (assembleDesignerReport reads the designer_reports row
  // itself, so we pass a placeholder projectId here and let it validate the match).
  // We still need to pass a projectId — read it from the DB first.
  const { Pool } = await import("pg");
  const dbUrl = process.env["DATABASE_URL"];
  if (!dbUrl) {
    console.error("[designer-render] ERROR: DATABASE_URL not set");
    process.exit(1);
  }

  const pool = new Pool({ connectionString: dbUrl });
  let projectId: string;
  try {
    const res = await pool.query<{ project_id: string }>(
      `SELECT project_id FROM designer_reports WHERE report_id = $1`,
      [reportId],
    );
    if (res.rows.length === 0) {
      console.error(`[designer-render] ERROR: no designer_reports row for report_id=${reportId}`);
      process.exit(1);
    }
    projectId = res.rows[0].project_id;
  } finally {
    await pool.end();
  }

  await assembleDesignerReport(projectId, reportId);
  console.log("[designer-render] Done. Outputs in inzohra-output/");
}

main().catch((err: unknown) => {
  console.error("[designer-render] ERROR:", err);
  process.exit(1);
});
