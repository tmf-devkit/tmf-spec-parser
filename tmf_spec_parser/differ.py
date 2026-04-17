"""
differ.py — Diff extracted spec data against an existing tmf_data.json.

Detects three categories of change that matter for API implementers:

  FIELD_ADDED      : a field appeared in the spec that wasn't in our data
  FIELD_REMOVED    : a field was removed from the spec (breaking for consumers)
  STATE_CHANGED    : lifecycle states changed (new state added or state removed)
  VERSION_CHANGED  : the spec version number bumped

Each finding has a severity:
  ERROR   — breaking change (mandatory field removed, lifecycle state removed)
  WARNING — additive change (new optional field, new lifecycle state, version bump)
  INFO    — informational only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    ERROR   = "ERROR"
    WARNING = "WARNING"
    INFO    = "INFO"


@dataclass
class Finding:
    api_id:      str
    severity:    Severity
    category:    str        # e.g. "FIELD_REMOVED", "STATE_CHANGED"
    entity:      Optional[str]
    message:     str

    def __str__(self) -> str:
        entity_part = f" [{self.entity}]" if self.entity else ""
        return f"[{self.severity.value}] {self.api_id}{entity_part} — {self.category}: {self.message}"


@dataclass
class DiffReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.INFO]

    @property
    def has_breaking_changes(self) -> bool:
        return bool(self.errors)

    def summary(self) -> str:
        e, w, i = len(self.errors), len(self.warnings), len(self.infos)
        return f"{e} error(s), {w} warning(s), {i} info(s)"

    def to_markdown(self) -> str:
        """Render as a SPEC_CHANGES.md document."""
        lines = [
            "# TMF Spec Changes Report",
            "",
            f"**Summary:** {self.summary()}",
            "",
        ]
        if not self.findings:
            lines.append("_No differences detected — specs are in sync._")
            return "\n".join(lines)

        for severity in (Severity.ERROR, Severity.WARNING, Severity.INFO):
            subset = [f for f in self.findings if f.severity == severity]
            if not subset:
                continue
            lines.append(f"## {severity.value}S ({len(subset)})")
            lines.append("")
            for finding in subset:
                entity_part = f" `{finding.entity}`" if finding.entity else ""
                lines.append(f"- **{finding.api_id}**{entity_part} — `{finding.category}`: {finding.message}")
            lines.append("")

        return "\n".join(lines)


# ── Core diff logic ────────────────────────────────────────────────────────────

def diff(
    existing: dict[str, dict],
    extracted: dict[str, dict],
) -> DiffReport:
    """
    Compare existing tmf_data["details"] against freshly extracted data.

    Parameters
    ----------
    existing  : the "details" section from the current tmf_data.json
    extracted : output of extractor.extract_all()

    Returns
    -------
    DiffReport with all findings
    """
    report = DiffReport()

    all_api_ids = set(existing) | set(extracted)

    for api_id in sorted(all_api_ids):
        old = existing.get(api_id)
        new = extracted.get(api_id)

        if old is None:
            report.findings.append(Finding(
                api_id=api_id, severity=Severity.INFO,
                category="API_ADDED", entity=None,
                message="API appears in extracted data but not in existing tmf_data.json",
            ))
            continue

        if new is None:
            report.findings.append(Finding(
                api_id=api_id, severity=Severity.WARNING,
                category="API_NOT_FETCHED", entity=None,
                message="API exists in tmf_data.json but was not fetched (check fetch errors)",
            ))
            continue

        # ── Version change ────────────────────────────────────────────────────
        old_ver = old.get("specRef", "")
        new_ver = new.get("version", "")
        if new_ver and new_ver != "unknown" and new_ver not in old_ver:
            report.findings.append(Finding(
                api_id=api_id, severity=Severity.INFO,
                category="VERSION_CHANGED", entity=None,
                message=f"Spec version changed: was '{old_ver}', now '{new_ver}'",
            ))

        # ── Entity field diffs ────────────────────────────────────────────────
        old_entities = {e["name"]: e for e in old.get("entities", [])}
        new_entities = {e["name"]: e for e in new.get("entities", [])}

        for entity_name, new_entity in new_entities.items():
            old_entity = old_entities.get(entity_name)
            if old_entity is None:
                report.findings.append(Finding(
                    api_id=api_id, severity=Severity.INFO,
                    category="ENTITY_ADDED", entity=entity_name,
                    message=f"New entity '{entity_name}' found in spec",
                ))
                continue

            old_mandatory = set(old_entity.get("mandatory", []))
            new_mandatory = set(new_entity.get("mandatory", []))
            old_optional  = set(old_entity.get("optional",  []))
            new_optional  = set(new_entity.get("optional",  []))

            # Mandatory field removed → breaking
            for f in sorted(old_mandatory - new_mandatory):
                report.findings.append(Finding(
                    api_id=api_id, severity=Severity.ERROR,
                    category="MANDATORY_FIELD_REMOVED", entity=entity_name,
                    message=f"Required field '{f}' was removed from spec",
                ))

            # New mandatory field → breaking for existing implementations
            for f in sorted(new_mandatory - old_mandatory):
                report.findings.append(Finding(
                    api_id=api_id, severity=Severity.ERROR,
                    category="MANDATORY_FIELD_ADDED", entity=entity_name,
                    message=f"New required field '{f}' added to spec — existing implementations may not supply it",
                ))

            # Optional field added → informational
            for f in sorted((new_optional - old_optional) - new_mandatory):
                report.findings.append(Finding(
                    api_id=api_id, severity=Severity.INFO,
                    category="OPTIONAL_FIELD_ADDED", entity=entity_name,
                    message=f"New optional field '{f}' added",
                ))

            # Optional field removed → warning (consumers may depend on it)
            for f in sorted((old_optional - new_optional) - old_mandatory):
                report.findings.append(Finding(
                    api_id=api_id, severity=Severity.WARNING,
                    category="OPTIONAL_FIELD_REMOVED", entity=entity_name,
                    message=f"Optional field '{f}' removed from spec",
                ))

        # Entities that vanished entirely
        for entity_name in sorted(set(old_entities) - set(new_entities)):
            report.findings.append(Finding(
                api_id=api_id, severity=Severity.ERROR,
                category="ENTITY_REMOVED", entity=entity_name,
                message=f"Entity '{entity_name}' no longer found in spec",
            ))

        # ── Lifecycle state diffs ─────────────────────────────────────────────
        old_states = set(old.get("lifecycle", []))
        new_states  = set(new.get("lifecycle", []))

        for s in sorted(old_states - new_states):
            report.findings.append(Finding(
                api_id=api_id, severity=Severity.ERROR,
                category="LIFECYCLE_STATE_REMOVED", entity=None,
                message=f"Lifecycle state '{s}' removed from spec — breaks state machine consumers",
            ))

        for s in sorted(new_states - old_states):
            report.findings.append(Finding(
                api_id=api_id, severity=Severity.WARNING,
                category="LIFECYCLE_STATE_ADDED", entity=None,
                message=f"New lifecycle state '{s}' in spec — update transitions table in config.py",
            ))

    return report
