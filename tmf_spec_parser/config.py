"""
config.py — Static knowledge tables for tmf-spec-parser.

Two categories:
  1. AUTO-DERIVED at parse time from OpenAPI specs (entities, lifecycle states,
     version, description).
  2. CURATED here because they cannot be reliably extracted from OpenAPI specs:
       - SCHEMA_TO_API   : maps well-known cross-API $ref schema names to API id
       - TRANSITIONS     : valid lifecycle state transitions (from CTK test cases)
       - TERMINAL_STATES : which states are end-states
"""

from __future__ import annotations

# ── Supported API registry ─────────────────────────────────────────────────────
API_REGISTRY: list[dict] = [
    # Customer domain
    {
        "id": "TMF629", "name": "Customer Management",
        "domain": "customer", "short": "Customer Mgmt",
        "repo": "TMF629_CustomerManagement",
    },
    # Product domain
    {
        "id": "TMF620", "name": "Product Catalog",
        "domain": "product", "short": "Product Catalog",
        "repo": "TMF620_ProductCatalog",
    },
    {
        "id": "TMF622", "name": "Product Ordering",
        "domain": "product", "short": "Product Ordering",
        "repo": "TMF622_ProductOrder",
    },
    {
        "id": "TMF637", "name": "Product Inventory",
        "domain": "product", "short": "Product Inventory",
        "repo": "TMF637_ProductInventory",
    },
    # Service domain
    {
        "id": "TMF633", "name": "Service Catalog",
        "domain": "service", "short": "Service Catalog",
        "repo": "TMF633_ServiceCatalog",
    },
    {
        "id": "TMF638", "name": "Service Inventory",
        "domain": "service", "short": "Service Inventory",
        "repo": "TMF638_ServiceInventory",
    },
    {
        "id": "TMF641", "name": "Service Ordering",
        "domain": "service", "short": "Service Ordering",
        "repo": "TMF641_ServiceOrder",
    },
    {
        "id": "TMF645", "name": "Service Qualification",
        "domain": "service", "short": "Service Qual",
        "repo": "TMF645_ServiceQualification",
    },
    {
        "id": "TMF653", "name": "Service Test",
        "domain": "service", "short": "Service Test",
        "repo": "TMF653_ServiceTestManagement",
    },
    # Resource domain
    {
        "id": "TMF634", "name": "Resource Catalog",
        "domain": "resource", "short": "Resource Catalog",
        "repo": "TMF634_ResourceCatalog",
    },
    {
        "id": "TMF639", "name": "Resource Inventory",
        "domain": "resource", "short": "Resource Inventory",
        "repo": "TMF639_ResourceInventory",
    },
    {
        "id": "TMF652", "name": "Resource Ordering",
        "domain": "resource", "short": "Resource Ordering",
        "repo": "TMF652_ResourceOrderManagement",
    },
    # Engagement domain
    {
        "id": "TMF621", "name": "Trouble Ticket",
        "domain": "engagement", "short": "Trouble Ticket",
        "repo": "TMF621_TroubleTicket",
    },
    {
        "id": "TMF656", "name": "Service Problem",
        "domain": "engagement", "short": "Service Problem",
        "repo": "TMF656_ServiceProblemManagement",
    },
    # Common domain — shared base abstractions used across all domains
    {
        "id": "TMF632", "name": "Party Management",
        "domain": "common", "short": "Party Mgmt",
        "repo": "TMF632_PartyManagement",
    },
    {
        "id": "TMF688", "name": "Event Management",
        "domain": "common", "short": "Event Mgmt",
        "repo": "TMF688-Event",
    },
]

API_IDS: list[str] = [a["id"] for a in API_REGISTRY]

# ── GitHub raw content base URL ───────────────────────────────────────────────
GITHUB_ORG = "tmforum-apis"
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/{org}/{repo}/master/{path}"
)
GITHUB_API_BASE = "https://api.github.com/repos/{org}/{repo}/contents/"

