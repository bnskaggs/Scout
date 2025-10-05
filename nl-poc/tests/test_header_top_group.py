"""Tests for header selection logic using validated result rows."""
from pathlib import Path
import sys


sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.viz import build_narrative  # noqa: E402


def _base_plan():
    return {
        "metrics": ["count"],
        "group_by": ["premise"],
        "order_by": [{"field": "count", "dir": "desc"}],
        "compileInfo": {"metricAlias": "count", "groupBy": ["premise"]},
    }


def test_header_uses_top_group_from_sorted_rows():
    plan = _base_plan()
    rows = [
        {"premise": "STREET", "count": 254},
        {"premise": "SINGLE FAMILY DWELLING", "count": 45},
        {"premise": "VEHICLE, PASSENGER/TRUCK", "count": 32},
    ]

    narrative = build_narrative(plan, rows)

    assert narrative == "STREET led with 254 incidents."


def test_header_sorts_rows_locally_when_needed():
    plan = _base_plan()
    rows = [
        {"premise": "VEHICLE, PASSENGER/TRUCK", "count": 32},
        {"premise": "STREET", "count": 254},
        {"premise": "SINGLE FAMILY DWELLING", "count": 45},
    ]

    narrative = build_narrative(plan, rows)

    assert narrative == "STREET led with 254 incidents."
    diagnostics = plan.get("diagnostics", [])
    assert any(d.get("type") == "header_local_sort" for d in diagnostics)


def test_metric_only_falls_back_to_total_header():
    plan = {
        "metrics": ["incidents"],
        "group_by": [],
        "compileInfo": {"metricAlias": "incidents", "groupBy": []},
    }
    rows = [{"incidents": 254}]

    narrative = build_narrative(plan, rows)

    assert narrative == "Total incidents: 254."
