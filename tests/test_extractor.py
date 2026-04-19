"""Tests for extractor.py — all run offline using fixture specs."""

from __future__ import annotations

import pytest

from tmf_spec_parser.extractor import (
    _extract_entities,
    _extract_links,
    _extract_mandatory_optional,
    _get_schemas,
    _is_root_entity,
    _spec_description,
    _spec_version,
    extract,
    extract_lifecycle,
)

# ── _get_schemas ──────────────────────────────────────────────────────────────

def test_get_schemas_oas3(tmf641_spec):
    schemas = _get_schemas(tmf641_spec)
    assert "ServiceOrder" in schemas
    assert "ServiceRef" in schemas


def test_get_schemas_swagger2(swagger2_spec):
    schemas = _get_schemas(swagger2_spec)
    assert "Individual" in schemas
    assert "Organization" in schemas


def test_get_schemas_empty():
    assert _get_schemas({}) == {}


# ── _spec_version ─────────────────────────────────────────────────────────────

def test_spec_version(tmf641_spec):
    assert _spec_version(tmf641_spec) == "4.1.0"


def test_spec_version_missing():
    assert _spec_version({}) == "unknown"


# ── _spec_description ─────────────────────────────────────────────────────────

def test_spec_description_first_sentence(tmf641_spec):
    desc = _spec_description(tmf641_spec)
    assert desc.endswith(".")


def test_spec_description_empty():
    assert _spec_description({}) == ""


# ── _is_root_entity ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,schema,expected", [
    ("ServiceOrder",     {"properties": {"id": {}}},    True),
    ("ServiceRef",       {"properties": {"id": {}}},    False),
    ("ServiceOrderFVO",  {"properties": {"id": {}}},    False),
    ("StateEnum",        {"type": "string"},              False),
    ("ServiceOrderItem", {"allOf": [{"$ref": "#/x"}]},  True),
    ("EmptySchema",      {},                             False),
])
def test_is_root_entity(name, schema, expected):
    assert _is_root_entity(name, schema) == expected


# ── _extract_mandatory_optional ───────────────────────────────────────────────

def test_extract_mandatory_optional_tmf641(tmf641_spec):
    schemas = _get_schemas(tmf641_spec)
    mandatory, optional = _extract_mandatory_optional(schemas["ServiceOrder"], schemas)
    assert "id" in mandatory
    assert "state" in mandatory
    assert "orderDate" in mandatory
    assert "priority" in optional or "requestedStartDate" in optional


def test_extract_mandatory_optional_no_required():
    schema = {"properties": {"foo": {}, "bar": {}}}
    mandatory, optional = _extract_mandatory_optional(schema, {})
    assert mandatory == []
    assert set(optional) == {"foo", "bar"}


def test_extract_mandatory_optional_caps_optional():
    props = {f"field_{i}": {} for i in range(20)}
    schema = {"properties": props}
    _, optional = _extract_mandatory_optional(schema, {})
    assert len(optional) <= 12


# ── extract_lifecycle ─────────────────────────────────────────────────────────

def test_extract_lifecycle_inline_enum(tmf641_spec):
    schemas = _get_schemas(tmf641_spec)
    entities = _extract_entities(schemas)
    states = extract_lifecycle("TMF641", schemas, entities)
    assert "acknowledged" in states
    assert "completed" in states
    assert "cancelled" in states


def test_extract_lifecycle_tmf638(tmf638_spec):
    schemas = _get_schemas(tmf638_spec)
    entities = _extract_entities(schemas)
    states = extract_lifecycle("TMF638", schemas, entities)
    assert "active" in states
    assert "terminated" in states


def test_extract_lifecycle_swagger2(swagger2_spec):
    schemas = _get_schemas(swagger2_spec)
    entities = _extract_entities(schemas)
    states = extract_lifecycle("TMF632", schemas, entities)
    assert "validated" in states


def test_extract_lifecycle_no_state_field():
    schema = {"properties": {"name": {"type": "string"}}}
    states = extract_lifecycle("TMF999", {"X": schema}, [])
    assert states == []


# ── _extract_links ────────────────────────────────────────────────────────────

def test_extract_links_tmf641_references_tmf638(tmf641_spec):
    schemas = _get_schemas(tmf641_spec)
    links = _extract_links("TMF641", schemas)
    targets = {lnk["target"] for lnk in links}
    assert "TMF638" in targets


def test_extract_links_tmf638_references_tmf639(tmf638_spec):
    schemas = _get_schemas(tmf638_spec)
    links = _extract_links("TMF638", schemas)
    targets = {lnk["target"] for lnk in links}
    assert "TMF639" in targets


def test_extract_links_no_self_reference(tmf641_spec):
    schemas = _get_schemas(tmf641_spec)
    links = _extract_links("TMF641", schemas)
    assert all(lnk["source"] != lnk["target"] for lnk in links)


def test_extract_links_deduplicated(tmf641_spec):
    schemas = _get_schemas(tmf641_spec)
    links = _extract_links("TMF641", schemas)
    keys = [(lnk["source"], lnk["target"], lnk["label"]) for lnk in links]
    assert len(keys) == len(set(keys))


# ── extract() full integration ────────────────────────────────────────────────

def test_extract_tmf641_full(tmf641_spec):
    result = extract("TMF641", tmf641_spec)
    assert result["id"] == "TMF641"
    assert result["version"] == "4.1.0"
    assert result["description"]
    assert any(e["name"] == "ServiceOrder" for e in result["entities"])
    assert "acknowledged" in result["lifecycle"]
    assert any(lnk["target"] == "TMF638" for lnk in result["links"])


def test_extract_tmf638_full(tmf638_spec):
    result = extract("TMF638", tmf638_spec)
    assert result["id"] == "TMF638"
    assert "active" in result["lifecycle"]
    assert "terminated" in result["lifecycle"]


def test_extract_swagger2(swagger2_spec):
    result = extract("TMF632", swagger2_spec)
    assert result["id"] == "TMF632"
    entity_names = {e["name"] for e in result["entities"]}
    assert "Individual" in entity_names or "Organization" in entity_names


def test_extract_empty_spec():
    result = extract("TMF999", {})
    assert result["id"] == "TMF999"
    assert result["entities"] == []
    assert result["lifecycle"] == []
    assert result["links"] == []
