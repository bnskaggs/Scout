"""Test the LIKE filter bug."""
import sys
from pathlib import Path
from types import ModuleType
from datetime import date

# Mock yaml module
if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    yaml_stub.safe_load = lambda stream: {}
    sys.modules["yaml"] = yaml_stub

# Mock duckdb module
if "duckdb" not in sys.modules:
    duckdb_stub = ModuleType("duckdb")
    duckdb_stub.connect = lambda path: None
    duckdb_stub.DuckDBPyConnection = object
    duckdb_stub.Error = Exception
    sys.modules["duckdb"] = duckdb_stub

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.planner import build_plan
from app.resolver import PlanResolver, SemanticModel, SemanticDimension, SemanticMetric
import json


class MockExecutor:
    def find_closest_value(self, dimension, value):
        # Return values for non-LIKE filters
        if dimension.name == "area" and value.lower() == "central":
            return "Central"
        # This should NOT be called for LIKE filters (weapon)
        if dimension.name == "weapon":
            print(f"ERROR: find_closest_value called for weapon={value} (LIKE should bypass!)")
            return None
        return value

    def closest_matches(self, dimension, value, limit=5):
        return ["HANDGUN", "RIFLE", "SHOTGUN"]

    def parse_date(self, value):
        return date.fromisoformat(value)


semantic = SemanticModel(
    table="la_crime_raw",
    date_grain="month",
    dimensions={
        "month": SemanticDimension("month", "DATE OCC"),
        "area": SemanticDimension("area", "AREA NAME"),
        "weapon": SemanticDimension("weapon", "Weapon Desc"),
    },
    metrics={
        "incidents": SemanticMetric("incidents", "count", ["month"]),
    },
)

resolver = PlanResolver(semantic, MockExecutor())

# Test the query
plan = build_plan('Incidents involving firearms in Central during 2024-04', prefer_llm=False)

print("Original Plan:")
print(json.dumps(plan, indent=2, default=str))

print("\n" + "="*60 + "\n")

try:
    resolved = resolver.resolve(plan)
    print("Resolved Plan:")
    print(json.dumps(resolved, indent=2, default=str))

    # Check that weapon filter preserved wildcards
    weapon_filters = [f for f in resolved['filters'] if f['field'] == 'weapon']
    assert len(weapon_filters) == 1, "Should have exactly one weapon filter"
    weapon_filter = weapon_filters[0]

    print("\nWeapon Filter:")
    print(f"  op: {weapon_filter['op']}")
    print(f"  value: {weapon_filter['value']}")

    assert weapon_filter['op'] == 'like_any', f"Expected op='like_any', got '{weapon_filter['op']}'"
    assert isinstance(weapon_filter['value'], list), "Value should be a list"
    assert '%firearm%' in weapon_filter['value'], "Should contain '%firearm%' pattern"

    print("\nPASS: LIKE filter preserved correctly!")

    # Now test SQL generation
    from app import sql_builder

    sql = sql_builder.build(resolved, semantic)
    print("\nGenerated SQL:")
    print(sql)

    # Check that SQL contains LIKE clauses
    assert "LIKE" in sql.upper(), "SQL should contain LIKE operator"
    assert "%firearm%" in sql.lower() or "%gun%" in sql.lower(), "SQL should contain wildcard patterns"

    print("\nPASS: SQL generation includes LIKE clauses!")

except Exception as e:
    print(f"\nFAIL: {e}")
    import traceback
    traceback.print_exc()
