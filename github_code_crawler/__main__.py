"""CLI: python -m github_code_crawler search "..." """

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import GitHubClient, resolve_token
from .crawler import build_code_query, crawl_code, summarize_store
from .licenses import DEFAULT_ALLOW
from .profiles import PROFILES, get_profile
from .store import JsonlStore


def _default_out() -> Path:
    return Path(__file__).resolve().parents[1] / "out" / "snippets.jsonl"


def _mission_out(profile: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in profile)
    return Path(__file__).resolve().parents[1] / "out" / safe / "snippets.jsonl"


def cmd_search(args: argparse.Namespace) -> int:
    token = resolve_token(args.token)
    client = GitHubClient(token)
    out = Path(args.out) if args.out else _default_out()
    store = JsonlStore(out)

    query = args.query
    if not args.raw_query:
        query = build_code_query(
            args.query,
            language=args.language,
            min_stars=args.min_stars,
            extension=args.extension,
            filename=args.filename,
            path_filter=args.path,
            org=args.org,
        )

    print(f"Query: {query}")
    print(f"Store: {store.path}")
    print(f"Licenses allowed: {', '.join(sorted(DEFAULT_ALLOW))}")
    if args.dry_run:
        print("DRY-RUN: will not write content bodies (metadata drops still recorded if not dry-store)")

    allow = DEFAULT_ALLOW
    if args.license:
        allow = frozenset(x.strip().lower() for x in args.license.split(",") if x.strip())

    stats = crawl_code(
        client,
        store,
        query,
        max_pages=args.max_pages,
        per_page=args.per_page,
        min_stars=args.min_stars or 0,
        allow_licenses=allow,
        allow_copyleft=args.allow_copyleft,
        allow_unknown_license=args.allow_unknown_license,
        max_file_bytes=args.max_bytes,
        dry_run=args.dry_run,
        fetch_content=not args.metadata_only,
    )

    print("---")
    print(
        f"hits={stats.search_hits} fetched={stats.fetched} kept={stats.kept} "
        f"drop_license={stats.dropped_license} drop_secret={stats.dropped_secret} "
        f"drop_dup={stats.dropped_dup} drop_err={stats.dropped_error} drop_stars={stats.dropped_stars}"
    )
    print(json.dumps(summarize_store(store), indent=2))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else _default_out()
    store = JsonlStore(out)
    print(json.dumps(summarize_store(store), indent=2))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else _default_out()
    store = JsonlStore(out)
    rows = [r for r in store.read_all() if r.get("kept")]
    if args.repo:
        rows = [r for r in rows if args.repo in (r.get("repo_full_name") or "")]
    limit = args.limit
    for r in rows[:limit]:
        print(f"## {r.get('repo_full_name')}:{r.get('path')}")
        print(f"license={r.get('license_spdx')} stars={r.get('repo_stars')} url={r.get('html_url')}")
        body = r.get("content") or ""
        if args.max_chars > 0:
            body = body[: args.max_chars]
        print(body)
        print()
    return 0


