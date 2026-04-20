/**
 * LetterAssembler — Phase 06.
 * Reads approved findings from Postgres, applies round typography, and writes:
 *   inzohra-output/<projectId>-round<N>-letter.json
 *   inzohra-output/<projectId>-round<N>-letter.pdf
 *   inzohra-output/<projectId>-round<N>-letter.docx
 * then inserts a row into letter_renders.
 *
 * PDF fonts: PDFKit built-in Helvetica / Helvetica-Bold / Helvetica-Oblique are used
 * as fallbacks for Calibri / Calibri-Bold / Calibri-Italic (Calibri is not bundled).
 * DOCX uses "Calibri" directly; Word will apply it if installed on the viewer's machine.
 */

import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";

// pdfkit ships as CJS; tsx resolves the default export correctly with esModuleInterop.
import PDFDocument from "pdfkit";

import {
  Document,
  Paragraph,
  TextRun,
  HeadingLevel,
  Packer,
  AlignmentType,
  UnderlineType,
} from "docx";

import { Client } from "pg";

import { BV_SANTA_ROSA_TEMPLATE } from "./templates/bv-santa-rosa";
import { applyRoundStyles } from "./round-renderer";
import type { Typography } from "./round-renderer";

// ---------------------------------------------------------------------------
// Discipline ordering (BV canonical)
// ---------------------------------------------------------------------------

const DISCIPLINE_ORDER = [
  "plan_integrity",
  "architectural",
  "accessibility",
  "energy",
  "electrical",
  "mechanical",
  "plumbing",
  "structural",
  "fire_life_safety",
  "calgreen",
] as const;

type Discipline = (typeof DISCIPLINE_ORDER)[number];

// ---------------------------------------------------------------------------
// DB row types (no @types/pg installed, so we type the shapes we need)
// ---------------------------------------------------------------------------

interface ProjectRow {
  project_id: string;
  permit_number: string;
  jurisdiction: string;
  project_address: string;
  applicant_name: string;
  project_description: string;
}

interface SubmittalRow {
  submittal_id: string;
  submittal_date: string; // DATE → JS string from pg
}

interface FindingRow {
  finding_id: string;
  project_id: string;
  submittal_id: string;
  review_round: number;
  discipline: string;
  rule_id: string | null;
  severity: string;
  requires_licensed_review: boolean;
  sheet_reference: { sheet_id: string; detail: string | null };
  evidence: unknown[];
  citations: Array<{
    code: string;
    section: string;
    jurisdiction: string;
    effective_date: string;
    frozen_text: string;
    retrieval_chain?: unknown[];
  }>;
  draft_comment_text: string;
  confidence: number;
  created_at: string;
  // joined from comment_drafts (may be null if table absent or no row)
  polished_text: string | null;
}

// ---------------------------------------------------------------------------
// JSON bundle types
// ---------------------------------------------------------------------------

export interface LetterBundle {
  project_id: string;
  submittal_id: string;
  review_round: number;
  jurisdiction: string;
  pack_version: string;
  generated_at: string;
  letterhead: {
    agency: string;
    reviewer: string;
  };
  project_block: {
    permit_number: string;
    address: string;
    applicant: string;
    description: string;
  };
  general_instructions: string;
  signature_block: {
    reviewer_name: string;
    title: string;
  };
  findings: Array<
    FindingRow & { comment_number: number; display_text: string; typography: Typography }
  >;
  round_typography: {
    round_1: "italic";
    round_2: "bold";
    round_3: "underlined";
  };
}

// ---------------------------------------------------------------------------
// DB helpers
// ---------------------------------------------------------------------------

async function fetchProject(client: Client, projectId: string): Promise<ProjectRow> {
  const res = await client.query<ProjectRow>(
    `SELECT project_id, permit_number, jurisdiction,
            project_address, applicant_name, project_description
     FROM projects WHERE project_id = $1`,
    [projectId],
  );
  if (res.rows.length === 0) {
    throw new Error(`Project not found: ${projectId}`);
  }
  return res.rows[0];
}

async function fetchSubmittal(client: Client, projectId: string): Promise<SubmittalRow> {
  // Take the most recent submittal for this project.
  const res = await client.query<SubmittalRow>(
    `SELECT submittal_id, submittal_date
     FROM submittals WHERE project_id = $1
     ORDER BY submittal_date DESC LIMIT 1`,
    [projectId],
  );
  if (res.rows.length === 0) {
    throw new Error(`No submittal found for project: ${projectId}`);
  }
  return res.rows[0];
}

