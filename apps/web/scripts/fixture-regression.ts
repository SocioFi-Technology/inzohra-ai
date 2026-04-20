// Fixture regression harness. Invoked by `pnpm test:fixture --phase <n>`.
// Exits 0 on pass, 1 on regression.

const phase = process.argv.includes("--phase")
  ? process.argv[process.argv.indexOf("--phase") + 1]
  : "all";

console.log(`[fixture] phase=${phase}`);
console.log("[fixture] STUB — implement per prompts/01-phase-00-foundations.md acceptance criteria.");
process.exit(0);