def cmd_mission(args: argparse.Namespace) -> int:
    """Run a curated profile (default: self-improvement for improve-swarm)."""
    profile = args.profile
    specs = get_profile(profile)
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        specs = [s for s in specs if s.name in want]
        if not specs:
            print(f"ERROR: --only matched nothing; available: {[s.name for s in get_profile(profile)]}")
            return 2

    out = Path(args.out) if args.out else _mission_out(profile)
    token = resolve_token(args.token)
    client = GitHubClient(token)
    store = JsonlStore(out)

    print(f"Mission profile: {profile}")
    print(f"Specs: {len(specs)}")
    print(f"Store: {out}")
    print(f"Licenses: {', '.join(sorted(DEFAULT_ALLOW))}")
    print("---")

    runs: list[dict] = []
    for i, spec in enumerate(specs, 1):
        q = build_code_query(
            spec.query_text,
            language=spec.language,
            min_stars=spec.min_stars if args.min_stars is None else args.min_stars,
            extension=spec.extension,
            filename=spec.filename,
            path_filter=spec.path,
        )
        print(f"\n[{i}/{len(specs)}] {spec.name}")
        print(f"  why: {spec.why}")
        print(f"  maps: {spec.maps_to}")
        print(f"  q: {q}")
        try:
            stars = spec.min_stars if args.min_stars is None else args.min_stars
            stats = crawl_code(
                client,
                store,
                q,
                max_pages=args.max_pages,
                per_page=args.per_page,
                min_stars=0,  # stars filtered loosely; code search omits stars often
                allow_licenses=DEFAULT_ALLOW,
                allow_copyleft=False,
                allow_unknown_license=False,
                max_file_bytes=args.max_bytes,
                dry_run=args.dry_run,
                fetch_content=not args.metadata_only,
            )
            _ = stars  # reserved for future repo enrichment filter
        except Exception as exc:
            print(f"  ERROR: {exc}")
            runs.append(
                {
                    "name": spec.name,
                    "why": spec.why,
                    "maps_to": spec.maps_to,
                    "hits": 0,
                    "kept": 0,
                    "drop_license": 0,
                    "drop_secret": 0,
                    "error": str(exc),
                }
            )
            continue

        runs.append(
            {
                "name": spec.name,
                "why": spec.why,
                "maps_to": spec.maps_to,
                "hits": stats.search_hits,
                "kept": stats.kept,
                "drop_license": stats.dropped_license,
                "drop_secret": stats.dropped_secret,
            }
        )
        print(
            f"  hits={stats.search_hits} kept={stats.kept} "
            f"lic_drop={stats.dropped_license} secret_drop={stats.dropped_secret}"
        )

    q_to_maps: dict[str, str] = {}
    for spec in specs:
        q = build_code_query(
            spec.query_text,
            language=spec.language,
            min_stars=spec.min_stars if args.min_stars is None else args.min_stars,
            extension=spec.extension,
            filename=spec.filename,
            path_filter=spec.path,
        )
        q_to_maps[q] = spec.maps_to

    rows = store.read_all()
    for r in rows:
        if r.get("query") in q_to_maps:
            r["mission_maps_to"] = q_to_maps[r["query"]]

    findings = out.parent / "FINDINGS.md"
    findings.write_text(_findings_markdown(profile, runs, rows, out), encoding="utf-8")

    # Also drop a pointer for StudioOps operators
    pointer = (
        Path(r"C:\WPAI\Software\StudioOps\improve-swarm") / "GITHUB-CRAWL-SELF-IMPROVEMENT.md"
    )
    try:
        pointer.write_text(
            "\n".join(
                [
                    "# GitHub crawl → self-improvement",
                    "",
                    f"Latest mission findings: `{findings}`",
                    f"Snippet store: `{out}`",
                    "",
                    "Regenerate:",
                    "```powershell",
                    "cd C:\\WPAI\\Software\\GitHubCodeCrawler",
                    "python -m github_code_crawler mission --profile self-improvement --max-pages 1 --per-page 8",
                    "```",
                    "",
                    "Do not copy code blindly — port algorithms, keep licenses, validate with `wpai improve review`.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    except OSError:
        pointer = None

    print("\n===")
    print(json.dumps(summarize_store(store), indent=2))
    print(f"Findings: {findings}")
    if pointer:
        print(f"StudioOps pointer: {pointer}")
    return 0


def _findings_markdown(profile: str, runs: list[dict], rows: list[dict], store_path: Path) -> str:
    kept = [r for r in rows if r.get("kept")]
    lines = [
        f"# Crawl findings — profile `{profile}`",
        "",
        "Mission: find open-source code useful for **WPAI improve-swarm** "
        "(evolutionary search, fitness, elites, mutation, auto-review).",
        "",
        f"Store: `{store_path}`",
        f"Kept snippets: **{len(kept)}**",
        "",
        "## Runs",
        "",
        "| Spec | Why (short) | Maps to | Hits | Kept | Drop license | Drop secret |",
        "|------|-------------|---------|-----:|-----:|-------------:|------------:|",
    ]
    for run in runs:
        err = run.get("error")
        if err:
            lines.append(
                f"| {run['name']} | ERROR | | 0 | 0 | | | {err[:40]} |"
            )
            continue
        lines.append(
            "| {name} | {why} | `{maps}` | {hits} | {kept} | {lic} | {sec} |".format(
                name=run["name"],
                why=(run.get("why") or "")[:42].replace("|", "/"),
                maps=(run.get("maps_to") or "")[:40].replace("|", "/"),
                hits=run.get("hits", 0),
                kept=run.get("kept", 0),
                lic=run.get("drop_license", 0),
                sec=run.get("drop_secret", 0),
            )
        )
    lines.extend(["", "## Kept artifacts (license-clean)", ""])
    if not kept:
        lines.append("_No snippets kept — try lowering --min-stars or widening queries._")
    for r in kept:
        maps = r.get("mission_maps_to") or ""
        lines.append(
            f"- **{r.get('repo_full_name')}:{r.get('path')}**  "
            f"`{r.get('license_spdx')}`  "
            f"[source]({r.get('html_url')})"
        )
        if maps:
            lines.append(f"  - **maps to improve-swarm:** `{maps}`")
        q = (r.get("query") or "")[:70]
        if q:
            lines.append(f"  - query: `{q}`")
    lines.extend(
        [
            "",
            "## Next for improve-swarm",
            "",
            "1. Review FINDINGS + snippets under `out/self-improvement/`.",
            "2. Port **algorithms** (selection, elitism, bandits) into `WpaiImproveSwarm.ps1` — not whole files.",
            "3. Validate with `wpai improve review` (must stay SHIPPED/PROPERTY honest).",
            "4. Record experiments: `wpai improve record -PathId … -Verdict SUPPORTED|KILLED`.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def cmd_profiles(args: argparse.Namespace) -> int:
    for name, specs in sorted(PROFILES.items()):
        print(f"{name}  ({len(specs)} searches)")
        for s in specs:
            print(f"  - {s.name}: {s.why}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="github_code_crawler",
        description="Crawl useful open-source code via the official GitHub API (not HTML scraping).",
    )
    p.add_argument("--token", default=None, help="GitHub PAT (else GITHUB_TOKEN / GH_TOKEN / gh auth token)")
    p.add_argument("--out", default=None, help="JSONL store path (default depends on command)")

    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser(
        "mission",
        help="Run curated mission (default: self-improvement → feed improve-swarm)",
    )
    m.add_argument(
        "--profile",
        default="self-improvement",
        help="Profile name (self-improvement | improve-swarm)",
    )
    m.add_argument("--only", default=None, help="Comma list of spec names to run")
    m.add_argument("--min-stars", type=int, default=None, help="Override stars floor for all specs")
    m.add_argument("--max-pages", type=int, default=1)
    m.add_argument("--per-page", type=int, default=8)
    m.add_argument("--max-bytes", type=int, default=120_000)
    m.add_argument("--metadata-only", action="store_true")
    m.add_argument("--dry-run", action="store_true")
    m.set_defaults(func=cmd_mission)

    pl = sub.add_parser("profiles", help="List mission profiles")
    pl.set_defaults(func=cmd_profiles)

    s = sub.add_parser("search", help="Search code and store snippets")
    s.add_argument("query", help='Search text, e.g. "rate limit retry" or use --raw-query')
    s.add_argument("--raw-query", action="store_true", help="Pass query string unmodified to GitHub")
    s.add_argument("--language", default=None, help="language:python")
    s.add_argument("--min-stars", type=int, default=50, help="stars:>=N on containing repo")
    s.add_argument("--extension", default=None, help="extension:py")
    s.add_argument("--filename", default=None, help="filename:utils.py")
    s.add_argument("--path", default=None, help="path:src/")
    s.add_argument("--org", default=None, help="org:github")
    s.add_argument("--max-pages", type=int, default=2, help="Code search pages (30 results/page default)")
    s.add_argument("--per-page", type=int, default=20)
    s.add_argument("--license", default=None, help="Comma list of SPDX ids to allow (default permissive set)")
    s.add_argument("--allow-copyleft", action="store_true")
    s.add_argument("--allow-unknown-license", action="store_true")
    s.add_argument("--max-bytes", type=int, default=200_000)
    s.add_argument("--metadata-only", action="store_true", help="Do not fetch file bodies")
    s.add_argument("--dry-run", action="store_true", help="Search + filter only; do not append store")
    s.set_defaults(func=cmd_search)

    t = sub.add_parser("stats", help="Summarize local store")
    t.set_defaults(func=cmd_stats)

    w = sub.add_parser("show", help="Print kept snippets")
    w.add_argument("--repo", default=None)
    w.add_argument("--limit", type=int, default=5)
    w.add_argument("--max-chars", type=int, default=1500)
    w.set_defaults(func=cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; mission output prints arrows (→) and other
    # Unicode that would otherwise crash mid-run. Force UTF-8 on our own streams
    # (errors="replace" can never raise on encode) so a stray glyph can't abort a crawl.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
