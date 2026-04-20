/**
 * Letter render CLI.
 * Usage: pnpm letter:render --project <id>
 *
 * Implementation proceeds in Phase 06 (see prompts/07-phase-06-drafter-letter.md).
 */
async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const projectIdx = args.indexOf("--project");
  if (projectIdx === -1) {
    console.error("Usage: letter:render --project <id>");
    process.exit(1);
  }

  const projectId = args[projectIdx + 1];
  console.log(`[render] STUB — implement per prompts/07-phase-06-drafter-letter.md`);
  console.log(`[render] project=${projectId}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
