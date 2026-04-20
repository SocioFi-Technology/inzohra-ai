/**
 * The authoritative list of rule IDs that set `requires_licensed_review = true`.
 * Any rule not in this list must not set the flag. Any rule in this list must always set it.
 *
 * See docs/17-invariants-and-risks.md invariant #6.
 */
export const CRITICAL_PATH_RULES: ReadonlySet<string> = new Set([
  // Structural
  "STR-SHEAR-ADEQUACY",
  "STR-HOLDOWN-CAPACITY",
  "STR-FRAMING-SIZING-ADEQUACY",
  "STR-FOUNDATION-ADEQUACY",

  // Architectural
  "ARCH-OCCUPANT-LOAD-CALC",
  "ARCH-EGRESS-CAPACITY-HIGH-LOAD",

  // Fire / Life Safety
  "FIRE-SEP-RATING-ADEQUACY",
  "FIRE-R21-TYPE-V-ONE-HOUR",
  "FIRE-OPENING-PROTECTIVE-ADEQUACY",

  // Electrical
  "ELEC-SERVICE-SIZE-ADEQUACY",

  // Mechanical
  "MECH-LOAD-CALC-ADEQUACY"
]);

export function requiresLicensedReview(ruleId: string): boolean {
  return CRITICAL_PATH_RULES.has(ruleId);
}
