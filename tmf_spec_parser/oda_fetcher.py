"""
oda_fetcher.py — Download ODA Component (ODAC) YAML manifests from GitHub.

Source repo: tmforum-rand/TMForum-ODA-Ready-for-publication, pinned to
tag v1.0.0 by default. The repo layout is:

    /TMFC001-ProductCatalogManagement/
        TMFC001-ProductCatalogManagement.component.yaml
        ... (stub code, CTKs, etc.)
    /TMFC002-ProductOrderCaptureAndValidation/
        ...
    /TMFC008-ServiceInventory/
        ...

37 components at v1.0.0. Each folder name encodes the component id.
The manifest filename is the same as the folder name with a
`.component.yaml` suffix in the typical case, but we use the GitHub
Contents API to enumerate and pick the best YAML candidate for
robustness against naming drift.

Strategy mirrors the OpenAPI fetcher (fetcher.py):
  1. Local cache hit returns immediately.
  2. List the repo root via Contents API to enumerate component folders.
  3. For each folder, list its contents and pick the best YAML file.
  4. Download the YAML via raw URL, with branch-fallback (main -> master)
     and tag preference (the pinned ref).
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import httpx

from tmf_spec_parser.config import (
    ODA_GITHUB_ORG,
    ODA_GITHUB_REPO,
    ODA_REPO_REF,
)

# Default cache directory: ~/.tmf-spec-parser/oda-cache/
DEFAULT_ODA_CACHE_DIR = Path.home() / ".tmf-spec-parser" / "oda-cache"

# Folder name pattern: TMFCxxx-Name (e.g. TMFC008-ServiceInventory).
_FOLDER_RE = re.compile(r"^(TMFC\d+)-(.+)$")

# Filenames to skip even if they have .yaml/.yml extension.
_YAML_BLOCKLIST = (
    "values.yaml",        # Helm values, not the component manifest
    "chart.yaml",         # Helm chart metadata
    "ctk-",               # Conformance Test Kit assets
    "package.yaml",
)

# Pinned tag URL templates. Using the tag both protects against upstream
# rewrites and makes the data file traceable.
_RAW_URL = (
    "https://raw.githubusercontent.com/{org}/{repo}/{ref}/{path}"
)
_CONTENTS_URL = (
    "https://api.github.com/repos/{org}/{repo}/contents/{path}?ref={ref}"
)


class ODAFetchError(Exception):
    """Raised when an ODAC manifest cannot be fetched."""


def _github_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _list_dir(
    client: httpx.Client,
    path: str,
    org: str,
    repo: str,
    ref: str,
) -> list[dict]:
    """Call the Contents API for a path within the repo at the pinned ref."""
    url = _CONTENTS_URL.format(org=org, repo=repo, ref=ref, path=path)
    resp = client.get(url, headers=_github_headers(), timeout=15)
    if resp.status_code != 200:
        return []
    data = resp.json()
    return data if isinstance(data, list) else []


def _score_yaml(name: str, folder_id: str) -> int:
    """Score a YAML filename. Higher is better; 0 means reject.

    Prefers files that mention the component id (TMFCxxx) in their name
    over generic-named YAMLs in the same folder.
    """
    nl = name.lower()
    if not nl.endswith((".yaml", ".yml")):
        return 0
    if any(b in nl for b in _YAML_BLOCKLIST):
        return 0
    score = 1
    if folder_id.lower() in nl:
        score += 5
    if ".component." in nl or "-component." in nl or nl.endswith("component.yaml"):
        score += 3
    return score


def _best_yaml(entries: list[dict], folder_id: str) -> str | None:
    """Pick the most likely component manifest from a folder listing."""
    candidates: list[tuple[int, str]] = []
    for entry in entries:
        if entry.get("type") != "file":
            continue
        name = entry["name"]
        score = _score_yaml(name, folder_id)
        if score:
            candidates.append((score, entry.get("path", name)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _fetch_raw(
    client: httpx.Client,
    path: str,
    org: str,
    repo: str,
    ref: str,
) -> str | None:
    """GET raw text content; return None on non-200."""
    url = _RAW_URL.format(org=org, repo=repo, ref=ref, path=path)
    resp = client.get(url, headers=_github_headers(), timeout=30, follow_redirects=True)
    if resp.status_code != 200:
        return None
    return resp.text


def list_components(
    client: httpx.Client | None = None,
    org: str = ODA_GITHUB_ORG,
    repo: str = ODA_GITHUB_REPO,
    ref: str = ODA_REPO_REF,
) -> list[tuple[str, str]]:
    """List ODAC component folders in the repo. Returns (component_id, folder_path)."""
    own_client = client is None
    if own_client:
        client = httpx.Client()
    try:
        entries = _list_dir(client, "", org, repo, ref)
    finally:
        if own_client:
            client.close()
    out: list[tuple[str, str]] = []
    for entry in entries:
        if entry.get("type") != "dir":
            continue
        name = entry["name"]
        m = _FOLDER_RE.match(name)
        if m:
            out.append((m.group(1), name))
    out.sort()
    return out


def fetch_manifest(
    component_id: str,
    folder_path: str,
    client: httpx.Client,
    cache_dir: Path = DEFAULT_ODA_CACHE_DIR,
    refresh: bool = False,
    delay: float = 0.3,
    org: str = ODA_GITHUB_ORG,
    repo: str = ODA_GITHUB_REPO,
    ref: str = ODA_REPO_REF,
) -> str:
    """Fetch a single ODAC manifest YAML, caching to disk. Returns YAML text.
    
    Note: At tag v1.0.0, the YAML manifests are nested inside a Specification/
    subdirectory rather than at the component folder root. The folder structure is:
        TMFC{nnn}-{Name}/
            Specification/
                TMFC{nnn}-{Name}.yaml  ← actual manifest
            CTK/
            ComponentConformanceProfile/
            TMFC{nnn}_{Name}_v{version}.pdf
    """
    cache_path = cache_dir / f"{component_id}.yaml"
    if cache_path.exists() and not refresh:
        return cache_path.read_text(encoding="utf-8")

    cache_dir.mkdir(parents=True, exist_ok=True)

    entries = _list_dir(client, folder_path, org, repo, ref)
    time.sleep(delay)
    if not entries:
        raise ODAFetchError(
            f"Could not list folder {folder_path!r} for {component_id} "
            f"(check network / GITHUB_TOKEN)"
        )

    yaml_path = _best_yaml(entries, component_id)
    
    # If no YAML at root, check inside Specification/ subdirectory
    if yaml_path is None:
        spec_subdir = next(
            (e for e in entries if e.get("type") == "dir" and e["name"] == "Specification"),
            None
        )
        if spec_subdir:
            spec_path = f"{folder_path}/Specification"
            spec_entries = _list_dir(client, spec_path, org, repo, ref)
            time.sleep(delay)
            if spec_entries:
                yaml_path = _best_yaml(spec_entries, component_id)
                if yaml_path and not yaml_path.startswith(folder_path):
                    yaml_path = f"{folder_path}/Specification/{yaml_path}"
    
    if yaml_path is None:
        raise ODAFetchError(
            f"No suitable .yaml manifest found in {folder_path!r} for {component_id}"
        )

    text = _fetch_raw(client, yaml_path, org, repo, ref)
    time.sleep(delay)
    if text is None:
        raise ODAFetchError(
            f"Could not download manifest at {yaml_path!r} for {component_id}"
        )

    cache_path.write_text(text, encoding="utf-8")
    return text


def fetch_all_manifests(
    cache_dir: Path = DEFAULT_ODA_CACHE_DIR,
    refresh: bool = False,
    delay: float = 0.3,
    org: str = ODA_GITHUB_ORG,
    repo: str = ODA_GITHUB_REPO,
    ref: str = ODA_REPO_REF,
    component_filter: list[str] | None = None,
) -> dict[str, str]:
    """Fetch all ODAC manifests under the pinned ref.

    Returns a dict of {component_id: yaml_text}. Components that fail to
    fetch are logged via warnings and omitted from the result.
    """
    results: dict[str, str] = {}
    errors: dict[str, str] = {}

    with httpx.Client() as client:
        components = list_components(client, org=org, repo=repo, ref=ref)
        time.sleep(delay)

        if component_filter:
            wanted = {c.upper() for c in component_filter}
            components = [c for c in components if c[0].upper() in wanted]

        for component_id, folder_path in components:
            try:
                results[component_id] = fetch_manifest(
                    component_id=component_id,
                    folder_path=folder_path,
                    client=client,
                    cache_dir=cache_dir,
                    refresh=refresh,
                    delay=delay,
                    org=org, repo=repo, ref=ref,
                )
            except ODAFetchError as exc:
                errors[component_id] = str(exc)

    if errors:
        import warnings
        for component_id, msg in errors.items():
            warnings.warn(
                f"[tmf-spec-parser oda] fetch failed for {component_id}: {msg}",
                stacklevel=2,
            )

    return results
