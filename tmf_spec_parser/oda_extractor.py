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

Scope: extracts APIs from `coreFunction`, `securityFunction`, and
`managementFunction` blocks. Each APIRef carries a `function` field
recording its provenance ("core" / "security" / "management") so
downstream consumers can group or filter by function block.

Events and per-API resources remain out of scope.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# ── Records ────────────────────────────────────────────────────────────────────

# Matches a trailing version token such as "v23.0" or "v25.5" at the end of the
# pipe-separated entry strings used in eTOMs, functionalFrameworkFunctions, and SIDs.
_FW_VERSION_RE = re.compile(r"^v\d+(?:\.\d+)*$")


@dataclass
class FrameworkEntry:
    """A single eTOM process or Functional Framework function reference.

    Parsed from strings like::

        "1.2.11|Product_Inventory_Management|v24.0"
         → id="1.2.11", name="Product Inventory Management", version="v24.0"

        "197|Customer_Product_Storage|v24.0"
         → id="197", name="Customer Product Storage", version="v24.0"

    The format is ``{id}|{Name_with_underscores}|{vN.M}``. The ``id`` is the
    first pipe-separated token. The ``version`` is the last pipe-separated token
    when it matches ``vN`` or ``vN.M``. Underscores in the name segment are
    replaced with spaces.
    """

    id: str
    name: str
    version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SIDEntry:
    """A single SID ABE reference extracted from the ``SIDs`` field in a v1 manifest.

    Parsed from strings like::

        "Product_Domain|Product_and_Offering_Instance_ABE|Product_ABE|v25.0"
         → domain="Product", abe_l1="Product and Offering Instance ABE",
           abe_l2="Product ABE", version="v25.0"

        "Product_Domain|Loyalty_ABE|Loyalty_Program_ABE|v25.0"
         → domain="Product", abe_l1="Loyalty ABE",
           abe_l2="Loyalty Program ABE", version="v25.0"

    The last pipe-separated token is the version if it matches ``vN.M``.
    The first token is the domain (strips trailing ``_Domain``).
    Remaining tokens are ABE hierarchy levels (L1 and optionally L2).
    """

    domain: str
    abe_l1: str
    abe_l2: str   # empty string when only one ABE level is present
    version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _underscore_to_spaces(s: str) -> str:
    """Replace underscores with spaces and strip leading/trailing whitespace."""
    return s.replace("_", " ").strip()


def _parse_framework_entry(raw: str) -> FrameworkEntry | None:
    """Parse one eTOM or FF entry string into a FrameworkEntry.

    Format: ``{id}|{Name_words}|{vN.M}``
    Returns None if the string is empty or has no usable id token.
    """
    raw = raw.strip()
    if not raw:
        return None
    parts = raw.split("|")
    entry_id = parts[0].strip()
    if not entry_id:
        return None
    # Detect a trailing version token and strip it.
    version = ""
    name_parts = parts[1:]
    if name_parts and _FW_VERSION_RE.match(name_parts[-1].strip()):
        version = name_parts[-1].strip()
        name_parts = name_parts[:-1]
    name = _underscore_to_spaces(" ".join(name_parts))
    return FrameworkEntry(id=entry_id, name=name, version=version)


def _parse_framework_list(entries: Any) -> list[FrameworkEntry]:
    """Turn a raw YAML list of framework entry strings into FrameworkEntry records.

    Non-string and empty entries are skipped silently.
    """
    out: list[FrameworkEntry] = []
    if not isinstance(entries, list):
        return out
    for item in entries:
        if not isinstance(item, str):
            continue
        fe = _parse_framework_entry(item)
        if fe is not None:
            out.append(fe)
    return out


def _parse_sid_entry(raw: str) -> SIDEntry | None:
    """Parse one SID entry string into a SIDEntry.

    Format: ``{Domain}_Domain|{ABE_L1}|[{ABE_L2}|]{vN.M}``
    Returns None if the string is empty or has fewer than two tokens.
    """
    raw = raw.strip()
    if not raw:
        return None
    parts = raw.split("|")
    if len(parts) < 2:  # noqa: PLR2004
        return None
    # Strip trailing version token.
    version = ""
    if _FW_VERSION_RE.match(parts[-1].strip()):
        version = parts[-1].strip()
        parts = parts[:-1]
    # First token is Domain_Domain → strip trailing "_Domain".
    domain_raw = parts[0].strip()
    domain = _underscore_to_spaces(
        domain_raw[:-7] if domain_raw.endswith("_Domain") else domain_raw
    )
    abe_parts = [_underscore_to_spaces(p) for p in parts[1:]]
    abe_l1 = abe_parts[0] if abe_parts else ""
    abe_l2 = abe_parts[1] if len(abe_parts) > 1 else ""
    return SIDEntry(domain=domain, abe_l1=abe_l1, abe_l2=abe_l2, version=version)


