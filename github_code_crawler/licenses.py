"""Open-source license allow/deny policy for crawled repos."""

from __future__ import annotations

from typing import FrozenSet, Optional

# SPDX-ish keys as returned by GitHub's license.spdx_id / license.key
DEFAULT_ALLOW: FrozenSet[str] = frozenset(
    {
        "mit",
        "apache-2.0",
        "bsd-2-clause",
        "bsd-3-clause",
        "isc",
        "unlicense",
        "cc0-1.0",
        "0bsd",
        "mpl-2.0",
        "zlib",
    }
)

# Strong copyleft / restrictive — blocked by default unless --allow-copyleft
DEFAULT_DENY: FrozenSet[str] = frozenset(
    {
        "gpl-2.0",
        "gpl-3.0",
        "agpl-3.0",
        "lgpl-2.1",
        "lgpl-3.0",
        "sspl-1.0",
        "busl-1.1",
        "proprietary",
        "other",
        "noassertion",
        "none",
    }
)


def normalize_license_id(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    return raw.strip().lower()


def license_allowed(
    spdx_or_key: Optional[str],
    *,
    allow: Optional[FrozenSet[str]] = None,
    deny: Optional[FrozenSet[str]] = None,
    allow_copyleft: bool = False,
    allow_unknown: bool = False,
) -> bool:
    """Return True if this license may be retained."""
    lid = normalize_license_id(spdx_or_key)
    allow_set = allow if allow is not None else DEFAULT_ALLOW
    deny_set = deny if deny is not None else DEFAULT_DENY

    if lid in ("unknown", "none", "noassertion", ""):
        return allow_unknown

    is_copyleft = lid.startswith("gpl") or lid.startswith("agpl") or lid.startswith("lgpl")

    if is_copyleft:
        return bool(allow_copyleft)

    if lid in deny_set:
        return False

    if allow_set and lid in allow_set:
        return True

    # Custom allow list that does not include this id
    if allow_set is not None and allow is not None and lid not in allow_set:
        return False

    return lid not in deny_set
