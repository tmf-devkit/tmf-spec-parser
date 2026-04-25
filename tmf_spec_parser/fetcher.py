"""
fetcher.py — Download TMForum OpenAPI specs from GitHub with local caching.

Strategy:
  1. Check local cache directory first.
  2. If missing or --refresh flag set, fetch from GitHub.
  3. Try the GitHub Contents API first (lists actual filenames, uses default branch).
     Fall back to probing known filename patterns directly.
  4. If the spec is not at the repo root, search one level of subdirectories.
  5. For raw URL access, try `main` branch first (newer repos), fall back to `master`.
  6. Optionally use a GitHub personal access token (env: GITHUB_TOKEN) to
     avoid the 60 req/hr anonymous rate limit.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx

from tmf_spec_parser.config import (
    API_REGISTRY,
    GITHUB_API_BASE,
    GITHUB_ORG,
)

# Default cache directory: ~/.tmf-spec-parser/cache/
DEFAULT_CACHE_DIR = Path.home() / ".tmf-spec-parser" / "cache"

# Spec file extensions we'll accept
SPEC_EXTENSIONS = (".swagger.json", ".oas.json", ".json", ".yaml", ".yml")

# Raw content URL template — {branch} tried in order: main, master
_RAW_BASE = "https://raw.githubusercontent.com/{org}/{repo}/{branch}/{path}"

# Branches to try for raw URL access, in order. 'main' first because most
# modern TMForum repos have switched to it (TMF653, and increasingly others).
_BRANCHES_TO_TRY = ("main", "master")

# Filename markers that indicate a non-primary spec file we should skip.
# NOTE: 'test' is intentionally NOT here — it would block legitimate spec files
# for APIs whose name contains "Test" (e.g., TMF653 Service Test Management).
# 'ctk' captures Conformance Test Kit files (the real test artifacts).
_FILENAME_BLOCKLIST = (
    "ctk",          # Conformance Test Kit
    "callback",     # Callback/listener variant
    "notification", # Notification/event variant
    "hub",          # Hub registration variant
    "listener",     # Listener registration variant
    ".admin.",      # Admin spec variant (e.g., Service_Test_Management.admin.swagger.json)
)

# Pattern to extract a version tuple like (4, 2, 0) from filenames such as
# TMF653-ServiceTest-v4.1.0.swagger.json or TMF653_..._API_v4.2.0_swagger.json
_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)

# Pattern that matches the canonical TMForum filename prefix (TMFxxx-...)
# and confirms a "primary" file as opposed to admin/regular variants.
_TMF_PREFIX_RE = re.compile(r"^tmf\d+[-_]", re.IGNORECASE)


class FetchError(Exception):
    """Raised when a spec cannot be fetched from any source."""


def _github_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _raw_urls(repo: str, path: str) -> list[str]:
    """Build raw.githubusercontent.com URLs for each branch we try."""
    return [
        _RAW_BASE.format(org=GITHUB_ORG, repo=repo, branch=br, path=path)
        for br in _BRANCHES_TO_TRY
    ]


def _contents_url(repo: str, subdir: str = "") -> str:
    """GitHub Contents API URL, optionally for a subdirectory."""
    base = GITHUB_API_BASE.format(org=GITHUB_ORG, repo=repo)
    return base + subdir if subdir else base


def _list_dir(url: str, client: httpx.Client) -> list[dict]:
    """Call GitHub Contents API, return list of file/dir entries."""
    resp = client.get(url, headers=_github_headers(), timeout=15)
    if resp.status_code != 200:
        return []
    data = resp.json()
    return data if isinstance(data, list) else []


def _extract_version(name: str) -> tuple[int, int, int]:
    """Extract a (major, minor, patch) version tuple from a filename. (0,0,0) if none."""
    m = _VERSION_RE.search(name)
    if not m:
        return (0, 0, 0)
    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3)) if m.group(3) else 0
    return (major, minor, patch)


def _score_filename(name: str) -> int:
    """
    Higher score = more likely to be the primary OpenAPI spec.
    Returns 0 for files we don't want.
    """
    nl = name.lower()

    # Reject files with blocklisted markers (CTK, callback, admin variant, etc.)
    if any(x in nl for x in _FILENAME_BLOCKLIST):
        return 0

    # Score by extension
    if nl.endswith(".swagger.json") or nl.endswith("_swagger.json"):
        base_score = 10
    elif nl.endswith(".oas.json") or nl.endswith("openapi.json"):
        base_score = 8
    elif nl.endswith(".json"):
        base_score = 5
    elif nl.endswith((".yaml", ".yml")):
        base_score = 4
    else:
        return 0

    # Boost files with the canonical TMFxxx- prefix (the official primary spec
    # naming convention). Distinguishes TMF653-ServiceTest-v4.0.0.swagger.json
    # from Service_Test_Management.admin.swagger.json.
    if _TMF_PREFIX_RE.match(name):
        base_score += 5

    return base_score


def _best_spec_file(entries: list[dict]) -> str | None:
    """Pick the best OpenAPI spec filename from a directory listing.

    Among files with the highest score, prefer the highest version number
    (so v4.2.0 wins over v4.0.0 wins over v3.0.0).
    """
    candidates: list[tuple[int, tuple[int, int, int], str]] = []
    for entry in entries:
        if entry.get("type") != "file":
            continue
        name = entry["name"]
        score = _score_filename(name)
        if score:
            rel = entry.get("path", name)
            version = _extract_version(name)
            candidates.append((score, version, rel))
    if not candidates:
        return None
    # Sort by (score, version) descending; highest wins.
    candidates.sort(reverse=True)
    return candidates[0][2]


def _fetch_raw(url: str, client: httpx.Client) -> httpx.Response | None:
    """GET a raw URL; return response only on 200."""
    resp = client.get(url, headers=_github_headers(), timeout=30, follow_redirects=True)
    return resp if resp.status_code == 200 else None


def _fetch_raw_any_branch(
    repo: str, path: str, client: httpx.Client, delay: float
) -> httpx.Response | None:
    """Try each branch in _BRANCHES_TO_TRY until one returns 200."""
    for url in _raw_urls(repo, path):
        resp = _fetch_raw(url, client)
        time.sleep(delay)
        if resp:
            return resp
    return None


def _parse_spec(resp: httpx.Response, api_id: str, url: str) -> dict:
    """Parse a 200 response as JSON or YAML into a dict."""
    content_type = resp.headers.get("content-type", "")
    text = resp.text

    if "yaml" in content_type or url.lower().endswith((".yaml", ".yml")):
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

    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    raise FetchError(f"Could not parse spec response for {api_id} from {url}")


def _is_real_spec(spec: dict) -> bool:
    """Basic sanity check — does this look like a real OpenAPI/Swagger spec?"""
    has_schemas = (
        bool(spec.get("components", {}).get("schemas"))
        or bool(spec.get("definitions"))
    )
    has_info = bool(spec.get("info", {}).get("version"))
    has_oas = any(k in spec for k in ("swagger", "openapi", "paths"))
    return has_schemas and (has_info or has_oas)


def _fetch_from_github(
    api_id: str,
    repo: str,
    client: httpx.Client,
    delay: float,
) -> dict:
    """
    Multi-strategy fetch:
    1. List repo root via Contents API (uses default branch), pick best spec file.
    2. Scan one level of subdirectories if root has nothing suitable.
    3. Fall back to probing well-known filenames on raw URLs.

    For raw URL fetches, we try both `main` and `master` since the TMForum org
    has a mix (older repos on master, newer ones like TMF653 on main).
    """

    # Strategy 1: root directory listing
    root_entries = _list_dir(_contents_url(repo), client)
    time.sleep(delay)

    if root_entries:
        rel_path = _best_spec_file(root_entries)
        if rel_path:
            resp = _fetch_raw_any_branch(repo, rel_path, client, delay)
            if resp:
                try:
                    spec = _parse_spec(resp, api_id, str(resp.url))
                    if _is_real_spec(spec):
                        return spec
                except FetchError:
                    pass

        # Strategy 2: scan subdirectories one level deep
        subdirs = [e for e in root_entries if e.get("type") == "dir"]
        for subdir_entry in subdirs[:5]:
            subdir_name = subdir_entry["name"]
            sub_entries = _list_dir(_contents_url(repo, subdir_name), client)
            time.sleep(delay)
            if not sub_entries:
                continue
            rel_path = _best_spec_file(sub_entries)
            if rel_path:
                resp = _fetch_raw_any_branch(repo, rel_path, client, delay)
                if resp:
                    try:
                        spec = _parse_spec(resp, api_id, str(resp.url))
                        if _is_real_spec(spec):
                            return spec
                    except FetchError:
                        pass

    # Strategy 3: direct raw URL probes (for when Contents API rate-limits)
    for filename in ["swagger.json", f"{api_id}.swagger.json", "openapi.json"]:
        resp = _fetch_raw_any_branch(repo, filename, client, delay)
        if resp:
            try:
                spec = _parse_spec(resp, api_id, str(resp.url))
                if _is_real_spec(spec):
                    return spec
            except FetchError:
                pass

    raise FetchError(
        f"Could not download a valid spec for {api_id} from repo '{repo}'. "
        "Set the GITHUB_TOKEN environment variable to avoid rate limits."
    )


def fetch_spec(
    api_entry: dict,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
    client: httpx.Client | None = None,
    delay: float = 0.3,
) -> dict:
    """Return the parsed OpenAPI spec dict for one API."""
    api_id = api_entry["id"]
    repo   = api_entry["repo"]
    cache_path = cache_dir / f"{api_id}.json"

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


def fetch_all(
    apis: list[str] | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
    delay: float = 0.3,
) -> dict[str, dict]:
    """Fetch specs for all (or a subset of) APIs."""
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
        import warnings
        for api_id, msg in errors.items():
            warnings.warn(
                f"[tmf-spec-parser] fetch failed for {api_id}: {msg}",
                stacklevel=2,
            )

    return results
