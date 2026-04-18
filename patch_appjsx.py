"""
patch_appjsx.py — Wire tmf-map App.jsx to import data from tmf_data.js
instead of inline hardcoded constants.

Run from: C:\\myclaude\\tmf-spec-parser
"""
import pathlib

APP = pathlib.Path(__file__).parent.parent / "tmf-map" / "src" / "App.jsx"
text = APP.read_text(encoding="utf-8")

# ── Old block to replace (everything from the first const down to API_DETAILS) ──
OLD_MARKER_START = 'import { useState, useEffect, useRef, useMemo } from "react";\nimport * as d3 from "d3";\n\n// ─── Domain config'
OLD_MARKER_END   = '// ─── State abbreviations for compact diagram display'

start = text.find(OLD_MARKER_START)
end   = text.find(OLD_MARKER_END)

if start == -1 or end == -1:
    print("ERROR: Could not find marker blocks in App.jsx")
    print(f"  start found: {start != -1}, end found: {end != -1}")
    exit(1)

NEW_HEADER = '''import { useState, useEffect, useRef, useMemo } from "react";
import * as d3 from "d3";
import TMF_DATA from "./tmf_data.js";

// ─── Domain config (UI only — colours not in spec data) ──────────────────────
const DOMAINS = {
  customer:   { label: "Customer",    color: "#00d4ff" },
  product:    { label: "Product",     color: "#ff9f0a" },
  service:    { label: "Service",     color: "#5e9bff" },
  resource:   { label: "Resource",    color: "#30d158" },
  engagement: { label: "Engagement",  color: "#ff6b6b" },
  common:     { label: "Common",      color: "#bf5af2" },
};

// ─── Data from tmf-spec-parser (auto-generated) ───────────────────────────────
const APIS     = TMF_DATA.apis;
const LINKS    = TMF_DATA.links;
const PATTERNS = TMF_DATA.patterns;

// Build GITHUB_REPOS map from apis registry
const GITHUB_REPOS = Object.fromEntries(
  TMF_DATA.apis.map(a => [a.id, a.repo])
);

// Reshape details to match the shape App.jsx expects
// tmf_data details already has {specRef, description, entities, lifecycle, terminal, transitions}
const API_DETAILS = TMF_DATA.details;

// ─── State abbreviations for compact diagram display
'''

patched = text[:start] + NEW_HEADER + text[end + len("// ─── State abbreviations for compact diagram display"):]
APP.write_text(patched, encoding="utf-8")
print("✓ App.jsx patched — now imports from tmf_data.js")
print(f"  File: {APP}")
