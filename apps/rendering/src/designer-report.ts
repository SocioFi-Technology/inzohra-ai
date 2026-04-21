/**
 * Designer checklist report renderer — Phase 09.
 * Separate rendering template from the reviewer letter.
 *
 * Reads checklist_queries + checklist_answers for a given project/report,
 * writes:
 *   inzohra-output/<reportId>-designer-report.pdf
 *   inzohra-output/<reportId>-designer-report.json
 * then updates the designer_reports row with paths, counts, and status='complete'.
 */

import PDFDocument from "pdfkit";
import * as fs from "fs";
import * as path from "path";
import { Pool } from "pg";

// ---------------------------------------------------------------------------
// DB row types
// ---------------------------------------------------------------------------

interface QueryRow {
  query_id: string;
  item_id: string;
  description: string;
  code_ref: string | null;
  threshold_value: number | null;
  threshold_unit: string | null;
}

interface AnswerRow {
  answer_id: string;
  query_id: string;
  status: "green" | "amber" | "red" | "unknown";
  measured_value: number | null;
  unit: string | null;
  required_value: number | null;
  code_citation: object | null;
  confidence: number;
  answer_text: string;
}

interface DesignerReportRow {
  report_id: string;
  project_id: string;
}

interface ProjectRow {
  address: string;
  permit_number: string;
}

// ---------------------------------------------------------------------------
// JSON bundle type (exported for testing)
// ---------------------------------------------------------------------------

export interface DesignerReportBundle {
  report_id: string;
  project_id: string;
  created_at: string;
  summary: {
    total: number;
    green: number;
    amber: number;
    red: number;
    unknown: number;
  };
  queries: Array<{
    query_id: string;
    item_id: string;
    description: string;
    code_ref: string | null;
    threshold_value: number | null;
    threshold_unit: string | null;
    answer: {
      answer_id: string;
      status: "green" | "amber" | "red" | "unknown";
      measured_value: number | null;
      unit: string | null;
      required_value: number | null;
      code_citation: object | null;
      confidence: number;
      answer_text: string;
    } | null;
  }>;
}

// ---------------------------------------------------------------------------
// Status ordering: red → amber → green → unknown
// ---------------------------------------------------------------------------

const STATUS_ORDER: Record<"green" | "amber" | "red" | "unknown", number> = {
  red: 0,
  amber: 1,
  green: 2,
  unknown: 3,
};

function statusSymbol(status: "green" | "amber" | "red" | "unknown"): string {
  switch (status) {
    case "green":
      return "\u2713"; // ✓
    case "amber":
      return "\u26A0"; // ⚠
    case "red":
      return "\u2717"; // ✗
    default:
      return "?";
  }
}

function statusLabel(status: "green" | "amber" | "red" | "unknown"): string {
  switch (status) {
    case "green":
      return "PASS";
    case "amber":
      return "WARN";
    case "red":
      return "FAIL";
    default:
      return "UNKNOWN";
  }
}

// ---------------------------------------------------------------------------
// DB helpers
// ---------------------------------------------------------------------------

async function fetchReportRow(
  pool: Pool,
  reportId: string,
): Promise<DesignerReportRow> {
  const res = await pool.query<DesignerReportRow>(
    `SELECT report_id, project_id FROM designer_reports WHERE report_id = $1`,
    [reportId],
  );
  if (res.rows.length === 0) {
    throw new Error(`designer_reports row not found for report_id=${reportId}`);
  }
  return res.rows[0];
}

async function fetchProject(pool: Pool, projectId: string): Promise<ProjectRow> {
  const res = await pool.query<ProjectRow>(
    `SELECT address, permit_number FROM projects WHERE project_id = $1`,
    [projectId],
  );
  if (res.rows.length === 0) {
    // Return a placeholder so the render still works without a projects row
    return { address: "Unknown address", permit_number: "Unknown" };
  }
  return res.rows[0];
}

async function fetchQueries(pool: Pool, projectId: string): Promise<QueryRow[]> {
  const res = await pool.query<QueryRow>(
    `SELECT query_id, item_id, description, code_ref, threshold_value, threshold_unit
     FROM checklist_queries
     WHERE project_id = $1
     ORDER BY item_id`,
    [projectId],
  );
  return res.rows;
}

async function fetchAnswers(
  pool: Pool,
  projectId: string,
): Promise<Map<string, AnswerRow>> {
  const res = await pool.query<AnswerRow>(
    `SELECT answer_id, query_id, status, measured_value, unit, required_value,
            code_citation, confidence, answer_text
     FROM checklist_answers
     WHERE project_id = $1`,
    [projectId],
  );
  const map = new Map<string, AnswerRow>();
  for (const row of res.rows) {
    map.set(row.query_id, row);
  }
  return map;
}

// ---------------------------------------------------------------------------
// JSON bundle builder (exported for testing)
// ---------------------------------------------------------------------------

