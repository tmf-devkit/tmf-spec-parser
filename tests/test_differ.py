"""Tests for differ.py."""

from __future__ import annotations

from tmf_spec_parser.differ import DiffReport, Finding, Severity, diff

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_existing(
    api_id: str = "TMF641",
    mandatory: list[str] | None = None,
    optional:  list[str] | None = None,
    lifecycle: list[str] | None = None,
    spec_ref:  str = "TMF641 v4.1.0",
) -> dict:
    entity = {
        "name":      "ServiceOrder",
        "mandatory": mandatory or ["id", "state"],
        "optional":  optional or ["priority"],
    }
    return {
        api_id: {
            "specRef":   spec_ref,
            "entities":  [entity],
            "lifecycle": lifecycle or ["acknowledged", "inProgress", "completed"],
        }
    }


def _make_extracted(
    api_id: str = "TMF641",
    mandatory: list[str] | None = None,
    optional:  list[str] | None = None,
    lifecycle: list[str] | None = None,
    version:   str = "4.1.0",
) -> dict:
    entity = {
        "name":      "ServiceOrder",
        "mandatory": mandatory or ["id", "state"],
        "optional":  optional or ["priority"],
    }
    return {
        api_id: {
            "version":   version,
            "entities":  [entity],
            "lifecycle": lifecycle or ["acknowledged", "inProgress", "completed"],
            "links":     [],
        }
    }


# ── DiffReport helpers ────────────────────────────────────────────────────────

def test_diff_report_errors_property():
    report = DiffReport(findings=[
        Finding("TMF641", Severity.ERROR,   "X", None, "msg"),
        Finding("TMF641", Severity.WARNING, "Y", None, "msg"),
    ])
    assert len(report.errors) == 1
    assert len(report.warnings) == 1


def test_diff_report_has_breaking_changes():
    report = DiffReport(findings=[Finding("TMF641", Severity.ERROR, "X", None, "m")])
    assert report.has_breaking_changes is True


def test_diff_report_no_breaking_changes():
    report = DiffReport(findings=[Finding("TMF641", Severity.WARNING, "X", None, "m")])
    assert report.has_breaking_changes is False


def test_diff_report_summary():
    report = DiffReport(findings=[
        Finding("A", Severity.ERROR,   "X", None, "m"),
        Finding("A", Severity.WARNING, "Y", None, "m"),
        Finding("A", Severity.INFO,    "Z", None, "m"),
    ])
    assert "1 error" in report.summary()
    assert "1 warning" in report.summary()
    assert "1 info" in report.summary()


def test_diff_report_to_markdown_no_findings():
    report = DiffReport()
    md = report.to_markdown()
    assert "No differences" in md


def test_diff_report_to_markdown_with_findings():
    report = DiffReport(findings=[
        Finding(
            "TMF641", Severity.ERROR,
            "MANDATORY_FIELD_REMOVED", "ServiceOrder",
            "field 'state' removed",
        ),
    ])
    md = report.to_markdown()
    assert "TMF641" in md
    assert "MANDATORY_FIELD_REMOVED" in md
    assert "ERROR" in md


# ── diff() function ───────────────────────────────────────────────────────────

def test_no_diff_when_identical():
    existing  = _make_existing()
    extracted = _make_extracted()
    report = diff(existing, extracted)
    non_version = [f for f in report.findings if f.category != "VERSION_CHANGED"]
    assert non_version == []


def test_mandatory_field_removed_is_error():
    existing  = _make_existing(mandatory=["id", "state", "orderDate"])
    extracted = _make_extracted(mandatory=["id", "state"])
    report = diff(existing, extracted)
    cats = [f.category for f in report.findings]
    assert "MANDATORY_FIELD_REMOVED" in cats
    errors = [f for f in report.findings if f.severity == Severity.ERROR]
    assert any("orderDate" in f.message for f in errors)


def test_new_mandatory_field_is_error():
    existing  = _make_existing(mandatory=["id", "state"])
    extracted = _make_extracted(mandatory=["id", "state", "newRequiredField"])
    report = diff(existing, extracted)
    assert "MANDATORY_FIELD_ADDED" in [f.category for f in report.findings]


def test_optional_field_removed_is_warning():
    existing  = _make_existing(optional=["priority", "description"])
    extracted = _make_extracted(optional=["priority"])
    report = diff(existing, extracted)
    warnings = [
        f for f in report.findings
        if f.severity == Severity.WARNING and f.category == "OPTIONAL_FIELD_REMOVED"
    ]
    assert any("description" in f.message for f in warnings)


def test_optional_field_added_is_info():
    existing  = _make_existing(optional=["priority"])
    extracted = _make_extracted(optional=["priority", "newOptionalField"])
    report = diff(existing, extracted)
    infos = [
        f for f in report.findings
        if f.severity == Severity.INFO and f.category == "OPTIONAL_FIELD_ADDED"
    ]
    assert any("newOptionalField" in f.message for f in infos)


def test_lifecycle_state_removed_is_error():
    existing  = _make_existing(lifecycle=["acknowledged", "inProgress", "completed"])
    extracted = _make_extracted(lifecycle=["acknowledged", "completed"])
    report = diff(existing, extracted)
    errors = [f for f in report.findings if f.category == "LIFECYCLE_STATE_REMOVED"]
    assert any("inProgress" in f.message for f in errors)


def test_lifecycle_state_added_is_warning():
    existing  = _make_existing(lifecycle=["acknowledged", "completed"])
    extracted = _make_extracted(lifecycle=["acknowledged", "pending", "completed"])
    report = diff(existing, extracted)
    warnings = [f for f in report.findings if f.category == "LIFECYCLE_STATE_ADDED"]
    assert any("pending" in f.message for f in warnings)


def test_version_change_is_info():
    existing  = _make_existing(spec_ref="TMF641 v4.1.0")
    extracted = _make_extracted(version="4.2.0")
    report = diff(existing, extracted)
    infos = [f for f in report.findings if f.category == "VERSION_CHANGED"]
    assert len(infos) == 1


def test_api_not_fetched_is_warning():
    existing  = _make_existing("TMF641")
    extracted = {}
    report = diff(existing, extracted)
    assert "API_NOT_FETCHED" in [f.category for f in report.findings]


def test_new_api_in_extracted_is_info():
    existing  = {}
    extracted = _make_extracted("TMF999")
    report = diff(existing, extracted)
    assert "API_ADDED" in [f.category for f in report.findings]


def test_entity_removed_is_error():
    existing = {
        "TMF641": {
            "specRef": "TMF641 v4.1.0",
            "entities": [
                {"name": "ServiceOrder",     "mandatory": ["id"], "optional": []},
                {"name": "ServiceOrderItem", "mandatory": ["id"], "optional": []},
            ],
            "lifecycle": [],
        }
    }
    extracted = {
        "TMF641": {
            "version":  "4.1.0",
            "entities": [{"name": "ServiceOrder", "mandatory": ["id"], "optional": []}],
            "lifecycle": [],
            "links":    [],
        }
    }
    report = diff(existing, extracted)
    assert "ENTITY_REMOVED" in [f.category for f in report.findings]


def test_multiple_apis_diffed():
    existing = {
        "TMF641": _make_existing("TMF641")["TMF641"],
        "TMF638": _make_existing("TMF638", mandatory=["id", "name", "state"])["TMF638"],
    }
    extracted = {
        "TMF641": _make_extracted("TMF641")["TMF641"],
        "TMF638": _make_extracted("TMF638", mandatory=["id", "name"])["TMF638"],
    }
    report = diff(existing, extracted)
    assert "TMF638" in {f.api_id for f in report.findings}
