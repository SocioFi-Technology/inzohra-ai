import { z } from "zod";

export const Discipline = z.enum([
  "plan_integrity",
  "architectural",
  "accessibility",
  "structural",
  "mechanical",
  "electrical",
  "plumbing",
  "energy",
  "fire_life_safety",
  "calgreen"
]);
export type Discipline = z.infer<typeof Discipline>;

export const Severity = z.enum(["revise", "provide", "clarify", "reference_only"]);
export type Severity = z.infer<typeof Severity>;

export const BBox = z.tuple([z.number(), z.number(), z.number(), z.number()]);
export type BBox = z.infer<typeof BBox>;

export const Citation = z.object({
  code: z.string(),
  section: z.string(),
  jurisdiction: z.string(),
  effective_date: z.string(),
  frozen_text: z.string(),
  retrieval_chain: z.array(z.unknown()).optional(),
  amendments_applied: z.array(z.unknown()).optional()
});
export type Citation = z.infer<typeof Citation>;

export const Evidence = z.union([
  z.object({
    entity_id: z.string().uuid(),
    bbox: BBox,
    raster_crop_uri: z.string().nullable().optional()
  }),
  z.object({
    measurement_id: z.string().uuid(),
    value: z.number(),
    unit: z.string(),
    confidence: z.number().min(0).max(1),
    trace: z.array(z.unknown()).optional()
  })
]);
export type Evidence = z.infer<typeof Evidence>;

export const Finding = z.object({
  finding_id: z.string().uuid(),
  project_id: z.string().uuid(),
  submittal_id: z.string().uuid(),
  review_round: z.number().int().min(1),
  discipline: Discipline,
  rule_id: z.string().nullable(),
  rule_version: z.string().nullable(),
  llm_reasoner_id: z.string().nullable(),
  prompt_hash: z.string().nullable(),
  severity: Severity,
  requires_licensed_review: z.boolean(),
  sheet_reference: z.object({
    sheet_id: z.string(),
    detail: z.string().nullable().optional()
  }),
  evidence: z.array(Evidence),
  citations: z.array(Citation),
  draft_comment_text: z.string().min(1),
  confidence: z.number().min(0).max(1),
  created_at: z.string(),
  extractor_versions_used: z.array(z.string())
});
export type Finding = z.infer<typeof Finding>;
