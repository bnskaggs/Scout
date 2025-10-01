import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.conversation import (
    PendingClarification,
    apply_clarification_answer,
    assess_ambiguity,
    rewrite_followup,
)
from app.nql.model import NQLQuery

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _normalise(nql_payload):
    return NQLQuery.parse_obj(nql_payload).dict()


@pytest.mark.parametrize("fixture_path", sorted(FIXTURES_DIR.glob("*.json")))
def test_conversation_fixture(fixture_path: Path):
    payload = json.loads(fixture_path.read_text())
    today_value = date.fromisoformat(payload["today"])
    state = _normalise(payload["initial_nql"])

    for turn in payload["turns"]:
        utterance = turn["utterance"]
        expected = _normalise(turn["expected"])
        clarification = turn.get("clarification")

        if clarification:
            result = assess_ambiguity(state, utterance)
            assert result.needs_clarification, f"Expected clarification for {fixture_path.name}"
            assert result.question == clarification["question"]
            assert result.missing_slots == clarification["missing_slots"]
            assert result.suggested_answers == clarification["suggested_answers"]
            pending = PendingClarification(
                utterance=utterance,
                question=result.question or "",
                missing_slots=result.missing_slots,
                suggested_answers=result.suggested_answers,
                context=result.context,
            )
            actual = apply_clarification_answer(
                state,
                pending,
                clarification["answer"],
                today=today_value,
            )
        else:
            result = assess_ambiguity(state, utterance)
            assert not result.needs_clarification, f"Unexpected clarification for {fixture_path.name}"
            actual = rewrite_followup(state, utterance, today=today_value)

        normalised_actual = _normalise(actual)
        assert normalised_actual == expected
        state = normalised_actual
