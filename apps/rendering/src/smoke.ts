/**
 * Rendering service smoke test.
 * Invoked by: `pnpm --filter @inzohra/rendering smoke`
 */
function main(): void {
  const required = ["DATABASE_URL", "S3_ENDPOINT"];
  const missing = required.filter((k) => !process.env[k]);
  if (missing.length > 0) {
    console.error(`RENDERING SMOKE: FAIL — missing env: ${missing.join(", ")}`);
    process.exit(1);
  }

  // Verify dependencies import.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  require("pdfkit");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  require("docx");

  console.log("RENDERING SMOKE: OK");
}

main();
