"""
extractor.py — Parse an OpenAPI spec dict and extract structured metadata.

For each API spec we extract:
  - api_id, version, description
  - entities  : list of {name, mandatory, optional} from components/schemas
  - lifecycle : list of valid state values (from enum on state/status fields)
  - links     : cross-API directed edges inferred from $ref schema names

What we deliberately do NOT auto-extract (stays in config.py):
  - Lifecycle transitions (not encoded in OpenAPI)
  - Terminal states
  - Integration patterns
"""

from __future__ import annotations

import re
from typing import Any

from tmf_spec_parser.config import (
    SCHEMA_TO_API,
    SCHEMA_TO_LABEL,
)

# All field names that may carry lifecycle state values.
# Expanded to include real patterns found in TMForum repos.
LIFECYCLE_FIELD_NAMES: set[str] = {
    "state", "status", "lifecycleStatus", "resourceStatus", "lifecycleState",
}

# Suffixes that identify pure enum/type helper schemas (not root entities)
_HELPER_SUFFIXES = (
    "Ref", "Type", "Enum", "FVO", "MVO", "Create", "Update",
    "Request", "Response", "Event", "Notification",
)

# Name patterns that clearly identify lifecycle/state enum schemas
_STATE_SCHEMA_PATTERNS = re.compile(
    r"(state|status|lifecycle|phase|condition)", re.IGNORECASE
)


# ── Schema location ───────────────────────────────────────────────────────────

def _get_schemas(spec: dict) -> dict[str, dict]:
    """Return schema definitions dict, handling both OAS3 and Swagger 2."""
    return (
        spec.get("components", {}).get("schemas", {})
        or spec.get("definitions", {})
        or {}
    )


def _resolve_ref(ref: str) -> str:
    """'#/definitions/Foo' → 'Foo'"""
    return ref.split("/")[-1]


# ── Schema walking ────────────────────────────────────────────────────────────

def _walk_schema(
    schema: dict,
    schemas: dict[str, dict],
    visited: set[str] | None = None,
    depth: int = 0,
) -> dict[str, Any]:
    """
    Recursively resolve $ref and allOf/anyOf chains.
    Returns a flat {property_name: property_schema} dict.
    """
    if visited is None:
        visited = set()
    if depth > 6:
        return {}

    props: dict[str, Any] = {}

    if "$ref" in schema:
        ref_name = _resolve_ref(schema["$ref"])
        if ref_name not in visited and ref_name in schemas:
            props.update(
                _walk_schema(schemas[ref_name], schemas, visited | {ref_name}, depth + 1)
            )
        return props

    for combiner in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(combiner, []):
            props.update(_walk_schema(sub, schemas, visited, depth + 1))

    props.update(schema.get("properties", {}))
    return props


# ── Lifecycle extraction ──────────────────────────────────────────────────────

def _enum_from_schema(schema: dict, schemas: dict[str, dict], depth: int = 0) -> list[str]:
    """
    Resolve a schema to its enum values, following $ref chains up to depth 3.
    Returns [] if no enum found.
    """
    if depth > 3:
        return []
    if "enum" in schema:
        return [str(v) for v in schema["enum"] if v is not None]
    if "$ref" in schema:
        ref_name = _resolve_ref(schema["$ref"])
        if ref_name in schemas:
            return _enum_from_schema(schemas[ref_name], schemas, depth + 1)
    for combiner in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(combiner, []):
            result = _enum_from_schema(sub, schemas, depth + 1)
            if result:
                return result
    return []


def _lifecycle_from_entity(
    entity_schema: dict,
    schemas: dict[str, dict],
) -> list[str]:
    """
    Try to find lifecycle states from a specific entity schema.
    Checks the known lifecycle field names, following $ref chains.
    """
    all_props = _walk_schema(entity_schema, schemas)
    for field_name, field_schema in all_props.items():
        if field_name not in LIFECYCLE_FIELD_NAMES:
            continue
        states = _enum_from_schema(field_schema, schemas)
        if states:
            return states
    return []


def _lifecycle_from_standalone_enums(schemas: dict[str, dict]) -> list[str]:
    """
    Fallback: scan ALL schemas for one that looks like a standalone state enum.
    Matches schemas whose name contains 'state'/'status'/'lifecycle'
    AND whose top-level type is string with an enum.

    Returns the enum from the first (largest) matching schema found.
    """
    candidates: list[tuple[int, list[str]]] = []
    for name, schema in schemas.items():
        if not _STATE_SCHEMA_PATTERNS.search(name):
            continue
        # Must be a simple string enum at top level
        if schema.get("type") == "string" and "enum" in schema:
            values = [str(v) for v in schema["enum"] if v is not None]
            if len(values) >= 2:
                candidates.append((len(values), values))
        # Or an allOf/oneOf wrapping a string enum
        for combiner in ("allOf", "anyOf", "oneOf"):
            for sub in schema.get(combiner, []):
                if sub.get("type") == "string" and "enum" in sub:
                    values = [str(v) for v in sub["enum"] if v is not None]
                    if len(values) >= 2:
                        candidates.append((len(values), values))

    if not candidates:
        return []
    candidates.sort(reverse=True)
    return candidates[0][1]


def extract_lifecycle(api_id: str, schemas: dict[str, dict], entities: list[dict]) -> list[str]:
    """
    Full lifecycle extraction pipeline:
    1. Try each known root entity first (most reliable)
    2. Fall back to scanning all schemas for state enum helpers
    """
    # Try root entities
    for entity in entities:
        schema = schemas.get(entity["name"], {})
        states = _lifecycle_from_entity(schema, schemas)
        if states:
            return states

    # Broader scan over all schemas using known field names
    for _name, schema in schemas.items():
        states = _lifecycle_from_entity(schema, schemas)
        if states:
            return states

    # Last resort: standalone enum schema scan
    return _lifecycle_from_standalone_enums(schemas)


