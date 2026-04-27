# ADR-001: ODAC Component Source and Schema

**Status:** Accepted
**Date:** 2026-04-27
**Context:** v0.3.0 — adding ODA Component view to tmf-spec-parser
**Supersedes:** none

---

## Context

A LinkedIn commenter (Business Analyst / Solution Architect, TMForum-savvy)
critiqued tmf-map for showing API-schema-`$ref` relationships as if they were
ODA architectural dependencies. They are not. ODA Components (ODACs) are the
unit of architectural dependency; their per-component manifests declare
exposed and dependent APIs explicitly.

To address this, tmf-spec-parser needs a new pipeline that fetches ODAC
manifests, extracts the `coreFunction.exposedAPIs` and
`coreFunction.dependentAPIs` lists, and emits a JSON file that tmf-map can
render as a second graph view.

This ADR records the decisions about **where** the manifests live, **which
fields** to extract, and **how** to handle the multiple CRD versions that
exist in the wild.

---

## Sources investigated

Three candidate sources were evaluated:

| # | Source | Discovery | Outcome |
|---|---|---|---|
| 1 | `https://github.com/tmforum-rand/TMForum-ODA-Ready-for-publication` | Stated by the official TMForum design guide as "the definitive repo for delivered Components". 37 component folders at tag `v1.0.0`, each named `TMFC{nnn}-{Name}`. | **Primary source** |
| 2 | `https://oda-production.s3.eu-west-2.amazonaws.com/{crd_version}/TMFC{nnn}-{Name}.yaml` | Public S3 bucket, cleanly partitioned by CRD version (`v1beta2/`, `v1beta3/`, `v1.0.0/`). Each YAML directly fetchable. | **Fallback / corroboration** |
| 3 | `https://www.tmforum.org/oda/directory/components-map/...` (HTML) | The rendered "official" view; useful for human verification only. | Reference only |

The S3 bucket would be the simplest source if listing were trivial, but it
has no advertised index. The GitHub repo has a Contents API that lists files
deterministically (the same pattern `tmf-spec-parser` already uses for
`tmforum-apis`), and a stable tag (`v1.0.0`) we can pin against.

**Decision:** GitHub repo as primary, S3 as fallback. Both URL patterns are
well-known and we can probe them in order.

---

## CRD version landscape

Three CRD versions are present in published manifests today:

### `oda.tmforum.org/v1beta2`
- Component metadata fields are **flat** under `spec` (`spec.id`, `spec.name`, `spec.version`, `spec.functionalBlock`, `spec.description`, `spec.publicationDate`, `spec.status`)
- API type field: `apitype` (lowercase)
- `specification` value: a single URL string
- `version` lives directly on each API entry
- `kind: component` (lowercase)
- Events under `coreFunction.publishedEvents` / `subscribedEvents`

### `oda.tmforum.org/v1beta3`
- Same flat metadata structure as v1beta2
- API type field: `apiType` (camelCase)
- `specification` still a single URL string
- `version` still on each API entry
- Events promoted to `eventNotification.publishedEvents` / `subscribedEvents`

### `oda.tmforum.org/v1` (current/v1beta4 ratified)
- Component metadata moved to `spec.componentMetadata.{...}` wrapper
- `specification` is an **array** of `{url, version}` objects
- `version` lives **inside** `specification[0].version`
- `apiType` and new `apiSDO` field
- `kind: Component` (TitleCase)
- `controllerRole` (security) renamed to `canvasSystemRole`
- `componentMetadata` adds `eTOMs`, `functionalFrameworkFunctions`, `SIDs`

**Decision:** The extractor reads all three shapes via a normalisation layer
that emits a uniform internal form. Detection is by `apiVersion` field at
the top level of the manifest.

---

## Fields extracted

For v0.3.0, the data emitted to `oda_data.json` is intentionally narrow:

### Per component (from `spec` or `spec.componentMetadata`)
| Field | Source | Type | Notes |
|---|---|---|---|
| `id` | `spec.id` or `spec.componentMetadata.id` | string | e.g. `TMFC008` |
| `name` | `spec.name` or `spec.componentMetadata.name` | string | e.g. `ServiceInventory` |
| `version` | `spec.version` or `spec.componentMetadata.version` | string | e.g. `1.2.0` |
| `functional_block` | `spec.functionalBlock` or `spec.componentMetadata.functionalBlock` | string | e.g. `CoreCommerce`, `IntelligenceManagement` |
| `description` | `spec.description` or `spec.componentMetadata.description` | string | Cleaned of trailing whitespace |
| `status` | `spec.status` or `spec.componentMetadata.status` | string | `specified`, `in-use`, etc. |
| `publication_date` | `spec.publicationDate` or `spec.componentMetadata.publicationDate` | string (ISO date) | |
| `crd_version` | `apiVersion` | string | `v1beta2`, `v1beta3`, `v1` |

### Per API entry (from `spec.coreFunction.exposedAPIs[]` and `spec.coreFunction.dependentAPIs[]`)
| Field | Source | Type | Notes |
|---|---|---|---|
| `id` | `id` | string | e.g. `TMF638` |
| `name` | `name` | string | e.g. `service-inventory-management-api` |
| `version` | `version` (v1beta2/3) or `specification[0].version` (v1) | string | e.g. `v4.0.0` |
| `required` | `required` | bool | `true` = mandatory; `false` = optional. **Kept** to enable required/optional styling in the renderer. |