export function buildDesignerReportBundle(
  reportRow: DesignerReportRow,
  queries: QueryRow[],
  answerMap: Map<string, AnswerRow>,
): DesignerReportBundle {
  // Sort queries: red → amber → green → unknown
  const sorted = [...queries].sort((a, b) => {
    const aStatus = answerMap.get(a.query_id)?.status ?? "unknown";
    const bStatus = answerMap.get(b.query_id)?.status ?? "unknown";
    return STATUS_ORDER[aStatus] - STATUS_ORDER[bStatus];
  });

  let green = 0;
  let amber = 0;
  let red = 0;
  let unknown = 0;

  const bundleQueries = sorted.map((q) => {
    const ans = answerMap.get(q.query_id) ?? null;
    const status = ans?.status ?? "unknown";
    switch (status) {
      case "green":
        green++;
        break;
      case "amber":
        amber++;
        break;
      case "red":
        red++;
        break;
      default:
        unknown++;
    }
    return {
      query_id: q.query_id,
      item_id: q.item_id,
      description: q.description,
      code_ref: q.code_ref,
      threshold_value: q.threshold_value,
      threshold_unit: q.threshold_unit,
      answer: ans
        ? {
            answer_id: ans.answer_id,
            status: ans.status,
            measured_value: ans.measured_value,
            unit: ans.unit,
            required_value: ans.required_value,
            code_citation: ans.code_citation,
            confidence: ans.confidence,
            answer_text: ans.answer_text,
          }
        : null,
    };
  });

  return {
    report_id: reportRow.report_id,
    project_id: reportRow.project_id,
    created_at: new Date().toISOString(),
    summary: {
      total: queries.length,
      green,
      amber,
      red,
      unknown,
    },
    queries: bundleQueries,
  };
}

// ---------------------------------------------------------------------------
// PDF builder
// ---------------------------------------------------------------------------

