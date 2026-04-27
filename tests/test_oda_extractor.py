"""Tests for the ODAC manifest extractor (no network calls).

Covers the three CRD versions found in the wild (v1beta2, v1beta3, v1) and
edge cases discovered during prototyping (placeholder IDs in
managementFunction templates, missing required flags, missing versions).
"""

from __future__ import annotations

import yaml

from tmf_spec_parser.oda_extractor import (
    APIRef,
    Component,
    build_links,
    compute_stats,
    parse_manifest,
)

# ── Fixture manifests (real-world abridged samples from oda-production S3) ────

V1BETA2_TMFC038 = """
apiVersion: oda.tmforum.org/v1beta2
kind: component
metadata:
  name: components.oda.tmforum.org
spec:
  coreFunction:
    dependentAPIs:
    - id: TMF639
      version: v4.0.0
      name: resource-inventory-management-api
      required: false
      specification: https://example.com/TMF639.json
    - id: TMF673
      version: v4.0.0
      name: geographic-address-management-api
      required: false
      specification: https://example.com/TMF673.json
    exposedAPIs:
    - id: TMF642
      version: v4.0.0
      name: alarm-management-api
      required: true
      specification: https://example.com/TMF642.json
  description: Resource Performance Management monitors performance.
  functionalBlock: IntelligenceManagement
  id: TMFC038
  name: ResourcePerformanceManagement
  publicationDate: 2023-08-18 00:00:00
  status: specified
  version: 1.1.0
"""

V1BETA3_TMFC001 = """
apiVersion: oda.tmforum.org/v1beta3
kind: component
metadata:
  name: components.oda.tmforum.org
spec:
  name: ProductCatalogManagement
  id: TMFC001
  functionalBlock: CoreCommerce
  description: The Product Catalog Management ODA Component.
  publicationDate: 2023-04-23 00:00:00
  status: specified
  version: 2.0.0
  coreFunction:
    dependentAPIs:
    - id: TMF633
      version: v4.0.0
      apiType: openapi
      name: service-catalog-management-api
      required: false
      specification: https://example.com/TMF633.json
    - id: TMF632
      version: v4.0.0
      apiType: openapi
      name: party-management-api
      required: false
      specification: https://example.com/TMF632.json
    exposedAPIs:
    - id: TMF620
      version: v4.1.0
      apiType: openapi
      name: product-catalog-management-api
      required: true
      specification: https://example.com/TMF620.json
"""

V1_TMFC037 = """
apiVersion: oda.tmforum.org/v1
kind: Component
metadata:
  name: components.oda.tmforum.org
spec:
  coreFunction:
    dependentAPIs:
    - id: TMF638
      apiType: openapi
      apiSDO: tmForum
      name: service-inventory-management-api
      required: true
      specification:
      - url: https://example.com/TMF638.json
        version: v4.0.0
    - id: TMF639
      apiType: openapi
      apiSDO: tmForum
      name: resource-inventory-management-api
      required: false
      specification:
      - url: https://example.com/TMF639.json
        version: v4.0.0
    exposedAPIs:
    - id: TMF649
      apiType: openapi
      apiSDO: tmForum
      name: performance-thresholding-management-api
      required: true
      specification:
      - url: https://example.com/TMF649.json
        version: v4.0.0
  componentMetadata:
    id: TMFC037
    name: ServicePerformanceManagement
    version: 1.2.0
    description: Service Performance Management.
    publicationDate: 2024-12-17 00:00:00
    status: specified
    functionalBlock: IntelligenceManagement
  managementFunction:
    exposedAPIs:
    - name: metrics
      apiType: prometheus
      id: exposedAPI_id
      version: exposedAPI_version
      required: false
    dependentAPIs:
    - name: dependentAPI_name
      id: dependentAPI_id
      version: dependentAPI_version
      apiType: dependentAPI_apiType
      required: false
"""


# ── Per-CRD tests ─────────────────────────────────────────────────────────────


