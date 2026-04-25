# Changelog

All notable changes to tmf-spec-parser are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
