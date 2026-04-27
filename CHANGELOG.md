# Changelog

All notable changes to tmf-spec-parser are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.3.0] — 2026-04-27

### Added
- **`oda` subcommand** — fetches ODA Component (ODAC) manifests from the
  TM Forum components staging repo (`tmforum-rand/TMForum-ODA-Ready-for-publication`,
  pinned to tag `v1.0.0`, 37 components) and emits `oda_data.json`. Optional
  `--js` flag also writes an ES module sibling. This is the data layer for the
  upcoming Component view in tmf-map, addressing the LinkedIn feedback that the
  current map is at the API schema-`$ref` layer rather than the architectural
  ODA Component layer.
  ```
  tmf-spec-parser oda --out ../tmf-map/src/oda_data.json --js
  tmf-spec-parser oda --components TMFC008,TMFC037   # subset
  ```
- New modules `tmf_spec_parser.oda_extractor`, `tmf_spec_parser.oda_fetcher`,
  `tmf_spec_parser.oda_emitter`. The extractor handles all three CRD versions
  found in the wild (`v1beta2`, `v1beta3`, `v1`) via a normalisation layer
  keyed off the `apiVersion` field. v1beta4 is folded into `v1` (the v1 GA
  was a rename).
- New config entries: `ODA_GITHUB_ORG`, `ODA_GITHUB_REPO`, `ODA_REPO_REF`,
  `ODA_CRD_VERSIONS`, `ODA_SPEC_SOURCE`. The existing `tmforum-apis` config
  is untouched.
- Architecture decision record `docs/ADR-001-odac-source-and-schema.md`
  documenting the source choice, CRD version handling, output schema, and
  scope decisions.
- Tests: `tests/test_oda_extractor.py` (17 tests covering all three CRD
  shapes, placeholder filtering, missing fields, kind/case insensitivity)
  and `tests/test_oda_emitter.py` (9 tests covering build, write_json,
  write_js_module, parent-directory creation).

### Scope
- v0.3.0 extracts only `coreFunction.exposedAPIs` and
  `coreFunction.dependentAPIs`. `securityFunction`, `managementFunction`,
  `eventNotification`, per-API `resources[]`, eTOMs, SIDs, owners and
  maintainers are deliberately out of scope. See ADR-001 for rationale.
- The `required` flag is preserved on every API entry and link, ready for
  mandatory/optional edge styling in the renderer.
- APIs outside tmf-map's existing 16-API set are emitted unfiltered — the
  renderer will decide how to display them. A `stats.apis_outside_tmf_map_set`
  count surfaces this for visibility.

### Behaviour
- The existing `generate` subcommand and its output (`tmf_data.json`) are
  unchanged. v0.3.0 is fully backwards-compatible — no breaking changes to
  any existing public surface.
- PyYAML is imported lazily inside the `oda` subcommand. Users on a default
  `pip install tmf-spec-parser` (without the `[yaml]` extra) get a friendly
  error message rather than an `ImportError`. Install with
  `pip install 'tmf-spec-parser[yaml]'` or `pip install pyyaml` separately.

## [0.2.6] — 2026-04-26

### Fixed
- **Entity ranking now domain-aware (Bug 3)**: TMF652 Resource Ordering still
  produced a wrong lifecycle (`standby, alarm, available`) after v0.2.5
  because its OpenAPI spec contains both `ResourceOrder` (the API's actual
  primary entity) and `Resource` (a copy of TMF639's primary entity, used
  as the ResourceRefOrValue base). `Resource` has more fields than
  `ResourceOrder`, so the field-count-only ranking pushed `ResourceOrder`
  past the top-4 entity cap. Lifecycle extraction then walked the alien
  `Resource` entity and returned its `resourceStatus` enum.

  `_extract_entities()` now accepts an optional `api_id` parameter and ranks
  entities first by domain-name overlap with the API's registry name
  (TMF652 = 'Resource Ordering' → stems `[resource, order]`, so
  `ResourceOrder` scores 2 and beats `Resource` which scores 1), then by
  field count as a tie-breaker. `extract()` passes the api_id automatically.

  After this fix TMF652 extracts the correct order states
  `(acknowledged, terminatedWithError, inProgress, done)` directly from the
  spec, no baseline merge needed.

