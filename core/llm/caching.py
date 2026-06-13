"""Disk-caching provider wrapper: memoizes complete_json by (model, system, user).

At temperature 0 every call is deterministic, so a cached run replays instantly —
this is what makes the real-model benches cheap to re-run. Wraps any LLMProvider.
"""

import hashlib
import json
from pathlib import Path

from core.llm.provider import LLMProvider


class CachingProvider:
    def __init__(self, inner: LLMProvider, cache_dir: Path, *, enabled: bool = True) -> None:
        self._inner = inner
        self._dir = cache_dir
        self._enabled = enabled
        self.model = getattr(inner, "model", "unknown")

    def _key(self, system: str, user: str) -> str:
        raw = f"{self.model}\x00{system}\x00{user}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def complete_json(self, system: str, user: str) -> dict:
        path = self._dir / f"{self._key(system, user)}.json"
        if self._enabled and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        out = self._inner.complete_json(system, user)
        self._dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out), encoding="utf-8")
        return out
