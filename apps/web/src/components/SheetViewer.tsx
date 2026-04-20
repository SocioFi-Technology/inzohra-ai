"use client";

import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";

// Point the worker at the bundled worker script.
if (typeof window !== "undefined") {
  pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;
}

type BBox = [number, number, number, number]; // [x1, y1, x2, y2] in PDF points

type BBoxHighlight = {
  id: string;
  bbox: BBox;
  label: string;
  color?: string;
};

type Props = {
  /** S3 URI of the document, e.g. "s3://inzohra-raw/{docId}/original.pdf" */
  documentS3Uri: string;
  /** 1-indexed page number to display */
  pageNumber: number;
  /** Page dimensions in PDF points (from PyMuPDF) */
  pageWidthPts: number;
  pageHeightPts: number;
  /** Optional bboxes to highlight */
  highlights?: BBoxHighlight[];
  /** Called when user clicks a highlight */
  onHighlightClick?: (id: string) => void;
  activeHighlightId?: string | null;
};

function s3UriToProxyUrl(uri: string): string {
  // s3://inzohra-raw/abc/original.pdf  →  /api/assets/inzohra-raw/abc/original.pdf
  return "/api/assets/" + uri.replace(/^s3:\/\//, "");
}

export function SheetViewer({
  documentS3Uri,
  pageNumber,
  pageWidthPts,
  pageHeightPts,
  highlights = [],
  onHighlightClick,
  activeHighlightId,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [canvasSize, setCanvasSize] = useState({ w: 0, h: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const pdfUrl = s3UriToProxyUrl(documentS3Uri);

  useEffect(() => {
    if (!canvasRef.current || !containerRef.current) return;
    let cancelled = false;

    setLoading(true);
    setError(null);

    (async () => {
      try {
        const pdf = await pdfjs.getDocument(pdfUrl).promise;
        if (cancelled) return;

        const page = await pdf.getPage(pageNumber);
        if (cancelled) return;

        const containerWidth = containerRef.current!.clientWidth || 800;
        const nativeVp = page.getViewport({ scale: 1 });
        const fitScale = (containerWidth - 16) / nativeVp.width;
        const viewport = page.getViewport({ scale: fitScale });

        setScale(fitScale);
        setCanvasSize({ w: viewport.width, h: viewport.height });

        const canvas = canvasRef.current!;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext("2d")!;

        await page.render({ canvasContext: ctx, viewport }).promise;
        if (!cancelled) setLoading(false);
      } catch (e) {
        if (!cancelled) {
          setError(String(e));
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdfUrl, pageNumber]);

  /**
   * Convert a PDF-point bbox to CSS pixel coordinates on the rendered canvas.
   *
   * PyMuPDF uses top-left origin (y increases downward), matching canvas/CSS.
   * So the transform is simply: css_px = pdf_pt * scale.
   */
  function bboxToCss(bbox: BBox) {
    const [x1, y1, x2, y2] = bbox;
    return {
      left: x1 * scale,
      top: y1 * scale,
      width: (x2 - x1) * scale,
      height: (y2 - y1) * scale,
    };
  }

  return (
    <div ref={containerRef} className="relative w-full overflow-auto bg-gray-700 flex justify-center">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center text-white text-sm">
          Rendering page {pageNumber}…
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center text-red-300 text-sm p-4">
          Failed to render PDF: {error}
        </div>
      )}

      <div className="relative inline-block">
        <canvas ref={canvasRef} className="block" />

        {/* Bbox overlay */}
        {!loading &&
          highlights.map((h) => {
            const css = bboxToCss(h.bbox);
            const isActive = h.id === activeHighlightId;
            return (
              <div
                key={h.id}
                role="button"
                tabIndex={0}
                onClick={() => onHighlightClick?.(h.id)}
                onKeyDown={(e) => e.key === "Enter" && onHighlightClick?.(h.id)}
                style={{
                  position: "absolute",
                  left: css.left,
                  top: css.top,
                  width: css.width,
                  height: css.height,
                  borderColor: h.color ?? "#3B82F6",
                  backgroundColor: isActive
                    ? `${h.color ?? "#3B82F6"}33`
                    : `${h.color ?? "#3B82F6"}11`,
                }}
                className={[
                  "border-2 rounded cursor-pointer transition-colors",
                  isActive ? "ring-2 ring-offset-1 ring-blue-400" : "",
                ].join(" ")}
                title={h.label}
              />
            );
          })}
      </div>
    </div>
  );
}
