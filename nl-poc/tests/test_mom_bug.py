"""Test the specific MoM bug query."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.planner import build_plan
import json

plan = build_plan('What premises in Hollywood had the biggest drop MoM in 2024-07?', prefer_llm=False)
print("Plan:")
print(json.dumps(plan, indent=2, default=str))

# Check filters
filters = plan['filters']
print("\nFilters check:")
print(f"  - Month filter: {[f for f in filters if f['field'] == 'month']}")
print(f"  - Area filter: {[f for f in filters if f['field'] == 'area']}")

# Check compare
compare = plan.get('compare')
print(f"\nCompare: {compare}")

# Verify
assert any(f['field'] == 'month' and f['value'] == '2024-07-01' for f in filters), "Missing correct month filter"
area_filters = [f for f in filters if f['field'] == 'area']
assert len(area_filters) == 1, f"Expected 1 area filter, got {len(area_filters)}"
assert area_filters[0]['value'] == 'Hollywood', f"Expected 'Hollywood', got '{area_filters[0]['value']}'"
assert compare is not None, "Missing compare"
assert compare['type'] == 'mom', "Compare type should be 'mom'"
assert 'internal_window' in compare, "Missing internal_window in compare"
assert compare['internal_window']['value'] == ['2024-06-01', '2024-08-01'], "Wrong internal window"

print("\nAll checks passed!")
