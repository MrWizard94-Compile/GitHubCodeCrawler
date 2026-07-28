"""Append-only local index of crawled snippets (JSONL)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


@dataclass
class SnippetRecord:
    schema_version: str = "1.0.0"
    id: str = ""
    query: str = ""
    repo_full_name: str = ""
    repo_html_url: str = ""
    repo_stars: int = 0
    path: str = ""
    html_url: str = ""
    git_url: str = ""
    license_spdx: str = ""
    language: str = ""
    score: float = 0.0
    content_sha256_16: str = ""
    content: str = ""
    content_bytes: int = 0
    secret_hits: List[str] = field(default_factory=list)
    kept: bool = True
    drop_reason: str = ""
    crawled_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class JsonlStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_hashes: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    h = obj.get("content_sha256_16")
                    if h:
                        self._seen_hashes.add(h)
                except json.JSONDecodeError:
                    continue

    def has_hash(self, h: str) -> bool:
        return h in self._seen_hashes

    def append(self, record: SnippetRecord) -> None:
        if not record.crawled_at:
            record.crawled_at = utc_now()
        if not record.id:
            record.id = f"snip-{record.content_sha256_16 or content_hash(record.path + record.repo_full_name)}"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        if record.content_sha256_16:
            self._seen_hashes.add(record.content_sha256_16)

    def read_all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out: List[Dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
