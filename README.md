# tmf-spec-parser

**Extract, validate and diff TMForum Open API specs.**

Part of [TMF DevKit](https://github.com/tmf-devkit) — open-source developer tooling for TMForum Open API implementations.

[![CI](https://github.com/tmf-devkit/tmf-spec-parser/actions/workflows/ci.yml/badge.svg)](https://github.com/tmf-devkit/tmf-spec-parser/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tmf-spec-parser)](https://pypi.org/project/tmf-spec-parser/)
[![Python](https://img.shields.io/pypi/pyversions/tmf-spec-parser)](https://pypi.org/project/tmf-spec-parser/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

---

## What it does

`tmf-spec-parser` fetches the official TMForum OpenAPI specs directly from
[github.com/tmforum-apis](https://github.com/tmforum-apis) and extracts
structured metadata:

| Extracted automatically | Curated (stays in `config.py`) |
|---|---|
| Entity names, mandatory fields, optional fields | Lifecycle state **transitions** (from CTK) |
| Lifecycle state values (enum) | Terminal states |
| Cross-API `$ref` relationships | Integration patterns |
| Spec version and description | Domain classification |

The output is `tmf_data.json` — a single structured file consumed by
**[tmf-map](https://github.com/tmf-devkit/tmf-map)** (the interactive API
relationship graph) and importable by **tmf-mock** and **tmf-lint** for
schema-aware conformance checking.

### Why transitions stay curated

The TMForum OpenAPI specs list valid _state values_ (as enums) but do not
encode _which transitions are permitted_. That information lives in the
Conformance Test Kit (CTK) documents and the API user guides. `tmf-spec-parser`
detects when new states appear in a spec and flags them so you can update the
transition table accordingly.

---

## Installation

```bash
pip install tmf-spec-parser
```

With YAML spec support (some older TMForum repos use YAML):

```bash
pip install "tmf-spec-parser[yaml]"
```

Docker:

```bash
docker pull mchavan23/tmf-spec-parser
```

---

## Quick start

```bash
# Generate tmf_data.json for all 16 supported APIs
tmf-spec-parser generate

# Also emit a JavaScript ES module (for direct import in React/Vite)
tmf-spec-parser generate --js

# Write output to tmf-map's public directory
tmf-spec-parser generate --out ../tmf-map/src/tmf_data.json --js

# Only process specific APIs
tmf-spec-parser generate --apis TMF638,TMF639,TMF641

# Bypass cache and re-download from GitHub
tmf-spec-parser generate --refresh
```

---

## Commands

### `generate`

Fetches specs, extracts metadata, merges curated transitions, and writes
`tmf_data.json`.

```
tmf-spec-parser generate [OPTIONS]

Options:
  -a, --apis TEXT       Comma-separated API IDs (default: all 16)
  -o, --out TEXT        Output path  [default: tmf_data.json]
  --js                  Also emit tmf_data.js ES module
  --ts                  Also emit tmf_data.ts TypeScript module
  -r, --refresh         Bypass cache, re-download from GitHub
  --cache-dir TEXT      Cache directory  [default: ~/.tmf-spec-parser/cache]
  --no-diff             Skip diff check against existing output
  --diff-out TEXT       Path for Markdown diff report  [default: SPEC_CHANGES.md]
```

On first run, specs are downloaded from GitHub and cached locally. Subsequent
runs use the cache unless `--refresh` is passed. Set `GITHUB_TOKEN` in your
environment to avoid the 60 req/hr anonymous rate limit:

```bash
export GITHUB_TOKEN=ghp_yourtoken
tmf-spec-parser generate --refresh
```

### `diff`

Compare an existing `tmf_data.json` against the current TMForum specs without
writing a new output file.

```bash
tmf-spec-parser diff --existing ./tmf_data.json
tmf-spec-parser diff --existing ./tmf_data.json --out SPEC_CHANGES.md
```

Findings are classified as:

| Severity | Category | Meaning |
|---|---|---|
| `ERROR` | `MANDATORY_FIELD_REMOVED` | A required field disappeared — breaks all consumers |
| `ERROR` | `MANDATORY_FIELD_ADDED` | A new required field — existing implementations won't supply it |
| `ERROR` | `LIFECYCLE_STATE_REMOVED` | A state was removed — breaks state machine consumers |
| `ERROR` | `ENTITY_REMOVED` | An entity disappeared from the spec |
| `WARNING` | `OPTIONAL_FIELD_REMOVED` | Consumers may depend on this |
| `WARNING` | `LIFECYCLE_STATE_ADDED` | Update `TRANSITIONS` in `config.py` |
| `INFO` | `VERSION_CHANGED` | Spec version bumped |
| `INFO` | `OPTIONAL_FIELD_ADDED` | Additive — no action required |

Exit code `1` if any `ERROR`-severity findings exist (useful in CI pipelines).

### `validate`

Sanity-check a `tmf_data.json` file: required keys present, link targets valid,
transition states exist in lifecycle.

```bash
tmf-spec-parser validate ./tmf_data.json
```

### `show`

Pretty-print extracted metadata for one API (reads from cache).

```bash
tmf-spec-parser show TMF641
tmf-spec-parser show TMF638
```

### `cache`

```bash
tmf-spec-parser cache list    # show cached spec files
tmf-spec-parser cache clear   # delete cache
```

---

## Output format

`tmf_data.json` structure:

```jsonc
{
  "generated_at":   "2026-04-17T10:23:00Z",
  "parser_version": "0.1.0",
  "apis": [
    { "id": "TMF641", "name": "Service Ordering", "domain": "service",
      "short": "Service Ordering", "repo": "TMF641_ServiceOrdering" }
  ],
  "links": [
    { "source": "TMF641", "target": "TMF638", "label": "creates Service" }
  ],
  "patterns": [
    { "id": "o2a", "name": "Order-to-Activate",
      "nodes": ["TMF629","TMF622","TMF641","TMF638","TMF639"], ... }
  ],
  "details": {
    "TMF641": {
      "specRef":     "TMF641 v4.1.0",
      "description": "Manages end-to-end service order lifecycle...",
      "entities": [
        {
          "name":      "ServiceOrder",
          "mandatory": ["id", "state", "orderDate"],
          "optional":  ["requestedStartDate", "priority", ...]
        }
      ],
      "lifecycle":   ["acknowledged", "inProgress", "pending", "held",
                      "completed", "failed", "cancelled"],
      "terminal":    ["completed", "failed", "cancelled"],
      "transitions": [
        { "from": "acknowledged", "to": "inProgress" },
        ...
      ]
    }
  }
}
```

---

## Using the output in tmf-map

After generating, copy `tmf_data.json` (or `tmf_data.js`) to your tmf-map
project and update the import:

```jsx
// src/App.jsx — replace hardcoded constants with:
import TMF_DATA from './tmf_data.json';

const APIS    = TMF_DATA.apis;
const LINKS   = TMF_DATA.links;
const PATTERNS = TMF_DATA.patterns;
const API_DETAILS = TMF_DATA.details;
```

Vite supports JSON imports natively. No configuration required.

---

## Using the output in tmf-mock / tmf-lint

```python
import json
from pathlib import Path

data = json.loads(Path("tmf_data.json").read_text())

# Get mandatory fields for TMF641 ServiceOrder
detail    = data["details"]["TMF641"]
mandatory = detail["entities"][0]["mandatory"]
# → ["id", "state", "orderDate"]

# Get valid lifecycle states
states = detail["lifecycle"]
# → ["acknowledged", "inProgress", ...]
```

---

## Supported APIs (v0.1)

| ID | Name | Domain |
|---|---|---|
| TMF629 | Customer Management | Customer |
| TMF632 | Party Management | Customer |
| TMF620 | Product Catalog | Product |
| TMF622 | Product Ordering | Product |
| TMF637 | Product Inventory | Product |
| TMF633 | Service Catalog | Service |
| TMF638 | Service Inventory | Service |
| TMF641 | Service Ordering | Service |
| TMF645 | Service Qualification | Service |
| TMF634 | Resource Catalog | Resource |
| TMF639 | Resource Inventory | Resource |
| TMF652 | Resource Ordering | Resource |
| TMF653 | Service Test | Resource |
| TMF621 | Trouble Ticket | Engagement |
| TMF656 | Service Problem | Engagement |
| TMF688 | Event Management | Common |

---

## Docker

```bash
# Generate tmf_data.json in current directory
docker run --rm \
  -v "$(pwd)":/output \
  -v "$(pwd)/cache":/root/.tmf-spec-parser/cache \
  -e GITHUB_TOKEN=$GITHUB_TOKEN \
  mchavan23/tmf-spec-parser \
  generate --out /output/tmf_data.json --js

# Diff against existing file
docker run --rm \
  -v "$(pwd)":/output \
  mchavan23/tmf-spec-parser \
  diff --existing /output/tmf_data.json --out /output/SPEC_CHANGES.md
```

---

## CI integration

Add to your GitHub Actions workflow to keep `tmf_data.json` current:

```yaml
- name: Refresh TMF spec data
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    pip install tmf-spec-parser
    tmf-spec-parser generate --out src/tmf_data.json --js
```

`tmf-spec-parser diff` returns exit code `1` on breaking changes, making it
suitable as a gate in deployment pipelines.

---

## Development

```bash
git clone https://github.com/tmf-devkit/tmf-spec-parser
cd tmf-spec-parser
pip install -e ".[dev]"
pytest
ruff check tmf_spec_parser tests
```

Tests run fully offline using synthetic fixture specs — no GitHub calls required.

---

## TMF DevKit

`tmf-spec-parser` is part of the TMF DevKit suite:

| Module | Description |
|---|---|
| [tmf-mock](https://github.com/tmf-devkit/tmf-mock) | Smart TMF mock server with domain-aware seed data |
| [tmf-lint](https://github.com/tmf-devkit/tmf-lint) | Runtime conformance checker for TMF API implementations |
| [tmf-map](https://github.com/tmf-devkit/tmf-map) | Interactive API relationship graph (consumes tmf_data.json) |
| **tmf-spec-parser** | Spec extraction and drift detection (this module) |

---

## License

Apache 2.0 — © 2026 Manoj Chavan
