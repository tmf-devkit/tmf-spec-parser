"""
oda_extractor.py — Normalise ODA Component (ODAC) YAML manifests.

ODAC manifests use three different CRD versions in the wild:

  * oda.tmforum.org/v1beta2 — flat metadata under spec, `apitype` lowercase,
    `specification` is a single URL string.
  * oda.tmforum.org/v1beta3 — flat metadata, `apiType` camelCase, events
    promoted to `eventNotification` block.
  * oda.tmforum.org/v1 (formerly v1beta4) — metadata moved to
    `spec.componentMetadata`, `specification` is an array of {url, version},
    `kind` is TitleCase `Component` instead of lowercase `component`.

This module turns any of those shapes into a uniform internal record. Pure
functions only, no I/O.

Scope (per ADR-001): only `coreFunction.exposedAPIs` and
`coreFunction.dependentAPIs`. Security and management functions, events,
and per-API resources are deliberately out of scope for v0.3.0.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# ── Records ────────────────────────────────────────────────────────────────────
@dataclass
class APIRef:
    """A single API entry within coreFunction.exposedAPIs or dependentAPIs."""

    id: str
    name: str
    version: str
    required: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Component:
    """Normalised ODA Component record."""

    id: str
    name: str
    version: str
    functional_block: str
    status: str
    publication_date: str
    description: str
    crd_version: str
    exposed_apis:   list[APIRef] = field(default_factory=list)
    dependent_apis: list[APIRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":               self.id,
            "name":             self.name,
            "version":          self.version,
            "functional_block": self.functional_block,
            "status":           self.status,
            "publication_date": self.publication_date,
            "description":      self.description,
            "crd_version":      self.crd_version,
            "exposed_apis":     [a.to_dict() for a in self.exposed_apis],
            "dependent_apis":   [a.to_dict() for a in self.dependent_apis],
        }


# ── Helpers ────────────────────────────────────────────────────────────────────
def _detect_crd_version(manifest: dict[str, Any]) -> str:
    """Return canonical CRD label: 'v1beta2', 'v1beta3', or 'v1'.

    Reads `apiVersion`; v1beta4 is folded into 'v1' (the v1 GA was a
    rename of v1beta4). Unknown CRDs return 'unknown'.
    """
    raw = str(manifest.get("apiVersion", "")).strip()
    suffix = raw.rsplit("/", 1)[1] if "/" in raw else raw
    if suffix in ("v1", "v1beta4"):
        return "v1"
    if suffix in ("v1beta2", "v1beta3"):
        return suffix
    return "unknown"


def _clean_text(value: Any) -> str:
    """Coerce a YAML scalar to a clean single-line string."""
    if value is None:
        return ""
    text = str(value).strip()
    # YAML folded scalars often re-introduce stray newlines; collapse them.
    return " ".join(text.split())


def _coerce_required(value: Any) -> bool:
    """API entries default to optional when `required` is absent or non-bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _api_version_from_entry(entry: dict[str, Any]) -> str:
    """Extract API version, handling v1beta2/3 (top-level) vs v1 (nested in
    specification[0]).
    """
    # v1beta2 / v1beta3: version sits directly on the entry.
    top = entry.get("version")
    if isinstance(top, str) and top:
        return top
    # v1: version sits on specification[0].version (specification is a list).
    spec = entry.get("specification")
    if isinstance(spec, list) and spec:
        first = spec[0]
        if isinstance(first, dict):
            v = first.get("version")
            if isinstance(v, str) and v:
                return v
    return ""


def _extract_api_list(entries: Any) -> list[APIRef]:
    """Turn a raw list of API entries into APIRef records.

    Skips entries without an `id` or with placeholder/boilerplate IDs (some
    v1 manifests leave literal strings like 'dependentAPI_id' in
    managementFunction templates — we drop anything that doesn't look like
    a real TMF API id).
    """
    out: list[APIRef] = []
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        api_id = str(entry.get("id", "")).strip()
        if not api_id or not api_id.upper().startswith("TMF"):
            continue
        out.append(
            APIRef(
                id=api_id,
                name=str(entry.get("name", "")).strip(),
                version=_api_version_from_entry(entry),
                required=_coerce_required(entry.get("required")),
            )
        )
    return out


