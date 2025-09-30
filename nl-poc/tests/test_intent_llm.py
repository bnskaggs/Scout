import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import os
from datetime import date
from importlib import reload

from app.planner import build_plan


def test_plan_top10_crimes_ytd():
    q = "Top 10 crime types in Hollywood for 2024 YTD; show MoM %."
    plan = build_plan(q, prefer_llm=False)
    assert "incidents" in plan["metrics"]
    assert "crime_type" in plan["group_by"]
    assert plan.get("limit", 10) == 10


def test_plan_single_month():
    q = "Incidents by area for 2023-06."
    plan = build_plan(q, prefer_llm=False)
    months = [f for f in plan.get("filters", []) if f["field"] == "month"]
    assert months and months[0]["op"] in ("=", "between")


def test_load_env_once(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=openai\nLLM_MODEL=gpt-test\nLLM_API_KEY=abc123\n", encoding="utf-8")

    # ensure the loader looks in our temp directory
    monkeypatch.chdir(tmp_path)
    for key in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    import app.llm_client as llm_client

    reload(llm_client)
    llm_client._load_env_once()

    assert os.getenv("LLM_PROVIDER") == "openai"
    assert os.getenv("LLM_MODEL") == "gpt-test"
    assert os.getenv("LLM_API_KEY") == "abc123"


def test_trend_question_without_dates_gets_trailing_year(monkeypatch):
    monkeypatch.setattr("app.time_utils.current_date", lambda: date(2024, 5, 15))

    plan = build_plan("Show the trend of incidents by month", prefer_llm=False)

    month_filters = [f for f in plan.get("filters", []) if f.get("field") == "month"]
    assert month_filters
    filter_value = month_filters[0]
    assert filter_value["op"] == "between"
    assert filter_value["value"] == ["2023-06-01", "2024-06-01"]
