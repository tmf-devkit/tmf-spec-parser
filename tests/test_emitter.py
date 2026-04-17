"""Tests for emitter.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tmf_spec_parser.emitter import (
    build,
    load_existing,
    write_js_module,
    write_json,
    write_ts_module,
    _build_links,
    _build_details,
)
from tmf_spec_parser.config import API_IDS


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def minimal_extracted() -> dict:
    """Minimal extracted dict for two APIs."""
    return {
        "TMF641": {
            "id":          "TMF641",
            "version":     "4.1.0",
            "description": "Service Order Management.",
            "entities":    [{"name": "ServiceOrder", "mandatory": ["id", "state"], "optional": ["priority"]}],
            "lifecycle":   ["acknowledged", "inProgress", "completed"],
            "links":       [{"source": "TMF641", "target": "TMF638", "label": "creates Service"}],
        },
        "TMF638": {
            "id":          "TMF638",
            "version":     "4.0.0",
            "description": "Service Inventory Management.",
            "entities":    [{"name": "Service", "mandatory": ["id", "name", "state"], "optional": []}],
            "lifecycle":   ["active", "inactive", "terminated"],
            "links":       [],
        },
    }


# ── _build_links ──────────────────────────────────────────────────────────────

def test_build_links_basic(minimal_extracted):
    links = _build_links(minimal_extracted)
    assert any(l["source"] == "TMF641" and l["target"] == "TMF638" for l in links)


def test_build_links_deduplicated():
    extracted = {
        "TMF641": {
            "links": [
                {"source": "TMF641", "target": "TMF638", "label": "creates Service"},
                {"source": "TMF641", "target": "TMF638", "label": "creates Service"},  # duplicate
            ]
        }
    }
    links = _build_links(extracted)
    assert len(links) == 1


def test_build_links_sorted(minimal_extracted):
    links = _build_links(minimal_extracted)
    sources = [l["source"] for l in links]
    assert sources == sorted(sources)


# ── _build_details ────────────────────────────────────────────────────────────

def test_build_details_includes_all_registry_apis(minimal_extracted):
    details = _build_details(minimal_extracted)
    # All 16 registry APIs should have an entry (even if not extracted)
    for api_id in API_IDS:
        assert api_id in details


def test_build_details_merges_transitions(minimal_extracted):
    details = _build_details(minimal_extracted)
    # TMF641 should have curated transitions from config
    assert len(details["TMF641"]["transitions"]) > 0


def test_build_details_merges_terminal_states(minimal_extracted):
    details = _build_details(minimal_extracted)
    assert "completed" in details["TMF641"]["terminal"]
    assert "failed" in details["TMF641"]["terminal"]


def test_build_details_specref_format(minimal_extracted):
    details = _build_details(minimal_extracted)
    assert details["TMF641"]["specRef"] == "TMF641 v4.1.0"


def test_build_details_fallback_for_unfetched():
    """APIs not in extracted should still appear with empty/curated data."""
    details = _build_details({})
    assert "TMF638" in details
    assert details["TMF638"]["entities"] == []
    # Transitions are curated so should still be present
    assert isinstance(details["TMF638"]["transitions"], list)


# ── build() ───────────────────────────────────────────────────────────────────

def test_build_top_level_keys(minimal_extracted):
    data = build(minimal_extracted)
    for key in ("generated_at", "parser_version", "apis", "links", "patterns", "details"):
        assert key in data


def test_build_apis_is_list(minimal_extracted):
    data = build(minimal_extracted)
    assert isinstance(data["apis"], list)
    assert len(data["apis"]) == 16  # all from API_REGISTRY


def test_build_generated_at_format(minimal_extracted):
    data = build(minimal_extracted)
    # Should be ISO format ending in Z
    assert data["generated_at"].endswith("Z")


def test_build_patterns_present(minimal_extracted):
    data = build(minimal_extracted)
    pattern_ids = {p["id"] for p in data["patterns"]}
    assert "o2a" in pattern_ids
    assert "c2i" in pattern_ids
    assert "t2r" in pattern_ids


# ── write_json ────────────────────────────────────────────────────────────────

def test_write_json_creates_file(minimal_extracted):
    data = build(minimal_extracted)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tmf_data.json"
        write_json(data, path)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["parser_version"] == data["parser_version"]


def test_write_json_creates_parent_dirs(minimal_extracted):
    data = build(minimal_extracted)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "subdir" / "nested" / "tmf_data.json"
        write_json(data, path)
        assert path.exists()


# ── write_js_module ───────────────────────────────────────────────────────────

def test_write_js_module(minimal_extracted):
    data = build(minimal_extracted)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tmf_data.js"
        write_js_module(data, path)
        content = path.read_text()
        assert "export default" in content
        assert "tmf-spec-parser" in content
        assert "TMF641" in content


# ── write_ts_module ───────────────────────────────────────────────────────────

def test_write_ts_module(minimal_extracted):
    data = build(minimal_extracted)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tmf_data.ts"
        write_ts_module(data, path)
        content = path.read_text()
        assert "TmfData" in content
        assert "export default" in content


# ── load_existing ─────────────────────────────────────────────────────────────

def test_load_existing_valid(minimal_extracted):
    data = build(minimal_extracted)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tmf_data.json"
        write_json(data, path)
        loaded = load_existing(path)
        assert loaded is not None
        assert loaded["parser_version"] == data["parser_version"]


def test_load_existing_missing_file():
    result = load_existing(Path("/nonexistent/tmf_data.json"))
    assert result is None


def test_load_existing_corrupt_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tmf_data.json"
        path.write_text("{ not valid json }")
        result = load_existing(path)
        assert result is None