# ── Entity extraction ─────────────────────────────────────────────────────────

def _is_root_entity(name: str, schema: dict) -> bool:
    """
    Heuristic: a root entity has properties/allOf and is not a helper type.
    """
    if name.endswith(_HELPER_SUFFIXES):
        return False
    has_props = bool(schema.get("properties")) or bool(schema.get("allOf"))
    return has_props


def _extract_mandatory_optional(
    schema: dict,
    schemas: dict[str, dict],
) -> tuple[list[str], list[str]]:
    """Return (mandatory_fields, optional_fields) for a schema."""
    all_props = _walk_schema(schema, schemas)

    required: set[str] = set(schema.get("required", []))
    for sub in schema.get("allOf", []):
        required.update(sub.get("required", []))
        if "$ref" in sub:
            ref_name = _resolve_ref(sub["$ref"])
            if ref_name in schemas:
                required.update(schemas[ref_name].get("required", []))

    mandatory = [p for p in all_props if p in required]
    optional  = [p for p in all_props if p not in required]
    return mandatory, optional[:12]


def _extract_entities(schemas: dict[str, dict]) -> list[dict]:
    """
    Extract root entities from all schemas.
    Sorted by total field count (most fields first), capped at 4.
    """
    entities: list[dict] = []
    for name, schema in schemas.items():
        if not _is_root_entity(name, schema):
            continue
        mandatory, optional = _extract_mandatory_optional(schema, schemas)
        if not mandatory and not optional:
            continue
        entities.append({
            "name":      name,
            "mandatory": mandatory,
            "optional":  optional,
        })

    entities.sort(key=lambda e: len(e["mandatory"]) + len(e["optional"]), reverse=True)
    return entities[:4]


# ── Cross-API link extraction ─────────────────────────────────────────────────

def _extract_links(api_id: str, schemas: dict[str, dict]) -> list[dict[str, str]]:
    """
    Walk all schemas for $ref names matching SCHEMA_TO_API.
    Emits deduplicated directed edges: api_id → target_api_id.
    """
    seen:  set[tuple[str, str, str]] = set()
    links: list[dict[str, str]]      = []

    def _scan(obj: Any) -> None:
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_name = _resolve_ref(obj["$ref"])
                target = SCHEMA_TO_API.get(ref_name)
                if target and target != api_id:
                    label = SCHEMA_TO_LABEL.get(ref_name, f"references {ref_name}")
                    key   = (api_id, target, label)
                    if key not in seen:
                        seen.add(key)
                        links.append({"source": api_id, "target": target, "label": label})
            for v in obj.values():
                _scan(v)
        elif isinstance(obj, list):
            for item in obj:
                _scan(item)

    _scan(schemas)
    return links


# ── Description cleaning ──────────────────────────────────────────────────────

# Boilerplate phrases found in real TMForum spec descriptions
_BOILERPLATE = re.compile(
    r"(this is swagger ui|swagger ui environment|generated for the|"
    r"tmf api reference\s*[:–-]?\s*|tmf\s*\d+\s*[-–]?\s*|"
    r"\*+|\s{2,})",
    re.IGNORECASE,
)


def _clean_description(raw: str) -> str:
    """Extract a clean first sentence from a spec's info.description."""
    if not raw:
        return ""
    # Strip markdown, normalize whitespace
    text = re.sub(r"#+\s*", "", raw)
    text = text.replace("\n", " ").replace("\r", "")
    text = _BOILERPLATE.sub(" ", text).strip()
    text = re.sub(r"\s{2,}", " ", text).strip()
    # First sentence only
    match = re.match(r"([^.!?]{10,}[.!?])", text)
    result = match.group(1).strip() if match else text[:200].strip()
    # If it still looks like boilerplate, return empty (emitter will use curated)
    if len(result) < 15 or "swagger" in result.lower():
        return ""
    return result


def _spec_version(spec: dict) -> str:
    return str(spec.get("info", {}).get("version", "unknown"))


def _spec_description(spec: dict) -> str:
    raw = spec.get("info", {}).get("description", "")
    return _clean_description(raw)


# ── Main public function ──────────────────────────────────────────────────────

def extract(api_id: str, spec: dict) -> dict:
    """
    Extract structured metadata from one API's OpenAPI spec.

    Returns
    -------
    {
        "id":          "TMF641",
        "version":     "4.1.0",
        "description": "...",
        "entities":    [{"name": ..., "mandatory": [...], "optional": [...]}],
        "lifecycle":   [...],
        "links":       [{"source": ..., "target": ..., "label": ...}],
    }
    """
    schemas    = _get_schemas(spec)
    version    = _spec_version(spec)
    description = _spec_description(spec)
    entities   = _extract_entities(schemas)
    lifecycle  = extract_lifecycle(api_id, schemas, entities)
    links      = _extract_links(api_id, schemas)

    return {
        "id":          api_id,
        "version":     version,
        "description": description,
        "entities":    entities,
        "lifecycle":   lifecycle,
        "links":       links,
    }


def extract_all(specs: dict[str, dict]) -> dict[str, dict]:
    """Run extract() for each API in the specs dict."""
    return {api_id: extract(api_id, spec) for api_id, spec in specs.items()}
