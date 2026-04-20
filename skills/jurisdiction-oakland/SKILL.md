# Oakland jurisdictional skill

## Scope
Loaded by any reviewer processing a project with `jurisdiction = "oakland"`. Provides the amendments, agency policies, dialect, checklists, and review conventions specific to the City of Oakland, Alameda County, California.

## Amendments summary

The Oakland pack amends the 2022 California codes per the Oakland Municipal Code (OMC). Notable amendments (full pack in `packs/oakland/amendments/`):

- **NFPA 13 full sprinklers in all R-2**: Oakland requires a full NFPA 13 sprinkler system in every new multi-family residential (R-2) building regardless of height or unit count, more restrictive than the state threshold. Deferred submittal requires Oakland Fire Prevention Bureau (OFP) pre-approval.
- **Fire alarm in R-2 buildings of 3+ units**: NFPA 72 addressable fire alarm with annunciator required for all new R-2 buildings with 3 or more units, regardless of stories.
- **Soft-story retrofit ordinance**: Pre-1978 wood-frame buildings of 5+ units with soft/weak/open-front stories must comply with OMC Chapter 15.27. Permit applications for alterations must include retrofit status documentation.
- **Seismic hazard zones**: Alquist-Priolo, Liquefaction, and Landslide hazard zones shown on Oakland Planning GIS require geotechnical reports prior to plan acceptance.
- **Oakland ECAP all-electric preference**: Oakland Equitable Climate Action Plan (ECAP) establishes a preference for all-electric HVAC and water heating in new construction. Gas systems require written justification.
- **EV charging**: Title 24 Part 6 EV-ready mandatory plus Oakland local ECAP reinforcement. All new SFR require 240V/50A dedicated EV circuit. R-2 buildings require EV infrastructure at minimum 10% of parking stalls.
- **Oakland Planning clearance prerequisite**: Design Review or CUP approval must be obtained from Oakland Planning before Building Services Division will accept permit application.

## Agency policies

- **Oakland Fire Prevention Bureau (OFP)**: Issues separate fire code comments. BV fire-life-safety reviewer shall flag all items requiring OFP concurrent review. OFP review must be complete before building permit issuance.
- **Oakland Equity Standards**: Oakland Building Services Division applies equity-review requirements for projects in designated "Sensitive Communities" (see Oakland Equity Atlas). Flag findings where accessibility or habitability non-compliance disproportionately affects sensitive communities.
- **Oakland ADU Ordinance**: Oakland has one of California's most permissive ADU ordinances (OMC Chapter 17.103). ADU setbacks and height limits may differ from standard R-1 zoning; confirm Planning clearance for ADU footprint.
- **Residential Tenant Protection**: For projects involving existing occupied buildings, confirm that Oakland Residential Rent Adjustment Program (RRAP) exemptions or permits are present for displacement-triggering work. This is an informational flag for the plan integrity reviewer — not a code finding.
- **EBMUD fire flow**: East Bay Municipal Utility District (EBMUD) issues fire flow availability letters. Oakland FPB requires EBMUD letter for all new R-2 construction. Include in submittal checklist flag.

## Comment dialect

BV writes in a specific voice on Oakland projects:
- Present tense, passive-avoiding.
- Opens with the sheet reference.
- Cites code section inline using Oakland Fire Prevention Bureau formatting where OFP comments are included.
- Uses "Revise" / "Provide" / "Clarify" / "Reference only" severity keywords matching the BV dialect.
- Agency label is "Oakland Building Services Division" (not "City of Oakland Building Department").
- OFP fire comments are separately numbered with prefix "OFPB-" and are not merged into the main BV letter.
- BV Job No. format for Oakland: OAK-XXXX-YY.

### Example style (Oakland R-2 NFPA 13 comment)
> *Sheet A-1.1: The plans indicate a new 24-unit apartment building (Group R-2) but do not address automatic fire sprinkler system requirements. Per the Oakland local amendment to CFC §903.2.8, an NFPA 13 automatic fire sprinkler system is required in all new Group R-2 buildings regardless of size. Provide: submit NFPA 13 sprinkler system plans to the Oakland Fire Prevention Bureau for concurrent review and approval prior to building permit issuance. A deferred submittal notation on the building plans is acceptable with written OFP pre-approval.*

Full few-shot examples are not separately authored for Oakland — use the dialect rules above with the Santa Rosa drafter examples (`packs/santa-rosa/drafter-examples.md`) as structural templates, substituting "Oakland Building Services Division" for the agency name and OAK-XXXX-YY for the BV job number.

## Letter template

- Font family: **Calibri**.
- Letterhead: BV logo + "Oakland Building Services Division" + reviewer contact block.
- Margins: 1.0" all sides (Oakland standard; slightly wider than Santa Rosa).
- Page numbers: bottom right.
- Oakland ePlans resubmittal URL: etrakit.oaklandca.gov — include in general instructions block.
- OFP comments are appended as a separate section after BV comments, with a divider and OFP contact block.
- Response slot: three-line text box after each comment.

## Submittal checklists

Oakland SFR submittal checklist (R-3) parsed into structured queries in `packs/oakland/checklists/sfr.json` (25 items). R-2 multi-family checklist not separately authored in this version — use the Santa Rosa R-2 checklist (`packs/santa-rosa/checklists/r2.json`) as a template, substituting Oakland-specific requirements from the Oakland amendments pack.

## Review round conventions

Italic → round 1; **bold** → round 2; <u>underlined</u> → round 3. Matches BV standard convention.

Oakland-specific: any comment that was open in Round 1 and not fully resolved in Round 2 shall be escalated as a **bold** finding with a note: "Previously issued as Round 1 comment [item number]. Not resolved. See response letter."

## Fee and timing

- Plan check turnaround: **20 business days** Round 1; **15 business days** Round 2+.
- Application expiration: unresolved comments after 180 days may result in expiration per OMC Chapter 15.02.
- Resubmittal fee: per `packs/oakland/fees.json`. Oakland also assesses a 2% Technology Fee on total permit fees.
- Fire department review (OFP): separate concurrent review, typically 15 business days for R-2. OFP approval required before building permit issuance.
- Oakland does not issue over-the-counter permits for new construction — all submittals enter the electronic plan check queue via etrakit.oaklandca.gov.

These fields flow into the letter's general-instructions block and the designer-portal timeline widget.

## Key differences from Santa Rosa

| Dimension | Santa Rosa | Oakland |
|---|---|---|
| Primary project type | SFR, ADU, small R-2 | R-2 (5-story wood over podium), SFR infill |
| Sprinkler — R-2 | NFPA 13 (state threshold) | NFPA 13 all new R-2, no threshold |
| Sprinkler — SFR | NFPA 13D required | NFPA 13D required |
| Sprinkler — ADU | NFPA 13D if >500 sqft or attached | NFPA 13D if attached or primary has system |
| Fire alarm — R-2 | Per CBC 907.2.9 state threshold | NFPA 72 all new R-2 with 3+ units |
| WUI/Fire Zone 3 | Major concern (post-Tubbs) | Minimal (urban core) |
| Soft-story | Pre-1980 concrete/masonry | Pre-1978 wood-frame 5+ units |
| EV charging | NEMA 14-50 in garage | Same + R-2 EV infrastructure 10% stalls |
| Round 1 turnaround | 15 business days | 20 business days |
| OFP concurrent review | Yes (SRFD) | Yes (Oakland FPB, separate comment letter) |
| Resubmittal portal | Santa Rosa ePlans | etrakit.oaklandca.gov |
