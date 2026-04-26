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
    API_REGISTRY,
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

# Schema-name suffixes that mark generic job/task/operation/integration helpers.
# TMF Catalog APIs all include ImportJob and ExportJob with a status enum like
# ('Not Started', 'Running', 'Succeeded', 'Failed') — that's not catalog state.
# Excluding these prevents Catalog APIs from extracting the wrong lifecycle.
_GENERIC_HELPER_PATTERNS = re.compile(
    r"(Job|Task|Operation|Process|Migration|Hub|Listener|Subscription)$",
)

# Suffixes for entity schemas treated as derived variants — should NOT seed
# lifecycle on their own (they're create/update payloads, events, etc.).
_VARIANT_SUFFIXES = ("FVO", "MVO", "Create", "Update", "Patch", "Event",
                     "Notification", "Request", "Response")

# Suffixes stripped from a state-enum schema name to find its "stem".
# e.g. ServiceOrderStateType -> ServiceOrder
_STATE_NAME_SUFFIX_RE = re.compile(
    r"(StatusType|StateType|LifecycleType|LifecycleStatus|Lifecycle|Status|State)$",
)

# Generic words to drop when deriving an API's domain stems from its name
_API_NAME_GENERIC_WORDS = {
    "management", "api", "open", "tmf", "specification", "mgmt",
}


def _word_stem(word: str) -> str:
    """Cheap stemming so 'Ordering' matches 'Order' and 'Tickets' matches 'Ticket'.
    Not a real stemmer — just enough for TMF API name ↔ entity name matching."""
    w = word.lower()
    if w.endswith("ing"):
        return w[:-3]
    if w.endswith("s") and len(w) > 3:
        return w[:-1]
    return w


def _api_domain_stems(api_id: str) -> list[str]:
    """Return the lowercase domain word-stems for an API based on its registry
    entry, e.g. 'Resource Ordering' -> ['resource', 'order'].
    Used to rank entities by how strongly their name matches the API's domain.
    """
    for entry in API_REGISTRY:
        if entry.get("id") == api_id:
            words = re.split(r"[\s_]+", entry.get("name", ""))
            stems = [
                _word_stem(w)
                for w in words
                if w and w.lower() not in _API_NAME_GENERIC_WORDS
            ]
            return [s for s in stems if s]
    return []


def _entity_words(entity_name: str) -> set[str]:
    """Split a CamelCase entity name into its lowercase words.
    'ResourceOrderItem' -> {'resource', 'order', 'item'}."""
    return {w.lower() for w in re.findall(r"[A-Z][a-z]*", entity_name) if w}


def _domain_overlap_score(api_stems: list[str], entity_name: str) -> int:
    """Number of API domain stems that exactly match a CamelCase word in the
    entity name. Higher = stronger evidence the entity is the API's primary.

    Example: api 'Resource Ordering' (stems ['resource','order']) vs:
      ResourceOrder       -> 2 (both match)
      Resource            -> 1 ('resource' matches)
      ResourceRefOrValue  -> 1 ('resource' matches; 'or' is an exact word but
                                 doesn't equal 'order' — substring matches
                                 are intentionally not counted)
      Attachment          -> 0
    """
    if not api_stems:
        return 0
    ews = _entity_words(entity_name)
    if not ews:
        return 0
    return sum(1 for s in api_stems if s in ews)


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


# ── Helper-schema classification (for lifecycle leak protection) ─────────────

def _is_cross_api_helper(name: str) -> bool:
    """Schema is a known cross-API reference type whose state belongs to a
    different API (e.g. ResourceRef carries TMF639's resourceStatus enum)."""
    return name in SCHEMA_TO_API


def _is_generic_helper(name: str) -> bool:
    """Schema is a generic job/task/operation/etc. — its state is not the
    API's domain lifecycle (e.g. ImportJob, ExportJob in Catalog APIs)."""
    return bool(_GENERIC_HELPER_PATTERNS.search(name))


def _is_variant_entity(name: str) -> bool:
    """Schema is a derived variant of a root entity (Create/Update/Event)."""
    return name.endswith(_VARIANT_SUFFIXES)


def _is_helper_for_lifecycle(name: str) -> bool:
    """True if a schema should NOT be treated as authoritative for the API's
    own primary lifecycle. Used to keep cross-API and generic-helper state
    enums from leaking into the wrong API's lifecycle extraction."""
    return (
        _is_cross_api_helper(name)
        or _is_generic_helper(name)
        or _is_variant_entity(name)
    )


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


