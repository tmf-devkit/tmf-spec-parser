"""
cli.py — Command-line interface for tmf-spec-parser.

Commands
--------
  generate   Fetch specs, extract metadata, write tmf_data.json
  diff       Compare existing tmf_data.json against current specs
  validate   Check that extracted data passes sanity rules
  show       Pretty-print extracted metadata for one API
  cache      Manage the local spec cache

Examples
--------
  tmf-spec-parser generate
  tmf-spec-parser generate --out ./tmf-map/public/tmf_data.json --js
  tmf-spec-parser generate --apis TMF638,TMF639,TMF641 --refresh
  tmf-spec-parser diff --existing ./tmf_data.json
  tmf-spec-parser show TMF641
  tmf-spec-parser cache clear
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tmf_spec_parser import __version__
from tmf_spec_parser.config import API_IDS, API_REGISTRY
from tmf_spec_parser.differ import diff
from tmf_spec_parser.emitter import (
    build,
    load_existing,
    write_js_module,
    write_json,
    write_ts_module,
)
from tmf_spec_parser.extractor import extract_all
from tmf_spec_parser.fetcher import DEFAULT_CACHE_DIR, fetch_all

console = Console()

DEFAULT_OUTPUT = Path("tmf_data.json")


# ── Root group ─────────────────────────────────────────────────────────────────
@click.group()
@click.version_option(__version__, prog_name="tmf-spec-parser")
def main() -> None:
    """tmf-spec-parser — Extract, validate and diff TMForum Open API specs."""


# ── generate ───────────────────────────────────────────────────────────────────
@main.command()
@click.option(
    "--apis", "-a", default=None,
    help="Comma-separated API IDs to process, e.g. TMF638,TMF641. Defaults to all 16.",
)
@click.option(
    "--out", "-o", default=str(DEFAULT_OUTPUT), show_default=True,
    help="Output path for tmf_data.json.",
)
@click.option("--js", is_flag=True, default=False,
              help="Also emit a tmf_data.js ES module alongside the JSON.")
@click.option("--ts", is_flag=True, default=False,
              help="Also emit a tmf_data.ts TypeScript module.")
@click.option("--refresh", "-r", is_flag=True, default=False,
              help="Bypass local cache and re-download all specs from GitHub.")
@click.option("--cache-dir", default=str(DEFAULT_CACHE_DIR), show_default=True,
              help="Directory for cached spec files.")
@click.option("--no-diff", is_flag=True, default=False,
              help="Skip the diff check against the existing output file.")
@click.option("--diff-out", default="SPEC_CHANGES.md", show_default=True,
              help="Path to write the diff report (Markdown).")
def generate(
    apis: str | None,
    out: str,
    js: bool,
    ts: bool,
    refresh: bool,
    cache_dir: str,
    no_diff: bool,
    diff_out: str,
) -> None:
    """Fetch TMForum specs and generate tmf_data.json."""

    api_list = [a.strip().upper() for a in apis.split(",")] if apis else None
    if api_list:
        invalid = [a for a in api_list if a not in API_IDS]
        if invalid:
            console.print(f"[red]Unknown API IDs: {', '.join(invalid)}[/red]")
            console.print(f"Valid IDs: {', '.join(API_IDS)}")
            sys.exit(1)

    output_path = Path(out)
    cache_path  = Path(cache_dir)

    console.print(Panel(
        f"[bold cyan]tmf-spec-parser[/bold cyan] v{__version__}\n"
        f"APIs: {', '.join(api_list) if api_list else 'all 16'}\n"
        f"Output: {output_path}\n"
        f"Cache: {cache_path}",
        title="Generate", border_style="cyan",
    ))

    # ── 1. Fetch ──────────────────────────────────────────────────────────────
    with console.status("[cyan]Fetching specs from GitHub…"):
        specs = fetch_all(apis=api_list, cache_dir=cache_path, refresh=refresh)

    if not specs:
        console.print("[red]No specs fetched. Check your network / GITHUB_TOKEN.[/red]")
        sys.exit(1)

    fetched_ids = sorted(specs)
    console.print(
        f"[green]✓[/green] Fetched {len(fetched_ids)} spec(s):"
        f" {', '.join(fetched_ids)}"
    )

    # ── 2. Extract ────────────────────────────────────────────────────────────
    with console.status("[cyan]Extracting metadata…"):
        extracted = extract_all(specs)

    console.print(f"[green]✓[/green] Extracted metadata for {len(extracted)} API(s)")

    # ── 3. Diff (optional) ────────────────────────────────────────────────────
    if not no_diff:
        existing = load_existing(output_path)
        if existing:
            report = diff(existing.get("details", {}), extracted)
            if report.findings:
                console.print(
                    f"\n[yellow]Diff against existing {output_path}:[/yellow]"
                )
                for finding in report.findings:
                    colour = {
                        "ERROR": "red", "WARNING": "yellow", "INFO": "blue",
                    }[finding.severity.value]
                    console.print(f"  [{colour}]{finding}[/{colour}]")
                diff_path = Path(diff_out)
                diff_path.write_text(report.to_markdown(), encoding="utf-8")
                console.print(f"\n[yellow]Diff report written to {diff_path}[/yellow]")
                if report.has_breaking_changes:
                    console.print(
                        "[red bold]⚠ Breaking changes detected"
                        " — review before deploying.[/red bold]"
                    )
            else:
                console.print(
                    "[green]✓[/green] No differences detected — specs are in sync."
                )

    # ── 4. Build & write ──────────────────────────────────────────────────────
    data = build(extracted)
    write_json(data, output_path)
    console.print(f"[green]✓[/green] Written: {output_path}")

    if js:
        js_path = output_path.with_suffix(".js")
        write_js_module(data, js_path)
        console.print(f"[green]✓[/green] Written: {js_path}")

    if ts:
        ts_path = output_path.with_suffix(".ts")
        write_ts_module(data, ts_path)
        console.print(f"[green]✓[/green] Written: {ts_path}")

    console.print(
        f"\n[bold green]Done.[/bold green]"
        f" {len(data['links'])} cross-API links,"
        f" {len(data['apis'])} APIs in output."
    )


# ── diff ───────────────────────────────────────────────────────────────────────
@main.command(name="diff")
@click.option("--existing", "-e", default=str(DEFAULT_OUTPUT), show_default=True,
              help="Path to existing tmf_data.json to compare against.")
@click.option("--apis", "-a", default=None,
              help="Comma-separated API IDs to check. Defaults to all.")
@click.option("--refresh", "-r", is_flag=True, default=False,
              help="Re-download specs before diffing.")
@click.option("--cache-dir", default=str(DEFAULT_CACHE_DIR), show_default=True)
@click.option("--out", "-o", default=None,
              help="Write Markdown report to this file.")
def diff_cmd(
    existing: str,
    apis: str | None,
    refresh: bool,
    cache_dir: str,
    out: str | None,
) -> None:
    """Compare tmf_data.json against current TMForum specs."""

    existing_path = Path(existing)
    existing_data = load_existing(existing_path)
    if not existing_data:
        console.print(f"[red]Could not load {existing_path}[/red]")
        sys.exit(1)

    api_list = [a.strip().upper() for a in apis.split(",")] if apis else None

    with console.status("[cyan]Fetching specs…"):
        specs = fetch_all(apis=api_list, cache_dir=Path(cache_dir), refresh=refresh)

    with console.status("[cyan]Extracting…"):
        extracted = extract_all(specs)

    report = diff(existing_data.get("details", {}), extracted)

    if not report.findings:
        console.print("[green]✓ No differences — specs are in sync.[/green]")
        return

    console.print(f"\n[bold]Diff report — {report.summary()}[/bold]\n")
    for finding in report.findings:
        colour = {
            "ERROR": "red", "WARNING": "yellow", "INFO": "blue",
        }[finding.severity.value]
        console.print(f"  [{colour}]{finding}[/{colour}]")

    if out:
        Path(out).write_text(report.to_markdown(), encoding="utf-8")
        console.print(f"\n[cyan]Report written to {out}[/cyan]")

    if report.has_breaking_changes:
        sys.exit(1)


# ── validate ───────────────────────────────────────────────────────────────────
@main.command()
@click.argument("json_file", default=str(DEFAULT_OUTPUT))
def validate(json_file: str) -> None:
    """Run sanity checks on a tmf_data.json file."""

    path = Path(json_file)
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for key in ("apis", "links", "details", "patterns"):
        if key not in data:
            errors.append(f"Missing top-level key: '{key}'")

    detail_ids = set(data.get("details", {}).keys())
    for entry in API_REGISTRY:
        if entry["id"] not in detail_ids:
            errors.append(f"Missing details for {entry['id']}")

    valid_ids = {a["id"] for a in data.get("apis", [])}
    for link in data.get("links", []):
        for side in ("source", "target"):
            if link.get(side) not in valid_ids:
                errors.append(
                    f"Link references unknown API: {link.get(side)!r} in {link}"
                )

    for api_id, detail in data.get("details", {}).items():
        states = set(detail.get("lifecycle", []))
        for t in detail.get("transitions", []):
            for side in ("from", "to"):
                if t.get(side) not in states:
                    errors.append(
                        f"{api_id}: transition {t}"
                        f" references unknown state '{t.get(side)}'"
                    )

    if errors:
        console.print(
            f"[red bold]Validation failed — {len(errors)} error(s):[/red bold]"
        )
        for e in errors:
            console.print(f"  [red]• {e}[/red]")
        sys.exit(1)
    else:
        console.print(f"[green bold]✓ {path} is valid.[/green bold]")


# ── show ───────────────────────────────────────────────────────────────────────
@main.command()
@click.argument("api_id")
@click.option("--cache-dir", default=str(DEFAULT_CACHE_DIR), show_default=True)
def show(api_id: str, cache_dir: str) -> None:
    """Pretty-print extracted metadata for one API (reads from cache)."""

    api_id = api_id.upper()
    entry  = next((a for a in API_REGISTRY if a["id"] == api_id), None)
    if not entry:
        console.print(
            f"[red]Unknown API: {api_id}. Valid: {', '.join(API_IDS)}[/red]"
        )
        sys.exit(1)

    cache_path = Path(cache_dir) / f"{api_id}.json"
    if not cache_path.exists():
        console.print(
            f"[yellow]Cache miss for {api_id}. Run 'generate' first.[/yellow]"
        )
        sys.exit(1)

    from tmf_spec_parser.config import TERMINAL_STATES, TRANSITIONS
    from tmf_spec_parser.extractor import extract

    spec = json.loads(cache_path.read_text(encoding="utf-8"))
    data = extract(api_id, spec)
    data["terminal"]    = TERMINAL_STATES.get(api_id, [])
    data["transitions"] = TRANSITIONS.get(api_id, [])

    console.print(Panel(
        f"[bold cyan]{api_id}[/bold cyan] — {entry['name']}\n"
        f"[dim]{entry['domain'].title()} domain · {data['version']}[/dim]\n\n"
        f"{data['description']}",
        title=api_id, border_style="cyan",
    ))

    if data["entities"]:
        tbl = Table(title="Entities", show_header=True, header_style="bold")
        tbl.add_column("Entity")
        tbl.add_column("Mandatory fields")
        tbl.add_column("Optional fields")
        for e in data["entities"]:
            opt_preview = ", ".join(e["optional"][:6])
            if len(e["optional"]) > 6:
                opt_preview += "…"
            tbl.add_row(
                e["name"],
                ", ".join(e["mandatory"]) or "—",
                opt_preview or "—",
            )
        console.print(tbl)

    if data["lifecycle"]:
        states_str = " → ".join(
            f"[red]{s}[/red]" if s in data["terminal"] else s
            for s in data["lifecycle"]
        )
        console.print(f"\n[bold]Lifecycle:[/bold] {states_str}")
        console.print(f"[bold]Transitions:[/bold] {len(data['transitions'])} defined")

    if data.get("links"):
        console.print("\n[bold]Cross-API links:[/bold]")
        for link in data["links"]:
            console.print(
                f"  → [cyan]{link['target']}[/cyan]  [dim]{link['label']}[/dim]"
            )


# ── cache ──────────────────────────────────────────────────────────────────────
@main.group()
def cache() -> None:
    """Manage the local spec cache."""


@cache.command(name="list")
@click.option("--cache-dir", default=str(DEFAULT_CACHE_DIR), show_default=True)
def cache_list(cache_dir: str) -> None:
    """List cached spec files."""
    path = Path(cache_dir)
    if not path.exists() or not list(path.glob("*.json")):
        console.print(f"[yellow]Cache is empty: {path}[/yellow]")
        return
    tbl = Table(title=f"Cache: {path}", show_header=True, header_style="bold")
    tbl.add_column("API")
    tbl.add_column("File")
    tbl.add_column("Size")
    for f in sorted(path.glob("*.json")):
        tbl.add_row(f.stem, f.name, f"{f.stat().st_size // 1024} KB")
    console.print(tbl)


@cache.command(name="clear")
@click.option("--cache-dir", default=str(DEFAULT_CACHE_DIR), show_default=True)
@click.confirmation_option(prompt="Clear all cached specs?")
def cache_clear(cache_dir: str) -> None:
    """Delete all cached spec files."""
    path = Path(cache_dir)
    removed = 0
    for f in path.glob("*.json"):
        f.unlink()
        removed += 1
    console.print(
        f"[green]✓[/green] Removed {removed} cached file(s) from {path}"
    )


# ── oda ────────────────────────────────────────────────────────────────────────
@main.command()
@click.option(
    "--out", "-o", default="oda_data.json", show_default=True,
    help="Output path for oda_data.json.",
)
@click.option("--js", is_flag=True, default=False,
              help="Also emit oda_data.js (ES module) alongside the JSON.")
@click.option("--refresh", "-r", is_flag=True, default=False,
              help="Bypass local cache and re-download all manifests from GitHub.")
@click.option("--components", "-c", default=None,
              help="Comma-separated component IDs to process, e.g. "
                   "TMFC008,TMFC037. Defaults to all.")
def oda(out: str, js: bool, refresh: bool, components: str | None) -> None:
    """Fetch ODA Component (ODAC) manifests and generate oda_data.json."""
    # Lazy imports so the rest of the CLI doesn't pay the pyyaml import cost.
    try:
        import yaml  # noqa: F401
    except ImportError:
        console.print(
            "[red]The 'oda' command requires PyYAML. Install with:[/red]\n"
            "  pip install 'tmf-spec-parser[yaml]'\n"
            "or\n  pip install pyyaml"
        )
        sys.exit(1)

    from tmf_spec_parser.config import (
        ODA_GITHUB_ORG,
        ODA_GITHUB_REPO,
        ODA_REPO_REF,
    )
    from tmf_spec_parser.oda_emitter import (
        build as oda_build,
    )
    from tmf_spec_parser.oda_emitter import (
        write_js_module as oda_write_js,
    )
    from tmf_spec_parser.oda_emitter import (
        write_json as oda_write_json,
    )
    from tmf_spec_parser.oda_extractor import parse_manifest
    from tmf_spec_parser.oda_fetcher import (
        DEFAULT_ODA_CACHE_DIR,
        fetch_all_manifests,
    )

    component_filter: list[str] | None = None
    if components:
        component_filter = [c.strip().upper() for c in components.split(",") if c.strip()]

    output_path = Path(out)

    console.print(Panel(
        f"[bold cyan]tmf-spec-parser oda[/bold cyan] v{__version__}\n"
        f"Source: {ODA_GITHUB_ORG}/{ODA_GITHUB_REPO}@{ODA_REPO_REF}\n"
        f"Components: {', '.join(component_filter) if component_filter else 'all'}\n"
        f"Output: {output_path}\n"
        f"Cache: {DEFAULT_ODA_CACHE_DIR}",
        title="ODA Component manifests", border_style="cyan",
    ))

    # ── 1. Fetch ─────────────────────────────────────────────────────────────────────────
    with console.status("[cyan]Fetching ODAC manifests from GitHub…"):
        manifests = fetch_all_manifests(
            refresh=refresh,
            component_filter=component_filter,
        )

    if not manifests:
        console.print(
            "[red]No manifests fetched. Check network or set GITHUB_TOKEN.[/red]"
        )
        sys.exit(1)

    console.print(
        f"[green]✓[/green] Fetched {len(manifests)} manifest(s)"
    )

    # ── 2. Parse ─────────────────────────────────────────────────────────────────────────
    import yaml
    parsed = []
    skipped: list[str] = []
    for cid, text in sorted(manifests.items()):
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            skipped.append(f"{cid} (YAML parse error: {exc})")
            continue
        comp = parse_manifest(doc)
        if comp is None:
            skipped.append(f"{cid} (manifest did not parse cleanly)")
            continue
        parsed.append(comp)

    if skipped:
        console.print(
            f"[yellow]Skipped {len(skipped)} manifest(s):[/yellow]"
        )
        for line in skipped:
            console.print(f"  [yellow]• {line}[/yellow]")

    console.print(
        f"[green]✓[/green] Parsed {len(parsed)} component(s)"
    )

    # ── 3. Build & write ───────────────────────────────────────────────────────────────────
    data = oda_build(parsed)
    oda_write_json(data, output_path)
    console.print(f"[green]✓[/green] Written: {output_path}")

    if js:
        js_path = output_path.with_suffix(".js")
        oda_write_js(data, js_path)
        console.print(f"[green]✓[/green] Written: {js_path}")

    stats = data["stats"]
    console.print(
        f"\n[bold green]Done.[/bold green] "
        f"{stats['components']} component(s), "
        f"{stats['exposed_api_count']} exposed APIs, "
        f"{stats['dependent_api_count']} dependent APIs, "
        f"{stats['unique_apis_referenced']} unique APIs referenced "
        f"({stats.get('apis_outside_tmf_map_set', 0)} outside tmf-map's 16-API set)."
    )

