-- Migration 0010: Backfill sheets.sheet_number from title_block entity payloads.
--
-- The TitleBlockAgent (Phase 01) stores alphanumeric sheet identifiers
-- (e.g. "A-1.2", "S-01", "P1.0") in the sheet_identifier_raw field of each
-- title_block entity's payload, but never wrote them back to sheets.sheet_number.
-- This migration populates that column so the LetterAssemblerAgent can resolve
-- sheet references to canonical IDs without parsing JSON at render time.
--
-- Logic applied:
--   1. For source_track = 'merged': value already contains the best merge of
--      text_raw and vision_raw; use it if it matches the sheet-ID pattern.
--   2. Fallback: use vision_raw if it matches the pattern.
--   3. Pattern: ^[A-Z][-.\\w]*\\d+  — starts with an uppercase discipline prefix
--      (A, S, E, M, P, G, C…) followed by alphanumeric / dash / dot characters.
--
-- Only updates rows where sheet_number IS NULL (idempotent).

UPDATE sheets s
SET sheet_number = sub.best_id
FROM (
    SELECT
        s2.sheet_id,
        CASE
            -- Prefer the merged/extracted value if it matches the pattern
            WHEN (e.payload -> 'sheet_identifier_raw' ->> 'value') ~ '^[A-Z][-.]?\d[\w\-.]*$'
                THEN (e.payload -> 'sheet_identifier_raw' ->> 'value')
            -- Fall back to vision_raw
            WHEN (e.payload -> 'sheet_identifier_raw' ->> 'vision_raw') ~ '^[A-Z][-.]?\d[\w\-.]*$'
                THEN (e.payload -> 'sheet_identifier_raw' ->> 'vision_raw')
            ELSE NULL
        END AS best_id
    FROM sheets s2
    JOIN entities e
        ON e.sheet_id = s2.sheet_id
        AND e.type = 'title_block'
    WHERE s2.sheet_number IS NULL
) sub
WHERE s.sheet_id = sub.sheet_id
  AND sub.best_id IS NOT NULL;
