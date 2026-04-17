"""
fetcher.py — Download TMForum OpenAPI specs from GitHub with local caching.

Strategy:
  1. Check local cache directory first.
  2. If missing or --refresh flag set, fetch from GitHub.
  3. GitHub source: raw content from the default branch.  We probe two common
     filename patterns since TMForum repos are not perfectly consistent.
  4. Optionally use a GitHub personal access token (env: GITHUB_TOKEN) to
     avoid the 60 req/hr anonymous rate limit.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx

from tmf_spec_parser.config import (
    API_REGISTRY,
    GITHUB_API_BASE,
    GITHUB_ORG,
    GITHUB_RAW_BASE,
)

# Default cache directory: ~/.tmf-spec-parser/cache/
DEFAULT_CACHE_DIR = Path.home() / ".tmf-spec-parser" / "cache"

# Candidate OpenAPI filenames — tried in order for each repo.
# TMForum repos are inconsistent; newer ones use swagger.json, some use openapi.yaml.
FILENAME_CANDIDATES = [
    "{api_id}-{name_lower}-v{major}.{minor}.0.swagger.json",
    "{api_id}-{name_lower}-v{major}.{minor}.0.oas.yaml",
    "{api_id}_{name_title}.swagger.json",
    "{api_id}.swagger.json",
    "swagger.json",
    "openapi.json",
    "openapi.yaml",
]


class FetchError(Exception):
    """Raised when a spec cannot be fetched from any source."""


def _github_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _raw_url(repo: str, filename: str) -> str:
    return GITHUB_RAW_BASE.format(org=GITHUB_ORG, repo=repo, filename=filename)


def _list_repo_files(repo: str, client: httpx.Client) -> list[str]:
    """Return filenames at the root of the repo via GitHub Contents API."""
    url = GITHUB_API_BASE.format(org=GITHUB_ORG, repo=repo)
    resp = client.get(url, headers=_github_headers(), timeout=15)
    if resp.status_code != 200:
        return []
    return [item["name"] for item in resp.json() if item["type"] == "file"]


def _infer_filename(repo_files: list[str]) -> Optional[str]:
    """Pick the best OpenAPI spec file from a list of repo filenames."""
    # Prefer swagger.json, then openapi.json, then yaml
    for priority in (".swagger.json", ".oas.json", "openapi.json", "openapi.yaml", "swagger.json"):
        for name in repo_files:
            if name.lower().endswith(priority.lower()):
                return name
    # Fallback: any JSON/YAML file that looks like a spec
    for name in repo_files:
        if re.search(r"\.(json|yaml|yml)$", name, re.IGNORECASE):
            return name
    return None


def fetch_spec(
    api_entry: dict,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
    client: Optional[httpx.Client] = None,
    delay: float = 0.25,
) -> dict:
    """
    Return the parsed OpenAPI spec dict for one API.

    Parameters
    ----------
    api_entry  : one entry from API_REGISTRY
    cache_dir  : where to store downloaded specs
    refresh    : bypass cache and re-download
    client     : optional shared httpx.Client (created internally if None)
    delay      : seconds to sleep after a network request (rate-limit courtesy)

    Returns
    -------
    Parsed spec as a Python dict (always JSON; YAML specs are converted).
    """
    api_id = api_entry["id"]
    repo   = api_entry["repo"]
    cache_path = cache_dir / f"{api_id}.json"

    # ── Cache hit ────────────────────────────────────────────────────────────
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    cache_dir.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    if own_client:
        client = httpx.Client()

    try:
        spec = _fetch_from_github(api_id, repo, client, delay)
    finally:
        if own_client:
            client.close()

    cache_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec


def _fetch_from_github(
    api_id: str,
    repo: str,
    client: httpx.Client,
    delay: float,
) -> dict:
    """Fetch the spec JSON from GitHub, trying several filename strategies."""

    # Strategy 1: list repo contents and pick the best file
    repo_files = _list_repo_files(repo, client)
    time.sleep(delay)

    if repo_files:
        filename = _infer_filename(repo_files)
        if filename:
            url = _raw_url(repo, filename)
            resp = client.get(url, headers=_github_headers(), timeout=30, follow_redirects=True)
            time.sleep(delay)
            if resp.status_code == 200:
                return _parse_response(resp, api_id, url)

    # Strategy 2: try a short list of well-known filenames directly
    for candidate in [
        f"{api_id}.swagger.json",
        "swagger.json",
        "openapi.json",
    ]:
        url = _raw_url(repo, candidate)
        resp = client.get(url, headers=_github_headers(), timeout=30, follow_redirects=True)
        time.sleep(delay)
        if resp.status_code == 200:
            return _parse_response(resp, api_id, url)

    raise FetchError(
        f"Could not download spec for {api_id} from repo {repo}. "
        f"Tried GitHub Contents API and common filename patterns. "
        f"Set GITHUB_TOKEN env var if you are hitting rate limits."
    )


def _parse_response(resp: httpx.Response, api_id: str, url: str) -> dict:
    """Parse an HTTP response as JSON (or YAML if needed)."""
    content_type = resp.headers.get("content-type", "")
    text = resp.text

    if "yaml" in content_type or url.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                return data
        except Exception as exc:
            raise FetchError(f"YAML parse error for {api_id}: {exc}") from exc

    try:
        data = resp.json()
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Last resort: try yaml anyway (some files served as JSON are actually YAML)
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    raise FetchError(f"Could not parse spec response for {api_id} from {url}")


def fetch_all(
    apis: Optional[list[str]] = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
    delay: float = 0.25,
) -> dict[str, dict]:
    """
    Fetch specs for all (or a subset of) APIs.

    Parameters
    ----------
    apis      : list of API IDs to fetch, e.g. ["TMF638", "TMF641"].
                Defaults to all entries in API_REGISTRY.
    cache_dir : local cache directory
    refresh   : bypass cache
    delay     : per-request sleep (seconds) — be polite to GitHub

    Returns
    -------
    dict mapping api_id → spec dict
    """
    targets = [a for a in API_REGISTRY if (apis is None or a["id"] in apis)]
    results: dict[str, dict] = {}
    errors:  dict[str, str]  = {}

    with httpx.Client() as client:
        for entry in targets:
            api_id = entry["id"]
            try:
                results[api_id] = fetch_spec(
                    entry, cache_dir=cache_dir, refresh=refresh,
                    client=client, delay=delay,
                )
            except FetchError as exc:
                errors[api_id] = str(exc)

    if errors:
        # Surface as a warning rather than hard failure so partial results
        # are still usable.
        import warnings
        for api_id, msg in errors.items():
            warnings.warn(f"[tmf-spec-parser] fetch failed for {api_id}: {msg}", stacklevel=2)

    return results
