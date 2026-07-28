"""Heuristic filters for accidental secrets in crawled code."""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

# High-signal patterns only — avoid drowning in false positives from example docs.
_SECRET_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret", re.compile(r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]")),
    ("github_pat", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("github_fine_grained", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("generic_api_key_assign", re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"][^'\"]{16,}['\"]"
    )),
    ("jwt_like", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]


def find_secret_hits(text: str) -> List[str]:
    """Return list of secret pattern names that matched."""
    if not text:
        return []
    hits: List[str] = []
    for name, pat in _SECRET_PATTERNS:
        if pat.search(text):
            hits.append(name)
    return hits


def is_safe_content(text: str) -> Tuple[bool, List[str]]:
    """True if content does not match known secret patterns."""
    hits = find_secret_hits(text)
    return (len(hits) == 0, hits)


def redact_for_log(text: str, max_len: int = 200) -> str:
    """Short, redacted snippet safe for console logs."""
    safe, _ = is_safe_content(text)
    snippet = (text or "").replace("\n", " ")[:max_len]
    if not safe:
        return "[REDACTED: possible secret]"
    return snippet