def _parse_sid_list(entries: Any) -> list[SIDEntry]:
    """Turn a raw YAML list of SID entry strings into SIDEntry records."""
    out: list[SIDEntry] = []
    if not isinstance(entries, list):
        return out
    for item in entries:
        if not isinstance(item, str):
            continue
        se = _parse_sid_entry(item)
        if se is not None:
            out.append(se)
    return out


@dataclass
class APIRef:
    """A single API entry within an exposedAPIs or dependentAPIs list.

    The `function` field records which function block the entry came from:
    "core", "security", or "management". Defaults to "core" for backward
    compatibility with code that constructs APIRefs directly.
    """

    id: str
    name: str
    version: str
    required: bool
    function: str = "core"

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
    exposed_apis:    list[APIRef]        = field(default_factory=list)
    dependent_apis:  list[APIRef]        = field(default_factory=list)
    etom_processes:  list[FrameworkEntry] = field(default_factory=list)
    ff_functions:    list[FrameworkEntry] = field(default_factory=list)
    sid_abes:        list[SIDEntry]       = field(default_factory=list)

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
            "etom_processes":   [e.to_dict() for e in self.etom_processes],
            "ff_functions":     [f.to_dict() for f in self.ff_functions],
            "sid_abes":         [s.to_dict() for s in self.sid_abes],
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


def _extract_api_list(entries: Any, function: str = "core") -> list[APIRef]:
    """Turn a raw list of API entries into APIRef records.

    Skips entries without an `id` or with placeholder/boilerplate IDs (some
    v1 manifests leave literal strings like 'dependentAPI_id' in
    managementFunction templates — we drop anything that doesn't look like
    a real TMF API id).

    `function` tags every emitted APIRef with the function block it came
    from ("core" / "security" / "management").
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
                function=function,
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


def _normalise_v1_metadata(spec: dict[str, Any]) -> dict[str, Any]:
    """Pull metadata from v1's spec.componentMetadata wrapper.

    Falls back to flat fields if the wrapper is missing — some early v1
    manifests in the wild are still half-migrated.

    The ``eTOMs`` and ``functionalFrameworkFunctions`` lists are only present
    in v1 manifests (they were added as part of the v1 spec). They are parsed
    here and returned as ``etom_processes`` and ``ff_functions`` keys.
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
        "etom_processes":   _parse_framework_list(meta.get("eTOMs")),
        "ff_functions":     _parse_framework_list(
            meta.get("functionalFrameworkFunctions")
        ),
        "sid_abes":         _parse_sid_list(meta.get("SIDs")),
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

    def _block(name: str) -> dict[str, Any]:
        block = spec.get(name, {})
        return block if isinstance(block, dict) else {}

    core       = _block("coreFunction")
    security   = _block("securityFunction")
    management = _block("managementFunction")

    exposed: list[APIRef] = (
        _extract_api_list(core.get("exposedAPIs"),       function="core")
        + _extract_api_list(security.get("exposedAPIs"),   function="security")
        + _extract_api_list(management.get("exposedAPIs"), function="management")
    )
    dependent: list[APIRef] = (
        _extract_api_list(core.get("dependentAPIs"),       function="core")
        + _extract_api_list(security.get("dependentAPIs"),   function="security")
        + _extract_api_list(management.get("dependentAPIs"), function="management")
    )

    # eTOM and FF cross-references are only present in v1 manifests;
    # flat-metadata (v1beta2/3) returns empty lists from _normalise_flat_metadata.
    etom_processes: list[FrameworkEntry] = meta.get("etom_processes") or []
    ff_functions:   list[FrameworkEntry] = meta.get("ff_functions")   or []
    sid_abes:       list[SIDEntry]       = meta.get("sid_abes")       or []

    return Component(
        id=meta["id"],
        name=meta["name"],
        version=meta["version"],
        functional_block=meta["functional_block"],
        status=meta["status"],
        publication_date=meta["publication_date"],
        description=meta["description"],
        crd_version=crd_version,
        exposed_apis=exposed,
        dependent_apis=dependent,
        etom_processes=etom_processes,
        ff_functions=ff_functions,
        sid_abes=sid_abes,
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
