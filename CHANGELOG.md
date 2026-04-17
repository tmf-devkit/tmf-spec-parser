# Changelog

All notable changes to tmf-spec-parser are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] — 2026-04-17

### Added
- `generate` command: fetch 16 TMForum API specs from GitHub, extract entities,
  lifecycle states and cross-API links, emit `tmf_data.json`
- `diff` command: compare existing `tmf_data.json` against current specs,
  classify changes as ERROR / WARNING / INFO, write `SPEC_CHANGES.md`
- `validate` command: sanity-check a `tmf_data.json` file (link integrity,
  transition state references, required keys)
- `show` command: pretty-print extracted metadata for a single API
- `cache list` / `cache clear` subcommands
- Local disk cache (`~/.tmf-spec-parser/cache/`) with `--refresh` override
- Optional `--js` / `--ts` flags to emit ES module / TypeScript module
- GitHub Actions CI workflow with weekly spec-refresh job
- `GITHUB_TOKEN` support to avoid anonymous rate limits
- 55+ unit tests covering extractor, differ, emitter, and config consistency
