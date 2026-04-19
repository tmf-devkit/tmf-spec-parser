# Changelog

All notable changes to tmf-spec-parser are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
