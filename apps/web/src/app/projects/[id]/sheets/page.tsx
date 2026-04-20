/**
 * /projects/[id]/sheets — redirect to the first sheet.
 */
import { redirect } from "next/navigation";
import { queryOne, query } from "@/lib/db";

type Props = { params: { id: string } };

export default async function SheetsIndexPage({ params }: Props) {
  const firstSheet = await queryOne(
    `SELECT s.sheet_id
     FROM sheets s
     JOIN documents d ON d.document_id = s.document_id
     JOIN submittals sub ON sub.submittal_id = d.submittal_id
     WHERE sub.project_id = $1
     ORDER BY s.page
     LIMIT 1`,
    [params.id]
  ) as Record<string, string> | null;

  if (firstSheet) {
    redirect(
      `/projects/${params.id}/sheets/${encodeURIComponent(firstSheet.sheet_id)}`
    );
  }

  const proj = await queryOne(
    `SELECT address, permit_number FROM projects WHERE project_id = $1`,
    [params.id]
  ) as Record<string, string> | null;

  return (
    <main className="p-8 text-gray-500">
      <p>
        Project {proj?.address ?? params.id} has no sheets yet. Run the
        ingestion pipeline first.
      </p>
    </main>
  );
}