### Added
- 2 new tests in `tests/test_extractor_lifecycle_isolation.py` for Bug 3:
  one locks in domain-aware ranking with a synthetic two-entity spec, one
  guards the no-api_id fallback path so callers that don't pass an api_id
  still get the legacy field-count ordering.
- New helpers in `extractor.py`: `_word_stem`, `_api_domain_stems`,
  `_entity_words`, `_domain_overlap_score`. Public API surface gains an
  optional `api_id` keyword on `_extract_entities`; `extract()` and
  `extract_all()` are unchanged.

### Behaviour
- Output schema of `tmf_data.json` is unchanged. APIs that previously
  ranked correctly still rank correctly. Backwards-compatible patch release.

## [0.2.5] — 2026-04-26

### Fixed
- **Lifecycle cross-domain leak (Bug 1)**: APIs that embed cross-API `*Ref`
  schemas (e.g. TMF652 Resource Order embedding `ResourceRef`) used to extract
  the *referenced* API's lifecycle enum as if it were their own. TMF652's
  lifecycle was being extracted as `standby, alarm, available` (TMF639
  Resource Inventory states) instead of order states. The extractor now
  skips schemas listed in `SCHEMA_TO_API` when scanning for the API's own
  lifecycle.
- **Generic-helper status pollution (Bug 2)**: TMF Catalog APIs (TMF620,
  TMF633, TMF634) ship `ImportJob` and `ExportJob` schemas with a generic
  CI-style status enum (`Not Started, Running, Succeeded, Failed`). The
  extractor used to return that as the catalog's lifecycle. Schemas whose
  name ends in `Job`, `Task`, `Operation`, `Process`, `Migration`, `Hub`,
  `Listener`, or `Subscription` are now classified as generic helpers and
  excluded from lifecycle extraction.
- **Standalone enum stem-match guard**: the standalone state-enum fallback
  (Phase 3) now requires the schema-name stem to *exactly* match a primary
  entity name. Previously a `startswith` check let `ResourceStatusType`
  (stem `Resource`) leak into TMF652 (entity `ResourceOrder`); now only
  `ResourceOrderStateType` (stem `ResourceOrder`) is accepted.

### Added
- 7 new tests in `tests/test_extractor_lifecycle_isolation.py` locking in
  correct behaviour for both leak classes and the variant-suffix case
  (`ServiceCreate` should never seed lifecycle for `Service`).
- New helper functions in `extractor.py`: `_is_cross_api_helper`,
  `_is_generic_helper`, `_is_variant_entity`, `_is_helper_for_lifecycle`.
  Public API surface is unchanged.

### Behaviour
- When the spec doesn't structurally encode the API's own lifecycle,
  `extract_lifecycle()` now returns `[]` cleanly instead of returning a
  cross-domain enum. The curated baseline merge in `emitter.py` then fills
  the gap with verified states. Output schema of `tmf_data.json` is
  unchanged — this is a fully backwards-compatible patch release.

## [0.2.4] — 2026-04-25

### Fixed
- **Fetcher filename scoring** — the substring blocklist used to reject test
  artifacts contained `"test"`, which incorrectly rejected every spec file in
  TMF653 Service Test Management (since the API name itself contains "Test").
  Replaced the blocklist with explicit markers (`ctk`, `callback`, `notification`,
  `hub`, `listener`, `.admin.`) that target the actual non-primary file
  variants. CTK files are caught by the `ctk` marker; admin variants are
  caught by `.admin.`.

### Improved
- **Filename scoring** boosts files matching the canonical TMF prefix pattern
  (`TMFxxx-` or `TMFxxx_`) by 5 points, so the official primary spec wins over
  legacy/admin variants in repos with multiple candidates.
