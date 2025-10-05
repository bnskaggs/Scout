"""Background watcher that keeps canonical caches in sync."""
from __future__ import annotations

import threading
from typing import Optional

from .store import CanonicalStore
from ..resolver.canonicalizer import Canonicalizer


class CanonicalWatcher:
    """Poll the canonical_map version and refresh caches on change."""

    def __init__(
        self,
        store: CanonicalStore,
        canonicalizer: Canonicalizer,
        *,
        interval: float = 2.0,
    ) -> None:
        self._store = store
        self._canonicalizer = canonicalizer
        self._interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._initial_load()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="canonical-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=self._interval * 2)
        self._thread = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _initial_load(self) -> None:
        version = self._store.get_version()
        mappings = self._store.load_mappings()
        self._canonicalizer.load(mappings, version)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            version = self._store.get_version()
            if version == self._canonicalizer.version:
                continue
            mappings = self._store.load_mappings()
            self._canonicalizer.load(mappings, version)
