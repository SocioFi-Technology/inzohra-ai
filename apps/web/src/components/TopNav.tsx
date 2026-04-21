"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavLink = {
  label: string;
  href: string;
};

const NAV_LINKS: NavLink[] = [
  { label: "Projects", href: "/" },
  { label: "Metrics", href: "/metrics" },
  { label: "Triage", href: "/triage" },
  { label: "Packs", href: "/admin/packs" },
];

export function TopNav() {
  const pathname = usePathname();

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <nav className="h-12 bg-white sticky top-0 z-50 border-b border-gray-200 flex items-center px-4 gap-6">
      {/* Logo */}
      <Link
        href="/"
        className="flex items-center gap-1.5 text-indigo-700 font-bold text-sm shrink-0"
      >
        <span className="text-base leading-none">&#11043;</span>
        <span>Inzohra-ai</span>
      </Link>

      {/* Middle nav links */}
      <div className="flex items-center gap-1">
        {NAV_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              isActive(link.href)
                ? "bg-indigo-50 text-indigo-700"
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-50"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </div>

      {/* Right: New Project */}
      <div className="ml-auto">
        <Link
          href="/projects/new"
          className="bg-indigo-600 text-white text-sm font-medium rounded px-3 py-1.5 hover:bg-indigo-700 transition-colors"
        >
          + New Project
        </Link>
      </div>
    </nav>
  );
}
