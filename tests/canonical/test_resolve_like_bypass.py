from app.canonical.store import CanonicalStore
from app.resolver import PlanResolver
from app.resolver.canonicalizer import Canonicalizer


def test_like_bypass_flag(make_store, crime_semantic, executor):
    store: CanonicalStore = make_store(crime_semantic)
    canonicalizer = Canonicalizer()
    canonicalizer.load(store.load_mappings(), store.get_version())
    resolver = PlanResolver(crime_semantic, executor, canonicalizer=canonicalizer)

    plan = {
        "metrics": ["count"],
        "filters": [
            {"field": "weapon", "op": "like", "value": "%firearm%"},
        ],
    }
    resolved = resolver.resolve(plan)
    assert resolved["filters"][0]["value"] == "%firearm%"
    meta = resolved.get("canonicalization")
    assert meta["like_bypass"] is True
    assert meta["applied"] is False
