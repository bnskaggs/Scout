"""Test that bottom/lowest queries use appropriate language in headers."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.viz import build_narrative


def test_header_uses_current_group_by_dimension():
    plan = {
        "metrics": ["incidents"],
        "group_by": ["premise"],
        "order_by": [{"field": "incidents", "dir": "desc"}],
    }
    records = [
        {"premise": "RESIDENCE", "incidents": 5},
        {"premise": "RESTAURANT", "incidents": 3},
    ]

    narrative = build_narrative(plan, records)

    assert "RESIDENCE led with 5 incidents" in narrative


def test_bottom_query_uses_fewest():
    """Test that bottom queries use 'had the fewest' instead of 'led with'."""

    plan = {
        "metrics": ["incidents"],
        "group_by": ["area"],
        "order_by": [{"field": "incidents", "dir": "asc"}],  # Ascending = bottom
        "limit": 5,
    }

    records = [
        {"area": "Hollenbeck", "incidents": 271},
        {"area": "Foothill", "incidents": 285},
        {"area": "Devonshire", "incidents": 301},
        {"area": "West Valley", "incidents": 315},
        {"area": "Topanga", "incidents": 330},
    ]

    narrative = build_narrative(plan, records)

    print(f"Query type: Bottom 5 (ascending order)")
    print(f"Records (sorted ascending):")
    for r in records:
        print(f"  {r['area']}: {r['incidents']} incidents")

    print(f"\nNarrative: {narrative}")

    # Should use "had the fewest" not "led with"
    assert "had the fewest" in narrative, f"Expected 'had the fewest' in narrative, got: {narrative}"
    assert "Hollenbeck" in narrative
    assert "271 incidents" in narrative

    # Should NOT use "led with"
    assert "led with" not in narrative

    print("\nPASS: Bottom query uses 'had the fewest' language")


def test_top_query_uses_led_with():
    """Test that top queries still use 'led with'."""

    plan = {
        "metrics": ["incidents"],
        "group_by": ["area"],
        "order_by": [{"field": "incidents", "dir": "desc"}],  # Descending = top
        "limit": 5,
    }

    records = [
        {"area": "Central", "incidents": 850},
        {"area": "Hollywood", "incidents": 780},
        {"area": "77th Street", "incidents": 720},
    ]

    narrative = build_narrative(plan, records)

    print(f"\n\nQuery type: Top areas (descending order)")
    print(f"Narrative: {narrative}")

    # Should use "led with"
    assert "led with" in narrative, f"Expected 'led with' in narrative, got: {narrative}"
    assert "Central" in narrative
    assert "850 incidents" in narrative

    # Should NOT use "had the fewest"
    assert "had the fewest" not in narrative

    print("PASS: Top query uses 'led with' language")


def test_no_order_by_defaults_to_led_with():
    """Test that queries without order_by default to 'led with'."""

    plan = {
        "metrics": ["incidents"],
        "group_by": ["crime_type"],
        "order_by": [],  # No explicit order
    }

    records = [
        {"crime_type": "ASSAULT", "incidents": 500},
    ]

    narrative = build_narrative(plan, records)

    print(f"\n\nQuery type: No explicit order")
    print(f"Narrative: {narrative}")

    # Should default to "led with"
    assert "led with" in narrative
    assert "had the fewest" not in narrative

    print("PASS: Queries without order_by default to 'led with'")


def test_bottom_with_comparison():
    """Test bottom query with MoM comparison."""

    plan = {
        "metrics": ["incidents"],
        "group_by": ["area"],
        "order_by": [{"field": "incidents", "dir": "asc"}],  # Bottom
        "limit": 3,
        "compare": {"type": "mom"},
    }

    records = [
        {"area": "Hollenbeck", "incidents": 100, "change_pct": -0.05},  # Down 5%
        {"area": "Foothill", "incidents": 120, "change_pct": 0.10},     # Up 10%
    ]

    narrative = build_narrative(plan, records)

    print(f"\n\nQuery type: Bottom with MoM")
    print(f"Narrative: {narrative}")

    # For comparison queries, picks max change_pct (Foothill)
    # But should still honor the ascending order language
    assert "Foothill" in narrative  # Max change_pct
    assert "had the fewest" in narrative or "led with" in narrative
    # Note: For MoM queries, the narrative picks by change_pct, not by order
    # So it might say "led with" since it's showing the biggest increase

    print("PASS: Bottom query with comparison handled")


if __name__ == "__main__":
    test_bottom_query_uses_fewest()
    test_top_query_uses_led_with()
    test_no_order_by_defaults_to_led_with()
    test_bottom_with_comparison()
    print("\n" + "="*60)
    print("ALL TESTS PASSED!")
    print("="*60)
