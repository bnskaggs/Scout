"""Test what happens when NO time range is specified."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.planner import build_plan_rule_based
from app.resolver import load_semantic_model
from app.sql_builder import build as build_sql

print("=" * 70)
print("DEFAULT TIME RANGE TEST")
print("=" * 70)

# Queries with NO explicit time
test_queries = [
    "Show me incidents by area",
    "Top 10 areas by incidents",
    "Trend of incidents",
    "What are the top crime types",
]

semantic = load_semantic_model(Path(__file__).parent.parent / "config" / "semantic.yml")

for i, query in enumerate(test_queries, 1):
    print(f"\n{'='*70}")
    print(f"TEST {i}: {query}")
    print('='*70)

    # Build plan
    print("\n[1] PLAN:")
    plan = build_plan_rule_based(query)
    filters = plan.get('filters', [])
    group_by = plan.get('group_by', [])

    print(f"    Group by: {group_by}")
    print(f"    Filters: {filters}")

    # Check month filters
    month_filters = [f for f in filters if f.get('field') == 'month']
    if month_filters:
        print(f"\n[2] DEFAULT MONTH FILTER ADDED:")
        for mf in month_filters:
            value = mf.get('value')
            print(f"    {mf}")
            if isinstance(value, list) and len(value) >= 2:
                start, end = value[0], value[1]
                if '2023' in start:
                    print(f"    WARNING: Default starts with 2023!")
                    print(f"    Expected: Should start with 2024-10 (12 months ago from 2025-10)")
                elif '2024' in start:
                    # Check if it's 2024-10
                    if '2024-10' in start:
                        print(f"    OK: Default correctly uses last 12 months (2024-10 to 2025-11)")
                    else:
                        print(f"    Check: Default uses 2024 but not 2024-10")
    else:
        print(f"\n[2] NO DEFAULT TIME FILTER")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("\nIf trend queries default to 2023 instead of last 12 months,")
print("that's the bug!")
print("=" * 70)
