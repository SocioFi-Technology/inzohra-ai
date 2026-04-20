import Link from "next/link";
import { pool } from "@/lib/db";

interface PackHeader {
  pack_id: string;
  jurisdiction: string;
  version: string;
  effective_date: string;
  superseded_by: string | null;
}

interface AmendmentRow {
  amendment_id: string;
  base_section_id: string;
  operation: string;
  amendment_text: string;
  effective_date: string;
}

interface PolicyRow {
  policy_id: string;
  title: string;
  applies_to_sections: string[];
  effective_date: string;
  body_text: string;
}

interface ChecklistRow {
  checklist_id: string;
  occupancy_class: string;
  item_count: number;
  version: string;
}

interface DrafterExampleRow {
  example_id: string;
  discipline: string;
  severity: string;
  polished_output: string;
}

async function fetchPackHeader(packId: string): Promise<PackHeader | null> {
  try {
    const res = await pool.query<PackHeader>(
      `SELECT pack_id, jurisdiction, version, effective_date, superseded_by
       FROM jurisdictional_packs WHERE pack_id = $1`,
      [packId],
    );
    return res.rows[0] ?? null;
  } catch {
    return null;
  }
}

async function fetchAmendments(packId: string): Promise<AmendmentRow[]> {
  try {
    const res = await pool.query<AmendmentRow>(
      `SELECT amendment_id, base_section_id, operation,
              LEFT(amendment_text, 120) AS amendment_text, effective_date
       FROM amendments WHERE pack_id = $1 ORDER BY effective_date DESC`,
      [packId],
    );
    return res.rows;
  } catch {
    return [];
  }
}

async function fetchPolicies(packId: string): Promise<PolicyRow[]> {
  try {
    const res = await pool.query<PolicyRow>(
      `SELECT policy_id, title, applies_to_sections, effective_date,
              LEFT(body_text, 120) AS body_text
       FROM agency_policies WHERE pack_id = $1 ORDER BY effective_date DESC`,
      [packId],
    );
    return res.rows;
  } catch {
    return [];
  }
}

async function fetchChecklists(packId: string): Promise<ChecklistRow[]> {
  try {
    const res = await pool.query<ChecklistRow>(
      `SELECT checklist_id, occupancy_class,
              jsonb_array_length(checklist_items) AS item_count, version
       FROM submittal_checklists WHERE pack_id = $1 ORDER BY occupancy_class`,
      [packId],
    );
    return res.rows;
  } catch {
    // Table may not exist yet (pre-migration 0013)
    return [];
  }
}

async function fetchDrafterExamples(packId: string): Promise<DrafterExampleRow[]> {
  try {
    const res = await pool.query<DrafterExampleRow>(
      `SELECT example_id, discipline, severity,
              LEFT(polished_output, 120) AS polished_output
       FROM drafter_examples WHERE pack_id = $1 ORDER BY discipline`,
      [packId],
    );
    return res.rows;
  } catch {
    // Table may not exist yet (pre-migration 0013)
    return [];
  }
}

type Tab = "amendments" | "policies" | "checklists" | "examples";

const TAB_LABELS: Record<Tab, string> = {
  amendments: "Amendments",
  policies: "Agency Policies",
  checklists: "Checklists",
  examples: "Drafter Examples",
};

