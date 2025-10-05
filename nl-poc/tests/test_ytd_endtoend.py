"""End-to-end test for YTD query to see what SQL and data is returned."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.planner import build_plan_rule_based
from app.resolver import load_semantic_model, PlanResolver
from app.sql_builder import build as build_sql
from app.executor import DuckDBExecutor
from datetime import date
from pathlib import Path

print("=" * 70)
print("END-TO-END YTD TEST")
print("=" * 70)

# Test query
query = "Show me incidents YTD"

print(f"\n[1] INPUT QUERY: {query}")

# Build plan
print("\n[2] BUILDING PLAN...")
plan = build_plan_rule_based(query)
print(f"    Filters: {plan.get('filters')}")
print(f"    Group by: {plan.get('group_by')}")

# Resolve plan
print("\n[3] RESOLVING PLAN...")
semantic_path = Path(__file__).parent.parent / "config" / "semantic.yml"
semantic = load_semantic_model(semantic_path)
db_path = Path(__file__).parent.parent / "data" / "games.duckdb"
executor = DuckDBExecutor(db_path)
resolver = PlanResolver(semantic, executor)
resolved, suggestions = resolver.resolve(plan)
print(f"    Resolved filters: {resolved.get('filters')}")
print(f"    Suggestions: {suggestions}")

# Build SQL
print("\n[4] BUILDING SQL...")
sql = build_sql(resolved, semantic)
print(f"    SQL:\n{sql}")

# Check what the month filter actually is
month_filters = [f for f in resolved.get('filters', []) if f.get('field') == 'month']
print(f"\n[5] MONTH FILTERS:")
for mf in month_filters:
    print(f"    {mf}")

print("\n" + "=" * 70)
print("DIAGNOSIS:")
print("=" * 70)
if month_filters:
    mf = month_filters[0]
    value = mf.get('value')
    if isinstance(value, list) and len(value) >= 2:
        start, end = value[0], value[1]
        print(f"✓ Month filter correctly set: {start} to {end}")
        if "2025" in str(start):
            print(f"✓ Start year is 2025 (correct!)")
        else:
            print(f"✗ Start year is NOT 2025: {start}")

        print("\nLikely cause: Database only has data up to 2023")
        print("When SQL runs with WHERE month >= '2025-01-01', it returns no rows")
        print("or perhaps the data exists but with 2023 dates.")
    else:
        print(f"Month filter value: {value}")
else:
    print("No month filter found!")

print("\n" + "=" * 70)