# ── ODA Component manifests ───────────────────────────────────────────────────
# The official staging repo for ODA Component (ODAC) YAML manifests, declared
# in tmforum-oda/oda-ca-docs as "the definitive repo for delivered Components".
# At tag v1.0.0 there are 37 components, each in its own folder named
# TMFC{nnn}-{Name} (e.g. TMFC008-ServiceInventory).
ODA_GITHUB_ORG  = "tmforum-rand"
ODA_GITHUB_REPO = "TMForum-ODA-Ready-for-publication"
ODA_REPO_REF    = "v1.0.0"  # Tag pinned to known-good release.

# Manifests use one of three CRD versions in the wild — the extractor must
# normalise across all three (see oda_extractor.py).
ODA_CRD_VERSIONS = ("v1", "v1beta3", "v1beta2")

# Spec source identifier embedded in oda_data.json for traceability.
ODA_SPEC_SOURCE = (
    f"github.com/{ODA_GITHUB_ORG}/{ODA_GITHUB_REPO}@{ODA_REPO_REF}"
)

# ── Cross-API schema → API mapping (curated) ─────────────────────────────────
SCHEMA_TO_API: dict[str, str] = {
    # Service domain
    "ServiceRef":                  "TMF638",
    "ServiceSpecificationRef":     "TMF633",
    "ServiceOrderRef":             "TMF641",
    "ServiceQualificationRef":     "TMF645",
    "ServiceTestRef":              "TMF653",
    "ServiceTestSpecificationRef": "TMF653",
    # Resource domain
    "ResourceRef":                 "TMF639",
    "ResourceSpecificationRef":    "TMF634",
    "ResourceOrderRef":            "TMF652",
    # Product domain
    "ProductOfferingRef":          "TMF620",
    "ProductSpecificationRef":     "TMF620",
    "ProductOrderRef":             "TMF622",
    "ProductRef":                  "TMF637",
    # Customer / Party domain
    "CustomerRef":                 "TMF629",
    "PartyRef":                    "TMF632",
    "PartyRoleRef":                "TMF632",
    "IndividualRef":               "TMF632",
    "OrganizationRef":             "TMF632",
    "RelatedParty":                "TMF632",
    # Engagement
    "TroubleTicketRef":            "TMF621",
    "ServiceProblemRef":           "TMF656",
    # Events / common
    "EventSubscriptionRef":        "TMF688",
}

SCHEMA_TO_LABEL: dict[str, str] = {
    "ServiceRef":                  "references Service",
    "ServiceSpecificationRef":     "references ServiceSpec",
    "ServiceOrderRef":             "references ServiceOrder",
    "ServiceQualificationRef":     "references ServiceQual",
    "ServiceTestRef":              "references ServiceTest",
    "ServiceTestSpecificationRef": "references ServiceTestSpec",
    "ResourceRef":                 "references Resource",
    "ResourceSpecificationRef":    "references ResourceSpec",
    "ResourceOrderRef":            "references ResourceOrder",
    "ProductOfferingRef":          "references ProductOffering",
    "ProductSpecificationRef":     "references ProductSpec",
    "ProductOrderRef":             "references ProductOrder",
    "ProductRef":                  "references Product",
    "CustomerRef":                 "references Customer",
    "PartyRef":                    "references Party",
    "PartyRoleRef":                "references PartyRole",
    "IndividualRef":               "references Individual",
    "OrganizationRef":             "references Organization",
    "RelatedParty":                "has RelatedParty",
    "TroubleTicketRef":            "references TroubleTicket",
    "ServiceProblemRef":           "references ServiceProblem",
    "EventSubscriptionRef":        "references EventSubscription",
}

