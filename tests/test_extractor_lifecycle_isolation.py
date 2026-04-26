"""Tests that lock in correct lifecycle extraction across API boundaries.

These tests document and prevent regression of two bugs surfaced after the
v0.2.4 release:

  Bug 1 (cross-domain enum leak): An API that embeds a *Ref to another API's
  entity (e.g. TMF652 embedding ResourceRef from TMF639) used to extract the
  inventory enum (e.g. 'standby, alarm, available') as if it were the order's
  own lifecycle.

  Bug 2 (generic-job-status pollution): TMF Catalog APIs include ImportJob /
  ExportJob schemas with a generic 'Not Started, Running, Succeeded, Failed'
  status enum. The extractor used to treat that as the catalog's lifecycle.

Both classes of bug are about the same flaw: scanning over schemas without
distinguishing the API's own primary domain from helper / cross-API content.
"""

from __future__ import annotations

import pytest

from tmf_spec_parser.extractor import (
    _extract_entities,
    _get_schemas,
    extract_lifecycle,
)

# ── Bug 1 — cross-API ref enums must not leak ────────────────────────────────

@pytest.fixture()
def tmf652_with_resourceref() -> dict:
    """TMF652 Resource Order spec where ResourceOrder.state is plain string
    (no enum, no ref) and a ResourceRef carries inventory-domain status.

    Real-world cause: TMF652 imports ResourceRef which has a resourceStatus
    field pointing at an inventory-domain enum like (standby, alarm, available).
    Without the leak guard, that enum gets returned as TMF652's lifecycle.
    """
    return {
        "openapi": "3.0.0",
        "info": {"version": "4.0.0"},
        "components": {"schemas": {
            "ResourceOrder": {
                "type": "object", "required": ["id"],
                "properties": {
                    "id":        {"type": "string"},
                    "state":     {"type": "string"},
                    "orderItem": {"$ref": "#/components/schemas/ResourceOrderItem"},
                },
            },
            "ResourceOrderItem": {
                "type": "object",
                "properties": {"resource": {"$ref": "#/components/schemas/ResourceRef"}},
            },
            "ResourceRef": {
                "type": "object",
                "properties": {
                    "id":             {"type": "string"},
                    "resourceStatus": {"$ref": "#/components/schemas/ResourceStatusType"},
                },
            },
            "ResourceStatusType": {
                "type": "string",
                "enum": ["standby", "alarm", "available"],
            },
        }},
    }


def test_resourceref_enum_does_not_leak_into_resource_order(tmf652_with_resourceref):
    """The inventory enum reachable through ResourceRef MUST NOT become
    TMF652's lifecycle."""
    schemas  = _get_schemas(tmf652_with_resourceref)
    entities = _extract_entities(schemas)
    states   = extract_lifecycle("TMF652", schemas, entities)

    # The polluting values must not appear at all.
    assert "standby"   not in states
    assert "alarm"     not in states
    assert "available" not in states


def test_resourceref_pollution_yields_empty_when_no_proper_enum(
    tmf652_with_resourceref,
):
    """When ResourceOrder has no inline state enum and no ResourceOrderStateType,
    extraction should return [] so the curated baseline can fill in. Returning
    the wrong enum (the inventory one) would silently corrupt the data."""
    schemas  = _get_schemas(tmf652_with_resourceref)
    entities = _extract_entities(schemas)
    states   = extract_lifecycle("TMF652", schemas, entities)
    assert states == []


def test_correct_order_state_enum_preferred_over_resourceref():
    """When BOTH a polluting ResourceRef-carried enum AND the correct
    ResourceOrderStateType are present, the order-domain enum wins."""
    spec = {
        "openapi": "3.0.0",
        "info": {"version": "4.0.0"},
        "components": {"schemas": {
            "ResourceOrder": {
                "type": "object", "required": ["id"],
                "properties": {
                    "id":    {"type": "string"},
                    "state": {"type": "string"},
                },
            },
            "ResourceRef": {
                "type": "object",
                "properties": {
                    "resourceStatus": {"$ref": "#/components/schemas/ResourceStatusType"},
                },
            },
            "ResourceStatusType": {
                "type": "string",
                "enum": ["standby", "alarm", "available"],
            },
            "ResourceOrderStateType": {
                "type": "string",
                "enum": [
                    "acknowledged", "inProgress", "completed", "failed", "cancelled",
                ],
            },
        }},
    }
    schemas  = _get_schemas(spec)
    entities = _extract_entities(schemas)
    states   = extract_lifecycle("TMF652", schemas, entities)
    assert "acknowledged" in states
    assert "inProgress"   in states
    assert "standby"      not in states