/**
 * Fetch findings, left-joining comment_drafts for polished text.
 * If comment_drafts table doesn't exist we catch and retry without the join.
 */
async function fetchFindings(
  client: Client,
  projectId: string,
  round: number,
): Promise<FindingRow[]> {
  const withDrafts = `
    SELECT
      f.finding_id, f.project_id, f.submittal_id, f.review_round,
      f.discipline, f.rule_id, f.severity, f.requires_licensed_review,
      f.sheet_reference, f.evidence, f.citations,
      f.draft_comment_text, f.confidence, f.created_at,
      cd.polished_text
    FROM findings f
    LEFT JOIN comment_drafts cd
      ON cd.finding_id = f.finding_id
      AND cd.project_id = f.project_id
      AND cd.review_round = f.review_round
    WHERE f.project_id = $1 AND f.review_round <= $2
    ORDER BY f.review_round, f.discipline, f.created_at
  `;

  const withoutDrafts = `
    SELECT
      f.finding_id, f.project_id, f.submittal_id, f.review_round,
      f.discipline, f.rule_id, f.severity, f.requires_licensed_review,
      f.sheet_reference, f.evidence, f.citations,
      f.draft_comment_text, f.confidence, f.created_at,
      NULL::text AS polished_text
    FROM findings f
    WHERE f.project_id = $1 AND f.review_round <= $2
    ORDER BY f.review_round, f.discipline, f.created_at
  `;

  try {
    const res = await client.query<FindingRow>(withDrafts, [projectId, round]);
    return res.rows;
  } catch (err: unknown) {
    // If comment_drafts table doesn't exist, fall back to findings only.
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("comment_drafts") || msg.includes("does not exist")) {
      const res = await client.query<FindingRow>(withoutDrafts, [projectId, round]);
      return res.rows;
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// JSON bundle builder (exported for testing)
// ---------------------------------------------------------------------------

export function buildJsonBundle(
  project: ProjectRow,
  submittal: SubmittalRow,
  findings: FindingRow[],
  currentRound: number,
): LetterBundle {
  const tmpl = BV_SANTA_ROSA_TEMPLATE;

  // Apply round styles (finding-id → typography)
  const styles = applyRoundStyles(findings, currentRound);
  const styleMap = new Map(styles.map((s) => [s.findingId, s.typography]));

  // Group by discipline in canonical order, then number globally.
  let commentNumber = 0;
  const orderedFindings: LetterBundle["findings"] = [];

  for (const discipline of DISCIPLINE_ORDER) {
    const group = findings.filter((f) => f.discipline === discipline);
    for (const f of group) {
      commentNumber += 1;
      const typography = styleMap.get(f.finding_id) ?? "normal";
      const displayText = f.polished_text ?? f.draft_comment_text;
      orderedFindings.push({
        ...f,
        comment_number: commentNumber,
        display_text: displayText,
        typography,
      });
    }
  }

  // Findings whose discipline is not in DISCIPLINE_ORDER go at the end.
  const unordered = findings.filter(
    (f) => !(DISCIPLINE_ORDER as readonly string[]).includes(f.discipline),
  );
  for (const f of unordered) {
    commentNumber += 1;
    const typography = styleMap.get(f.finding_id) ?? "normal";
    orderedFindings.push({
      ...f,
      comment_number: commentNumber,
      display_text: f.polished_text ?? f.draft_comment_text,
      typography,
    });
  }

  return {
    project_id: project.project_id,
    submittal_id: submittal.submittal_id,
    review_round: currentRound,
    jurisdiction: project.jurisdiction,
    pack_version: "2022",
    generated_at: new Date().toISOString(),
    letterhead: {
      agency: tmpl.agencyName,
      reviewer: tmpl.reviewerName,
    },
    project_block: {
      permit_number: project.permit_number,
      address: project.project_address,
      applicant: project.applicant_name,
      description: project.project_description,
    },
    general_instructions: tmpl.generalInstructions,
    signature_block: {
      reviewer_name: tmpl.reviewerName,
      title: tmpl.reviewerTitle,
    },
    findings: orderedFindings,
    round_typography: {
      round_1: "italic",
      round_2: "bold",
      round_3: "underlined",
    },
  };
}

// ---------------------------------------------------------------------------
// PDF builder
// ---------------------------------------------------------------------------

const LABEL_MAP: Record<string, string> = {
  plan_integrity: "Plan Integrity",
  architectural: "Architectural",
  accessibility: "Accessibility",
  energy: "Energy (Title 24)",
  electrical: "Electrical",
  mechanical: "Mechanical",
  plumbing: "Plumbing",
  structural: "Structural",
  fire_life_safety: "Fire & Life Safety",
  calgreen: "CALGreen",
};

function disciplineLabel(disc: string): string {
  return LABEL_MAP[disc] ?? disc.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

async function writePdf(bundle: LetterBundle, outPath: string): Promise<void> {
  const tmpl = BV_SANTA_ROSA_TEMPLATE;

  return new Promise<void>((resolve, reject) => {
    const doc = new PDFDocument({
      size: tmpl.pageSize,
      margins: tmpl.margins,
      bufferPages: true,
    });

    const stream = fs.createWriteStream(outPath);
    doc.pipe(stream);

    // ---- Helpers -----------------------------------------------------------

    // PDFKit built-in fallbacks for Calibri (not bundled):
    //   Calibri          → Helvetica
    //   Calibri-Bold     → Helvetica-Bold
    //   Calibri-Italic   → Helvetica-Oblique
    const fontNormal = "Helvetica";
    const fontBold = "Helvetica-Bold";
    const fontItalic = "Helvetica-Oblique";

    function applyTypography(typography: Typography): void {
      switch (typography) {
        case "bold":
          doc.font(fontBold);
          break;
        case "italic":
          doc.font(fontItalic);
          break;
        case "underlined":
          // PDFKit does not have a built-in underline; we use normal font and
          // rely on the text option `underline: true`.
          doc.font(fontNormal);
          break;
        default:
          doc.font(fontNormal);
      }
    }

    const usableWidth =
      doc.page.width - tmpl.margins.left - tmpl.margins.right;
    const headerTop = tmpl.margins.top - 16;

    // ---- Header (first page) ----------------------------------------------
    doc.font(fontBold).fontSize(11);
    doc.text(`Bureau Veritas  |  Plan Check — ${tmpl.agencyName}`, tmpl.margins.left, headerTop, {
      width: usableWidth,
      align: "center",
    });
    doc.moveDown(0.5);

    // ---- Project block -----------------------------------------------------
    doc.font(fontBold).fontSize(tmpl.fontSize);
    doc.text("Project Information", { underline: true });
    doc.moveDown(0.3);
    doc.font(fontNormal).fontSize(tmpl.fontSize);

    const pb = bundle.project_block;
    const projLines = [
      `Permit Number:   ${pb.permit_number}`,
      `Address:         ${pb.address}`,
      `Applicant:       ${pb.applicant}`,
      `Description:     ${pb.description}`,
      `Submittal Date:  ${bundle.generated_at.slice(0, 10)}`,
      `Review Round:    ${bundle.review_round}`,
    ];
    for (const line of projLines) {
      doc.text(line, { lineGap: tmpl.lineGap });
    }
    doc.moveDown(0.8);

    // ---- General instructions ---------------------------------------------
    doc.font(fontBold).fontSize(tmpl.fontSize).text("General Instructions", { underline: true });
    doc.moveDown(0.3);
    doc.font(fontItalic).fontSize(tmpl.fontSize).text(bundle.general_instructions, {
      lineGap: tmpl.lineGap,
      width: usableWidth,
    });
    doc.moveDown(0.8);

    // ---- Findings grouped by discipline -----------------------------------
    const grouped = new Map<string, typeof bundle.findings>();
    for (const f of bundle.findings) {
      const disc = f.discipline;
      if (!grouped.has(disc)) grouped.set(disc, []);
      grouped.get(disc)!.push(f);
    }

    // Emit in canonical order, then any remainder.
    const emittedDiscs = new Set<string>();
    const emitGroup = (disc: string): void => {
      const group = grouped.get(disc);
      if (!group || group.length === 0) return;
      emittedDiscs.add(disc);

      doc.font(fontBold).fontSize(12).text(disciplineLabel(disc), {
        lineGap: tmpl.lineGap,
      });
      doc.moveDown(0.4);

      for (const f of group) {
        const sheetRef =
          f.sheet_reference.sheet_id !== ""
            ? `[${f.sheet_reference.sheet_id}${f.sheet_reference.detail ? ` — ${f.sheet_reference.detail}` : ""}] `
            : "";

        const prefix = `${f.comment_number}. ${sheetRef}`;
        const text = f.display_text;

        applyTypography(f.typography);
        doc.fontSize(tmpl.fontSize).text(`${prefix}${text}`, {
          lineGap: tmpl.lineGap,
          width: usableWidth,
          underline: f.typography === "underlined",
        });
        if (f.requires_licensed_review) {
          doc
            .font(fontItalic)
            .fontSize(9)
            .text("  ► Licensed professional review required.", {
              lineGap: 2,
            });
        }
        doc.moveDown(0.5);
      }
      doc.moveDown(0.3);
    };

    for (const disc of DISCIPLINE_ORDER) {
      emitGroup(disc);
    }
    // Emit any disciplines not in the canonical order.
    for (const disc of grouped.keys()) {
      if (!emittedDiscs.has(disc)) emitGroup(disc);
    }

    // ---- Signature block --------------------------------------------------
    doc.moveDown(1);
    doc.font(fontNormal).fontSize(tmpl.fontSize);
    doc.text(`Sincerely,`);
    doc.moveDown(0.5);
    doc.font(fontBold).text(bundle.signature_block.reviewer_name);
    doc.font(fontNormal).text(bundle.signature_block.title);

    // ---- Page numbers (applied to all buffered pages) ---------------------
    const pages = doc.bufferedPageRange();
    for (let i = 0; i < pages.count; i++) {
      doc.switchToPage(pages.start + i);
      const footerY = doc.page.height - tmpl.margins.bottom + 10;
      doc
        .font(fontNormal)
        .fontSize(9)
        .text(`Page ${i + 1} of ${pages.count}`, tmpl.margins.left, footerY, {
          width: usableWidth,
          align: "right",
        });
    }

    doc.end();

    stream.on("finish", resolve);
    stream.on("error", reject);
  });
}

// ---------------------------------------------------------------------------
// DOCX builder
// ---------------------------------------------------------------------------

async function writeDocx(bundle: LetterBundle, outPath: string): Promise<void> {
  const tmpl = BV_SANTA_ROSA_TEMPLATE;

  function makeRuns(text: string, typography: Typography): TextRun[] {
    const base = {
      text,
      font: "Calibri",
      size: tmpl.fontSize * 2, // docx size is in half-points
    };

    switch (typography) {
      case "bold":
        return [new TextRun({ ...base, bold: true })];
      case "italic":
        return [new TextRun({ ...base, italics: true })];
      case "underlined":
        return [new TextRun({ ...base, underline: { type: UnderlineType.SINGLE } })];
      default:
        return [new TextRun(base)];
    }
  }

  function labelParagraph(label: string): Paragraph {
    return new Paragraph({
      heading: HeadingLevel.HEADING_2,
      children: [
        new TextRun({
          text: label,
          font: "Calibri",
          bold: true,
          size: 24, // 12pt in half-points
        }),
      ],
    });
  }

  const allParagraphs: Paragraph[] = [];

  // ---- Header -----------------------------------------------------------
  allParagraphs.push(
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({
          text: `Bureau Veritas  |  Plan Check — ${tmpl.agencyName}`,
          font: "Calibri",
          bold: true,
          size: 24,
        }),
      ],
    }),
    new Paragraph({ children: [] }), // spacer
  );

  // ---- Project block ----------------------------------------------------
  const pb = bundle.project_block;
  const projectLines = [
    `Permit Number: ${pb.permit_number}`,
    `Address: ${pb.address}`,
    `Applicant: ${pb.applicant}`,
    `Description: ${pb.description}`,
    `Submittal Date: ${bundle.generated_at.slice(0, 10)}`,
    `Review Round: ${bundle.review_round}`,
  ];
  allParagraphs.push(
    labelParagraph("Project Information"),
    ...projectLines.map(
      (l) =>
        new Paragraph({
          children: [new TextRun({ text: l, font: "Calibri", size: tmpl.fontSize * 2 })],
        }),
    ),
    new Paragraph({ children: [] }),
  );

  // ---- General instructions ---------------------------------------------
  allParagraphs.push(
    labelParagraph("General Instructions"),
    new Paragraph({
      children: [
        new TextRun({
          text: bundle.general_instructions,
          font: "Calibri",
          italics: true,
          size: tmpl.fontSize * 2,
        }),
      ],
    }),
    new Paragraph({ children: [] }),
  );

  // ---- Findings ---------------------------------------------------------
  const grouped = new Map<string, typeof bundle.findings>();
  for (const f of bundle.findings) {
    if (!grouped.has(f.discipline)) grouped.set(f.discipline, []);
    grouped.get(f.discipline)!.push(f);
  }

  const emittedDiscs = new Set<string>();

  const emitDocxGroup = (disc: string): void => {
    const group = grouped.get(disc);
    if (!group || group.length === 0) return;
    emittedDiscs.add(disc);

    allParagraphs.push(labelParagraph(disciplineLabel(disc)));

    for (const f of group) {
      const sheetRef =
        f.sheet_reference.sheet_id !== ""
          ? `[${f.sheet_reference.sheet_id}${f.sheet_reference.detail ? ` — ${f.sheet_reference.detail}` : ""}] `
          : "";

      const prefix = `${f.comment_number}. ${sheetRef}`;

      allParagraphs.push(
        new Paragraph({
          children: [
            new TextRun({
              text: prefix,
              font: "Calibri",
              bold: true,
              size: tmpl.fontSize * 2,
            }),
            ...makeRuns(f.display_text, f.typography),
          ],
        }),
      );

      if (f.requires_licensed_review) {
        allParagraphs.push(
          new Paragraph({
            children: [
              new TextRun({
                text: "  \u25BA Licensed professional review required.",
                font: "Calibri",
                italics: true,
                size: 18, // 9pt
              }),
            ],
          }),
        );
      }
    }

    allParagraphs.push(new Paragraph({ children: [] }));
  };

  for (const disc of DISCIPLINE_ORDER) {
    emitDocxGroup(disc);
  }
  for (const disc of grouped.keys()) {
    if (!emittedDiscs.has(disc)) emitDocxGroup(disc);
  }

  // ---- Signature --------------------------------------------------------
  allParagraphs.push(
    new Paragraph({ children: [new TextRun({ text: "Sincerely,", font: "Calibri", size: tmpl.fontSize * 2 })] }),
    new Paragraph({ children: [] }),
    new Paragraph({
      children: [
        new TextRun({ text: bundle.signature_block.reviewer_name, font: "Calibri", bold: true, size: tmpl.fontSize * 2 }),
      ],
    }),
    new Paragraph({
      children: [
        new TextRun({ text: bundle.signature_block.title, font: "Calibri", size: tmpl.fontSize * 2 }),
      ],
    }),
  );

  const docxDoc = new Document({
    sections: [
      {
        properties: {},
        children: allParagraphs,
      },
    ],
  });

  const buf = await Packer.toBuffer(docxDoc);
  fs.writeFileSync(outPath, buf);
}