def _normalise_flat_metadata(spec: dict[str, Any]) -> dict[str, str]:
    """Pull metadata fields from a v1beta2/v1beta3 flat-style spec."""
    return {
        "id":               _clean_text(spec.get("id")),
        "name":             _clean_text(spec.get("name")),
        "version":          _clean_text(spec.get("version")),
        "functional_block": _clean_text(spec.get("functionalBlock")),
        "status":           _clean_text(spec.get("status")),
        "publication_date": _clean_text(spec.get("publicationDate")),
        "description":      _clean_text(spec.get("description")),
    }


def _normalise_v1_metadata(spec: dict[str, Any]) -> dict[str, str]:
    """Pull metadata from v1's spec.componentMetadata wrapper.

    Falls back to flat fields if the wrapper is missing — some early v1
    manifests in the wild are still half-migrated.
    """
    meta = spec.get("componentMetadata")
    if not isinstance(meta, dict):
        meta = spec  # fallback to flat
    return {
        "id":               _clean_text(meta.get("id")),
        "name":             _clean_text(meta.get("name")),
        "version":          _clean_text(meta.get("version")),
        "functional_block": _clean_text(meta.get("functionalBlock")),
        "status":           _clean_text(meta.get("status")),
        "publication_date": _clean_text(meta.get("publicationDate")),
        "description":      _clean_text(meta.get("description")),
    }


# ── Public API ─────────────────────────────────────────────────────────────────
def parse_manifest(manifest: dict[str, Any]) -> Component | None:
    """Parse a single ODAC manifest dict into a Component, or return None.

    Returns None if the input is not a recognised ODA Component manifest
    (wrong `kind`, missing `spec`, or no usable `id`).
    """
    if not isinstance(manifest, dict):
        return None
    kind = str(manifest.get("kind", "")).strip().lower()
    if kind != "component":
        return None
    spec = manifest.get("spec")
    if not isinstance(spec, dict):
        return None

    crd_version = _detect_crd_version(manifest)
    if crd_version == "v1":
        meta = _normalise_v1_metadata(spec)
    elif crd_version in ("v1beta2", "v1beta3"):
        meta = _normalise_flat_metadata(spec)
    else:
        # Unknown CRD: try v1 first, fall back to flat.
        meta = _normalise_v1_metadata(spec)
        if not meta["id"]:
            meta = _normalise_flat_metadata(spec)

    if not meta["id"]:
        return None

    core = spec.get("coreFunction", {})
    if not isinstance(core, dict):
        core = {}

    return Component(
        id=meta["id"],
        name=meta["name"],
        version=meta["version"],
        functional_block=meta["functional_block"],
        status=meta["status"],
        publication_date=meta["publication_date"],
        description=meta["description"],
        crd_version=crd_version,
        exposed_apis=_extract_api_list(core.get("exposedAPIs")),
        dependent_apis=_extract_api_list(core.get("dependentAPIs")),
    )


def build_links(components: list[Component]) -> list[dict[str, Any]]:
    """Produce flat link records: component -> dependent API.

    Only `dependent_apis` produce links — a component depends on other APIs;
    its exposed APIs are what it serves, not what it consumes.
    Component-to-component dependency is derivable at render time by
    joining `target_api` to other components' `exposed_apis`.
    """
    links: list[dict[str, Any]] = []
    for comp in components:
        for api in comp.dependent_apis:
            links.append({
                "source":     comp.id,
                "target_api": api.id,
                "kind":       "depends_on",
                "required":   api.required,
            })
    return links


def compute_stats(
    components: list[Component],
    known_apis: set[str] | None = None,
) -> dict[str, Any]:
    """Summary counts for the output file."""
    exposed_count   = sum(len(c.exposed_apis)   for c in components)
    dependent_count = sum(len(c.dependent_apis) for c in components)
    unique_apis: set[str] = set()
    for c in components:
        for a in c.exposed_apis:
            unique_apis.add(a.id)
        for a in c.dependent_apis:
            unique_apis.add(a.id)
    out: dict[str, Any] = {
        "components":             len(components),
        "exposed_api_count":      exposed_count,
        "dependent_api_count":    dependent_count,
        "unique_apis_referenced": len(unique_apis),
    }
    if known_apis is not None:
        out["apis_outside_tmf_map_set"] = len(unique_apis - known_apis)
    return out
