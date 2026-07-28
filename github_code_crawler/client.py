"""GitHub REST API client with auth, rate-limit backoff, and code search."""

from __future__ import annotations

import base64
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

import requests

API_ROOT = "https://api.github.com"


@dataclass
class RateLimit:
    remaining: int
    reset_epoch: int
    limit: int

    @classmethod
    def from_headers(cls, headers: requests.structures.CaseInsensitiveDict) -> "RateLimit":
        def _i(name: str, default: int = 0) -> int:
            try:
                return int(headers.get(name, default))
            except (TypeError, ValueError):
                return default

        return cls(
            remaining=_i("X-RateLimit-Remaining", 0),
            reset_epoch=_i("X-RateLimit-Reset", 0),
            limit=_i("X-RateLimit-Limit", 0),
        )


def resolve_token(explicit: Optional[str] = None) -> str:
    """Resolve PAT from arg, env, or `gh auth token`."""
    if explicit:
        return explicit.strip()
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    try:
        out = subprocess.check_output(
            ["gh", "auth", "token"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        tok = (out or "").strip()
        if tok:
            return tok
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    raise RuntimeError(
        "No GitHub token found. Set GITHUB_TOKEN / GH_TOKEN, pass --token, "
        "or run `gh auth login`."
    )


class GitHubClient:
    """Thin REST wrapper. Prefer API over HTML scraping (ToS + structured data)."""

    def __init__(self, token: str, user_agent: str = "WPAI-GitHubCodeCrawler/1.0") -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": user_agent,
            }
        )
        self.last_rate = RateLimit(remaining=5000, reset_epoch=0, limit=5000)

    def _sleep_for_rate_limit(self, headers: requests.structures.CaseInsensitiveDict) -> None:
        self.last_rate = RateLimit.from_headers(headers)
        # Code search is ~10 req/min authenticated; core is higher.
        remaining = self.last_rate.remaining
        if remaining <= 1:
            reset = self.last_rate.reset_epoch
            now = int(time.time())
            wait = max(reset - now + 1, 5)
            wait = min(wait, 120)
            time.sleep(wait)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 5,
    ) -> requests.Response:
        url = path if path.startswith("http") else f"{API_ROOT}{path}"
        for attempt in range(max_retries):
            resp = self.session.request(method, url, params=params, timeout=60)
            self._sleep_for_rate_limit(resp.headers)

            if resp.status_code == 403 and "rate limit" in (resp.text or "").lower():
                # Secondary rate limit or exhausted
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    time.sleep(min(int(retry_after), 120))
                else:
                    time.sleep(min(10 * (attempt + 1), 90))
                continue
            if resp.status_code == 422:
                # Validation (e.g. query too broad / code search constraints)
                return resp
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            return resp
        return resp

    def search_code(
        self,
        query: str,
        *,
        per_page: int = 30,
        max_pages: int = 3,
        sort: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        GET /search/code — requires auth.
        Note: GitHub code search has indexing lag and quality filters;
        not every public file is searchable.
        """
        page = 1
        while page <= max_pages:
            params: Dict[str, Any] = {
                "q": query,
                "per_page": min(per_page, 100),
                "page": page,
            }
            if sort:
                params["sort"] = sort
                params["order"] = "desc"

            resp = self.request("GET", "/search/code", params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"code search failed {resp.status_code}: {resp.text[:500]}")

            data = resp.json()
            items: List[Dict[str, Any]] = data.get("items") or []
            if not items:
                break
            for item in items:
                yield item
            # Polite pause: code search secondary limits are aggressive
            time.sleep(6.5)
            if len(items) < per_page:
                break
            page += 1

    def search_repositories(
        self,
        query: str,
        *,
        per_page: int = 30,
        max_pages: int = 2,
        sort: str = "stars",
    ) -> Iterator[Dict[str, Any]]:
        page = 1
        while page <= max_pages:
            params = {
                "q": query,
                "per_page": min(per_page, 100),
                "page": page,
                "sort": sort,
                "order": "desc",
            }
            resp = self.request("GET", "/search/repositories", params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"repo search failed {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            items = data.get("items") or []
            if not items:
                break
            for item in items:
                yield item
            time.sleep(1.0)
            if len(items) < per_page:
                break
            page += 1

    def get_file_content(self, owner: str, repo: str, path: str, ref: Optional[str] = None) -> str:
        """Fetch decoded file content via contents API (base64)."""
        api_path = f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}"
        params = {"ref": ref} if ref else None
        resp = self.request("GET", api_path, params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"contents {owner}/{repo}:{path} -> {resp.status_code}")
        data = resp.json()
        if isinstance(data, list):
            raise RuntimeError("path is a directory, not a file")
        encoding = data.get("encoding")
        content = data.get("content") or ""
        if encoding == "base64":
            raw = base64.b64decode(content)
            # Prefer utf-8; fall back to latin-1 to avoid crash on binary-ish
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1", errors="replace")
        return str(content)

    def get_repo_license(self, owner: str, repo: str) -> Optional[str]:
        resp = self.request("GET", f"/repos/{owner}/{repo}/license")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        lic = data.get("license") or {}
        return lic.get("spdx_id") or lic.get("key")
