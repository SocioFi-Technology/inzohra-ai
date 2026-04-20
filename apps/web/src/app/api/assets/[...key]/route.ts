/**
 * Proxy route for MinIO assets.
 * Fetches from the local MinIO instance (same-origin to avoid CORS in dev).
 *
 * Usage:
 *   /api/assets/inzohra-raster/{docId}/p001/extract.png
 *   /api/assets/inzohra-raw/{docId}/original.pdf
 */
import { NextResponse } from "next/server";

const S3_ENDPOINT = process.env.S3_ENDPOINT ?? "http://localhost:9000";

export async function GET(
  _req: Request,
  { params }: { params: { key: string[] } }
) {
  const objectPath = params.key.join("/");
  const url = `${S3_ENDPOINT}/${objectPath}`;

  try {
    const upstream = await fetch(url);
    if (!upstream.ok) {
      return NextResponse.json(
        { error: `Upstream ${upstream.status}: ${objectPath}` },
        { status: upstream.status }
      );
    }

    const contentType =
      upstream.headers.get("content-type") ?? "application/octet-stream";

    return new NextResponse(upstream.body, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=86400, immutable",
      },
    });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 502 });
  }
}