def test_v1beta2_manifest_parses() -> None:
    comp = parse_manifest(yaml.safe_load(V1BETA2_TMFC038))
    assert comp is not None
    assert comp.id == "TMFC038"
    assert comp.name == "ResourcePerformanceManagement"
    assert comp.functional_block == "IntelligenceManagement"
    assert comp.crd_version == "v1beta2"
    assert comp.version == "1.1.0"
    assert len(comp.exposed_apis) == 1
    assert len(comp.dependent_apis) == 2


def test_v1beta3_manifest_parses() -> None:
    comp = parse_manifest(yaml.safe_load(V1BETA3_TMFC001))
    assert comp is not None
    assert comp.id == "TMFC001"
    assert comp.name == "ProductCatalogManagement"
    assert comp.functional_block == "CoreCommerce"
    assert comp.crd_version == "v1beta3"
    assert comp.version == "2.0.0"
    assert len(comp.exposed_apis) == 1
    assert len(comp.dependent_apis) == 2


def test_v1_manifest_parses_with_componentMetadata_wrapper() -> None:
    comp = parse_manifest(yaml.safe_load(V1_TMFC037))
    assert comp is not None
    # In v1, metadata is nested under componentMetadata — the parser must
    # find it there, not at the top level of spec.
    assert comp.id == "TMFC037"
    assert comp.name == "ServicePerformanceManagement"
    assert comp.functional_block == "IntelligenceManagement"
    assert comp.crd_version == "v1"
    assert comp.version == "1.2.0"


def test_v1beta4_apiVersion_folded_into_v1() -> None:
    # The v1 GA was a rename of v1beta4; both should produce crd_version="v1".
    raw = yaml.safe_load(V1_TMFC037)
    raw["apiVersion"] = "oda.tmforum.org/v1beta4"
    comp = parse_manifest(raw)
    assert comp is not None
    assert comp.crd_version == "v1"


# ── Per-API-entry tests ───────────────────────────────────────────────────────


def test_v1_specification_array_yields_correct_version() -> None:
    """In v1, each API's version is buried inside specification[0].version
    rather than directly on the entry."""
    comp = parse_manifest(yaml.safe_load(V1_TMFC037))
    assert comp is not None
    tmf638 = next(a for a in comp.dependent_apis if a.id == "TMF638")
    assert tmf638.version == "v4.0.0"


def test_required_flag_is_preserved() -> None:
    comp = parse_manifest(yaml.safe_load(V1_TMFC037))
    assert comp is not None
    tmf638 = next(a for a in comp.dependent_apis if a.id == "TMF638")
    tmf639 = next(a for a in comp.dependent_apis if a.id == "TMF639")
    tmf649 = next(a for a in comp.exposed_apis  if a.id == "TMF649")
    assert tmf638.required is True
    assert tmf639.required is False
    assert tmf649.required is True


def test_required_flag_defaults_to_false_when_missing() -> None:
    raw = yaml.safe_load(V1BETA2_TMFC038)
    # Strip the `required` field from the first dependent API entry.
    del raw["spec"]["coreFunction"]["dependentAPIs"][0]["required"]
    comp = parse_manifest(raw)
    assert comp is not None
    assert comp.dependent_apis[0].required is False


# ── Edge cases ─────────────────────────────────────────────────────────────────


def test_managementFunction_placeholders_do_not_leak_into_core() -> None:
    """v1 manifests contain literal placeholders like 'dependentAPI_id' in
    managementFunction templates. Those must NEVER appear in core_function
    output."""
    comp = parse_manifest(yaml.safe_load(V1_TMFC037))
    assert comp is not None
    placeholder_ids = {"exposedAPI_id", "dependentAPI_id"}
    leaked = {a.id for a in comp.exposed_apis + comp.dependent_apis} & placeholder_ids
    assert not leaked, f"placeholder IDs leaked into output: {leaked}"


def test_non_TMF_ids_filtered() -> None:
    """API entries without a TMFxxx id (e.g., custom or boilerplate) are
    dropped from output."""
    raw = yaml.safe_load(V1BETA3_TMFC001)
    raw["spec"]["coreFunction"]["dependentAPIs"].append({
        "id": "some-custom-internal-api",
        "version": "v1.0.0",
        "name": "internal",
        "required": False,
    })
    comp = parse_manifest(raw)
    assert comp is not None
    ids = [a.id for a in comp.dependent_apis]
    assert all(i.startswith("TMF") for i in ids)
    assert "some-custom-internal-api" not in ids


