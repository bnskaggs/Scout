from app.canonical.store import CanonicalStore


def test_threshold_filtering(make_store, crime_semantic):
    store: CanonicalStore = make_store(crime_semantic)
    results = store.search("area", "cent")
    assert results, "Expected Central to appear in fuzzy results"
    top_three = results[:3]
    assert any(candidate.candidate == "Central" and candidate.score >= 0.8 for candidate in top_three)
    assert all(candidate.score >= 0.7 for candidate in results)
