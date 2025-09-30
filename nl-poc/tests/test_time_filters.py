import sys
from datetime import date, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

from zoneinfo import ZoneInfo

if "yaml" not in sys.modules:
    yaml_stub = ModuleType("yaml")
    yaml_stub.safe_load = lambda data: {}
    sys.modules["yaml"] = yaml_stub

if "duckdb" not in sys.modules:
    duckdb_stub = ModuleType("duckdb")
    duckdb_stub.Error = Exception
    duckdb_stub.DuckDBPyConnection = object
    duckdb_stub.connect = lambda path: None
    sys.modules["duckdb"] = duckdb_stub

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.sql_builder import _build_filters
from app.time_utils import extract_time_range


def _semantic_model():
    month_dimension = SimpleNamespace(name="month", column="DATE OCC", dtype="date")
    return SimpleNamespace(
        table="la_crime_raw",
        date_grain="month",
        dimensions={"month": month_dimension},
        metrics={},
    )


def test_extract_time_range_single_month_filter():
    time_range = extract_time_range("Incidents for 2023-06")
    assert time_range is not None
    assert time_range.start == date(2023, 6, 1)
    assert time_range.end == date(2023, 6, 1)
    assert time_range.op == "="

    where_clause = _build_filters([time_range.to_filter()], _semantic_model(), alias="base")
    assert where_clause == "WHERE base.month = DATE '2023-06-01'"


def test_extract_time_range_quarter_between_filter():
    time_range = extract_time_range("Q1 2024")
    assert time_range is not None
    assert time_range.start == date(2024, 1, 1)
    assert time_range.end == date(2024, 4, 1)
    assert time_range.label == "Q1 2024"

    where_clause = _build_filters([time_range.to_filter()], _semantic_model(), alias="base")
    assert (
        where_clause
        == "WHERE base.month >= DATE '2024-01-01' AND base.month < DATE '2024-04-01'"
    )


def test_extract_time_range_past_nine_months_uses_chicago_today():
    utc_now = datetime(2024, 3, 1, 3, 0, tzinfo=ZoneInfo("UTC"))
    chicago_today = utc_now.astimezone(ZoneInfo("America/Chicago")).date()

    time_range = extract_time_range("past 9 months", today=chicago_today)
    assert time_range is not None
    assert time_range.start == date(2023, 6, 1)
    assert time_range.end == date(2024, 3, 1)
    assert time_range.label == "Past 9 months"

    where_clause = _build_filters([time_range.to_filter()], _semantic_model(), alias="base")
    assert (
        where_clause
        == "WHERE base.month >= DATE '2023-06-01' AND base.month < DATE '2024-03-01'"
    )