export default async function PackDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ packId: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { packId } = await params;
  const { tab: rawTab } = await searchParams;
  const decodedPackId = decodeURIComponent(packId);

  const activeTab: Tab =
    rawTab === "policies" || rawTab === "checklists" || rawTab === "examples"
      ? rawTab
      : "amendments";

  const [header, amendments, policies, checklists, examples] = await Promise.all([
    fetchPackHeader(decodedPackId),
    fetchAmendments(decodedPackId),
    fetchPolicies(decodedPackId),
    fetchChecklists(decodedPackId),
    fetchDrafterExamples(decodedPackId),
  ]);

  if (!header) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Pack not found: {decodedPackId}</p>
        <Link href="/admin/packs" className="text-sm text-blue-600 hover:underline mt-2 inline-block">
          ← Back to packs
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb */}
      <div className="mb-4">
        <Link href="/admin/packs" className="text-sm text-blue-600 hover:underline">
          ← All packs
        </Link>
      </div>

      {/* Pack header */}
      <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-gray-900 font-mono">{header.pack_id}</h2>
            <div className="flex items-center gap-3 mt-1">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                {header.jurisdiction}
              </span>
              <span className="text-sm text-gray-600">v{header.version}</span>
              <span className="text-sm text-gray-400">
                Effective{" "}
                {header.effective_date
                  ? new Date(header.effective_date).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                      timeZone: "UTC",
                    })
                  : "—"}
              </span>
            </div>
          </div>
          {header.superseded_by == null ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
              Active
            </span>
          ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-400">
              Superseded by {header.superseded_by}
            </span>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="flex gap-1">
          {(Object.entries(TAB_LABELS) as [Tab, string][]).map(([tab, label]) => (
            <a
              key={tab}
              href={`?tab=${tab}`}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              {label}
            </a>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === "amendments" && (
        <section>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            {amendments.length} Amendment{amendments.length !== 1 ? "s" : ""}
          </h3>
          {amendments.length === 0 ? (
            <p className="text-sm text-gray-400">No amendments for this pack.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm border-collapse border border-gray-200 bg-white">
                <thead className="bg-gray-50">
                  <tr>
                    {["Base Section ID", "Operation", "Effective Date", "Amendment Text (preview)"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left border border-gray-200 font-medium text-xs text-gray-600 uppercase tracking-wide">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {amendments.map((a) => (
                    <tr key={a.amendment_id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 border border-gray-200 font-mono text-xs text-gray-700">
                        {a.base_section_id}
                      </td>
                      <td className="px-3 py-2 border border-gray-200">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
                          {a.operation}
                        </span>
                      </td>
                      <td className="px-3 py-2 border border-gray-200 text-xs text-gray-500">
                        {a.effective_date
                          ? new Date(a.effective_date).toLocaleDateString("en-US", {
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                              timeZone: "UTC",
                            })
                          : "—"}
                      </td>
                      <td className="px-3 py-2 border border-gray-200 text-xs text-gray-600 max-w-xs truncate">
                        {a.amendment_text}&hellip;
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {activeTab === "policies" && (
        <section>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            {policies.length} Agency Polic{policies.length !== 1 ? "ies" : "y"}
          </h3>
          {policies.length === 0 ? (
            <p className="text-sm text-gray-400">No agency policies for this pack.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm border-collapse border border-gray-200 bg-white">
                <thead className="bg-gray-50">
                  <tr>
                    {["Title", "Applies To Sections", "Effective Date", "Body (preview)"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left border border-gray-200 font-medium text-xs text-gray-600 uppercase tracking-wide">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {policies.map((pol) => (
                    <tr key={pol.policy_id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 border border-gray-200 font-medium text-gray-800 text-xs">
                        {pol.title}
                      </td>
                      <td className="px-3 py-2 border border-gray-200 text-xs text-gray-600">
                        {(pol.applies_to_sections ?? []).join(", ") || "—"}
                      </td>
                      <td className="px-3 py-2 border border-gray-200 text-xs text-gray-500">
                        {pol.effective_date
                          ? new Date(pol.effective_date).toLocaleDateString("en-US", {
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                              timeZone: "UTC",
                            })
                          : "—"}
                      </td>
                      <td className="px-3 py-2 border border-gray-200 text-xs text-gray-600 max-w-xs truncate">
                        {pol.body_text}&hellip;
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {activeTab === "checklists" && (
        <section>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            {checklists.length} Checklist{checklists.length !== 1 ? "s" : ""}
          </h3>
          {checklists.length === 0 ? (
            <p className="text-sm text-gray-400">
              No checklists found. Table may not exist yet (requires migration 0013).
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm border-collapse border border-gray-200 bg-white">
                <thead className="bg-gray-50">
                  <tr>
                    {["Checklist ID", "Occupancy Class", "Items", "Version"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left border border-gray-200 font-medium text-xs text-gray-600 uppercase tracking-wide">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {checklists.map((cl) => (
                    <tr key={cl.checklist_id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 border border-gray-200 font-mono text-xs text-gray-600">
                        {cl.checklist_id}
                      </td>
                      <td className="px-3 py-2 border border-gray-200 font-medium text-gray-800">
                        {cl.occupancy_class}
                      </td>
                      <td className="px-3 py-2 border border-gray-200 text-center text-gray-700">
                        {cl.item_count}
                      </td>
                      <td className="px-3 py-2 border border-gray-200 font-mono text-xs text-gray-500">
                        {cl.version}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {activeTab === "examples" && (
        <section>
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            {examples.length} Drafter Example{examples.length !== 1 ? "s" : ""}
          </h3>
          {examples.length === 0 ? (
            <p className="text-sm text-gray-400">
              No drafter examples found. Table may not exist yet (requires migration 0013).
            </p>
          ) : (
            <div className="grid gap-3">
              {examples.map((ex) => (
                <div key={ex.example_id} className="bg-white border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">
                      {ex.discipline}
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700">
                      {ex.severity}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 leading-relaxed">
                    {ex.polished_output}&hellip;
                  </p>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Dry-run section */}
      <details className="mt-8 border border-gray-200 rounded-lg">
        <summary className="px-4 py-3 text-sm font-medium text-gray-700 cursor-pointer hover:bg-gray-50 rounded-lg">
          Dry-run amendment resolution
        </summary>
        <div className="px-4 py-4 border-t border-gray-200 bg-gray-50 rounded-b-lg">
          <p className="text-sm text-gray-600">
            Run the following command to preview how this pack&apos;s amendments resolve against the
            fixture project without writing to the database:
          </p>
          <pre className="mt-2 bg-gray-100 rounded p-3 text-xs font-mono text-gray-800 overflow-x-auto">
            {`python scripts/seed_packs.py --dry-run --pack-id ${decodedPackId}`}
          </pre>
          <p className="text-xs text-gray-400 mt-2">
            This preview applies amendment resolution on the 2008 Dennis Ln · Santa Rosa · CA · Permit B25-2734
            fixture project and prints a diff of affected sections to stdout.
          </p>
        </div>
      </details>
    </div>
  );
}
