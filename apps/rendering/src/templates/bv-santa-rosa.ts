/**
 * BV · Santa Rosa letter template.
 * Calibri typography, BV header/footer, margins per skills/jurisdiction-santa-rosa/SKILL.md.
 *
 * Points reference: 1 inch = 72 pts.
 * Top/bottom margins: 1 inch = 72 pts.
 * Left/right margins: 0.875 inch = 63 pts.
 */

export const BV_SANTA_ROSA_TEMPLATE = {
  fontFamily: "Calibri",
  fontFamilyBold: "Calibri-Bold",
  fontFamilyItalic: "Calibri-Italic",
  margins: { top: 72, bottom: 72, left: 63, right: 63 }, // 1" top/bot, 0.875" left/right in pts
  fontSize: 11,
  lineGap: 4,
  headerHeight: 60,
  footerHeight: 40,
  pageSize: "LETTER" as const,
  roundTypography: {
    1: "italic" as const,
    2: "bold" as const,
    3: "underlined" as const,
  },
  agencyName: "City of Santa Rosa · Building Division",
  reviewerName: "Bureau Veritas",
  reviewerTitle: "Plan Check Engineer",
  generalInstructions: [
    "All corrections shall be made on the original drawings and resubmitted.",
    "Resubmittals must include a written response to each correction item.",
    "Plan check turnaround: 10 business days for resubmittals.",
    "Questions regarding this correction letter should be directed to the plan check engineer.",
  ].join(" "),
};