def _lifecycle_from_standalone_enums(
    schemas: dict[str, dict],
    entity_names: set[str] | None = None,
) -> list[str]:
    """
    Standalone state-enum fallback. Scans schemas whose name looks like a
    lifecycle helper (`*StateType`, `*StatusType`, `*Lifecycle*`, etc.).

    Cross-API ref types and generic job/task helpers are skipped — their
    enums describe a different domain, not the current API's lifecycle.

    When `entity_names` is provided (the normal case), an enum is only
    accepted if its schema-name stem exactly matches one of the entities,
    e.g. `ServiceOrderStateType` (stem = `ServiceOrder`) is accepted for
    an API whose primary entity is `ServiceOrder`. `ResourceStatusType`
    (stem = `Resource`) is rejected for an API whose entity is
    `ResourceOrder`, because `Resource` ≠ `ResourceOrder`.

    When no entity names are known (sparse test specs), the largest enum
    found among the candidate schemas is returned as a last resort.
    """
    related_candidates: list[tuple[int, list[str]]] = []
    fallback_candidates: list[tuple[int, list[str]]] = []

    for name, schema in schemas.items():
        if not _STATE_SCHEMA_PATTERNS.search(name):
            continue
        if _is_cross_api_helper(name) or _is_generic_helper(name):
            continue

        stem = _STATE_NAME_SUFFIX_RE.sub("", name)
        is_related = bool(entity_names) and stem in entity_names
        bucket = related_candidates if is_related else fallback_candidates

        # Direct top-level string enum
        if schema.get("type") == "string" and "enum" in schema:
            values = [str(v) for v in schema["enum"] if v is not None]
            if len(values) >= 2:
                bucket.append((len(values), values))
        # Wrapped in allOf/anyOf/oneOf
        for combiner in ("allOf", "anyOf", "oneOf"):
            for sub in schema.get(combiner, []):
                if sub.get("type") == "string" and "enum" in sub:
                    values = [str(v) for v in sub["enum"] if v is not None]
                    if len(values) >= 2:
                        bucket.append((len(values), values))

    if related_candidates:
        related_candidates.sort(reverse=True)
        return related_candidates[0][1]
    # Only fall back to unrelated enums if no entities are known to relate to.
    if not entity_names and fallback_candidates:
        fallback_candidates.sort(reverse=True)
        return fallback_candidates[0][1]
    return []


def extract_lifecycle(api_id: str, schemas: dict[str, dict], entities: list[dict]) -> list[str]:
    """
    Full lifecycle extraction pipeline with cross-domain leak protection.

    1. PRIMARY entities first: try root entities that are NOT cross-API ref
       types, generic job/task helpers, or variants. This is the authoritative
       source — the API's own primary entity defines its lifecycle.
    2. Broad scan over non-helper schemas (e.g. items / sub-entities) when
       primary entities don't yield states. Schemas whose name relates to a
       primary entity are tried first.
    3. Standalone enum scan: only enums whose schema-name stem exactly
       matches a primary entity are accepted (prevents `ResourceStatusType`
       from leaking into `ResourceOrder`).
    4. Last-resort fallback to helper entities, but ONLY if no primary
       entities exist at all (keeps minimal test specs working).

    Returning [] is the correct outcome when the spec doesn't structurally
    encode the API's own lifecycle — the curated baseline in emitter.py
    will fill the gap with verified states.
    """
    primary_entities = [e for e in entities if not _is_helper_for_lifecycle(e["name"])]
    helper_entities  = [e for e in entities if     _is_helper_for_lifecycle(e["name"])]
    primary_names = {e["name"] for e in primary_entities}

    # Phase 1: primary root entities
    for entity in primary_entities:
        schema = schemas.get(entity["name"], {})
        states = _lifecycle_from_entity(schema, schemas)
        if states:
            return states

    # Phase 2: broad scan over non-helper schemas, related-name first
    related: list[str] = []
    other: list[str] = []
    for name in schemas:
        if _is_helper_for_lifecycle(name):
            continue
        if primary_names and any(name.startswith(en) for en in primary_names):
            related.append(name)
        else:
            other.append(name)
    for name in related + other:
        states = _lifecycle_from_entity(schemas[name], schemas)
        if states:
            return states

    # Phase 3: standalone state-enum scan with stem-match guard
    states = _lifecycle_from_standalone_enums(schemas, primary_names)
    if states:
        return states

    # Phase 4: last-resort helper entities (only when no primaries exist)
    if not primary_entities:
        for entity in helper_entities:
            schema = schemas.get(entity["name"], {})
            states = _lifecycle_from_entity(schema, schemas)
            if states:
                return states

    return []


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


def _extract_entities(
    schemas: dict[str, dict],
    api_id: str | None = None,
) -> list[dict]:
    """
    Extract root entities from all schemas.
    Sort key: (-domain_overlap, -field_count) so entities matching the API's
    domain words come first, ties broken by total field count. Capped at 4.

    The domain-overlap pre-rank prevents helper / cross-API entities (e.g.
    `Resource`, `Attachment`, `ResourceRefOrValue` in the TMF652 spec) from
    pushing the API's actual primary entity (e.g. `ResourceOrder`) out of
    the top-4 truncation. When `api_id` is None or unknown, falls back to
    plain field-count ranking.
    """
    api_stems = _api_domain_stems(api_id) if api_id else []

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
            "_overlap":  _domain_overlap_score(api_stems, name),
            "_total":    len(mandatory) + len(optional),
        })

    entities.sort(key=lambda e: (-e["_overlap"], -e["_total"]))
    return [
        {"name": e["name"], "mandatory": e["mandatory"], "optional": e["optional"]}
        for e in entities[:4]
    ]


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
    entities   = _extract_entities(schemas, api_id)
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
