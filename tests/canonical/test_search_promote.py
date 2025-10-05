import time

from app.canonical.store import CanonicalStore
from app.canonical.watcher import CanonicalWatcher
from app.resolver import PlanResolver
from app.resolver.canonicalizer import Canonicalizer


def test_search_and_promote(make_store, games_semantic, executor):
    store: CanonicalStore = make_store(games_semantic)
    canonicalizer = Canonicalizer()
    canonicalizer.load(store.load_mappings(), store.get_version())
    resolver = PlanResolver(games_semantic, executor, canonicalizer=canonicalizer)

    results = store.search("title", "mk")
    assert results, "Expected fuzzy search to return at least one candidate"
    target = next(candidate for candidate in results if "mortal kombat" in candidate.candidate.lower())

    before_version = store.get_version()
    new_version = store.promote("title", "MK1", target.candidate, target.score, promoted_by="pytest")
    assert new_version == before_version + 1

    canonicalizer.load(store.load_mappings(), new_version)
    resolution = canonicalizer.resolve("title", "mk1")
    assert resolution.applied
    assert resolution.value == target.candidate

    plan = {"metrics": ["count"], "filters": [{"field": "title", "op": "=", "value": "MK1"}]}
    resolved = resolver.resolve(plan)
    assert resolved["filters"][0]["value"] == target.candidate
    assert resolved["canonicalization"]["applied"] is True


def test_hot_reload_watcher(make_store, crime_semantic, executor):
    store: CanonicalStore = make_store(crime_semantic)
    canonicalizer = Canonicalizer()
    watcher = CanonicalWatcher(store, canonicalizer, interval=0.1)
    watcher.start()
    try:
        resolver = PlanResolver(crime_semantic, executor, canonicalizer=canonicalizer)
        canonicalizer.load(store.load_mappings(), store.get_version())
        plan = {"metrics": ["count"], "filters": [{"field": "area", "op": "=", "value": "Downtown"}]}
        resolved = resolver.resolve(plan)
        assert resolved["filters"][0]["value"] == "Downtown"
        assert resolved["canonicalization"]["applied"] is False

        version = store.promote("area", "Downtown", "Central", 0.92)
        for _ in range(30):
            if canonicalizer.version >= version:
                break
            time.sleep(0.1)
        refreshed = resolver.resolve(plan)
        assert refreshed["filters"][0]["value"] == "Central"
        assert refreshed["canonicalization"]["applied"] is True
    finally:
        watcher.stop()
