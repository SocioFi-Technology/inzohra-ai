/**
 * round-renderer.ts
 * Computes BV round typography for each finding based on the round it was raised
 * and the current review round.
 *
 * Rules:
 *   raised=1, current=1 → italic   (new in this round)
 *   raised=1, current=2 → bold     (unresolved from round 1)
 *   raised=1, current≥3 → underlined (still unresolved from round 1)
 *   raised=2, current=2 → italic
 *   raised=2, current≥3 → bold
 *   raised=3, current=3 → italic
 *   any other combination → normal
 */

export type Typography = "italic" | "bold" | "underlined" | "normal";

export interface RoundStyle {
  findingId: string;
  raisedInRound: number;
  currentRound: number;
  typography: Typography;
}

/**
 * Compute the display typography for a single finding.
 */
export function computeTypography(
  raisedInRound: number,
  currentRound: number,
): Typography {
  if (raisedInRound === currentRound) {
    // New comment in the current round → italic
    return "italic";
  }

  if (raisedInRound === 1) {
    if (currentRound === 2) return "bold";
    if (currentRound >= 3) return "underlined";
  }

  if (raisedInRound === 2) {
    if (currentRound >= 3) return "bold";
  }

  return "normal";
}

/**
 * Apply round styles to a list of findings.
 */
export function applyRoundStyles(
  findings: Array<{ finding_id: string; review_round: number }>,
  currentRound: number,
): RoundStyle[] {
  return findings.map((f) => ({
    findingId: f.finding_id,
    raisedInRound: f.review_round,
    currentRound,
    typography: computeTypography(f.review_round, currentRound),
  }));
}
