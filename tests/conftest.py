"""Shared fixtures for tmf-spec-parser tests — no network calls."""

from __future__ import annotations

import pytest


# ── Minimal synthetic OpenAPI specs ──────────────────────────────────────────
# These mimic the real TMForum spec structure but are self-contained.

@pytest.fixture()
def tmf641_spec() -> dict:
    """Minimal TMF641 Service Ordering spec."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title":   "Service Ordering Management",
            "version": "4.1.0",
            "description": "Manages service order lifecycle from acknowledgement through fulfillment. Supports complex order scenarios.",
        },
        "components": {
            "schemas": {
                "ServiceOrder": {
                    "type": "object",
                    "required": ["id", "state", "orderDate"],
                    "properties": {
                        "id":          {"type": "string"},
                        "state":       {
                            "type": "string",
                            "enum": ["acknowledged", "inProgress", "pending", "held",
                                     "completed", "failed", "cancelled"],
                        },
                        "orderDate":               {"type": "string", "format": "date-time"},
                        "requestedStartDate":      {"type": "string", "format": "date-time"},
                        "requestedCompletionDate": {"type": "string", "format": "date-time"},
                        "priority":                {"type": "string"},
                        "description":             {"type": "string"},
                        "service": {"$ref": "#/components/schemas/ServiceRef"},
                    },
                },
                "ServiceOrderItem": {
                    "type": "object",
                    "required": ["id", "action", "state"],
                    "properties": {
                        "id":       {"type": "string"},
                        "action":   {"type": "string"},
                        "state":    {"type": "string"},
                        "quantity": {"type": "integer"},
                        "service":  {"$ref": "#/components/schemas/ServiceRef"},
                    },
                },
                "ServiceRef": {
                    "type": "object",
                    "properties": {
                        "id":   {"type": "string"},
                        "href": {"type": "string"},
                        "name": {"type": "string"},
                    },
                },
            }
        },
    }


@pytest.fixture()
def tmf638_spec() -> dict:
    """Minimal TMF638 Service Inventory spec."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title":   "Service Inventory Management",
            "version": "4.0.0",
            "description": "Provides a register of all instantiated services provisioned in the network.",
        },
        "components": {
            "schemas": {
                "Service": {
                    "type": "object",
                    "required": ["id", "name", "state", "serviceType"],
                    "properties": {
                        "id":          {"type": "string"},
                        "name":        {"type": "string"},
                        "serviceType": {"type": "string"},
                        "state": {
                            "type": "string",
                            "enum": ["feasibilityChecked", "designed", "reserved",
                                     "active", "inactive", "terminated"],
                        },
                        "startDate":             {"type": "string"},
                        "serviceCharacteristic": {"type": "array", "items": {}},
                        "supportingResource": {"$ref": "#/components/schemas/ResourceRef"},
                    },
                },
                "ResourceRef": {
                    "type": "object",
                    "properties": {
                        "id":   {"type": "string"},
                        "href": {"type": "string"},
                    },
                },
            }
        },
    }


@pytest.fixture()
def swagger2_spec() -> dict:
    """Swagger 2.0 style spec (older TMF repos still use this format)."""
    return {
        "swagger": "2.0",
        "info": {
            "title":   "Party Management",
            "version": "4.0.0",
            "description": "Manages party entities (individuals and organisations).",
        },
        "definitions": {
            "Individual": {
                "type": "object",
                "required": ["id", "fullName"],
                "properties": {
                    "id":        {"type": "string"},
                    "fullName":  {"type": "string"},
                    "birthDate": {"type": "string"},
                    "gender":    {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["initialized", "validated", "deceassed"],
                    },
                },
            },
            "Organization": {
                "type": "object",
                "required": ["id", "name"],
                "properties": {
                    "id":   {"type": "string"},
                    "name": {"type": "string"},
                    "tradingName": {"type": "string"},
                },
            },
        },
    }
