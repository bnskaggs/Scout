import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.planner import build_plan_rule_based


def test_compare_year_vs_year_sets_time_mode():
    plan = build_plan_rule_based("Compare assaults in 2023 vs 2024")
    compare = plan.get("compare")
    assert compare is not None
    assert compare.get("mode") == "time"
    assert compare.get("lhs_time") == "2023-01-01/2024-01-01"
    assert compare.get("rhs_time") == "2024-01-01/2025-01-01"


def test_compare_quarter_vs_quarter_sets_time_mode():
    plan = build_plan_rule_based("Compare incidents Q1 2024 vs Q1 2023")
    compare = plan.get("compare")
    assert compare is not None
    assert compare.get("mode") == "time"
    assert compare.get("lhs_time") == "2024-01-01/2024-04-01"
    assert compare.get("rhs_time") == "2023-01-01/2023-04-01"


def test_compare_dimension_values_detects_dimension_mode():
    plan = build_plan_rule_based("Compare assaults in Hollywood vs Wilshire in 2024")
    compare = plan.get("compare")
    assert compare is not None
    assert compare.get("mode") == "dimension"
    assert compare.get("dimension") == "area"
    diagnostics = (plan.get("extras") or {}).get("diagnostics", [])
    assert any(d.get("type") == "ambiguous_compare" for d in diagnostics)


def test_ambiguous_compare_returns_diagnostic():
    plan = build_plan_rule_based("Compare assaults in 2023 vs Hollywood")
    diagnostics = (plan.get("extras") or {}).get("diagnostics", [])
    assert any(d.get("type") == "ambiguous_compare" for d in diagnostics)
    compare = plan.get("compare")
    assert compare is not None
    assert compare.get("mode") == "dimension"
