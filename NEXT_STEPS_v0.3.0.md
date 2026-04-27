# TMF DevKit v0.3.0 — Next Steps

## ✅ Completed (this session)

- [x] ODA repo coordinates added to `config.py`
- [x] Three new modules created: `oda_extractor.py`, `oda_fetcher.py`, `oda_emitter.py`
- [x] CLI `oda` subcommand wired into `cli.py`
- [x] Version bumped to 0.3.0 in `__init__.py` + `pyproject.toml`
- [x] ADR-001 written to `docs/ADR-001-odac-source-and-schema.md`
- [x] CHANGELOG.md updated with v0.3.0 entry
- [x] 28 tests written (all passing): `test_oda_extractor.py` (19), `test_oda_emitter.py` (9)
- [x] All ruff lint checks passing (E, F, I, UP)

## 🚀 Immediate next steps (local verification)

Run these commands in `C:\myclaude\tmf-spec-parser` to verify the build is clean:

```cmd
ruff check .
pytest -q
```

Both should be green. If any failures, review and fix before proceeding.

## 🌐 Live run against real GitHub repo (requires GITHUB_TOKEN)

Once local checks are green, test against the real 37-component ODAC staging repo:

```cmd
set GITHUB_TOKEN=<your_token>
pip install pyyaml
tmf-spec-parser oda --out ../tmf-map/src/oda_data.json --js
```

Expected output:
- **37 components** fetched (TMFC001–TMFC038 with gaps)
- `oda_data.json` + `oda_data.js` written to `../tmf-map/src/`
- Stats: ~53 unique APIs referenced, ~37 outside tmf-map's 16-API set

If the live run succeeds, inspect the output files:
- Check `oda_data.json` schema matches ADR-001
- Verify `oda_data.js` has ES module export syntax
- Spot-check a few component records (TMFC008 Service Inventory, TMFC001 Product Catalog)

## 📦 Build + Publish to PyPI

Once satisfied with the live run:

```cmd
cd C:\myclaude\tmf-spec-parser
python -m build
twine upload dist/*
```

Username: `__token__`
Password: <your PyPI token>

Expected: `tmf-spec-parser-0.3.0.tar.gz` and `.whl` uploaded successfully.

## 🏷️ Git tag + push

```cmd
git add -A
git commit -F commit_msg.txt
git push
git tag v0.3.0
git push --tags
```

## 📝 Session closeout documentation

Update or create `C:\myclaude\TMF_DevKit_Session_Context_v0.3.0_Closeout.md` capturing:
- What shipped (ODA extraction pipeline, 3 modules, CLI subcommand, ADR, tests)
- What's deferred (tmf-map renderer integration — next session)
- Open questions from ADR-001 (multi-CRD coexistence, security function inclusion, functional block colors, render-mode interaction)

## 🎯 Next session: tmf-map renderer integration

Wiring the `oda_data.json` into tmf-map as a second graph view. Tasks:
1. Add view-mode toggle (API view ↔ Component view)
2. Render component nodes + API nodes + dependency edges
3. Handle APIs outside the 16-API set (dim, ghost, or hide-by-default)
4. Mandatory/optional edge styling (use `required` flag)
5. Functional block color map (8 distinct blocks: CoreCommerce, Production, IntelligenceManagement, etc.)
6. Update README with Component view screenshots + usage

The data layer is done. Renderer is next.

## 🔍 Known constraints / reminders

- PyYAML is optional (`[yaml]` extra) — the `oda` subcommand handles missing dep gracefully
- Existing `generate` subcommand unchanged — v0.3.0 is fully backwards-compatible
- CRD versions: v1beta2, v1beta3, v1 all supported via normalisation layer
- Scope: `coreFunction` only; security/management/events deferred
- GitHub rate limit: 60 req/hr anonymous, 5000/hr with `GITHUB_TOKEN` — use token for live runs
