/**
 * BV · Santa Rosa letter template.
 * Calibri typography, BV header/footer, margins per skills/jurisdiction-santa-rosa/SKILL.md.
 */
export const BV_SANTA_ROSA_TEMPLATE = {
  fontFamily: "Calibri",
  margins: { top: 72, bottom: 72, left: 63, right: 63 },
  fontSize: 11,
  roundTypography: {
    1: "italic" as const,
    2: "bold" as const,
    3: "underline" as const
  }
};
