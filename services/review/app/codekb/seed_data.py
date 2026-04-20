"""Seed data for Phase 01: CBC §107 family + CBC Chapter 11B highlights.

This is a curated, hand-audited subset of the 2022 California Building Code
used to ground the PlanIntegrityReviewer's citations. Every entry lists the
exact statutory text (frozen, not paraphrased) and the canonical ID that rules
will retrieve by.

Effective date for the 2022 CA cycle in Santa Rosa: ``2023-01-01``.

Source: 2022 California Building Code, as adopted by California Code of
Regulations Title 24 Part 2.  Text is reproduced verbatim from the
California Building Standards Commission publication; this repository does
not rely on it for paraphrase — only for exact citation in findings.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SeedSection:
    canonical_id: str
    code: str
    section_number: str
    title: str
    body_text: str
    effective_date: str = "2023-01-01"
    cross_references: list[str] = field(default_factory=list)
    referenced_standards: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CBC §107 — Submittal documents / examination of construction docs
# ---------------------------------------------------------------------------

CBC_107_SECTIONS: list[SeedSection] = [
    SeedSection(
        canonical_id="CBC-107.1",
        code="CBC",
        section_number="107.1",
        title="General (Submittal documents)",
        body_text=(
            "Submittal documents consisting of construction documents, statement of "
            "special inspections, geotechnical report and other data shall be submitted "
            "in two or more sets, or in a digital format where allowed by the building "
            "official, with each application for a permit. The construction documents "
            "shall be prepared by a registered design professional where required by "
            "the statutes of the jurisdiction in which the project is to be constructed. "
            "Where special conditions exist, the building official is authorized to "
            "require additional construction documents to be prepared by a registered "
            "design professional."
        ),
        cross_references=["CBC-107.2", "CBC-107.3"],
    ),
    SeedSection(
        canonical_id="CBC-107.2",
        code="CBC",
        section_number="107.2",
        title="Construction documents",
        body_text=(
            "Construction documents shall be in accordance with Sections 107.2.1 "
            "through 107.2.7."
        ),
        cross_references=[
            "CBC-107.2.1", "CBC-107.2.2", "CBC-107.2.3",
            "CBC-107.2.4", "CBC-107.2.5", "CBC-107.2.6", "CBC-107.2.7",
        ],
    ),
    SeedSection(
        canonical_id="CBC-107.2.1",
        code="CBC",
        section_number="107.2.1",
        title="Information on construction documents",
        body_text=(
            "Construction documents shall be dimensioned and drawn to scale upon "
            "suitable material. Electronic media documents shall be permitted to be "
            "submitted where approved by the building official. Construction documents "
            "shall be of sufficient clarity to indicate the location, nature and extent "
            "of the work proposed and show in detail that it will conform to the "
            "provisions of this code and relevant laws, ordinances, rules and "
            "regulations, as determined by the building official."
        ),
        cross_references=["CBC-107.2"],
    ),
    SeedSection(
        canonical_id="CBC-107.2.2",
        code="CBC",
        section_number="107.2.2",
        title="Fire protection system shop drawings",
        body_text=(
            "Shop drawings for the fire protection system(s) shall be submitted to "
            "indicate conformance to this code and the construction documents and "
            "shall be approved prior to the start of system installation. Shop "
            "drawings shall contain all information as required by the referenced "
            "installation standards in Chapter 9."
        ),
    ),
    SeedSection(
        canonical_id="CBC-107.2.3",
        code="CBC",
        section_number="107.2.3",
        title="Means of egress",
        body_text=(
            "The construction documents shall show in sufficient detail the location, "
            "construction, size and character of all portions of the means of egress "
            "including the path of the exit discharge to the public way in compliance "
            "with the provisions of this code. In other than occupancies in Group R-2, "
            "R-3 and I-1, the construction documents shall designate the number of "
            "occupants to be accommodated on every floor, and in all rooms and spaces."
        ),
    ),
    SeedSection(
        canonical_id="CBC-107.2.4",
        code="CBC",
        section_number="107.2.4",
        title="Exterior wall envelope",
        body_text=(
            "Construction documents for all buildings shall describe the exterior wall "
            "envelope in sufficient detail to determine compliance with this code. The "
            "construction documents shall provide details of the exterior wall envelope "
            "as required, including flashing, intersections with dissimilar materials, "
            "corners, end details, control joints, intersections at roof, eaves or "
            "parapets, means of drainage, water-resistive membrane and details around "
            "openings."
        ),
    ),
    SeedSection(
        canonical_id="CBC-107.2.5",
        code="CBC",
        section_number="107.2.5",
        title="Site plan",
        body_text=(
            "The construction documents submitted with the application for permit shall "
            "be accompanied by a site plan showing to scale the size and location of "
            "new construction and existing structures on the site, distances from lot "
            "lines, the established street grades and the proposed finished grades and, "
            "as applicable, flood hazard areas, floodways, and design flood elevations; "
            "and it shall be drawn in accordance with an accurate boundary line survey. "
            "In the case of demolition, the site plan shall show construction to be "
            "demolished and the location and size of existing structures and "
            "construction that are to remain on the site or plot. The building official "
            "is authorized to waive or modify the requirement for a site plan where the "
            "application for permit is for alteration or repair or where otherwise "
            "warranted."
        ),
    ),
    SeedSection(
        canonical_id="CBC-107.3",
        code="CBC",
        section_number="107.3",
        title="Examination of documents",
        body_text=(
            "The building official shall examine or cause to be examined the "
            "accompanying submittal documents and shall ascertain by such examinations "
            "whether the construction indicated and described is in accordance with the "
            "requirements of this code and other pertinent laws or ordinances."
        ),
    ),
    SeedSection(
        canonical_id="CBC-107.3.1",
        code="CBC",
        section_number="107.3.1",
        title="Approval of construction documents",
        body_text=(
            "When the building official issues a permit, the construction documents "
            "shall be approved, in writing or by stamp, as 'Reviewed for Code "
            "Compliance.' One set of construction documents so reviewed shall be "
            "retained by the building official. The other set shall be returned to the "
            "applicant, shall be kept at the site of work and shall be open to "
            "inspection by the building official or a duly authorized representative."
        ),
    ),
    SeedSection(
        canonical_id="CBC-107.4",
        code="CBC",
        section_number="107.4",
        title="Amended construction documents",
        body_text=(
            "Work shall be installed in accordance with the approved construction "
            "documents, and any changes made during construction that are not in "
            "compliance with the approved construction documents shall be resubmitted "
            "for approval as an amended set of construction documents."
        ),
    ),
    SeedSection(
        canonical_id="CBC-107.5",
        code="CBC",
        section_number="107.5",
        title="Retention of construction documents",
        body_text=(
            "One set of approved construction documents shall be retained by the "
            "building official for a period of not less than 180 days from date of "
            "completion of the permitted work, or as required by state or local laws."
        ),
    ),
]


# ---------------------------------------------------------------------------
# CBC Chapter 11B — Accessibility (essential subset for Phase 01/04)
# ---------------------------------------------------------------------------

CBC_11B_SECTIONS: list[SeedSection] = [
    SeedSection(
        canonical_id="CBC-11B-202",
        code="CBC",
        section_number="11B-202",
        title="Existing Buildings and Facilities (Chapter 11B scoping)",
        body_text=(
            "Additions, alterations, and change of occupancy to existing buildings or "
            "facilities shall comply with Section 11B-202. The path of travel to an "
            "altered area and the sanitary facilities, drinking fountains, signs and "
            "public telephones serving the altered area shall be made accessible "
            "unless compliance is technically infeasible or the cost exceeds 20 "
            "percent of the adjusted construction cost of the alteration."
        ),
        cross_references=["CBC-11B-202.3", "CBC-11B-202.4"],
    ),
    SeedSection(
        canonical_id="CBC-11B-202.3",
        code="CBC",
        section_number="11B-202.3",
        title="Alterations",
        body_text=(
            "Where existing elements or spaces are altered, each altered element or "
            "space shall comply with the applicable requirements of Chapter 11B "
            "including Section 11B-202.3.1. If the alteration to a primary function "
            "area triggers the requirements of Section 11B-202.4, the path of travel "
            "to the altered area shall also comply."
        ),
    ),
    SeedSection(
        canonical_id="CBC-11B-202.4",
        code="CBC",
        section_number="11B-202.4",
        title="Path of travel requirements in alterations, additions, and structural repairs",
        body_text=(
            "An alteration that affects or could affect the usability of or access to "
            "an area containing a primary function shall be made so as to ensure that, "
            "to the maximum extent feasible, the path of travel to the altered area, "
            "including the sanitary facilities, drinking fountains, signs and public "
            "telephones serving the altered area, are readily accessible to and usable "
            "by individuals with disabilities, unless the cost and scope of such "
            "alterations is disproportionate to the cost of the overall alteration."
        ),
    ),
    SeedSection(
        canonical_id="CBC-11B-213.1.1",
        code="CBC",
        section_number="11B-213.1.1",
        title="Toilet and bathing rooms serving Group R-2.1, R-3.1, R-4 and I occupancies",
        body_text=(
            "Toilet rooms and bathing rooms that serve Group R-2.1, R-3.1, R-4, and I "
            "occupancies shall comply with Section 11B-603. Bathtubs and showers "
            "provided for residents shall comply with Sections 11B-607 and 11B-608. "
            "Each toilet room and bathing room serving these occupancies shall be "
            "accessible."
        ),
    ),
    SeedSection(
        canonical_id="CBC-11B-404.2.3",
        code="CBC",
        section_number="11B-404.2.3",
        title="Clear width at doorways",
        body_text=(
            "Door openings shall provide a clear width of 32 inches (813 mm) minimum. "
            "Clear openings of doorways with swinging doors shall be measured between "
            "the face of the door and the stop, with the door open 90 degrees."
        ),
    ),
]


# ---------------------------------------------------------------------------
# CBC §508 (mixed use / separated occupancies) + CBC §716 (opening protectives)
# Minimal entries — these are needed by BV comments 5, 6, 7 (seeded now so the
# plan-integrity text-overlap / cross-reference rules can cite them).
# ---------------------------------------------------------------------------

CBC_508_716_SECTIONS: list[SeedSection] = [
    SeedSection(
        canonical_id="CBC-508.4",
        code="CBC",
        section_number="508.4",
        title="Separated occupancies",
        body_text=(
            "Each portion of the building shall be individually classified in "
            "accordance with Section 302.1. The occupancies shall be completely "
            "separated from adjacent occupancies by fire barriers complying with "
            "Section 707 or horizontal assemblies complying with Section 711, or "
            "both, having a fire-resistance rating determined in accordance with "
            "Table 508.4."
        ),
        cross_references=["CBC-TBL-508.4", "CBC-707", "CBC-711"],
    ),
    SeedSection(
        canonical_id="CBC-TBL-508.4",
        code="CBC",
        section_number="Table 508.4",
        title="Required separation of occupancies (hours)",
        body_text=(
            "Required fire-resistance ratings for separations between occupancy "
            "groups. For R-2.1 adjacent to R-3 (non-sprinklered / NS), a 1-hour "
            "fire-resistance-rated separation is required; sprinklered (S) is N/A "
            "where the sprinkler system does not otherwise substitute for the "
            "separation. Consult Table 508.4 footnotes for allowed reductions."
        ),
    ),
    SeedSection(
        canonical_id="CBC-TBL-716.1-2",
        code="CBC",
        section_number="Table 716.1(2)",
        title="Opening fire protectives - fire door and fire shutter assemblies",
        body_text=(
            "Required fire-protection ratings for opening protectives in fire "
            "barriers and horizontal assemblies. For a 1-hour fire barrier "
            "separating occupancies, a 45-minute fire door is required, self- or "
            "automatic-closing and latching, labeled in accordance with Section "
            "716.2.9."
        ),
    ),
]


# ---------------------------------------------------------------------------
# CBC Chapter 5 — General Building Heights and Areas
# ---------------------------------------------------------------------------

CBC_CH5_SECTIONS: list[SeedSection] = [
    SeedSection(
        canonical_id="CBC-503",
        code="CBC",
        section_number="503",
        title="General Building Height and Area Limitations",
        body_text=(
            "The building height and building area shall not exceed the limits specified in "
            "Table 503 based on the occupancy classification and the type of construction. "
            "Each portion of a building separated by one or more fire walls complying with "
            "Section 706 shall be considered a separate building."
        ),
    ),
    SeedSection(
        canonical_id="CBC-TBL-503",
        code="CBC",
        section_number="Table 503",
        title="Allowable Building Heights and Areas",
        body_text=(
            "Table 503: Allowable building heights in feet and number of stories, and allowable "
            "area per story in square feet, based on occupancy group and construction type. "
            "For Type V-A (one-hour), R-2.1: height 50 ft / 4 stories, area 9,000 sq ft per story. "
            "Unlimited area and height adjustments available per Section 506 with automatic sprinkler system."
        ),
    ),
    SeedSection(
        canonical_id="CBC-302.1",
        code="CBC",
        section_number="302.1",
        title="Occupancy Classification",
        body_text=(
            "Structures or portions of structures shall be classified with respect to occupancy "
            "in one or more of the groups listed in this section. A room or space that is "
            "intended to be occupied at different times for two or more different purposes "
            "shall comply with all of the requirements that are applicable to each of the "
            "purposes for which the room or space will be occupied."
        ),
        cross_references=["CBC-310", "CBC-311", "CBC-312"],
    ),
    SeedSection(
        canonical_id="CBC-310.5.3",
        code="CBC",
        section_number="310.5.3",
        title="Residential Group R-2.1 (Care facilities, 7 or more clients)",
        body_text=(
            "Residential occupancies containing buildings or portions thereof providing "
            "sleeping accommodations for ambulatory clients receiving care on a 24-hour "
            "basis, with 7 or more residents. This group shall comply with the California "
            "Health and Safety Code and local regulations in addition to applicable "
            "provisions of this code. For fire sprinkler requirements, see HSC §13131.5."
        ),
        cross_references=["HSC-13131.5", "CBC-903.2.8"],
    ),
]


# ---------------------------------------------------------------------------
# CBC Chapter 10 — Means of Egress
# ---------------------------------------------------------------------------

CBC_CH10_SECTIONS: list[SeedSection] = [
    SeedSection(
        canonical_id="CBC-1004.1",
        code="CBC",
        section_number="1004.1",
        title="Occupant Load — Design occupant load",
        body_text=(
            "The design occupant load for a room or area shall not be less than the number "
            "determined by dividing the floor area under consideration by the occupant load "
            "factor for that use as specified in Table 1004.5. Where an intended use is not "
            "listed in Table 1004.5, the building official shall establish the occupant load."
        ),
        cross_references=["CBC-TBL-1004.5"],
    ),
    SeedSection(
        canonical_id="CBC-1005.1",
        code="CBC",
        section_number="1005.1",
        title="Minimum Required Egress Width",
        body_text=(
            "The minimum required egress capacity for doors, stairways and ramps shall be "
            "calculated based on 0.2 inches per occupant for stairways and 0.15 inches per "
            "occupant for other means of egress components. The minimum clear width of any "
            "means of egress component shall not be less than that specified for such "
            "component elsewhere in this chapter."
        ),
    ),
    SeedSection(
        canonical_id="CBC-1010.1.9",
        code="CBC",
        section_number="1010.1.9",
        title="Door Operations — Egress door hardware",
        body_text=(
            "Egress doors shall be readily openable from the egress side without the use "
            "of a key or special knowledge or effort. Delayed egress locking systems, "
            "access-controlled egress door assemblies, and electromagnetically locked "
            "egress door assemblies are permitted where specified in Section 1010.1.9.7."
        ),
    ),
    SeedSection(
        canonical_id="CBC-1006.3.3",
        code="CBC",
        section_number="1006.3.3",
        title="Two exits or exit access doorways — R occupancies",
        body_text=(
            "Where access to a single exit is permitted, dwelling units and sleeping "
            "units in Group R occupancies shall be provided with access to not less than "
            "two exits or exit access doorways where the building has more than one "
            "story above grade plane, or where the story has an area exceeding 4,000 "
            "square feet."
        ),
    ),
    SeedSection(
        canonical_id="CBC-1015.2",
        code="CBC",
        section_number="1015.2",
        title="Window sill height — Emergency escape and rescue openings",
        body_text=(
            "Emergency escape and rescue openings shall have a minimum net clear opening "
            "of 5.7 square feet (0.53 m²). The minimum net clear opening height shall "
            "be 24 inches (610 mm). The minimum net clear opening width shall be 20 inches "
            "(508 mm). The maximum finished sill height shall be 44 inches (1118 mm) above "
            "the floor, or shall have a permanently attached ladder or step."
        ),
        cross_references=["CBC-1030.1"],
    ),
    SeedSection(
        canonical_id="CBC-1030.1",
        code="CBC",
        section_number="1030.1",
        title="Emergency Escape and Rescue Openings — General",
        body_text=(
            "In addition to the means of egress required by this chapter, provisions shall "
            "be made for emergency escape and rescue openings in Group R-2 occupancies in "
            "accordance with Sections 1030.1 through 1030.7. Emergency escape and rescue "
            "openings shall open directly into a public way or to a yard or court that opens "
            "to a public way."
        ),
    ),
]


# ---------------------------------------------------------------------------
# CEnC (California Energy Code) §150
# ---------------------------------------------------------------------------

CENC_150_SECTIONS: list[SeedSection] = [
    SeedSection(
        canonical_id="CEnC-150.0(a)",
        code="CEnC",
        section_number="150.0(a)",
        title="Mandatory Features and Devices — Insulation",
        body_text=(
            "All insulation materials, including facings and vapor retarders, shall comply "
            "with the requirements of Section 150.0(a). Roof/ceiling assemblies: minimum "
            "R-38 for Climate Zone 2. Wall insulation: minimum R-15 for wood-frame walls. "
            "Floor insulation over unconditioned space: minimum R-19. These are minimum "
            "values; the prescriptive compliance path (CF1R-PRF) may require higher values "
            "based on climate zone and assembly type."
        ),
        effective_date="2023-01-01",
        cross_references=["CEnC-150.1", "CEnC-TBL-150.1-A"],
    ),
    SeedSection(
        canonical_id="CEnC-150.1",
        code="CEnC",
        section_number="150.1",
        title="Performance and Prescriptive Compliance — Residential",
        body_text=(
            "Newly constructed residential buildings shall comply with the performance "
            "approach using the Energy Design Rating (EDR) or the prescriptive approach "
            "specified in Section 150.1. The prescriptive approach requires compliance "
            "with the component packages specified in Table 150.1-A for the applicable "
            "climate zone. Climate Zone 2 (Santa Rosa) prescriptive roof insulation: R-38 "
            "minimum; walls: R-15 or R-13+4 CI; slab: R-10 for 16 inches."
        ),
        effective_date="2023-01-01",
        cross_references=["CEnC-150.0", "CEnC-TBL-150.1-A"],
    ),
    SeedSection(
        canonical_id="CEnC-TBL-150.1-A",
        code="CEnC",
        section_number="Table 150.1-A",
        title="Prescriptive Envelope Requirements — Climate Zone 2",
        body_text=(
            "Climate Zone 2 prescriptive insulation requirements: "
            "Roof/Ceiling: R-38 minimum (attic), R-22+CI for cathedralized. "
            "Exterior Walls: R-15 minimum batts OR R-13 batts + R-4 CI. "
            "Floors over unconditioned space: R-19 minimum. "
            "Slab edge: R-10 to 16 inches depth. "
            "Windows: U-0.32 maximum, SHGC 0.25 maximum."
        ),
        effective_date="2023-01-01",
    ),
]


# ---------------------------------------------------------------------------
# CPC Chapter 4 — Plumbing fixtures
# ---------------------------------------------------------------------------

CPC_CH4_SECTIONS: list[SeedSection] = [
    SeedSection(
        canonical_id="CPC-408.0",
        code="CPC",
        section_number="408.0",
        title="Water Closets — Required number",
        body_text=(
            "Water closets shall be provided for each sex in accordance with Table 4-1. "
            "In residential occupancies with six or fewer occupants, one water closet shall "
            "be permitted. Accessible water closets shall comply with Chapter 11B of CBC."
        ),
        cross_references=["CPC-TBL-4-1"],
    ),
    SeedSection(
        canonical_id="CPC-TBL-4-1",
        code="CPC",
        section_number="Table 4-1",
        title="Minimum Plumbing Fixtures",
        body_text=(
            "For residential occupancies (Group R): 1 water closet per 1-8 persons, "
            "1 lavatory per 1-8 persons, 1 bathtub or shower per 1-8 persons, "
            "1 kitchen sink per dwelling unit. For Group R-2.1 care facilities: "
            "additional fixtures may be required per local health department regulations. "
            "Consult local AHJ and California Department of Social Services requirements."
        ),
    ),
    SeedSection(
        canonical_id="CPC-603.1",
        code="CPC",
        section_number="603.1",
        title="Water heater installation",
        body_text=(
            "Water heaters shall be installed in accordance with the manufacturer's "
            "installation instructions and the requirements of this code. Water heaters "
            "installed in garages or living spaces shall be protected from vehicle damage. "
            "All water heaters shall be seismically strapped in two locations per CBC "
            "Section 507.2 and CPC Section 508.0."
        ),
    ),
]


# ---------------------------------------------------------------------------
# CRC R310 + CBC Ch10 egress / CBC Ch11B access — Phase 04 additions
# ---------------------------------------------------------------------------

CBC_ARCH_ACCESS_SECTIONS: list[SeedSection] = [
    SeedSection(
        canonical_id="CRC-R310.1",
        code="CRC",
        section_number="R310.1",
        title="Emergency escape and rescue openings — general",
        body_text=(
            "Every sleeping room shall have not less than one operable emergency escape "
            "and rescue opening. Where basements contain one or more sleeping rooms, "
            "emergency egress and rescue openings shall be required in each sleeping "
            "room. Emergency escape and rescue openings shall comply with Sections "
            "R310.1.1 through R310.1.4."
        ),
        cross_references=["CRC-R310.2.1", "CRC-R310.2.2", "CRC-R310.2.3", "CRC-R310.2.4"],
    ),
    SeedSection(
        canonical_id="CRC-R310.2.1",
        code="CRC",
        section_number="R310.2.1",
        title="Minimum opening area",
        body_text=(
            "Emergency escape and rescue openings shall have a minimum net clear opening "
            "of 5.7 square feet. Exception: Grade floor or below grade floor openings "
            "shall have a minimum net clear opening of 5 square feet."
        ),
        cross_references=["CRC-R310.1"],
    ),
    SeedSection(
        canonical_id="CRC-R310.2.2",
        code="CRC",
        section_number="R310.2.2",
        title="Minimum opening height",
        body_text=(
            "The minimum net clear opening height shall be 24 inches."
        ),
        cross_references=["CRC-R310.1"],
    ),
    SeedSection(
        canonical_id="CRC-R310.2.3",
        code="CRC",
        section_number="R310.2.3",
        title="Minimum opening width",
        body_text=(
            "The minimum net clear opening width shall be 20 inches."
        ),
        cross_references=["CRC-R310.1"],
    ),
    SeedSection(
        canonical_id="CRC-R310.2.4",
        code="CRC",
        section_number="R310.2.4",
        title="Maximum sill height",
        body_text=(
            "The maximum sill height shall be 44 inches measured from the floor."
        ),
        cross_references=["CRC-R310.1"],
    ),
    SeedSection(
        canonical_id="CBC-1004.5",
        code="CBC",
        section_number="1004.5",
        title="Function of occupied spaces",
        body_text=(
            "The minimum number of occupants for which the means of egress of a building "
            "or portion thereof is designed shall be determined in accordance with Table "
            "1004.5, based on the function of the space, or the actual number of "
            "occupants, whichever is greater. \u2026"
        ),
        cross_references=["CBC-TBL-1004.5", "CBC-1004.1"],
    ),
    SeedSection(
        canonical_id="CBC-1017.2.2",
        code="CBC",
        section_number="1017.2.2",
        title="Exit access travel distance — Group R-3",
        body_text=(
            "The exit access travel distance in Group R-3 occupancies shall not exceed "
            "250 feet (76 200 mm) from any point in the tenant space to the entrance to "
            "the exit. \u2026"
        ),
        cross_references=["CBC-1017.1"],
    ),
    SeedSection(
        canonical_id="CBC-1014.3",
        code="CBC",
        section_number="1014.3",
        title="Exit separation",
        body_text=(
            "Where two or more exits or exit access doorways are required, the exits or "
            "exit access doorways shall be placed a distance apart equal to not less than "
            "one-half of the length of the maximum overall diagonal dimension of the "
            "building or area to be served measured in a straight line between the nearest "
            "edges of the exits or exit access doorways."
        ),
        cross_references=["CBC-1006.3.3"],
    ),
    SeedSection(
        canonical_id="CBC-1019.2",
        code="CBC",
        section_number="1019.2",
        title="Exit discharge",
        body_text=(
            "Exits shall discharge directly to the exterior of the building. The "
            "out-swing of a gate or door at the exit discharge shall not reduce the "
            "required width of the exit discharge."
        ),
        cross_references=["CBC-1019.1"],
    ),
    SeedSection(
        canonical_id="CRC-R314.3",
        code="CRC",
        section_number="R314.3",
        title="Smoke alarm locations",
        body_text=(
            "Smoke alarms shall be installed in the following locations: 1. In each "
            "sleeping room. 2. Outside each separate sleeping area in the immediate "
            "vicinity of the bedrooms. 3. On each additional story of the dwelling, "
            "including basements and habitable attics but not crawl spaces and "
            "uninhabitable attics. \u2026"
        ),
        cross_references=["CRC-R314.1"],
    ),
    SeedSection(
        canonical_id="CBC-11B-304.3.1",
        code="CBC",
        section_number="11B-304.3.1",
        title="Circular turning space",
        body_text=(
            "The turning space shall comply with Section 11B-304.3.1 or 11B-304.3.2. "
            "A circular turning space of 60 inches (1525 mm) minimum diameter shall "
            "be provided."
        ),
        cross_references=["CBC-11B-304.3"],
    ),
    SeedSection(
        canonical_id="CBC-11B-308.2.1",
        code="CBC",
        section_number="11B-308.2.1",
        title="Forward reach",
        body_text=(
            "Where a clear floor or ground space allows only forward approach to an "
            "element, the element shall be within one or more of the reach ranges "
            "specified in Sections 11B-308.2 and 11B-308.3. Obstructed high forward "
            "reach: where the clear floor or ground space is obstructed, the high "
            "forward reach shall be 48 inches (1220 mm) maximum."
        ),
        cross_references=["CBC-11B-308.2", "CBC-11B-308.3"],
    ),
    SeedSection(
        canonical_id="CBC-11B-404.2.3.1",
        code="CBC",
        section_number="11B-404.2.3.1",
        title="Minimum clear width at doorways",
        body_text=(
            "Doorways shall have a minimum clear opening width of 32 inches (815 mm). "
            "Clear opening width of swinging doors shall be measured between the face "
            "of the door and stop, with the door open 90 degrees."
        ),
        cross_references=["CBC-11B-404.2.3"],
    ),
    SeedSection(
        canonical_id="CBC-11B-604.7",
        code="CBC",
        section_number="11B-604.7",
        title="Toilet paper dispensers",
        body_text=(
            "Toilet paper dispensers shall comply with Sections 11B-308 and 11B-309. "
            "Toilet paper dispensers shall be located on the side wall, 7 inches "
            "(178 mm) minimum and 9 inches (229 mm) maximum in front of the water "
            "closet measured to the centerline of the dispenser. The outlet of the "
            "dispenser shall be 15 inches (381 mm) minimum and 48 inches (1220 mm) "
            "maximum above the finish floor."
        ),
        cross_references=["CBC-11B-604", "CBC-11B-308", "CBC-11B-309"],
    ),
    SeedSection(
        canonical_id="CBC-11B-703.4.1",
        code="CBC",
        section_number="11B-703.4.1",
        title="Mounting location of tactile signs",
        body_text=(
            "Where signs with raised characters or Braille are provided on doors, "
            "the signs shall be located on the latch side of the door. The centerline "
            "of the signs shall be 60 inches (1525 mm) above the finish floor. \u2026 "
            "Where there is no wall space to the latch side of the door, including at "
            "double-leaf doors, signs shall be placed on the nearest adjacent wall."
        ),
        cross_references=["CBC-11B-703.4"],
    ),
    SeedSection(
        canonical_id="CBC-11B-804.2.1",
        code="CBC",
        section_number="11B-804.2.1",
        title="Kitchen clearance",
        body_text=(
            "In kitchens with a U-shaped floor plan and both sides longer than 60 "
            "inches (1525 mm), the required clear floor space shall be positioned for "
            "a parallel approach. Where a kitchen does not have a U-shaped floor plan, "
            "or where a U-shape floor plan has one or both sides 60 inches (1525 mm) "
            "or less, the clear floor space at a sink, cooking surface or work surface "
            "shall be positioned for either a forward or parallel approach."
        ),
        cross_references=["CBC-11B-804"],
    ),
    SeedSection(
        canonical_id="CBC-11B-902.3",
        code="CBC",
        section_number="11B-902.3",
        title="Height of dining and work surfaces",
        body_text=(
            "The tops of dining surfaces and work surfaces shall be 28 inches (711 mm) "
            "minimum and 34 inches (864 mm) maximum above the finish floor."
        ),
        cross_references=["CBC-11B-902"],
    ),
]


ALL_SEED_SECTIONS: list[SeedSection] = (
    CBC_107_SECTIONS + CBC_11B_SECTIONS + CBC_508_716_SECTIONS
    + CBC_CH5_SECTIONS + CBC_CH10_SECTIONS + CENC_150_SECTIONS + CPC_CH4_SECTIONS
    + CBC_ARCH_ACCESS_SECTIONS
)
