"""Test that MoM header picks the highest change_pct, not highest count."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.viz import build_narrative


def test_mom_header_picks_max_change():
    """Test that MoM queries pick the row with highest change_pct for header."""

    plan = {
        "metrics": ["incidents"],
        "group_by": ["crime_type"],
        "compare": {"type": "mom"},
    }

    # Records sorted by incidents (descending), NOT by change_pct
    records = [
        {
            "crime_type": "VEHICLE - STOLEN",
            "incidents": 2183,
            "change_pct": -0.018,  # Down 1.8% (negative!)
        },
        {
            "crime_type": "BATTERY - SIMPLE ASSAULT",
            "incidents": 1450,
            "change_pct": 0.05,  # Up 5%
        },
        {
            "crime_type": "BURGLARY",
            "incidents": 850,
            "change_pct": 0.25,  # Up 25% (HIGHEST change!)
        },
        {
            "crime_type": "THEFT",
            "incidents": 1200,
            "change_pct": 0.12,  # Up 12%
        },
    ]

    narrative = build_narrative(plan, records)

    print(f"Plan: MoM comparison, group by crime_type")
    print(f"\nRecords (sorted by incidents):")
    for r in records:
        print(f"  {r['crime_type']}: {r['incidents']} incidents, change_pct={r['change_pct']:.1%}")

    print(f"\nNarrative: {narrative}")

    # Should pick BURGLARY (highest change_pct = 0.25)
    assert "BURGLARY" in narrative, f"Expected BURGLARY in narrative, got: {narrative}"
    assert "850 incidents" in narrative
    assert "up" in narrative.lower()
    assert "25" in narrative  # 25% change

    # Should NOT pick VEHICLE - STOLEN even though it has highest incidents
    assert "VEHICLE - STOLEN" not in narrative
    assert "2183" not in narrative

    print("\nPASS: Header correctly picks crime type with highest MoM increase (BURGLARY)")


def test_mom_header_handles_negative_changes():
    """Test that header picks max change even if all changes are negative."""

    plan = {
        "metrics": ["incidents"],
        "group_by": ["area"],
        "compare": {"type": "mom"},
    }

    # All negative changes - should pick the least negative (closest to 0)
    records = [
        {"area": "Central", "incidents": 500, "change_pct": -0.30},  # Down 30%
        {"area": "Hollywood", "incidents": 400, "change_pct": -0.05},  # Down 5% (least negative!)
        {"area": "West LA", "incidents": 350, "change_pct": -0.15},  # Down 15%
    ]

    narrative = build_narrative(plan, records)

    print(f"\n\nAll negative changes test:")
    print(f"Records:")
    for r in records:
        print(f"  {r['area']}: change_pct={r['change_pct']:.1%}")

    print(f"\nNarrative: {narrative}")

    # Should pick Hollywood (least negative = -0.05)
    assert "Hollywood" in narrative
    assert "down 5" in narrative.lower() or "down" in narrative.lower()

    print("PASS: Header picks least negative change when all are negative")


def test_non_comparison_uses_first_record():
    """Test that non-comparison queries still use first record."""

    plan = {
        "metrics": ["incidents"],
        "group_by": ["area"],
        "compare": None,  # No comparison
    }

    records = [
        {"area": "Central", "incidents": 500},
        {"area": "Hollywood", "incidents": 400},
    ]

    narrative = build_narrative(plan, records)

    print(f"\n\nNon-comparison test:")
    print(f"Narrative: {narrative}")

    # Should use first record (Central)
    assert "Central" in narrative
    assert "500 incidents" in narrative

    print("PASS: Non-comparison queries use first record")


def test_null_change_pct_handled():
    """Test that records with null change_pct are skipped."""

    plan = {
        "metrics": ["incidents"],
        "group_by": ["crime_type"],
        "compare": {"type": "mom"},
    }

    records = [
        {"crime_type": "Type A", "incidents": 100, "change_pct": None},  # No prior data
        {"crime_type": "Type B", "incidents": 80, "change_pct": 0.15},  # Up 15%
        {"crime_type": "Type C", "incidents": 90, "change_pct": None},
    ]

    narrative = build_narrative(plan, records)

    print(f"\n\nNull change_pct test:")
    print(f"Narrative: {narrative}")

    # Should pick Type B (only non-null change_pct)
    assert "Type B" in narrative
    assert "80 incidents" in narrative
    assert "up" in narrative.lower()

    print("PASS: Null change_pct records are skipped")


if __name__ == "__main__":
    test_mom_header_picks_max_change()
    test_mom_header_handles_negative_changes()
    test_non_comparison_uses_first_record()
    test_null_change_pct_handled()
    print("\n" + "="*60)
    print("ALL TESTS PASSED!")
    print("="*60)