# ── Bug 2 — generic job/task helpers must not pollute lifecycle ──────────────

@pytest.fixture()
def tmf620_with_importjob() -> dict:
    """TMF620 Product Catalog spec where Catalog.lifecycleStatus is plain
    string (no enum) and an ImportJob schema carries a generic job-status
    enum like (Not Started, Running, Succeeded, Failed).

    Real-world cause: every TMForum Catalog API ships ImportJob and ExportJob
    helper schemas. Their status enum is generic CI/job tracking, not the
    catalog's domain lifecycle.
    """
    return {
        "openapi": "3.0.0",
        "info": {"version": "4.1.0"},
        "components": {"schemas": {
            "Catalog": {
                "type": "object", "required": ["id", "name"],
                "properties": {
                    "id":              {"type": "string"},
                    "name":            {"type": "string"},
                    "lifecycleStatus": {"type": "string"},
                },
            },
            "ImportJob": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["Not Started", "Running", "Succeeded", "Failed"],
                    },
                },
            },
            "ExportJob": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["Not Started", "Running", "Succeeded", "Failed"],
                    },
                },
            },
        }},
    }


def test_importjob_status_does_not_leak_into_catalog(tmf620_with_importjob):
    """The 'Not Started, Running, Succeeded, Failed' enum from ImportJob
    MUST NOT become TMF620's lifecycle."""
    schemas  = _get_schemas(tmf620_with_importjob)
    entities = _extract_entities(schemas)
    states   = extract_lifecycle("TMF620", schemas, entities)

    assert "Not Started" not in states
    assert "Running"     not in states
    assert "Succeeded"   not in states


def test_importjob_pollution_yields_empty_when_no_proper_enum(
    tmf620_with_importjob,
):
    """When the catalog's only state field is plain string and the only
    candidate enum belongs to ImportJob, extraction must return [] so the
    curated baseline can supply correct catalog states."""
    schemas  = _get_schemas(tmf620_with_importjob)
    entities = _extract_entities(schemas)
    states   = extract_lifecycle("TMF620", schemas, entities)
    assert states == []


def test_correct_catalog_state_enum_preferred_over_importjob():
    """When BOTH ImportJob status AND the correct CatalogStateType are
    present, the catalog-domain enum wins."""
    spec = {
        "openapi": "3.0.0",
        "info": {"version": "4.1.0"},
        "components": {"schemas": {
            "Catalog": {
                "type": "object", "required": ["id"],
                "properties": {
                    "id":              {"type": "string"},
                    "lifecycleStatus": {"$ref": "#/components/schemas/CatalogStateType"},
                },
            },
            "ImportJob": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["Not Started", "Running", "Succeeded", "Failed"],
                    },
                },
            },
            "CatalogStateType": {
                "type": "string",
                "enum": [
                    "inStudy", "inDesign", "inTest", "active", "launched", "retired",
                ],
            },
        }},
    }
    schemas  = _get_schemas(spec)
    entities = _extract_entities(schemas)
    states   = extract_lifecycle("TMF620", schemas, entities)
    assert "inStudy"  in states
    assert "active"   in states
    assert "Not Started" not in states


# ── Variant suffix entities should not seed lifecycle ────────────────────────

def test_create_variant_does_not_seed_lifecycle():
    """An entity ending in 'Create' (a payload variant) must not be picked
    over the primary entity for lifecycle even if it has a state enum."""
    spec = {
        "openapi": "3.0.0",
        "info": {"version": "4.0.0"},
        "components": {"schemas": {
            "Service": {
                "type": "object", "required": ["id", "name"],
                "properties": {
                    "id":    {"type": "string"},
                    "name":  {"type": "string"},
                    "state": {"type": "string"},  # plain — not authoritative
                },
            },
            "ServiceCreate": {
                "type": "object", "required": ["id"],
                "properties": {
                    "id":    {"type": "string"},
                    # A test-fixture status enum that should NOT be picked up
                    "state": {
                        "type": "string",
                        "enum": ["draft-state-1", "draft-state-2"],
                    },
                },
            },
        }},
    }
    schemas  = _get_schemas(spec)
    entities = _extract_entities(schemas)
    states   = extract_lifecycle("TMF638", schemas, entities)
    # The Service primary entity has no enum, ServiceCreate is a variant -> []
    assert "draft-state-1" not in states