// ---------------------------------------------------------------------------
// DB: insert letter_renders row
// ---------------------------------------------------------------------------

async function insertLetterRender(
  client: Client,
  opts: {
    projectId: string;
    round: number;
    pdfPath: string;
    docxPath: string;
    jsonPath: string;
    findingCount: number;
  },
): Promise<void> {
  const renderId = crypto.randomUUID();
  await client.query(
    `INSERT INTO letter_renders
       (render_id, project_id, review_round, pdf_path, docx_path, json_path, finding_count, created_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
     ON CONFLICT DO NOTHING`,
    [
      renderId,
      opts.projectId,
      opts.round,
      opts.pdfPath,
      opts.docxPath,
      opts.jsonPath,
      opts.findingCount,
    ],
  );
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

export async function assembleLetter(projectId: string, round = 1): Promise<void> {
  const dbUrl = process.env["DATABASE_URL"];
  if (!dbUrl) {
    throw new Error("DATABASE_URL environment variable is not set");
  }

  const client = new Client({ connectionString: dbUrl });
  await client.connect();

  try {
    const project = await fetchProject(client, projectId);
    const submittal = await fetchSubmittal(client, projectId);
    const findings = await fetchFindings(client, projectId, round);

    const bundle = buildJsonBundle(project, submittal, findings, round);

    // Ensure output directory exists
    const outDir = path.resolve(process.cwd(), "inzohra-output");
    fs.mkdirSync(outDir, { recursive: true });

    const base = `${projectId}-round${round}-letter`;
    const jsonPath = path.join(outDir, `${base}.json`);
    const pdfPath = path.join(outDir, `${base}.pdf`);
    const docxPath = path.join(outDir, `${base}.docx`);

    // 1. JSON bundle
    fs.writeFileSync(jsonPath, JSON.stringify(bundle, null, 2), "utf8");
    console.log(`[letter] JSON written → ${jsonPath}`);

    // 2. PDF
    await writePdf(bundle, pdfPath);
    console.log(`[letter] PDF  written → ${pdfPath}`);

    // 3. DOCX
    await writeDocx(bundle, docxPath);
    console.log(`[letter] DOCX written → ${docxPath}`);

    // 4. letter_renders row
    await insertLetterRender(client, {
      projectId,
      round,
      pdfPath,
      docxPath,
      jsonPath,
      findingCount: bundle.findings.length,
    });

    console.log(
      `[letter] Done. ${bundle.findings.length} finding(s) rendered for project ${projectId}, round ${round}.`,
    );
  } finally {
    await client.end();
  }
}
