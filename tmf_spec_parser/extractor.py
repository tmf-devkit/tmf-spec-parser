"""
extractor.py — Parse an OpenAPI spec dict and extract structured metadata.

For each API spec we extract:
  - api_id, display name, version, description
  - entities  : list of {name, mandatory, optional} from components/schemas
  - lifecycle : list of valid state values (from enum on state/status fields)
  - links     : cross-API directed edges inferred from $ref schema names

What we deliberately do NOT auto-extract (stays in config.py):
  - Lifecycle transitions (not encoded in OpenAPI)
  - Terminal states (inferrable but error-prone)
  - Integration patterns
"""

from __future__ import annotations

import re
from typing import Any

from tmf_spec_parser.config import (
    LIFECYCLE_FIELD_NAMES,
    SCHEMA_TO_API,
    SCHEMA_TO_LABEL,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_schemas(spec: dict) -> dict[str, dict]:
    """Return the schema definitions dict, handling both OAS3 and Swagger 2."""
    return (
        spec.get("components", {}).get("schemas", {})
        or spec.get("definitions", {})
        or {}
    )


def _resolve_ref(ref: str) -> str:
    """Extract the schema name from a $ref string, e.g. '#/definitions/Foo' → 'Foo'."""
    return ref.split("/")[-1]


def _walk_schema(
    schema: dict,
    schemas: dict[str, dict],
    visited: set[str] | None = None,
) -> dict[str, Any]:
    """
    Recursively resolve $ref and allOf/anyOf chains.
    Returns a flattened dict of {property_name: property_schema}.
    Stops at depth 5 to prevent infinite recursion on circular refs.
    """
    if visited is None:
        visited = set()

    props: dict[str, Any] = {}

    # Direct $ref
    if "$ref" in schema:
        ref_name = _resolve_ref(schema["$ref"])
        if ref_name not in visited and ref_name in schemas:
            visited = visited | {ref_name}
            props.update(_walk_schema(schemas[ref_name], schemas, visited))
        return props

    # allOf / anyOf composition
    for combiner in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(combiner, []):
            props.update(_walk_schema(sub, schemas, visited))

    # Direct properties
    props.update(schema.get("properties", {}))
    return props


def _extract_lifecycle_from_schema(
    schema: dict,
    schemas: dict[str, dict],
) -> list[str]:
    """
    Find lifecycle state values by scanning for enum fields whose name matches
    LIFECYCLE_FIELD_NAMES.  Returns a sorted-by-definition-order list.
    """
    all_props = _walk_schema(schema, schemas)
    for field_name, field_schema in all_props.items():
        if field_name not in LIFECYCLE_FIELD_NAMES:
            continue
        # Inline enum
        if "enum" in field_schema:
            return [str(v) for v in field_schema["enum"] if v is not None]
        # $ref to a schema that has the enum
        if "$ref" in field_schema:
            ref_name = _resolve_ref(field_schema["$ref"])
            if ref_name in schemas:
                sub = schemas[ref_name]
                if "enum" in sub:
                    return [str(v) for v in sub["enum"] if v is not None]
    return []


def _is_root_entity(name: str, schema: dict) -> bool:
    """
    Heuristic: an entity worth exposing has 'properties' or uses allOf,
    is not purely a Ref/Enum helper, and has a non-trivial name.
    """
    if name.endswith(("Ref", "Type", "Enum", "FVO", "MVO", "Create", "Update")):
        return False
    has_props = bool(schema.get("properties")) or bool(schema.get("allOf"))
    return has_props


def _extract_mandatory_optional(
    schema: dict,
    schemas: dict[str, dict],
) -> tuple[list[str], list[str]]:
    """Return (mandatory_fields, optional_fields) for a schema."""
    all_props  = _walk_schema(schema, schemas)
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


def _extract_cross_api_links(
    api_id: str,
    schemas: dict[str, dict],
) -> list[dict[str, str]]:
    """
    Walk all schemas looking for $ref names that match SCHEMA_TO_API.
    Emits directed edges: api_id → target_api_id.
    Deduplicates — one edge per (source, target, label) triple.
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


def _spec_version(spec: dict) -> str:
    """Extract version string from info.version."""
    return str(spec.get("info", {}).get("version", "unknown"))


def _spec_description(spec: dict) -> str:
    """First sentence of info.description, cleaned up."""
    raw = spec.get("info", {}).get("description", "")
    raw = re.sub(r"#+\s*", "", raw)
    raw = raw.replace("\n", " ").strip()
    match = re.match(r"([^.!?]+[.!?])", raw)
    return match.group(1).strip() if match else raw[:200]


# ── Main public function ───────────────────────────────────────────────────────

def extract(api_id: str, spec: dict) -> dict:
    """
    Extract structured metadata from one API's OpenAPI spec.

    Returns a dict matching the shape consumed by emitter.py:
    {
        "id":          "TMF641",
        "version":     "4.1.0",
        "description": "...",
        "entities":    [{"name": "...", "mandatory": [...], "optional": [...]}],
        "lifecycle":   [...],
        "links":       [{"source": "TMF641", "target": "TMF638", "label": "..."}],
    }
    """
    schemas = _get_schemas(spec)
    version = _spec_version(spec)
    description = _spec_description(spec)

    # ── Entities ──────────────────────────────────────────────────────────────
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
    entities = entities[:4]

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    lifecycle: list[str] = []
    for entity in entities:
        schema = schemas.get(entity["name"], {})
        states = _extract_lifecycle_from_schema(schema, schemas)
        if states:
            lifecycle = states
            break
    if not lifecycle:
        for _name, schema in schemas.items():
            states = _extract_lifecycle_from_schema(schema, schemas)
            if states:
                lifecycle = states
                break

    # ── Cross-API links ────────────────────────────────────────────────────────
    links = _extract_cross_api_links(api_id, schemas)

    return {
        "id":          api_id,
        "version":     version,
        "description": description,
        "entities":    entities,
        "lifecycle":   lifecycle,
        "links":       links,
    }


def extract_all(specs: dict[str, dict]) -> dict[str, dict]:
    """
    Run extract() for each API in the specs dict.

    Parameters
    ----------
    specs : {api_id: spec_dict}

    Returns
    -------
    {api_id: extracted_dict}
    """
    return {api_id: extract(api_id, spec) for api_id, spec in specs.items()}