# ── Curated lifecycle transitions (source: TMForum CTK + spec documents) ──────
TRANSITIONS: dict[str, list[dict[str, str]]] = {
    "TMF641": [
        {"from": "acknowledged", "to": "inProgress"},
        {"from": "acknowledged", "to": "cancelled"},
        {"from": "inProgress",   "to": "pending"},
        {"from": "inProgress",   "to": "held"},
        {"from": "inProgress",   "to": "completed"},
        {"from": "inProgress",   "to": "failed"},
        {"from": "inProgress",   "to": "cancelled"},
        {"from": "pending",      "to": "inProgress"},
        {"from": "held",         "to": "inProgress"},
    ],
    "TMF638": [
        {"from": "feasibilityChecked", "to": "designed"},
        {"from": "designed",           "to": "reserved"},
        {"from": "reserved",           "to": "active"},
        {"from": "active",             "to": "inactive"},
        {"from": "inactive",           "to": "active"},
        {"from": "active",             "to": "terminated"},
        {"from": "inactive",           "to": "terminated"},
    ],
    "TMF639": [
        {"from": "standby",   "to": "available"},
        {"from": "available", "to": "reserved"},
        {"from": "reserved",  "to": "available"},
        {"from": "available", "to": "suspended"},
        {"from": "suspended", "to": "available"},
        {"from": "available", "to": "alarm"},
        {"from": "alarm",     "to": "available"},
        {"from": "available", "to": "retired"},
        {"from": "reserved",  "to": "retired"},
        {"from": "suspended", "to": "retired"},
    ],
    "TMF629": [
        {"from": "pending",  "to": "approved"},
        {"from": "pending",  "to": "inactive"},
        {"from": "approved", "to": "inactive"},
        {"from": "inactive", "to": "terminated"},
    ],
    "TMF622": [
        {"from": "acknowledged", "to": "inProgress"},
        {"from": "acknowledged", "to": "cancelled"},
        {"from": "inProgress",   "to": "pending"},
        {"from": "inProgress",   "to": "held"},
        {"from": "inProgress",   "to": "completed"},
        {"from": "inProgress",   "to": "failed"},
        {"from": "inProgress",   "to": "cancelled"},
        {"from": "pending",      "to": "inProgress"},
        {"from": "held",         "to": "inProgress"},
    ],
    "TMF633": [
        {"from": "inStudy",  "to": "inDesign"},
        {"from": "inDesign", "to": "inTest"},
        {"from": "inTest",   "to": "active"},
        {"from": "inTest",   "to": "inStudy"},
        {"from": "active",   "to": "launched"},
        {"from": "launched", "to": "retired"},
    ],
    "TMF634": [
        {"from": "inStudy",  "to": "inDesign"},
        {"from": "inDesign", "to": "inTest"},
        {"from": "inTest",   "to": "active"},
        {"from": "inTest",   "to": "inStudy"},
        {"from": "active",   "to": "launched"},
        {"from": "launched", "to": "retired"},
    ],
    "TMF620": [
        {"from": "inStudy",  "to": "inDesign"},
        {"from": "inDesign", "to": "inTest"},
        {"from": "inTest",   "to": "active"},
        {"from": "inTest",   "to": "inStudy"},
        {"from": "active",   "to": "launched"},
        {"from": "launched", "to": "active"},
        {"from": "launched", "to": "retired"},
        {"from": "launched", "to": "obsolete"},
        {"from": "retired",  "to": "obsolete"},
    ],
    "TMF621": [
        {"from": "acknowledged", "to": "inProgress"},
        {"from": "acknowledged", "to": "cancelled"},
        {"from": "inProgress",   "to": "pending"},
        {"from": "inProgress",   "to": "held"},
        {"from": "inProgress",   "to": "resolved"},
        {"from": "pending",      "to": "inProgress"},
        {"from": "held",         "to": "inProgress"},
        {"from": "resolved",     "to": "closed"},
        {"from": "resolved",     "to": "inProgress"},
    ],
    "TMF637": [
        {"from": "created",  "to": "pending"},
        {"from": "pending",  "to": "active"},
        {"from": "pending",  "to": "inactive"},
        {"from": "active",   "to": "inactive"},
        {"from": "inactive", "to": "active"},
        {"from": "active",   "to": "terminated"},
        {"from": "inactive", "to": "terminated"},
    ],
    "TMF645": [
        {"from": "acknowledged", "to": "inProgress"},
        {"from": "inProgress",   "to": "done.standard"},
        {"from": "inProgress",   "to": "done.provideAlternative"},
        {"from": "inProgress",   "to": "done.unableToProvide"},
    ],
    "TMF652": [
        {"from": "acknowledged", "to": "inProgress"},
        {"from": "acknowledged", "to": "cancelled"},
        {"from": "inProgress",   "to": "pending"},
        {"from": "inProgress",   "to": "held"},
        {"from": "inProgress",   "to": "completed"},
        {"from": "inProgress",   "to": "failed"},
        {"from": "inProgress",   "to": "cancelled"},
        {"from": "pending",      "to": "inProgress"},
        {"from": "held",         "to": "inProgress"},
    ],
    "TMF653": [
        {"from": "acknowledged", "to": "inProgress"},
        {"from": "acknowledged", "to": "cancelled"},
        {"from": "inProgress",   "to": "completed"},
        {"from": "inProgress",   "to": "failed"},
        {"from": "inProgress",   "to": "cancelled"},
    ],
    "TMF656": [
        {"from": "submitted",    "to": "acknowledged"},
        {"from": "acknowledged", "to": "held"},
        {"from": "acknowledged", "to": "inProgress"},
        {"from": "held",         "to": "inProgress"},
        {"from": "inProgress",   "to": "resolved"},
        {"from": "inProgress",   "to": "held"},
        {"from": "resolved",     "to": "closed"},
        {"from": "resolved",     "to": "inProgress"},
    ],
    "TMF688": [],
    "TMF632": [],
}

