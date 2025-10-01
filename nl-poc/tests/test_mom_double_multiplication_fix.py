"""Test that MoM change_pct is not double-multiplied by 100."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.planner import build_plan_rule_based
from app.resolver import load_semantic_model
from app.sql_builder import build as build_sql
import duckdb
import re

print("=" * 70)
print("MoM CHANGE_PCT DOUBLE MULTIPLICATION FIX TEST")
print("=" * 70)

# Test query
query = "Show crime types month over month for 2024-05"

print(f"\nQuery: {query}\n")

# Build plan
print("[1] PLAN:")
plan = build_plan_rule_based(query)
compare = plan.get('compare')
print(f"    Compare: {compare}")

# Build SQL
print("\n[2] SQL:")
semantic = load_semantic_model(Path(__file__).parent.parent / "config" / "semantic.yml")
sql = build_sql(plan, semantic)

# Check if SQL multiplies by 100
if "* 100" in sql or "* 100.0" in sql:
    print("    SQL contains: * 100 (good - SQL does the multiplication)")
else:
    print("    WARNING: SQL does NOT multiply by 100!")

# Print the change_pct formula
match = re.search(r'CASE.*?END AS change_pct', sql, re.DOTALL)
if match:
    formula = match.group(0).replace('\n', ' ')
    print(f"\n    Formula: {formula[:150]}...")

# Execute and check results
print("\n[3] EXECUTING SQL...")
db_path = Path(__file__).parent.parent / "data" / "games.duckdb"
conn = duckdb.connect(str(db_path), read_only=True)

try:
    result = conn.execute(sql).fetchall()
    print(f"    Returned {len(result)} rows")

    if result:
        # Show first few rows
        print("\n[4] SAMPLE RESULTS (change_pct from SQL):")
        for i, row in enumerate(result[:5], 1):
            # Assuming structure: (crime_type, incidents, change_pct, month)
            if len(row) >= 3:
                crime_type = row[0] if len(row) > 0 else "?"
                incidents = row[1] if len(row) > 1 else "?"
                change_pct = row[2] if len(row) > 2 else None
                print(f"    {i}. {crime_type}: {incidents} incidents, change_pct={change_pct}")

                # Check if percentage is reasonable
                if change_pct is not None:
                    if abs(change_pct) > 1000:
                        print(f"       WARNING: {change_pct}% seems very high!")
                    elif abs(change_pct) > 10000:
                        print(f"       ERROR: {change_pct}% is likely double-multiplied!")

finally:
    conn.close()

print("\n" + "=" * 70)
print("DIAGNOSIS:")
print("=" * 70)
print("\nExpected behavior:")
print("  - SQL formula: (current - prior) / prior * 100")
print("  - Returns values like: 50 (for 50% increase), 900 (for 900% increase)")
print("  - viz.py should NOT multiply by 100 again")
print("  - main.py should NOT multiply by 100 again")
print("\nIf change_pct values are:")
print("  - Between -100 and 1000: Probably correct")
print("  - Above 10,000: Likely double multiplication bug")
print("  - Between 1000-10,000: Could be correct for dramatic changes")
print("=" * 70)

# Test the formatting functions
print("\n[5] TESTING FORMAT FUNCTIONS:")
from app.main import _format_change_pct
from app.viz import build_narrative

# Simulate data with change_pct already multiplied by 100 (from SQL)
test_records = [
    {"crime_type": "BURGLARY", "incidents": 100, "change_pct": 50.0},  # 50% increase
    {"crime_type": "THEFT", "incidents": 200, "change_pct": -25.5},  # 25.5% decrease
    {"crime_type": "ASSAULT", "incidents": 150, "change_pct": 900.0},  # 900% increase
]

print("\n  Input (change_pct already * 100 from SQL):")
for rec in test_records:
    print(f"    {rec}")

formatted = _format_change_pct(test_records)
print("\n  After _format_change_pct():")
for rec in formatted:
    print(f"    {rec['crime_type']}: change_pct={rec['change_pct']}, "
          f"formatted='{rec.get('change_pct_formatted', 'N/A')}'")

    # Check for double multiplication
    if 'change_pct_formatted' in rec:
        formatted_val = rec['change_pct_formatted']
        numeric_part = formatted_val.replace('%', '').replace('+', '').replace('-', '')
        try:
            numeric = float(numeric_part)
            if abs(numeric) > 10000:
                print(f"       ERROR: {formatted_val} suggests double multiplication!")
        except ValueError:
            pass

# Test narrative
test_plan = {
    "group_by": ["crime_type"],
    "metrics": ["incidents"],
    "compare": {"type": "mom"},
    "order_by": []
}

narrative = build_narrative(test_plan, test_records)
print(f"\n  Narrative: {narrative}")

# Check narrative for unreasonable percentages
if "9000%" in narrative or "90000%" in narrative:
    print("       ERROR: Narrative shows double-multiplied percentage!")
elif "900%" in narrative:
    print("       OK: 900% is shown correctly (not 90000%)")

print("\n" + "=" * 70)
print("PASS: If formatted values are reasonable (50%, 900%, not 5000% or 90000%)")
print("=" * 70)
