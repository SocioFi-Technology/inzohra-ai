# § 18 — Glossary and conventions

## Glossary

| Term | Definition |
|---|---|
| **AHJ** | Authority Having Jurisdiction. The agency issuing the permit. |
| **APN** | Assessor's Parcel Number. A unique parcel identifier. |
| **bbox** | Bounding box. `[x1, y1, x2, y2]` in PDF page units. |
| **BV** | Bureau Veritas. The primary reviewer firm for the initial fixture. |
| **CBC** | California Building Code. Title 24 Part 2. |
| **CRC** | California Residential Code. Title 24 Part 2.5. |
| **CEC** | California Electrical Code. Title 24 Part 3. |
| **CMC** | California Mechanical Code. Title 24 Part 4. |
| **CPC** | California Plumbing Code. Title 24 Part 5. |
| **CFC** | California Fire Code. Title 24 Part 9. |
| **CEnC** | California Energy Code. Title 24 Part 6. |
| **CalGreen** | California Green Building Standards Code. Title 24 Part 11. |
| **CF1R** | Certificate of Compliance, Residential. A Title 24 compliance form. |
| **RMS-1** | A Title 24 residential measures summary. |
| **HSC** | California Health & Safety Code. Section 13131.x governs residential care facility occupancies. |
| **NCO** | Net Clear Opening. Operable window opening area for egress. |
| **Sheet** | One page of a plan set with its own identifier and discipline. |
| **Submittal** | A point-in-time delivery of documents to the AHJ. |
| **Round** | A review cycle on a submittal. Round 1 = initial; round 2 = resubmittal after comments; etc. |
| **Discipline letter** | `G` general, `A` architectural, `S` structural, `M` mechanical, `E` electrical, `P` plumbing, `T` Title 24, `F` fire. |
| **Severity** | Revise / Provide / Clarify / Reference only. BV dialect. |
| **`requires_licensed_review`** | Flag on findings that must be signed off by a licensed reviewer. |
| **Provenance chain** | The full trace from a finding down to the source pixels it came from. |
| **Cross-doc claim** | A fact asserted across multiple documents, aggregated for reconciliation. |
| **R-2.1** | Residential Care occupancy classification for licensed 24-hour care, 7+ occupants. |
| **Shear wall** | A structural wall resisting lateral loads. |
| **Holdown** | A mechanical anchor resisting uplift on a shear wall. |
| **Path of travel** | ADA/11B accessible route from arrival to area of use. |
| **Turning space** | A clear space for wheelchair rotation, typically 60" diameter. |

## Conventions

- **Citations** render as `CRC §R310.2.1` or `CBC §11B-404.2.3`.
- **Sheet IDs** are the on-sheet identifier exactly as drawn, e.g. `A-1.2`, `E-1.0`, `S-0.1`.
- **Dates** in ISO-8601: `2025-03-15`.
- **Measurements** stored in base units (inches, square feet), rendered in the architectural convention at display time.
- **IDs** are UUIDv7 in storage; publicly exposed as short random strings via a mapping table.
- **Filenames** in this repo use kebab-case for docs/prompts, snake_case for Python, camelCase for TS.
