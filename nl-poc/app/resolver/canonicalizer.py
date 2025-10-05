"""Canonical value resolution helpers."""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Dict, Optional


@dataclass(frozen=True)
class CanonicalResolution:
    value: object
    applied: bool
    like_bypass: bool
    canonical: Optional[str] = None
    synonym: Optional[str] = None


class Canonicalizer:
    """Resolve raw dimension values using canonical_map entries."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._version: int = 0
        self._mappings: Dict[str, Dict[str, Dict[str, float]]] = {}

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def load(self, mappings: Dict[str, Dict[str, Dict[str, float]]], version: int) -> None:
        with self._lock:
            self._mappings = {dim: dict(entries) for dim, entries in mappings.items()}
            self._version = int(version)

    def resolve(self, dim: str, raw: object) -> CanonicalResolution:
        if not isinstance(raw, str):
            return CanonicalResolution(value=raw, applied=False, like_bypass=False)
        token = raw.strip()
        if not token:
            return CanonicalResolution(value=raw, applied=False, like_bypass=False)
        like_bypass = "%" in token
        if like_bypass:
            return CanonicalResolution(value=raw, applied=False, like_bypass=True)
        lookup = self._get_dim_map(dim)
        normalised = _normalise(token)
        entry = lookup.get(normalised)
        if not entry:
            return CanonicalResolution(value=raw, applied=False, like_bypass=False)
        canonical = entry.get("canonical") or raw
        return CanonicalResolution(
            value=canonical,
            applied=True,
            like_bypass=False,
            canonical=canonical,
            synonym=token,
        )

    # ------------------------------------------------------------------
    def _get_dim_map(self, dim: str) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return dict(self._mappings.get(dim, {}))


def _normalise(value: str) -> str:
    return value.strip().lower()
