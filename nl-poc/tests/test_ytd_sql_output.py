"""Test to see actual SQL generated for YTD query and what data it returns."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.planner import build_plan_rule_based
from app.resolver import load_semantic_model
from app.sql_builder import build as build_sql
import duckdb

print("=" * 70)
print("YTD SQL GENERATION TEST")
print("=" * 70)

# Test query
query = "Show me incidents YTD"

print(f"\nQuery: {query}\n")

# Build plan
print("[1] PLAN:")
plan = build_plan_rule_based(query)
filters = plan.get('filters', [])
for f in filters:
    if f.get('field') == 'month':
        print(f"    Month filter: {f}")

# Build SQL
print("\n[2] SQL:")
semantic = load_semantic_model(Path(__file__).parent.parent / "config" / "semantic.yml")
sql = build_sql(plan, semantic)
print(sql)

# Execute and see results
print("\n[3] EXECUTING SQL...")
db_path = Path(__file__).parent.parent / "data" / "games.duckdb"
conn = duckdb.connect(str(db_path), read_only=True)

try:
    result = conn.execute(sql).fetchall()
    print(f"    Returned {len(result)} rows")
    if result:
        # Show first few rows
        print("\n[4] SAMPLE RESULTS:")
        for row in result[:10]:
            print(f"    {row}")
    else:
        print("\n[4] NO RESULTS RETURNED!")

    # Now check what we would get if we query 2025 data directly
    print("\n[5] MANUAL CHECK - Querying 2025 data directly:")
    direct_sql = """
        WITH base AS (SELECT DATE_TRUNC('month', "DATE OCC") AS month, * FROM la_crime_raw)
        SELECT month, COUNT(*) as incidents
        FROM base
        WHERE base.month >= DATE '2025-01-01' AND base.month < DATE '2025-11-01'
        GROUP BY month
        ORDER BY month
    """
    direct_result = conn.execute(direct_sql).fetchall()
    print(f"    Found {len(direct_result)} months with data:")
    for row in direct_result:
        print(f"    {row}")

    if not direct_result:
        print("    NO 2025 DATA FOUND in database!")

finally:
    conn.close()

print("\n" + "=" * 70)
print("DIAGNOSIS:")
print("=" * 70)

if filters:
    month_filter = [f for f in filters if f.get('field') == 'month'][0]
    value = month_filter.get('value')
    if isinstance(value, list) and len(value) >= 2:
        start, end = value[0], value[1]
        if '2025' in start:
            print("- Filter is correctly set to 2025")
            if result:
                print(f"- SQL returned {len(result)} rows")
                print("- CHECK: Are these rows actually from 2025 or 2023?")
            else:
                print("- But SQL returned NO DATA")
                print("- This means database has no data for 2025-01 to 2025-11")
        elif '2023' in start:
            print(f"ERROR: Filter is set to 2023, not 2025!")
            print(f"  Filter value: {value}")
            print("  This is the BUG!")

print("=" * 70)
