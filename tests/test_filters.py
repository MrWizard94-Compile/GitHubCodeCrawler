"""Unit tests for license + secrets filters (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from github_code_crawler.licenses import license_allowed
from github_code_crawler.secrets_filter import find_secret_hits, is_safe_content
from github_code_crawler.crawler import build_code_query
from github_code_crawler.store import content_hash


def test_license_mit_allowed():
    assert license_allowed("MIT") is True
    assert license_allowed("mit") is True
    assert license_allowed("Apache-2.0") is True


def test_license_gpl_blocked():
    assert license_allowed("GPL-3.0") is False
    assert license_allowed("gpl-3.0", allow_copyleft=True) is True
    assert license_allowed("unknown", allow_unknown=False) is False
    assert license_allowed("unknown", allow_unknown=True) is True


def test_secrets_github_pat():
    text = 'token = "ghp_abcdefghijklmnopqrstuvwxyz012345"'
    hits = find_secret_hits(text)
    assert "github_pat" in hits
    ok, _ = is_safe_content(text)
    assert ok is False


def test_secrets_clean_code():
    text = "def add(a, b):\n    return a + b\n"
    ok, hits = is_safe_content(text)
    assert ok is True
    assert hits == []


def test_build_query():
    q = build_code_query("rate limit", language="python", min_stars=100, extension="py")
    assert "rate limit" in q
    assert "language:python" in q
    # stars are applied client-side (code search + stars: is unreliable)
    assert "stars:" not in q
    assert "extension:py" in q


def test_content_hash_stable():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")


if __name__ == "__main__":
    test_license_mit_allowed()
    test_license_gpl_blocked()
    test_secrets_github_pat()
    test_secrets_clean_code()
    test_build_query()
    test_content_hash_stable()
    print("ALL PASS")