**Out of scope for v0.3.0:**
- `securityFunction.exposedAPIs` / `dependentAPIs` (mostly TMF669 boilerplate)
- `managementFunction.exposedAPIs` / `dependentAPIs` (mostly Prometheus metrics)
- `eventNotification.publishedEvents` / `subscribedEvents`
- Per-API `resources[]` (HTTP methods)
- `eTOMs`, `functionalFrameworkFunctions`, `SIDs`
- `owners`, `maintainers`

The TMForum directory's headline view (`Mandatory` / `Optional` for both
exposed and dependent) ignores security/management function APIs in its
graph, and our scope mirrors that convention.

---

## Output schema

```json
{
  "generated_at": "2026-04-27T...Z",
  "parser_version": "0.3.0",
  "spec_source": "github.com/tmforum-rand/TMForum-ODA-Ready-for-publication@v1.0.0",
  "components": [
    {
      "id": "TMFC008",
      "name": "ServiceInventory",
      "version": "1.2.0",
      "functional_block": "Production",
      "status": "specified",
      "publication_date": "2024-11-12",
      "description": "Service Inventory component is responsible for...",
      "crd_version": "v1",
      "exposed_apis": [
        {"id": "TMF638", "name": "...", "version": "v4.0.0", "required": true},
        {"id": "TMF701", "name": "...", "version": "v4.1.0", "required": false}
      ],
      "dependent_apis": [
        {"id": "TMF633", "name": "...", "version": "v4.0.0", "required": true},
        {"id": "TMF641", "name": "...", "version": "v4.0.0", "required": false},
        {"id": "TMF669", "name": "...", "version": "v4.0.0", "required": false}
      ]
    }
  ],
  "links": [
    {"source": "TMFC008", "target_api": "TMF633", "kind": "depends_on", "required": true},
    {"source": "TMFC008", "target_api": "TMF641", "kind": "depends_on", "required": false}
  ],
  "stats": {
    "components": 37,
    "exposed_api_count": 78,
    "dependent_api_count": 224,
    "unique_apis_referenced": 53,
    "apis_outside_tmf_map_set": 37
  }
}
```

### Link model

A `link` represents one component-to-API relationship. The component is the
node; the API is the edge target. Components don't reference each other
directly in the YAML — they reference APIs that other components expose. The
component-to-component dependency graph is **derivable** at render time by
joining `links[].target_api` to `components[].exposed_apis[].id`.

This keeps the data file faithful to the YAML and pushes graph-construction
logic into the renderer where it belongs.

---

## Handling APIs outside the tmf-map 16-API set

ODAC manifests reference many APIs that aren't in tmf-map's current 16
(TMF620, 621, 622, 629, 632, 633, 634, 637, 638, 639, 641, 645, 652, 653,
656, 688). For example, TMFC001 references TMF651, TMF662, TMF669, TMF671,
TMF672, TMF673, TMF674, TMF675, TMF701.

**Decision:** Emit them all in `oda_data.json`. The renderer decides how to
display them (as ghost nodes, dim labels, or hide-by-default). Don't filter
in the parser — that's data loss baked into the format.

A `stats.apis_outside_tmf_map_set` count is emitted for visibility.

---

## CLI surface

New subcommand on the existing `tmf-spec-parser` CLI:

```
tmf-spec-parser oda --out PATH [--js] [--refresh] [--components LIST]
```

- `--out`: target JSON path (defaults to `oda_data.json`)
- `--js`: also emit `.js` ES-module sibling
- `--refresh`: bypass local cache
- `--components`: comma-separated subset of component IDs (e.g. `TMFC008,TMFC037`)

Defaults align with the existing `generate` command. The new command does
not affect existing behaviour — `generate` continues to produce
`tmf_data.json` exactly as before. Backwards compatible.

PyYAML is imported lazily inside the `oda` subcommand so users on
`pip install tmf-spec-parser` (without the `[yaml]` extra) get a clear
error message rather than an `ImportError` at module load.

---

## Decisions recap

1. **Source:** `tmforum-rand/TMForum-ODA-Ready-for-publication` GitHub repo, pinned to tag `v1.0.0`. S3 fallback.
2. **CRD versions:** Support `v1beta2`, `v1beta3`, `v1` via a normalisation layer keyed off the `apiVersion` field.
3. **Scope:** `coreFunction.exposedAPIs` and `coreFunction.dependentAPIs` only. Defer security/management/events/resources to a future ADR.
4. **`required` flag:** Kept in the output to enable mandatory/optional edge styling.
5. **Out-of-set APIs:** Emit unfiltered. Renderer decides display.
6. **Output:** New `oda_data.json` (and optional `oda_data.js`) sibling to existing `tmf_data.json`. Format mirrors that file's structure.
7. **CLI:** New `oda` subcommand. Existing `generate` untouched.
8. **Version bump:** v0.3.0 (new public surface, no breaking changes).

---

## Open questions deferred

- **Multi-CRD-version coexistence:** When TMFC008 has both `v1beta2` and `v1.0.0` manifests on S3, which do we trust? For now: pick the highest CRD version available on a per-component basis. May need revisiting.
- **Security function inclusion:** Several components only declare TMF669 (PartyRole) under `securityFunction` rather than `coreFunction`. If we drop these we may misrepresent some components. Re-evaluate after the v0.3.0 prototype reveals how often it matters.
- **Functional block taxonomy:** Roughly 8 distinct values seen so far (`CoreCommerce`, `Production`, `IntelligenceManagement`, `PartyManagement`, etc.). Will need a colour map, possibly aligned with but distinct from the API domain colour map.
- **Render mode:** Toggle in tmf-map vs separate `tmf-oda-map` site. Decided: toggle (one URL for the portfolio narrative). Implementation deferred to next session.
