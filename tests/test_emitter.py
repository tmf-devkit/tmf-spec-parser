"""Tests for emitter.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tmf_spec_parser.config import API_IDS
from tmf_spec_parser.emitter import (
    _build_details,
    _build_links,
    build,
    load_existing,
    write_js_module,
    write_json,
    write_ts_module,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def minimal_extracted() -> dict:
    """Minimal extracted dict for two APIs."""
    tmf641_entity = {"name": "ServiceOrder", "mandatory": ["id", "state"], "optional": ["priority"]}
    tmf638_entity = {"name": "Service", "mandatory": ["id", "name", "state"], "optional": []}
    return {
        "TMF641": {
            "id":          "TMF641",
            "version":     "4.1.0",
            "description": "Service Order Management.",
            "entities":    [tmf641_entity],
            "lifecycle":   ["acknowledged", "inProgress", "completed"],
            "links":       [{"source": "TMF641", "target": "TMF638", "label": "creates Service"}],
        },
        "TMF638": {
            "id":          "TMF638",
            "version":     "4.0.0",
            "description": "Service Inventory Management.",
            "entities":    [tmf638_entity],
            "lifecycle":   ["active", "inactive", "terminated"],
            "links":       [],
        },
    }


# ── _build_links ──────────────────────────────────────────────────────────────

def test_build_links_basic():
    links = _build_links(minimal_extracted())
    assert any(lnk["source"] == "TMF641" and lnk["target"] == "TMF638" for lnk in links)


def test_build_links_deduplicated():
    extracted = {
        "TMF641": {
            "links": [
                {"source": "TMF641", "target": "TMF638", "label": "creates Service"},
                {"source": "TMF641", "target": "TMF638", "label": "creates Service"},
            ]
        }
    }
    links = _build_links(extracted)
    assert len(links) == 1


def test_build_links_sorted():
    links = _build_links(minimal_extracted())
    sources = [lnk["source"] for lnk in links]
    assert sources == sorted(sources)


# ── _build_details ────────────────────────────────────────────────────────────

def test_build_details_includes_all_registry_apis():
    details = _build_details(minimal_extracted())
    for api_id in API_IDS:
        assert api_id in details


def test_build_details_merges_transitions():
    details = _build_details(minimal_extracted())
    assert len(details["TMF641"]["transitions"]) > 0


def test_build_details_merges_terminal_states():
    details = _build_details(minimal_extracted())
    assert "completed" in details["TMF641"]["terminal"]
    assert "failed" in details["TMF641"]["terminal"]


def test_build_details_specref_format():
    details = _build_details(minimal_extracted())
    assert details["TMF641"]["specRef"] == "TMF641 v4.1.0"


def test_build_details_fallback_for_unfetched():
    """When no spec is fetched, curated baseline fills entities/lifecycle/transitions."""
    details = _build_details({})
    assert "TMF638" in details
    # Baseline now fills entities — not empty (this is the correct v0.2 behaviour)
    assert len(details["TMF638"]["entities"]) > 0
    assert len(details["TMF638"]["lifecycle"]) > 0
    assert len(details["TMF638"]["transitions"]) > 0


# ── build() ───────────────────────────────────────────────────────────────────

def test_build_top_level_keys():
    data = build(minimal_extracted())
    for key in ("generated_at", "parser_version", "apis", "links", "patterns", "details"):
        assert key in data


def test_build_apis_is_list():
    data = build(minimal_extracted())
    assert isinstance(data["apis"], list)
    assert len(data["apis"]) == 16


def test_build_generated_at_format():
    data = build(minimal_extracted())
    assert data["generated_at"].endswith("Z")


def test_build_patterns_present():
    data = build(minimal_extracted())
    pattern_ids = {p["id"] for p in data["patterns"]}
    assert "o2a" in pattern_ids
    assert "c2i" in pattern_ids
    assert "t2r" in pattern_ids


# ── write_json ────────────────────────────────────────────────────────────────

def test_write_json_creates_file():
    data = build(minimal_extracted())
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tmf_data.json"
        write_json(data, path)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["parser_version"] == data["parser_version"]


def test_write_json_creates_parent_dirs():
    data = build(minimal_extracted())
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "subdir" / "nested" / "tmf_data.json"
        write_json(data, path)
        assert path.exists()


# ── write_js_module ───────────────────────────────────────────────────────────

def test_write_js_module():
    data = build(minimal_extracted())
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tmf_data.js"
        write_js_module(data, path)
        content = path.read_text()
        assert "export default" in content
        assert "tmf-spec-parser" in content
        assert "TMF641" in content


# ── write_ts_module ───────────────────────────────────────────────────────────

def test_write_ts_module():
    data = build(minimal_extracted())
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tmf_data.ts"
        write_ts_module(data, path)
        content = path.read_text()
        assert "TmfData" in content
        assert "export default" in content


# ── load_existing ─────────────────────────────────────────────────────────────

def test_load_existing_valid():
    data = build(minimal_extracted())
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
