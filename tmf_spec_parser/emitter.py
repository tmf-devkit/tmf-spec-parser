"""
emitter.py — Assemble and write tmf_data.json (and optional JS/TS module).

Key addition in v0.2: curated baseline merge.
  _CURATED_BASELINE holds hand-verified entities, lifecycle, and descriptions
  for all 16 APIs.  Any field that the extractor left empty falls back to the
  curated value.  This means the output is always complete even when live spec
  fetch/extraction is partial.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tmf_spec_parser import __version__
from tmf_spec_parser.config import (
    API_REGISTRY,
    PATTERNS,
    TERMINAL_STATES,
    TRANSITIONS,
)

# ── Curated entity helpers (broken out to keep lines ≤100 chars) ──────────────

def _e(name: str, mandatory: list[str], optional: list[str]) -> dict:
    return {"name": name, "mandatory": mandatory, "optional": optional}


_ENT = {
    "TMF641": [
        _e("ServiceOrder",
           ["id", "state", "orderDate"],
           ["requestedStartDate", "requestedCompletionDate", "priority",
            "description", "category"]),
        _e("ServiceOrderItem",
           ["id", "action", "state"],
           ["quantity", "service", "orderItemRelationship", "appointment"]),
    ],
    "TMF638": [
        _e("Service",
           ["id", "name", "state", "serviceType"],
           ["startDate", "endDate", "serviceCharacteristic",
            "serviceRelationship", "supportingResource", "place"]),
    ],
    "TMF639": [
        _e("Resource",
           ["id", "name", "resourceStatus"],
           ["resourceType", "startOperatingDate", "endOperatingDate",
            "resourceCharacteristic", "activationFeature", "place"]),
    ],
    "TMF629": [
        _e("Customer",
           ["id", "status", "engagedParty"],
           ["name", "customerRank", "validFor", "relatedParty",
            "paymentMethod", "contactMedium"]),
    ],
    "TMF622": [
        _e("ProductOrder",
           ["id", "state", "orderDate"],
           ["requestedStartDate", "requestedCompletionDate",
            "channel", "relatedParty"]),
        _e("ProductOrderItem",
           ["id", "action", "state"],
           ["quantity", "productOffering", "billingAccount", "itemPrice"]),
    ],
    "TMF633": [
        _e("ServiceSpecification",
           ["id", "name", "lifecycleStatus"],
           ["version", "description", "validFor",
            "serviceSpecCharacteristic", "resourceSpecification"]),
    ],
    "TMF634": [
        _e("ResourceSpecification",
           ["id", "name", "lifecycleStatus"],
           ["version", "category", "description",
            "resourceSpecCharacteristic", "resourceSpecRelationship"]),
    ],
    "TMF620": [
        _e("ProductOffering",
           ["id", "name", "lifecycleStatus"],
           ["version", "description", "productSpecification",
            "place", "validFor"]),
        _e("ProductSpecification",
           ["id", "name", "lifecycleStatus"],
           ["version", "brand", "productSpecCharacteristic",
            "serviceSpecification"]),
    ],
    "TMF621": [
        _e("TroubleTicket",
           ["id", "name", "severity", "status"],
           ["requestedResolutionDate", "resolutionDate", "relatedEntity",
            "relatedParty", "note", "channel"]),
    ],
    "TMF637": [
        _e("Product",
           ["id", "status", "productOffering"],
           ["name", "description", "startDate", "endDate",
            "productCharacteristic", "realizingService", "place"]),
    ],
    "TMF645": [
        _e("ServiceQualification",
           ["id", "state"],
           ["requestedResponseDate", "serviceQualificationItem",
            "relatedParty", "expirationDate"]),
    ],
    "TMF652": [
        _e("ResourceOrder",
           ["id", "state", "orderDate"],
           ["requestedStartDate", "requestedCompletionDate",
            "relatedParty", "channel"]),
        _e("ResourceOrderItem",
           ["id", "action", "state"],
           ["quantity", "resource", "orderItemRelationship", "appointment"]),
    ],
    "TMF653": [
        _e("ServiceTest",
           ["id", "state", "serviceTestSpecification"],
           ["startDateTime", "endDateTime", "testMeasure",
            "relatedService", "place"]),
    ],
    "TMF656": [
        _e("ServiceProblem",
           ["id", "status", "priority", "category"],
           ["affectedService", "originatingSystem", "relatedTroubleTicket",
            "statusChangeDate", "resolutionDate"]),
    ],
    "TMF688": [
        _e("EventSubscription",
           ["id", "callback", "query"],
           ["fields"]),
        _e("Event",
           ["eventId", "eventTime", "eventType"],
           ["correlationId", "domain", "href", "priority"]),
    ],
    "TMF632": [
        _e("Individual",
           ["id", "fullName"],
           ["birthDate", "nationality", "gender",
            "maritalStatus", "contactMedium"]),
        _e("Organization",
           ["id", "name", "tradingName"],
           ["organizationIdentification", "organizationType",
            "contactMedium", "relatedParty"]),
    ],
}

_LC = {
    "TMF641": ["acknowledged", "inProgress", "pending", "held",
               "completed", "failed", "cancelled"],
    "TMF638": ["feasibilityChecked", "designed", "reserved",
               "active", "inactive", "terminated"],
    "TMF639": ["standby", "alarm", "available", "reserved",
               "suspended", "retired"],
    "TMF629": ["pending", "approved", "inactive", "terminated"],
    "TMF622": ["acknowledged", "inProgress", "pending", "held",
               "completed", "failed", "cancelled"],
    "TMF633": ["inStudy", "inDesign", "inTest", "active", "launched", "retired"],
    "TMF634": ["inStudy", "inDesign", "inTest", "active", "launched", "retired"],
    "TMF620": ["inStudy", "inDesign", "inTest", "active", "launched",
               "retired", "obsolete"],
    "TMF621": ["acknowledged", "inProgress", "pending", "held",
               "resolved", "closed", "cancelled"],
    "TMF637": ["created", "pending", "active", "inactive", "terminated"],
    "TMF645": ["acknowledged", "inProgress", "done.unableToProvide",
               "done.provideAlternative", "done.standard"],
    "TMF652": ["acknowledged", "inProgress", "pending", "held",
               "completed", "failed", "cancelled"],
    "TMF653": ["acknowledged", "inProgress", "completed", "failed", "cancelled"],
    "TMF656": ["submitted", "acknowledged", "held", "inProgress",
               "resolved", "closed"],
    "TMF688": [],
    "TMF632": [],
}

_DESC = {
    "TMF641": (
        "Manages end-to-end service order lifecycle from customer"
        " acknowledgement through fulfillment."
    ),
    "TMF638": (
        "Provides a queryable register of all instantiated services"
        " provisioned in the network."
    ),
    "TMF639": (
        "Manages physical and logical resources — network elements,"
        " ports, circuits, IP addresses."
    ),
    "TMF629": (
        "Manages customer accounts including profile, preferences,"
        " and account lifecycle."
    ),
    "TMF622": (
        "Handles product order creation and tracking against the product catalog."
    ),
    "TMF633": (
        "Manages service specifications that define characteristics"
        " and behaviours of services."
    ),
    "TMF634": (
        "Manages resource specifications defining physical and logical"
        " network resource characteristics."
    ),
    "TMF620": (
        "Manages product offerings and product specifications available"
        " in the product catalog."
    ),
    "TMF621": (
        "Manages trouble tickets for tracking service issues raised"
        " by customers or network operations."
    ),
    "TMF637": (
        "Manages the inventory of product instances provisioned for customers."
    ),
    "TMF645": (
        "Determines technical and commercial feasibility of provisioning"
        " a service before an order is placed."
    ),
    "TMF652": (
        "Creates and tracks orders for provisioning physical or logical"
        " network resources."
    ),
    "TMF653": (
        "Manages service test instances — scheduling, execution,"
        " and result retrieval."
    ),
    "TMF656": (
        "Manages service problems detected from network alarms or trouble tickets."
    ),
    "TMF688": (
        "Provides a standardised publish-subscribe event notification"
        " mechanism used across all TMF APIs."
    ),
    "TMF632": (
        "Manages party entities (individuals and organisations)"
        " and their relationships."
    ),
}


def _merge_with_baseline(api_id: str, extracted: dict) -> dict:
    """Extracted values take priority; baseline fills any gaps."""
    return {
        "description": extracted.get("description") or _DESC.get(api_id, ""),
        "entities":    extracted.get("entities")    or _ENT.get(api_id, []),
        "lifecycle":   extracted.get("lifecycle")   or _LC.get(api_id, []),
    }


# ── Link assembly ─────────────────────────────────────────────────────────────

def _build_links(extracted: dict[str, dict]) -> list[dict[str, str]]:
    """Merge auto-extracted cross-API links, deduplicated."""
    seen:  set[tuple[str, str, str]] = set()
    links: list[dict[str, str]]      = []

    for _api_id, data in extracted.items():
        for link in data.get("links", []):
            key = (link["source"], link["target"], link["label"])
            if key not in seen:
                seen.add(key)
                links.append(link)

    links.sort(key=lambda lnk: (lnk["source"], lnk["target"]))
    return links


def _build_details(extracted: dict[str, dict]) -> dict[str, dict]:
    """Build the details section merging extracted + curated baseline."""
    details: dict[str, dict] = {}

    for entry in API_REGISTRY:
        api_id  = entry["id"]
        ext     = extracted.get(api_id, {})
        merged  = _merge_with_baseline(api_id, ext)

        version  = ext.get("version", "unknown")
        spec_ref = f"{api_id} v{version}" if version != "unknown" else api_id

        details[api_id] = {
            "specRef":     spec_ref,
            "description": merged["description"],
            "entities":    merged["entities"],
            "lifecycle":   merged["lifecycle"],
            "terminal":    TERMINAL_STATES.get(api_id, []),
            "transitions": TRANSITIONS.get(api_id, []),
        }

    return details


# ── Public API ────────────────────────────────────────────────────────────────

def build(extracted: dict[str, dict]) -> dict:
    """Assemble the full tmf_data structure."""
    return {
        "generated_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parser_version": __version__,
        "apis":           API_REGISTRY,
        "links":          _build_links(extracted),
        "patterns":       PATTERNS,
        "details":        _build_details(extracted),
    }


def write_json(data: dict, output_path: Path, indent: int = 2) -> None:
    """Write tmf_data.json to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, indent=indent, ensure_ascii=False),
        encoding="utf-8",
    )


def write_js_module(data: dict, output_path: Path) -> None:
    """Write a JavaScript ES module for direct import in React/Vite."""
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    header = (
        f"// Auto-generated by tmf-spec-parser v{__version__}\n"
        "// Do not edit manually — run: tmf-spec-parser generate\n\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(header + f"export default {json_str};\n", encoding="utf-8")


def write_ts_module(data: dict, output_path: Path) -> None:
    """Write a TypeScript module with inline type annotation."""
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    header = (
        f"// Auto-generated by tmf-spec-parser v{__version__}\n"
        "// Do not edit manually — run: tmf-spec-parser generate\n\n"
        "export interface TmfData { [key: string]: unknown; }\n\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        header + f"const TMF_DATA: TmfData = {json_str};\n\nexport default TMF_DATA;\n",
        encoding="utf-8",
    )


def load_existing(path: Path) -> dict | None:
    """Load an existing tmf_data.json for diffing. Returns None if not found."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