async function writePdf(
  bundle: DesignerReportBundle,
  project: ProjectRow,
  outPath: string,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const doc = new PDFDocument({
      size: "LETTER",
      margins: { top: 72, bottom: 72, left: 72, right: 72 },
      bufferPages: true,
    });

    const stream = fs.createWriteStream(outPath);
    doc.pipe(stream);

    const fontNormal = "Helvetica";
    const fontBold = "Helvetica-Bold";
    const fontItalic = "Helvetica-Oblique";
    const fontSize = 10;
    const usableWidth = doc.page.width - 72 - 72;

    // ---- Header ------------------------------------------------------------
    doc
      .font(fontBold)
      .fontSize(13)
      .text("Inzohra Designer Pre-Check Report", 72, 72, {
        width: usableWidth,
        align: "center",
      });
    doc.moveDown(0.4);

    // Project address line
    doc
      .font(fontNormal)
      .fontSize(fontSize)
      .text(`Project: ${project.address}  |  Permit: ${project.permit_number}`, {
        width: usableWidth,
        align: "center",
      });
    doc.moveDown(0.3);
    doc
      .font(fontNormal)
      .fontSize(9)
      .text(`Generated: ${bundle.created_at.slice(0, 10)}`, {
        width: usableWidth,
        align: "center",
      });
    doc.moveDown(1);

    // ---- Summary table -----------------------------------------------------
    doc.font(fontBold).fontSize(fontSize).text("Summary", { underline: true });
    doc.moveDown(0.4);

    const { total, green, amber, red, unknown } = bundle.summary;
    const summaryLines = [
      `Total Items:  ${total}`,
      `Passed (green):   ${green}`,
      `Warning (amber):  ${amber}`,
      `Failed (red):     ${red}`,
      `Not checked:      ${unknown}`,
    ];
    doc.font(fontNormal).fontSize(fontSize);
    for (const line of summaryLines) {
      doc.text(line, { lineGap: 2 });
    }
    doc.moveDown(1);

    // ---- Per-question sections ---------------------------------------------
    doc.font(fontBold).fontSize(fontSize).text("Checklist Items", { underline: true });
    doc.moveDown(0.5);

    for (const q of bundle.queries) {
      const status = q.answer?.status ?? "unknown";
      const symbol = statusSymbol(status);
      const label = statusLabel(status);

      // Choose accent font for the status badge
      switch (status) {
        case "green":
          doc.font(fontBold);
          break;
        case "amber":
          doc.font(fontBold);
          break;
        case "red":
          doc.font(fontBold);
          break;
        default:
          doc.font(fontNormal);
      }

      // Item header: "[✓ PASS]  ITEM_ID  Description..."
      const headerText = `${symbol} ${label}  [${q.item_id}]  ${q.description}`;
      doc.fontSize(fontSize).text(headerText, {
        width: usableWidth,
        lineGap: 2,
      });

      // Code reference
      if (q.code_ref) {
        doc
          .font(fontItalic)
          .fontSize(9)
          .text(`  Code ref: ${q.code_ref}`, { lineGap: 2 });
      }

      // Threshold
      if (q.threshold_value !== null && q.threshold_unit !== null) {
        doc
          .font(fontNormal)
          .fontSize(9)
          .text(`  Threshold: ${q.threshold_value} ${q.threshold_unit}`, { lineGap: 2 });
      }

      // Answer text
      if (q.answer) {
        const ans = q.answer;
        doc
          .font(fontNormal)
          .fontSize(fontSize)
          .text(`  ${ans.answer_text}`, {
            width: usableWidth - 10,
            lineGap: 2,
          });

        if (ans.measured_value !== null) {
          const unit = ans.unit ?? "";
          const required = ans.required_value !== null ? ` (required: ${ans.required_value} ${unit})` : "";
          doc
            .font(fontNormal)
            .fontSize(9)
            .text(`  Measured: ${ans.measured_value} ${unit}${required}`, { lineGap: 2 });
        }

        if (ans.confidence < 1) {
          doc
            .font(fontItalic)
            .fontSize(9)
            .text(`  Confidence: ${(ans.confidence * 100).toFixed(0)}%`, { lineGap: 2 });
        }
      } else {
        doc
          .font(fontItalic)
          .fontSize(9)
          .text("  No answer recorded.", { lineGap: 2 });
      }

      doc.moveDown(0.6);
    }

    // ---- Footer (all pages) -----------------------------------------------
    doc.moveDown(1);
    doc
      .font(fontItalic)
      .fontSize(8)
      .text(
        "This pre-check report is informational only. " +
          "Final code compliance determination is the responsibility of the licensed plan reviewer.",
        { width: usableWidth, align: "center" },
      );

    // Page numbers
    const pages = doc.bufferedPageRange();
    for (let i = 0; i < pages.count; i++) {
      doc.switchToPage(pages.start + i);
      const footerY = doc.page.height - 72 + 10;
      doc
        .font(fontNormal)
        .fontSize(9)
        .text(`Page ${i + 1} of ${pages.count}`, 72, footerY, {
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
// DB: update designer_reports row
// ---------------------------------------------------------------------------

async function updateDesignerReport(
  pool: Pool,
  reportId: string,
  opts: {
    pdfPath: string;
    jsonPath: string;
    queryCount: number;
    greenCount: number;
    amberCount: number;
    redCount: number;
  },
): Promise<void> {
  await pool.query(
    `UPDATE designer_reports
     SET pdf_path = $1,
         json_path = $2,
         query_count = $3,
         green_count = $4,
         amber_count = $5,
         red_count = $6,
         status = 'complete'
     WHERE report_id = $7`,
    [
      opts.pdfPath,
      opts.jsonPath,
      opts.queryCount,
      opts.greenCount,
      opts.amberCount,
      opts.redCount,
      reportId,
    ],
  );
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

export async function assembleDesignerReport(
  projectId: string,
  reportId: string,
): Promise<void> {
  const dbUrl = process.env["DATABASE_URL"];
  if (!dbUrl) {
    throw new Error("DATABASE_URL environment variable is not set");
  }

  const pool = new Pool({ connectionString: dbUrl });

  try {
    const reportRow = await fetchReportRow(pool, reportId);
    if (reportRow.project_id !== projectId) {
      throw new Error(
        `report_id ${reportId} belongs to project ${reportRow.project_id}, not ${projectId}`,
      );
    }

    const project = await fetchProject(pool, projectId);
    const queries = await fetchQueries(pool, projectId);
    const answerMap = await fetchAnswers(pool, projectId);

    const bundle = buildDesignerReportBundle(reportRow, queries, answerMap);

    // Ensure output directory exists
    const outDir = path.resolve(process.cwd(), "inzohra-output");
    fs.mkdirSync(outDir, { recursive: true });

    const jsonPath = path.join(outDir, `${reportId}-designer-report.json`);
    const pdfPath = path.join(outDir, `${reportId}-designer-report.pdf`);

    // 1. JSON bundle
    fs.writeFileSync(jsonPath, JSON.stringify(bundle, null, 2), "utf8");
    console.log(`[designer-report] JSON written → ${jsonPath}`);

    // 2. PDF
    await writePdf(bundle, project, pdfPath);
    console.log(`[designer-report] PDF  written → ${pdfPath}`);

    // 3. Update DB row
    await updateDesignerReport(pool, reportId, {
      pdfPath,
      jsonPath,
      queryCount: bundle.summary.total,
      greenCount: bundle.summary.green,
      amberCount: bundle.summary.amber,
      redCount: bundle.summary.red,
    });

    console.log(
      `[designer-report] Done. ` +
        `${bundle.summary.total} item(s) — ` +
        `${bundle.summary.green} green / ` +
        `${bundle.summary.amber} amber / ` +
        `${bundle.summary.red} red`,
    );
  } finally {
    await pool.end();
  }
}