def test_non_component_kind_returns_None() -> None:
    raw = {"apiVersion": "v1", "kind": "Service", "spec": {}}
    assert parse_manifest(raw) is None


def test_missing_spec_returns_None() -> None:
    raw = {"apiVersion": "oda.tmforum.org/v1", "kind": "Component"}
    assert parse_manifest(raw) is None


def test_missing_id_returns_None() -> None:
    raw = yaml.safe_load(V1BETA3_TMFC001)
    del raw["spec"]["id"]
    assert parse_manifest(raw) is None


def test_kind_comparison_is_case_insensitive() -> None:
    """v1 uses 'Component' (TitleCase); v1beta2/3 use 'component' (lowercase).
    Both must parse."""
    raw = yaml.safe_load(V1BETA2_TMFC038)
    raw["kind"] = "Component"   # mixed case shouldn't matter
    assert parse_manifest(raw) is not None


# ── Aggregate helpers ─────────────────────────────────────────────────────────


def test_build_links_only_emits_dependent_edges() -> None:
    components = [
        parse_manifest(yaml.safe_load(V1BETA2_TMFC038)),
        parse_manifest(yaml.safe_load(V1BETA3_TMFC001)),
        parse_manifest(yaml.safe_load(V1_TMFC037)),
    ]
    components = [c for c in components if c is not None]
    links = build_links(components)
    # Exposed APIs MUST NOT produce links — only dependents.
    for link in links:
        assert link["kind"] == "depends_on"
        # The link's target_api should appear in some component's
        # dependent_apis, not exposed_apis (sanity).
    assert len(links) == sum(len(c.dependent_apis) for c in components)


def test_build_links_preserves_required_flag() -> None:
    components = [parse_manifest(yaml.safe_load(V1_TMFC037))]
    links = build_links([c for c in components if c is not None])
    tmf638_link = next(li for li in links if li["target_api"] == "TMF638")
    tmf639_link = next(li for li in links if li["target_api"] == "TMF639")
    assert tmf638_link["required"] is True
    assert tmf639_link["required"] is False


def test_compute_stats_known_apis_subset() -> None:
    components = [
        parse_manifest(yaml.safe_load(V1BETA2_TMFC038)),
        parse_manifest(yaml.safe_load(V1BETA3_TMFC001)),
        parse_manifest(yaml.safe_load(V1_TMFC037)),
    ]
    components = [c for c in components if c is not None]
    known = {"TMF620", "TMF638", "TMF639", "TMF632", "TMF633"}
    stats = compute_stats(components, known_apis=known)
    assert stats["components"] == 3
    assert stats["exposed_api_count"] == 3       # 1 each from the 3 fixtures
    assert stats["dependent_api_count"] == 6     # 2 + 2 + 2
    # Out-of-set APIs in our fixtures: TMF673, TMF642, TMF649 — three.
    assert stats["apis_outside_tmf_map_set"] == 3


def test_compute_stats_no_known_apis_omits_outside_count() -> None:
    components = [parse_manifest(yaml.safe_load(V1_TMFC037))]
    stats = compute_stats([c for c in components if c is not None])
    assert "apis_outside_tmf_map_set" not in stats


# ── APIRef / Component dataclasses ─────────────────────────────────────────────


def test_apiref_to_dict_round_trip() -> None:
    ref = APIRef(id="TMF638", name="svc-inv", version="v4.0.0", required=True)
    assert ref.to_dict() == {
        "id": "TMF638",
        "name": "svc-inv",
        "version": "v4.0.0",
        "required": True,
    }


def test_component_to_dict_includes_all_fields() -> None:
    comp = Component(
        id="TMFC008",
        name="ServiceInventory",
        version="1.2.0",
        functional_block="Production",
        status="specified",
        publication_date="2024-11-12",
        description="...",
        crd_version="v1",
    )
    d = comp.to_dict()
    assert d["id"] == "TMFC008"
    assert d["exposed_apis"] == []
    assert d["dependent_apis"] == []
    assert "functional_block" in d
    assert "crd_version" in d
