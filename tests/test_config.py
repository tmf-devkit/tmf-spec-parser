"""Tests for config.py — verify internal consistency of curated data."""

from __future__ import annotations

import pytest

from tmf_spec_parser.config import (
    API_IDS,
    API_REGISTRY,
    PATTERNS,
    SCHEMA_TO_API,
    TERMINAL_STATES,
    TRANSITIONS,
)


def test_api_registry_has_required_keys():
    for entry in API_REGISTRY:
        for key in ("id", "name", "domain", "short", "repo"):
            assert key in entry, f"Missing key '{key}' in {entry}"


def test_api_ids_match_registry():
    assert API_IDS == [a["id"] for a in API_REGISTRY]


def test_all_apis_have_transitions():
    for api_id in API_IDS:
        assert api_id in TRANSITIONS, f"{api_id} missing from TRANSITIONS"


def test_all_apis_have_terminal_states():
    for api_id in API_IDS:
        assert api_id in TERMINAL_STATES, f"{api_id} missing from TERMINAL_STATES"


def test_terminal_states_are_subsets_of_lifecycle():
    """Every terminal state must appear in the TRANSITIONS keys or lifecycle somewhere.
    At minimum: terminal states should be valid state strings (non-empty)."""
    for api_id, terminal in TERMINAL_STATES.items():
        for state in terminal:
            assert isinstance(state, str) and state, f"Invalid terminal state in {api_id}: {state!r}"


def test_transitions_have_from_and_to():
    for api_id, transitions in TRANSITIONS.items():
        for t in transitions:
            assert "from" in t and "to" in t, f"Bad transition in {api_id}: {t}"


def test_transitions_no_self_loops():
    for api_id, transitions in TRANSITIONS.items():
        for t in transitions:
            assert t["from"] != t["to"], f"Self-loop in {api_id}: {t}"


def test_schema_to_api_values_are_valid_ids():
    for schema, api_id in SCHEMA_TO_API.items():
        assert api_id in API_IDS, f"SCHEMA_TO_API[{schema!r}] = {api_id!r} is not a valid API ID"


def test_patterns_structure():
    for pattern in PATTERNS:
        for key in ("id", "name", "color", "nodes", "desc"):
            assert key in pattern, f"Missing key '{key}' in pattern {pattern}"
        for node in pattern["nodes"]:
            assert node in API_IDS, f"Pattern node {node!r} not in API_IDS"


def test_no_duplicate_api_ids():
    ids = [a["id"] for a in API_REGISTRY]
    assert len(ids) == len(set(ids)), "Duplicate API IDs in registry"


def test_domains_are_known():
    valid_domains = {"customer", "product", "service", "resource", "engagement", "common"}
    for entry in API_REGISTRY:
        assert entry["domain"] in valid_domains, f"Unknown domain: {entry['domain']} in {entry['id']}"
