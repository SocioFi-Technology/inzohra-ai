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


ALL_SEED_SECTIONS: list[SeedSection] = (
    CBC_107_SECTIONS + CBC_11B_SECTIONS + CBC_508_716_SECTIONS
)
