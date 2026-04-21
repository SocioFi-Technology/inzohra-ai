import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import * as fs from "fs";
import * as path from "path";

type RenderPaths = {
  pdf_path: string;
  docx_path: string;
};

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const type = req.nextUrl.searchParams.get("type") ?? "pdf";

  let render: RenderPaths | null = null;
  try {
    const res = await pool.query(
      `SELECT pdf_path, docx_path FROM letter_renders WHERE project_id = $1 ORDER BY created_at DESC LIMIT 1`,
      [params.id],
    );
    render = (res.rows[0] as RenderPaths) ?? null;
  } catch {
    render = null;
  }

  if (!render) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  const rawPath = type === "docx" ? render.docx_path : render.pdf_path;

  // Try the stored path first, then the rendering-service output directory
  let filePath = rawPath;
  if (!fs.existsSync(filePath)) {
    filePath = path.join(
      process.cwd(),
      "..",
      "..",
      "services",
      "rendering",
      "inzohra-output",
      path.basename(rawPath),
    );
  }

  if (!fs.existsSync(filePath)) {
    return NextResponse.json({ error: "file not found" }, { status: 404 });
  }

  const buf = fs.readFileSync(filePath);
  const ext = type === "docx" ? "docx" : "pdf";
  const mime =
    type === "docx"
      ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      : "application/pdf";

  return new NextResponse(buf, {
    headers: {
      "Content-Type": mime,
      "Content-Disposition": `attachment; filename="letter-round-1.${ext}"`,
    },
  });
}
