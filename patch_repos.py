"""One-shot patch script — fix the 5 wrong repo names in config.py."""
import pathlib

path = pathlib.Path(__file__).parent / "tmf_spec_parser" / "config.py"
text = path.read_text(encoding="utf-8")

fixes = {
    '"repo": "TMF632_Party"':              '"repo": "TMF632_PartyManagement"',
    '"repo": "TMF622_ProductOrdering"':    '"repo": "TMF622_ProductOrder"',
    '"repo": "TMF641_ServiceOrdering"':    '"repo": "TMF641_ServiceOrder"',
    '"repo": "TMF652_ResourceOrdering"':   '"repo": "TMF652_ResourceOrderManagement"',
    '"repo": "TMF688_Event"':              '"repo": "TMF688-Event"',
}

for old, new in fixes.items():
    if old in text:
        text = text.replace(old, new)
        print(f"  Fixed: {old!r} -> {new!r}")
    else:
        print(f"  WARN: not found: {old!r}")

path.write_text(text, encoding="utf-8")
print("Done. config.py updated.")
