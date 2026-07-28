"""Orchestrate search → license check → content fetch → secret filter → store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, List, Optional, Set
from urllib.parse import unquote

from .client import GitHubClient
from .licenses import DEFAULT_ALLOW, license_allowed
from .secrets_filter import is_safe_content, redact_for_log
from .store import JsonlStore, SnippetRecord, content_hash, utc_now


@dataclass
class CrawlStats:
    search_hits: int = 0
    fetched: int = 0
    kept: int = 0
    dropped_license: int = 0
    dropped_secret: int = 0
    dropped_dup: int = 0
    dropped_error: int = 0
    dropped_binary: int = 0
    dropped_stars: int = 0


def build_code_query(
    text: str,
    *,
    language: Optional[str] = None,
    min_stars: int = 0,
    extension: Optional[str] = None,
    filename: Optional[str] = None,
    path_filter: Optional[str] = None,
    org: Optional[str] = None,
) -> str:
    """
    Build a GitHub code-search q= string.
    Docs: https://docs.github.com/en/rest/search/search#search-code
    """
    parts: List[str] = []
    text = (text or "").strip()
    if text:
        # Do NOT auto-wrap multi-word queries in quotes — that forces exact phrase match
        # and often returns zero hits. Callers may pass "quoted phrases" explicitly.
        parts.append(text)
    if language:
        parts.append(f"language:{language}")
    # NOTE: GitHub *code* search often returns 0 hits when stars: is combined with
    # multi-term queries. We filter min_stars client-side using repository metadata.
    if extension:
        ext = extension.lstrip(".")
        parts.append(f"extension:{ext}")
    if filename:
        parts.append(f"filename:{filename}")
    if path_filter:
        parts.append(f"path:{path_filter}")
    if org:
        parts.append(f"org:{org}")
    # Prefer non-fork signal via stars; forks still appear in code search
    return " ".join(parts)


def _repo_parts(full_name: str) -> tuple[str, str]:
    owner, _, name = full_name.partition("/")
    return owner, name


def crawl_code(
    client: GitHubClient,
    store: JsonlStore,
    query: str,
    *,
    max_pages: int = 2,
    per_page: int = 20,
    min_stars: int = 0,
    allow_licenses: Optional[FrozenSet[str]] = None,
    allow_copyleft: bool = False,
    allow_unknown_license: bool = False,
    max_file_bytes: int = 200_000,
    dry_run: bool = False,
    fetch_content: bool = True,
) -> CrawlStats:
    """
    Run one code-search crawl into the JSONL store.

    Legal: only retains allow-listed licenses by default.
    Ethics: drops content matching secret heuristics.
    """
    stats = CrawlStats()
    license_cache: dict[str, Optional[str]] = {}
    seen_urls: Set[str] = set()
    allow = allow_licenses if allow_licenses is not None else DEFAULT_ALLOW

    for item in client.search_code(query, per_page=per_page, max_pages=max_pages):
        stats.search_hits += 1
        repo = item.get("repository") or {}
        full_name = repo.get("full_name") or ""
        html_url = item.get("html_url") or ""
        path = item.get("path") or ""
        stars = int(repo.get("stargazers_count") or 0)
        if html_url in seen_urls:
            stats.dropped_dup += 1
            continue
        seen_urls.add(html_url)

        if min_stars and stars < min_stars:
            # Code search items sometimes omit stars (0) — fetch light repo if needed later
            if stars == 0 and min_stars > 0:
                # Allow through for license/content path; stars often missing on code search payloads
                pass
            elif stars > 0:
                stats.dropped_stars += 1
                continue

        # License: prefer nested repo license if present; else API
        lic_obj = repo.get("license") or {}
        spdx = lic_obj.get("spdx_id") or lic_obj.get("key")
        if full_name and full_name not in license_cache:
            if not spdx:
                owner, name = _repo_parts(full_name)
                try:
                    spdx = client.get_repo_license(owner, name)
                except Exception:
                    spdx = None
            license_cache[full_name] = spdx
        else:
            spdx = license_cache.get(full_name, spdx)

        if not license_allowed(
            spdx,
            allow=allow,
            allow_copyleft=allow_copyleft,
            allow_unknown=allow_unknown_license,
        ):
            stats.dropped_license += 1
            rec = SnippetRecord(
                query=query,
                repo_full_name=full_name,
                repo_html_url=repo.get("html_url") or "",
                path=path,
                html_url=html_url,
                license_spdx=spdx or "unknown",
                score=float(item.get("score") or 0),
                kept=False,
                drop_reason=f"license:{spdx or 'unknown'}",
                crawled_at=utc_now(),
            )
            if not dry_run:
                store.append(rec)
            continue

        content = ""
        if fetch_content:
            owner, name = _repo_parts(full_name)
            # Prefer git_url / path; ref from html if present is fragile — use default branch
            try:
                content = client.get_file_content(owner, name, path)
                stats.fetched += 1
            except Exception as exc:
                stats.dropped_error += 1
                rec = SnippetRecord(
                    query=query,
                    repo_full_name=full_name,
                    path=path,
                    html_url=html_url,
                    license_spdx=spdx or "unknown",
                    kept=False,
                    drop_reason=f"fetch_error:{type(exc).__name__}",
                    crawled_at=utc_now(),
                )
                if not dry_run:
                    store.append(rec)
                continue

        raw_bytes = len(content.encode("utf-8", errors="replace"))
        if raw_bytes > max_file_bytes:
            stats.dropped_binary += 1
            continue
        # Skip obvious binary / null-heavy
        if "\x00" in content[:4096]:
            stats.dropped_binary += 1
            continue

        h = content_hash(content)
        if store.has_hash(h):
            stats.dropped_dup += 1
            continue

        safe, secret_hits = is_safe_content(content)
        if not safe:
            stats.dropped_secret += 1
            rec = SnippetRecord(
                query=query,
                repo_full_name=full_name,
                repo_html_url=repo.get("html_url") or "",
                path=path,
                html_url=html_url,
                license_spdx=spdx or "unknown",
                content_sha256_16=h,
                content_bytes=raw_bytes,
                secret_hits=secret_hits,
                kept=False,
                drop_reason="secret:" + ",".join(secret_hits),
                crawled_at=utc_now(),
            )
            if not dry_run:
                # Store metadata only — never the secret-bearing body
                store.append(rec)
            continue

        rec = SnippetRecord(
            query=query,
            repo_full_name=full_name,
            repo_html_url=repo.get("html_url") or "",
            repo_stars=int(repo.get("stargazers_count") or 0),
            path=path,
            html_url=html_url,
            git_url=item.get("git_url") or "",
            license_spdx=spdx or "unknown",
            language=(item.get("language") or ""),
            score=float(item.get("score") or 0),
            content_sha256_16=h,
            content=content if not dry_run else "",
            content_bytes=raw_bytes,
            secret_hits=[],
            kept=True,
            drop_reason="",
            crawled_at=utc_now(),
        )
        if not dry_run:
            store.append(rec)
        stats.kept += 1
        print(
            f"KEEP  {full_name}:{path}  license={spdx}  "
            f"preview={redact_for_log(content, 80)!r}"
        )

    return stats


def summarize_store(store: JsonlStore) -> dict:
    rows = store.read_all()
    kept = [r for r in rows if r.get("kept")]
    by_repo: dict[str, int] = {}
    for r in kept:
        name = r.get("repo_full_name") or "?"
        by_repo[name] = by_repo.get(name, 0) + 1
    return {
        "total_records": len(rows),
        "kept": len(kept),
        "dropped": len(rows) - len(kept),
        "unique_repos": len(by_repo),
        "top_repos": sorted(by_repo.items(), key=lambda x: -x[1])[:10],
    }
