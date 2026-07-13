"""Static profession + qualification-field definitions for the intake form.

`value` slugs match the directory names under `src/ai/knowledge/professions/`
so a submitted `profession` can be passed straight through to the lead
qualifier's retriever for profession-specific knowledge lookup.
"""

from __future__ import annotations

from typing import TypedDict


class ProfessionFieldDef(TypedDict):
    field_key: str
    label: str
    field_type: str  # "text" | "select" | "multiselect"
    options: list[str] | None
    is_required: bool


class ProfessionDef(TypedDict):
    value: str
    label: str
    fields: list[ProfessionFieldDef]


def _field(
    field_key: str,
    label: str,
    field_type: str = "text",
    options: list[str] | None = None,
    required: bool = True,
) -> ProfessionFieldDef:
    return {
        "field_key": field_key,
        "label": label,
        "field_type": field_type,
        "options": options,
        "is_required": required,
    }


PROFESSIONS: list[ProfessionDef] = [
    {
        "value": "software-developer",
        "label": "Software Development",
        "fields": [
            _field(
                "project_type",
                "Project type",
                "select",
                [
                    "Website", "Web app", "Mobile app", "API/backend", "E-commerce",
                    "Booking system", "CRM/internal tool", "Dashboard", "SaaS",
                    "Automation", "Other",
                ],
            ),
            _field("business_goal", "Business goal", "text"),
            _field(
                "target_users",
                "Target users",
                "select",
                ["Customers", "Employees", "Admins", "Partners", "Students", "Patients", "Other"],
            ),
            _field(
                "platforms_needed",
                "Platforms needed",
                "select",
                ["Web", "Android", "iOS", "Both mobile platforms", "Desktop", "API/backend only"],
            ),
            _field(
                "core_features",
                "Core features",
                "multiselect",
                [
                    "Login", "Booking", "Payments", "Inventory", "Reports", "Notifications",
                    "Chat", "File upload", "Search", "Admin dashboard", "Other",
                ],
            ),
        ],
    },
    {
        "value": "ui-ux-design",
        "label": "UI/UX Design",
        "fields": [
            _field(
                "design_type",
                "Design type",
                "select",
                ["Mobile App", "Website", "Dashboard", "Desktop Application", "Other"],
            ),
            _field("business_goal", "Business goal", "text"),
            _field("target_users", "Target users", "text"),
            _field(
                "design_scope",
                "Design scope",
                "select",
                ["New design", "Redesign", "Improve existing design", "Design system only"],
            ),
            _field(
                "expected_deliverables",
                "Expected deliverables",
                "multiselect",
                ["Wireframes", "User flows", "High-fidelity UI", "Prototype", "Design system", "UX research"],
            ),
        ],
    },
    {
        "value": "graphic-design",
        "label": "Graphic Design",
        "fields": [
            _field(
                "design_category",
                "Design category",
                "select",
                [
                    "Logo", "Brand identity", "Social media graphics", "Poster", "Brochure",
                    "Packaging", "Presentation", "Illustration", "Other",
                ],
            ),
            _field("business_goal", "Business goal", "text"),
            _field("target_users", "Target users", "text"),
            _field(
                "brand_assets_available",
                "Brand assets available",
                "select",
                ["Yes", "Partial", "None"],
            ),
            _field(
                "expected_deliverables",
                "Expected deliverables",
                "multiselect",
                [
                    "Source files", "Print-ready files", "Social media versions",
                    "Multiple revisions", "Brand guideline",
                ],
            ),
        ],
    },
    {
        "value": "digital-marketing-consulting",
        "label": "Digital Marketing Consulting",
        "fields": [
            _field(
                "marketing_objective",
                "Marketing objective",
                "select",
                ["Brand awareness", "Lead generation", "Sales", "Website traffic", "Customer retention", "Other"],
            ),
            _field(
                "marketing_channels",
                "Marketing channels",
                "multiselect",
                ["Facebook", "Instagram", "TikTok", "Google", "LinkedIn", "Email", "Other"],
            ),
            _field("target_audience", "Target audience", "text"),
            _field(
                "services_required",
                "Services required",
                "multiselect",
                ["Strategy", "Advertising", "SEO", "Content planning", "Analytics", "Campaign management"],
            ),
            _field(
                "current_marketing_status",
                "Current marketing status",
                "select",
                ["No marketing yet", "Existing campaigns", "Need optimization"],
            ),
        ],
    },
    {
        "value": "content-writer",
        "label": "Copywriter / Content Writer",
        "fields": [
            _field(
                "content_type",
                "Content type",
                "select",
                [
                    "Website copy", "Blog", "Product descriptions", "Email", "Advertisement",
                    "Social media", "Script", "Press release", "Other",
                ],
            ),
            _field(
                "content_objective",
                "Content objective",
                "select",
                ["Inform", "Sell", "Educate", "Promote", "Entertain"],
            ),
            _field("target_audience", "Target audience", "text"),
            _field(
                "tone_of_writing",
                "Tone of writing",
                "select",
                ["Professional", "Friendly", "Formal", "Casual", "Persuasive"],
            ),
            _field("content_volume", "Approximate content volume", "text"),
        ],
    },
    {
        "value": "photography&videography",
        "label": "Photography & Videography",
        "fields": [
            _field(
                "project_type",
                "Project type",
                "select",
                [
                    "Portrait", "Wedding", "Event", "Product", "Food", "Corporate",
                    "Real estate", "Commercial video", "Social media content", "Other",
                ],
            ),
            _field(
                "purpose",
                "Purpose",
                "select",
                ["Marketing", "Personal", "Corporate", "Documentation", "Other"],
            ),
            _field(
                "location",
                "Location",
                "select",
                ["Studio", "Client location", "Outdoor", "Not decided"],
            ),
            _field(
                "required_deliverables",
                "Required deliverables",
                "multiselect",
                ["Edited photos", "Raw photos", "Highlight video", "Full video", "Short-form social media clips"],
            ),
            _field(
                "estimated_duration",
                "Estimated duration",
                "select",
                ["Half day", "One day", "Multiple days", "Other"],
            ),
        ],
    },
]

PROFESSIONS_BY_VALUE: dict[str, ProfessionDef] = {p["value"]: p for p in PROFESSIONS}


def required_field_keys(profession: str) -> set[str]:
    profession_def = PROFESSIONS_BY_VALUE.get(profession)
    if profession_def is None:
        return set()
    return {f["field_key"] for f in profession_def["fields"] if f["is_required"]}