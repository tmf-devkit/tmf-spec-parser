"""
fetcher.py — Download TMForum OpenAPI specs from GitHub with local caching.

Strategy:
  1. Check local cache directory first.
  2. If missing or --refresh flag set, fetch from GitHub.
  3. Try the GitHub Contents API first (lists actual filenames).
     Fall back to probing known filename patterns directly.
  4. If the spec is not at the repo root, search one level of subdirectories.
  5. Optionally use a GitHub personal access token (env: GITHUB_TOKEN) to
     avoid the 60 req/hr anonymous rate limit.
"""

from __future__ import annotations

import json
import os
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

# Raw content URL — note {path} not {filename} to support subdirs
_RAW_BASE = "https://raw.githubusercontent.com/{org}/{repo}/master/{path}"


class FetchError(Exception):
    """Raised when a spec cannot be fetched from any source."""


def _github_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _raw_url(repo: str, path: str) -> str:
    """Build a raw.githubusercontent.com URL. path may include subdirectory."""
    return _RAW_BASE.format(org=GITHUB_ORG, repo=repo, path=path)


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


def _score_filename(name: str) -> int:
    """Higher score = more likely to be the primary OpenAPI spec."""
    nl = name.lower()
    if any(x in nl for x in ("ctk", "test", "callback", "notification", "hub", "listener")):
        return 0
    if nl.endswith(".swagger.json"):
        return 10
    if nl.endswith(".oas.json") or nl.endswith("openapi.json"):
        return 8
    if nl.endswith(".json"):
        return 5
    if nl.endswith((".yaml", ".yml")):
        return 4
    return 0


def _best_spec_file(entries: list[dict]) -> str | None:
    """Pick the best OpenAPI spec filename from a directory listing."""
    candidates: list[tuple[int, str]] = []
    for entry in entries:
        if entry.get("type") != "file":
            continue
        score = _score_filename(entry["name"])
        if score:
            rel = entry.get("path", entry["name"])
            candidates.append((score, rel))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _fetch_raw(url: str, client: httpx.Client) -> httpx.Response | None:
    """GET a raw URL; return response only on 200."""
    resp = client.get(url, headers=_github_headers(), timeout=30, follow_redirects=True)
    return resp if resp.status_code == 200 else None


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
    1. List repo root via Contents API, pick best spec file.
    2. Scan one level of subdirectories if root has nothing suitable.
    3. Fall back to probing well-known filenames on raw URLs.
    """

    # Strategy 1: root directory listing
    root_entries = _list_dir(_contents_url(repo), client)
    time.sleep(delay)

    if root_entries:
        rel_path = _best_spec_file(root_entries)
        if rel_path:
            url = _raw_url(repo, rel_path)
            resp = _fetch_raw(url, client)
            time.sleep(delay)
            if resp:
                try:
                    spec = _parse_spec(resp, api_id, url)
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
                url = _raw_url(repo, rel_path)
                resp = _fetch_raw(url, client)
                time.sleep(delay)
                if resp:
                    try:
                        spec = _parse_spec(resp, api_id, url)
                        if _is_real_spec(spec):
                            return spec
                    except FetchError:
                        pass

    # Strategy 3: direct raw URL probes (for when Contents API rate-limits)
    for filename in ["swagger.json", f"{api_id}.swagger.json", "openapi.json"]:
        url = _raw_url(repo, filename)
        resp = _fetch_raw(url, client)
        time.sleep(delay)
        if resp:
            try:
                spec = _parse_spec(resp, api_id, url)
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
