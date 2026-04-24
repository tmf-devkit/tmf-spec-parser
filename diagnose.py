"""
diagnose.py — Verify extractor output against cached specs.
Run: python diagnose.py
"""
import json
import pathlib
import sys

CACHE = pathlib.Path.home() / ".tmf-spec-parser" / "cache"

# Add project to path
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from tmf_spec_parser.config import API_REGISTRY  # noqa: E402
from tmf_spec_parser.emitter import _build_details  # noqa: E402
from tmf_spec_parser.extractor import extract  # noqa: E402

ALL_APIS = [a["id"] for a in API_REGISTRY]

print("=== EXTRACTION RESULTS (cached specs only) ===\n")
print(f"{'API':<8} {'ver':<10} {'entities':<10} {'lifecycle states':<20} {'desc':<5} {'source'}")
print("-" * 75)

extracted = {}
for api_id in ALL_APIS:
    f = CACHE / f"{api_id}.json"
    if not f.exists():
        print(f"{api_id:<8} {'—':<10} {'—':<10} {'(not cached)':<20} {'—':<5} MISSING")
        extracted[api_id] = {}
        continue

    spec   = json.loads(f.read_text())
    result = extract(api_id, spec)
    extracted[api_id] = result

    ents   = len(result["entities"])
    states = len(result["lifecycle"])
    desc   = "OK" if len(result.get("description","")) > 15 else "—"
    ver    = result.get("version","?")[:9]
    lc_preview = ",".join(result["lifecycle"][:3])
    if len(result["lifecycle"]) > 3:
        lc_preview += "…"
    print(f"{api_id:<8} {ver:<10} {ents:<10} {lc_preview:<20} {desc:<5} extracted")

print("\n=== AFTER BASELINE MERGE ===\n")
print(f"{'API':<8} {'entities':<10} {'lifecycle states':<8} {'description[:60]'}")
print("-" * 75)

details = _build_details(extracted)
all_good = True
for api_id in ALL_APIS:
    d = details[api_id]
    ents   = len(d["entities"])
    states = len(d["lifecycle"])
    desc   = d.get("description","")[:60]
    flag   = "" if (ents > 0 and (states > 0 or api_id in ("TMF688","TMF632"))) else " ⚠"
    if flag:
        all_good = False
    print(f"{api_id:<8} {ents:<10} {states:<8} {desc}{flag}")

print()
if all_good:
    print("✅ All 16 APIs have complete data after merge.")
else:
    print("⚠  Some APIs still missing data — check flags above.")