- **Version-aware tie-breaking** — when multiple spec files have the same score
  (e.g. v3.0.0, v4.0.0, v4.1.0, v4.2.0), the highest version wins instead of
  alphabetical order. Picks v4.2.0 over v4.1.0 over v4.0.0.
- Added `_swagger.json` (underscore variant) to the recognised swagger
  extensions, supporting filenames like
  `TMF653_Service_Test_Management_API_v4.2.0_swagger.json`.

## [0.2.3] — 2026-04-24

### Fixed
- **Fetcher branch handling**: raw URL fetches now try `main` first and fall
  back to `master`. Previously hardcoded `master`, which caused TMF653 (and any
  other repos that have switched their default branch to `main`) to fail with
  "Could not download a valid spec". The Contents API call already used the
  default branch — only the raw URL probes were affected.

## [0.2.2] — 2026-04-24

### Fixed
- TMF632 Party Management domain corrected from `customer` to `common`. In the
  TMForum SID, Party is a shared base abstraction (Individual, Organization)
  that Customer (TMF629) extends — it underpins every domain, not just Customer.
  (v0.2.1 shipped without this fix applied to the source tree; this release
  corrects the regression.)

## [0.2.1] — 2026-04-24

### Fixed
- **Edge labels**: all 22 entries in `SCHEMA_TO_LABEL` replaced with factual
  `references X` labels. Previous action-verb labels (`creates Service`,
  `triggers ServiceOrder`, `creates ResourceOrder`, `triggers ProductOrder`)
  injected architectural causality that is not in the OpenAPI specs. Edges
  drawn by tmf-map now describe the structural fact — the source API's schemas
  contain a `$ref` to the target entity — without making dependency claims that
  belong to the ODA Component layer. The `RelatedParty` label (`has RelatedParty`)
  is retained since it is a direct embed, not a ref-by-id.
- TMF653 Service Test domain corrected from `resource` to `service`. Service
  Test tests *services* (operates against TMF638 Service Inventory), not
  resources — it belongs in the service management stack.

## [0.2.0] — 2026-04-18

### Fixed
- Corrected GitHub repo names for 5 APIs that were returning no data:
  TMF641 (`TMF641_ServiceOrder`), TMF622 (`TMF622_ProductOrder`),
  TMF632 (`TMF632_PartyManagement`), TMF652 (`TMF652_ResourceOrderManagement`),
  TMF688 (`TMF688-Event`)

### Improved
- **Lifecycle extraction**: now resolves `$ref` chains to standalone enum schemas
  (`stateValues`, `StatusType`, `TroubleTicketStatusType` etc.) and scans
  all schemas as a fallback — fixes 8 APIs that were returning empty lifecycle states
- **Subdirectory scanning**: fetcher now searches one level of subdirectories when
  the spec is not at the repo root
- **Description cleaning**: strips Swagger UI boilerplate from `info.description`
- **Curated baseline merge**: `emitter.py` now merges extracted data with a
  hand-verified baseline for all 16 APIs — output is always complete even when
  live extraction is partial
- Extended `LIFECYCLE_FIELD_NAMES` to include `lifecycleState` (used by TMF639)
- Added `_is_real_spec()` validation to reject CTK/test files from fetcher results

### Added
- `diagnose.py` script for local extraction quality verification

## [0.1.0] — 2026-04-17

### Added
- `generate` command: fetch 16 TMForum API specs from GitHub, extract entities,
  lifecycle states and cross-API links, emit `tmf_data.json`
- `diff` command: compare existing `tmf_data.json` against current specs,
  classify changes as ERROR / WARNING / INFO, write `SPEC_CHANGES.md`
- `validate` command: sanity-check a `tmf_data.json` file
- `show` command: pretty-print extracted metadata for a single API
- `cache list` / `cache clear` subcommands
- Local disk cache with `--refresh` override
- Optional `--js` / `--ts` flags to emit ES module / TypeScript module
- GitHub Actions CI workflow with weekly spec-refresh job
- 55+ unit tests covering extractor, differ, emitter, and config consistency
