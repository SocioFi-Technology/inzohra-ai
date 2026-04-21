/**
 * Letter render CLI.
 * Usage: pnpm letter:render --project <uuid> [--round <n>]
 */

import { assembleLetter } from "./letter";
import * as fs from "fs";
import * as path from "path";

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const projectIdx = args.indexOf("--project");
  const roundIdx = args.indexOf("--round");

  if (projectIdx === -1 || !args[projectIdx + 1]) {
    console.error("Usage: letter:render --project <uuid> [--round <n>]");
    process.exit(1);
  }

  const projectId = args[projectIdx + 1];
  const round = roundIdx !== -1 ? parseInt(args[roundIdx + 1] ?? "1", 10) : 1;

  // Ensure output directory exists
  const outDir = path.resolve(process.cwd(), "inzohra-output");
  fs.mkdirSync(outDir, { recursive: true });

  console.log(`[render] project=${projectId} round=${round}`);
  await assembleLetter(projectId, round);
  console.log(`[render] Done. Outputs in inzohra-output/`);
}

main().catch((err: unknown) => {
  console.error("[render] ERROR:", err);
  process.exit(1);
});
