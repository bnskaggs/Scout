import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.followup_rewriter import rewrite_followup_state


@pytest.mark.parametrize(
    "last_state, utterance, expected",
    [
        (
            {
                "metric": "incidents",
                "time": "2024-06",
                "group_by": "area",
                "filters": [],
            },
            "How many stabbings happened in Hollywood?",
            {
                "action": "reset",
                "metric": "stabbings",
                "time": "all_time",
                "group_by": None,
                "filters": ["area = 'Hollywood'"],
            },
        ),
        (
            {
                "metric": "incidents",
                "time": "2024",
                "group_by": "weapon",
                "filters": [],
            },
            "Same but by area",
            {
                "action": "replace_dimension",
                "metric": "incidents",
                "time": "2024",
                "group_by": "area",
                "filters": [],
            },
        ),
        (
            {
                "metric": "incidents",
                "time": "2024",
                "group_by": "area",
                "filters": [],
            },
            "Only for Hollywood please",
            {
                "action": "add_filter",
                "metric": "incidents",
                "time": "2024",
                "group_by": "area",
                "filters": ["area = 'Hollywood'"],
            },
        ),
        (
            {
                "metric": "incidents",
                "time": "2024",
                "group_by": "area",
                "filters": ["area = 'Hollywood'"],
            },
            "What about last month?",
            {
                "action": "reuse",
                "metric": "incidents",
                "time": "last_month",
                "group_by": "area",
                "filters": ["area = 'Hollywood'"],
            },
        ),
    ],
)
def test_followup_rewriter(last_state, utterance, expected):
    assert rewrite_followup_state(last_state, utterance) == expected