# ── Terminal states (curated) ─────────────────────────────────────────────────
TERMINAL_STATES: dict[str, list[str]] = {
    "TMF641": ["completed", "failed", "cancelled"],
    "TMF638": ["terminated"],
    "TMF639": ["retired"],
    "TMF629": ["terminated"],
    "TMF622": ["completed", "failed", "cancelled"],
    "TMF633": ["retired"],
    "TMF634": ["retired"],
    "TMF620": ["retired", "obsolete"],
    "TMF621": ["closed", "cancelled"],
    "TMF637": ["terminated"],
    "TMF645": ["done.unableToProvide", "done.provideAlternative", "done.standard"],
    "TMF652": ["completed", "failed", "cancelled"],
    "TMF653": ["completed", "failed", "cancelled"],
    "TMF656": ["closed"],
    "TMF688": [],
    "TMF632": [],
}

# ── Integration patterns (curated) ────────────────────────────────────────────
PATTERNS: list[dict] = [
    {
        "id":    "o2a",
        "name":  "Order-to-Activate",
        "color": "#ff9f0a",
        "nodes": ["TMF629", "TMF622", "TMF641", "TMF638", "TMF639"],
        "desc":  "Customer → Product Order → Service Order → Service → Resource",
    },
    {
        "id":    "c2i",
        "name":  "Catalog-to-Inventory",
        "color": "#5e9bff",
        "nodes": ["TMF620", "TMF633", "TMF634"],
        "desc":  "Sync catalog specifications with provisioned inventory instances",
    },
    {
        "id":    "t2r",
        "name":  "Trouble-to-Resolve",
        "color": "#ff6b6b",
        "nodes": ["TMF621", "TMF656", "TMF638"],
        "desc":  "Incident detection → problem management → service resolution",
    },
]

# ── State field names to scan for lifecycle enums ─────────────────────────────
# Extended set — real TMForum specs use inconsistent field names.
LIFECYCLE_FIELD_NAMES: set[str] = {
    "state", "status", "lifecycleStatus", "resourceStatus", "lifecycleState",
}
