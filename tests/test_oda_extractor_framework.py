"""Tests for FrameworkEntry parsing in the ODAC manifest extractor.

Covers:
  - _parse_framework_entry / _parse_framework_list helpers
  - etom_processes and ff_functions fields on Component
  - v1 manifests with real-world eTOMs and FF entries
  - v1beta2/v1beta3 manifests produce empty framework lists (fields not in spec)
  - Edge cases: no version token, empty list, None, non-string entries
"""

from __future__ import annotations

import yaml

from tmf_spec_parser.oda_extractor import (
    FrameworkEntry,
    _parse_framework_entry,
    _parse_framework_list,
    _parse_sid_entry,
    _parse_sid_list,
    parse_manifest,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

# Abridged v1 manifest modelled on TMFC001 ProductCatalogManagement.
# Uses the real pipe-separated format: {id}|{Name_words}|{vN.M}
V1_WITH_FRAMEWORK_FIELDS = """
apiVersion: oda.tmforum.org/v1
kind: Component
metadata:
  name: components.oda.tmforum.org
spec:
  componentMetadata:
    id: TMFC001
    name: ProductCatalogManagement
    version: 2.1.0
    description: Product Catalog Management ODA Component.
    publicationDate: 2024-11-12 00:00:00
    status: specified
    functionalBlock: CoreCommerce
    eTOMs:
      - 1.2.20|Product_Catalog_Lifecycle_Management|v23.0
      - 1.1.19|Loyalty_Program_Management|v23.0
    functionalFrameworkFunctions:
      - 3|Repository_Entity_Relations_Configuration|v23.0
      - 4|Repository_Entity_Grouping_Configuration|v23.0
    SIDs:
      - Product_Domain|Product_and_Offering_Instance_ABE|Product_ABE|v25.0
      - Product_Domain|Loyalty_ABE|Loyalty_Program_ABE|v25.0
  coreFunction:
    exposedAPIs:
    - id: TMF620
      name: product-catalog-management-api
      required: true
      specification:
      - url: https://example.com/TMF620.json
        version: v4.1.0
    dependentAPIs:
    - id: TMF632
      name: party-management-api
      required: false
      specification:
      - url: https://example.com/TMF632.json
        version: v4.0.0
"""

# v1 manifest that intentionally has no eTOMs / FF fields — both lists should
# default to [].
V1_WITHOUT_FRAMEWORK_FIELDS = """
apiVersion: oda.tmforum.org/v1
kind: Component
metadata:
  name: components.oda.tmforum.org
spec:
  componentMetadata:
    id: TMFC037
    name: ServicePerformanceManagement
    version: 1.2.0
    description: Service Performance Management.
    publicationDate: 2024-12-17 00:00:00
    status: specified
    functionalBlock: IntelligenceManagement
  coreFunction:
    exposedAPIs:
    - id: TMF649
      name: performance-thresholding-management-api
      required: true
      specification:
      - url: https://example.com/TMF649.json
        version: v4.0.0
    dependentAPIs:
    - id: TMF638
      name: service-inventory-management-api
      required: true
      specification:
      - url: https://example.com/TMF638.json
        version: v4.0.0
"""

# v1beta3 manifest — eTOMs/FF fields were not part of the v1beta spec; both lists
# should be empty.
V1BETA3_NO_FRAMEWORK = """
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
    - id: TMF632
      version: v4.0.0
      name: party-management-api
      required: false
    exposedAPIs:
    - id: TMF620
      version: v4.1.0
      name: product-catalog-management-api
      required: true
"""


# ── _parse_framework_entry unit tests ─────────────────────────────────────────


def test_parse_entry_full_etom() -> None:
    """Standard eTOM entry with id, multi-word name, and version token."""
    fe = _parse_framework_entry("1.2.20|Product_Catalog_Lifecycle_Management|v23.0")
    assert fe is not None
    assert fe.id == "1.2.20"
    assert fe.name == "Product Catalog Lifecycle Management"
    assert fe.version == "v23.0"


def test_parse_entry_numeric_ff_id() -> None:
    """FF entries use integer IDs instead of dotted eTOM notation."""
    fe = _parse_framework_entry("197|Customer_Product_Storage|v23.0")
    assert fe is not None
    assert fe.id == "197"
    assert fe.name == "Customer Product Storage"
    assert fe.version == "v23.0"


def test_parse_entry_single_word_name() -> None:
    fe = _parse_framework_entry("3|Repository_Entity_Relations_Configuration|v23.0")
    assert fe is not None
    assert fe.id == "3"
    assert fe.name == "Repository Entity Relations Configuration"
    assert fe.version == "v23.0"


def test_parse_entry_no_version_token() -> None:
    """Entry strings without a trailing version token still parse; version is ''."""
    fe = _parse_framework_entry("1.4.4|Service_Quality_Management")
    assert fe is not None
    assert fe.id == "1.4.4"
    assert fe.name == "Service Quality Management"
    assert fe.version == ""


def test_parse_entry_version_with_multiple_dots() -> None:
    """Version tokens like v25.5 (two-part) should be detected and stripped."""
    fe = _parse_framework_entry("1.2.11|Product_Inventory_Management|v25.5")
    assert fe is not None
    assert fe.version == "v25.5"
    assert "v25.5" not in fe.name


def test_parse_entry_empty_string_returns_none() -> None:
    assert _parse_framework_entry("") is None


def test_parse_entry_whitespace_only_returns_none() -> None:
    assert _parse_framework_entry("   ") is None


def test_parse_entry_id_only_no_name() -> None:
    """An entry that is just an ID with no name tokens produces name=''."""
    fe = _parse_framework_entry("1.2.11")
    assert fe is not None
    assert fe.id == "1.2.11"
    assert fe.name == ""
    assert fe.version == ""


# ── _parse_framework_list unit tests ──────────────────────────────────────────


def test_parse_list_two_etom_entries() -> None:
    entries = [
        "1.2.20|Product_Catalog_Lifecycle_Management|v23.0",
        "1.1.19|Loyalty_Program_Management|v23.0",
    ]
    result = _parse_framework_list(entries)
    assert len(result) == 2
    assert result[0].id == "1.2.20"
    assert result[1].id == "1.1.19"


def test_parse_list_skips_non_string_entries() -> None:
    entries = [
        "1.2.20_Product_Catalog_Lifecycle_Management_v23.0",
        42,
        None,
        {"id": "bad"},
        "1.1.19_Loyalty_Program_Management_v23.0",
    ]
    result = _parse_framework_list(entries)
    assert len(result) == 2


def test_parse_list_none_input_returns_empty() -> None:
    assert _parse_framework_list(None) == []


def test_parse_list_empty_list_returns_empty() -> None:
    assert _parse_framework_list([]) == []


def test_parse_list_non_list_input_returns_empty() -> None:
    assert _parse_framework_list("not a list") == []


# ── FrameworkEntry dataclass ───────────────────────────────────────────────────


def test_framework_entry_to_dict() -> None:
    fe = FrameworkEntry(
        id="1.2.20",
        name="Product Catalog Lifecycle Management",
        version="v23.0",
    )
    assert fe.to_dict() == {
        "id": "1.2.20",
        "name": "Product Catalog Lifecycle Management",
        "version": "v23.0",
    }


# ── Component-level extraction tests ──────────────────────────────────────────


def test_v1_etom_processes_extracted() -> None:
    """eTOMs field in a v1 manifest populates etom_processes on the Component."""
    comp = parse_manifest(yaml.safe_load(V1_WITH_FRAMEWORK_FIELDS))
    assert comp is not None
    assert len(comp.etom_processes) == 2
    ids = [e.id for e in comp.etom_processes]
    assert "1.2.20" in ids
    assert "1.1.19" in ids


def test_v1_ff_functions_extracted() -> None:
    """functionalFrameworkFunctions field populates ff_functions on the Component."""
    comp = parse_manifest(yaml.safe_load(V1_WITH_FRAMEWORK_FIELDS))
    assert comp is not None
    assert len(comp.ff_functions) == 2
    ids = [f.id for f in comp.ff_functions]
    assert "3" in ids
    assert "4" in ids


def test_v1_etom_entry_names_and_versions_correct() -> None:
    comp = parse_manifest(yaml.safe_load(V1_WITH_FRAMEWORK_FIELDS))
    assert comp is not None
    by_id = {e.id: e for e in comp.etom_processes}
    assert by_id["1.2.20"].name == "Product Catalog Lifecycle Management"
    assert by_id["1.2.20"].version == "v23.0"
    assert by_id["1.1.19"].name == "Loyalty Program Management"
    assert by_id["1.1.19"].version == "v23.0"


def test_v1_ff_entry_names_and_versions_correct() -> None:
    comp = parse_manifest(yaml.safe_load(V1_WITH_FRAMEWORK_FIELDS))
    assert comp is not None
    by_id = {f.id: f for f in comp.ff_functions}
    assert by_id["3"].name == "Repository Entity Relations Configuration"
    assert by_id["3"].version == "v23.0"
    assert by_id["4"].name == "Repository Entity Grouping Configuration"
    assert by_id["4"].version == "v23.0"


def test_v1_without_framework_fields_returns_empty_lists() -> None:
    """v1 manifest with no eTOMs / FF fields still produces a valid Component
    with empty etom_processes and ff_functions."""
    comp = parse_manifest(yaml.safe_load(V1_WITHOUT_FRAMEWORK_FIELDS))
    assert comp is not None
    assert comp.etom_processes == []
    assert comp.ff_functions == []


def test_v1beta3_manifest_produces_empty_framework_lists() -> None:
    """v1beta2/v1beta3 manifests never carry eTOM or FF fields — both lists
    should always be empty for these CRD versions."""
    comp = parse_manifest(yaml.safe_load(V1BETA3_NO_FRAMEWORK))
    assert comp is not None
    assert comp.crd_version == "v1beta3"
    assert comp.etom_processes == []
    assert comp.ff_functions == []


def test_framework_fields_appear_in_to_dict() -> None:
    """to_dict() must include etom_processes, ff_functions, and sid_abes so they
    are serialised into oda_data.json."""
    comp = parse_manifest(yaml.safe_load(V1_WITH_FRAMEWORK_FIELDS))
    assert comp is not None
    d = comp.to_dict()
    assert "etom_processes" in d
    assert "ff_functions" in d
    assert "sid_abes" in d
    assert len(d["etom_processes"]) == 2
    assert len(d["ff_functions"]) == 2
    assert len(d["sid_abes"]) == 2


def test_framework_entry_dicts_have_id_name_version_keys() -> None:
    comp = parse_manifest(yaml.safe_load(V1_WITH_FRAMEWORK_FIELDS))
    assert comp is not None
    d = comp.to_dict()
    for entry in d["etom_processes"] + d["ff_functions"]:
        assert set(entry.keys()) == {"id", "name", "version"}


def test_existing_api_fields_unaffected_by_framework_extraction() -> None:
    """Adding framework extraction must not change exposed_apis or dependent_apis."""
    comp = parse_manifest(yaml.safe_load(V1_WITH_FRAMEWORK_FIELDS))
    assert comp is not None
    assert len(comp.exposed_apis) == 1
    assert comp.exposed_apis[0].id == "TMF620"
    assert len(comp.dependent_apis) == 1
    assert comp.dependent_apis[0].id == "TMF632"


# ── SID tests ──────────────────────────────────────────────────────────────────


def test_parse_sid_entry_two_abe_levels() -> None:
    """Standard SID entry: Domain | ABE L1 | ABE L2 | version."""
    se = _parse_sid_entry("Product_Domain|Product_and_Offering_Instance_ABE|Product_ABE|v25.0")
    assert se is not None
    assert se.domain == "Product"
    assert se.abe_l1 == "Product and Offering Instance ABE"
    assert se.abe_l2 == "Product ABE"
    assert se.version == "v25.0"


def test_parse_sid_entry_one_abe_level() -> None:
    """SID entry with only one ABE level — abe_l2 should be empty string."""
    se = _parse_sid_entry("Service_Domain|Service_ABE|v25.0")
    assert se is not None
    assert se.domain == "Service"
    assert se.abe_l1 == "Service ABE"
    assert se.abe_l2 == ""
    assert se.version == "v25.0"


def test_parse_sid_entry_strips_domain_suffix() -> None:
    """'_Domain' suffix on the first token must be stripped from the domain name."""
    se = _parse_sid_entry("Resource_Domain|Resource_ABE|v25.0")
    assert se is not None
    assert se.domain == "Resource"
    assert "Domain" not in se.domain


def test_parse_sid_entry_no_version() -> None:
    se = _parse_sid_entry("Product_Domain|Product_ABE")
    assert se is not None
    assert se.domain == "Product"
    assert se.version == ""


def test_parse_sid_entry_empty_returns_none() -> None:
    assert _parse_sid_entry("") is None


def test_parse_sid_entry_single_token_returns_none() -> None:
    assert _parse_sid_entry("Product_Domain") is None


def test_parse_sid_list_two_entries() -> None:
    entries = [
        "Product_Domain|Product_and_Offering_Instance_ABE|Product_ABE|v25.0",
        "Product_Domain|Loyalty_ABE|Loyalty_Program_ABE|v25.0",
    ]
    result = _parse_sid_list(entries)
    assert len(result) == 2
    assert result[0].abe_l2 == "Product ABE"
    assert result[1].abe_l2 == "Loyalty Program ABE"


def test_parse_sid_list_none_returns_empty() -> None:
    assert _parse_sid_list(None) == []


def test_v1_sid_abes_extracted() -> None:
    """SIDs field in a v1 manifest populates sid_abes on the Component."""
    comp = parse_manifest(yaml.safe_load(V1_WITH_FRAMEWORK_FIELDS))
    assert comp is not None
    assert len(comp.sid_abes) == 2
    domains = {s.domain for s in comp.sid_abes}
    assert domains == {"Product"}
    l2s = {s.abe_l2 for s in comp.sid_abes}
    assert "Product ABE" in l2s
    assert "Loyalty Program ABE" in l2s


def test_v1_without_sids_returns_empty_list() -> None:
    comp = parse_manifest(yaml.safe_load(V1_WITHOUT_FRAMEWORK_FIELDS))
    assert comp is not None
    assert comp.sid_abes == []


def test_v1beta3_sid_abes_empty() -> None:
    comp = parse_manifest(yaml.safe_load(V1BETA3_NO_FRAMEWORK))
    assert comp is not None
    assert comp.sid_abes == []


def test_sid_abes_in_to_dict() -> None:
    comp = parse_manifest(yaml.safe_load(V1_WITH_FRAMEWORK_FIELDS))
    assert comp is not None
    d = comp.to_dict()
    assert "sid_abes" in d
    for entry in d["sid_abes"]:
        assert set(entry.keys()) == {"domain", "abe_l1", "abe_l2", "version"}
