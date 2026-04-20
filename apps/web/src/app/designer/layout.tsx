import Link from "next/link";
import React from "react";

export const metadata = {
  title: "Designer Portal — Inzohra-ai",
  description: "Submit plan sets and checklists for structured review.",
};

export default function DesignerLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-lg font-bold text-gray-900">Designer Portal</h1>
            <nav className="flex items-center gap-4">
              <Link
                href="/designer/upload"
                className="text-sm text-gray-600 hover:text-blue-600 transition-colors"
              >
                Upload
              </Link>
              <Link
                href="/designer"
                className="text-sm text-gray-600 hover:text-blue-600 transition-colors"
              >
                My Reports
              </Link>
            </nav>
          </div>
          <Link
            href="/"
            className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            &larr; Back to Inzohra-ai
          </Link>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
