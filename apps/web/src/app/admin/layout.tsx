import Link from "next/link";
import React from "react";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-4">
        <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">
          ← Back to projects
        </Link>
        <span className="text-gray-300">|</span>
        <h1 className="text-sm font-semibold text-gray-800 uppercase tracking-wide">
          Admin
        </h1>
        <nav className="ml-4 flex gap-4">
          <Link
            href="/admin/packs"
            className="text-sm text-blue-600 hover:underline"
          >
            Jurisdictional Packs
          </Link>
          <Link
            href="/metrics"
            className="text-sm text-blue-600 hover:underline"
          >
            Metrics
          </Link>
        </nav>
      </header>
      <main className="p-6 max-w-7xl mx-auto">{children}</main>
    </div>
  );
}
