"""Test COMPARE YTD query - this is likely where the bug is."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.planner import build_plan_rule_based
from app.resolver import load_semantic_model
from app.sql_builder import build as build_sql
import duckdb

print("=" * 70)
print("COMPARE YTD SQL GENERATION TEST")
print("=" * 70)

# Test comparison YTD queries
test_queries = [
    "Compare incidents 2023 vs 2024 YTD",
    "Show me 2024 YTD incidents",
    "Show me incidents for 2024 YTD",
]

semantic = load_semantic_model(Path(__file__).parent.parent / "config" / "semantic.yml")
db_path = Path(__file__).parent.parent / "data" / "games.duckdb"
conn = duckdb.connect(str(db_path), read_only=True)

for i, query in enumerate(test_queries, 1):
    print(f"\n{'='*70}")
    print(f"TEST {i}: {query}")
    print('='*70)

    # Build plan
    print("\n[1] PLAN:")
    plan = build_plan_rule_based(query)
    filters = plan.get('filters', [])
    print(f"    Filters: {filters}")

    # Check month filters
    month_filters = [f for f in filters if f.get('field') == 'month']
    if month_filters:
        print(f"\n[2] MONTH FILTER:")
        for mf in month_filters:
            value = mf.get('value')
            print(f"    {mf}")
            if isinstance(value, list) and len(value) >= 2:
                start, end = value[0], value[1]
                if '2023' in start and '2024' not in start:
                    print(f"    ERROR: Filter starts with 2023, not 2024!")
                    print(f"    This is likely the BUG!")
                elif '2024' in start:
                    print(f"    OK: Filter correctly uses 2024")

    # Build SQL
    print("\n[3] SQL:")
    sql = build_sql(plan, semantic)
    print(sql[:500])  # First 500 chars
    if len(sql) > 500:
        print("...")

    # Check SQL for year references
    if '2023' in sql:
        # Count occurrences
        count_2023 = sql.count('2023')
        count_2024 = sql.count('2024')
        print(f"\n[4] SQL YEAR CHECK:")
        print(f"    '2023' appears {count_2023} times")
        print(f"    '2024' appears {count_2024} times")

        if 'vs 2024 YTD' in query and count_2023 > 0 and count_2024 == 0:
            print(f"    ERROR: Query asks for 2024 YTD but SQL only has 2023!")

conn.close()

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("\nIf any test shows '2023' in SQL when query asks for '2024 YTD',")
print("that's the bug we need to fix!")
print("=" * 70)
