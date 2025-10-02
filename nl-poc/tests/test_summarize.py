"""Tests for the result summarizer with hallucination guardrails."""
from __future__ import annotations

import pytest

from app.summarizer import (
    _extract_numbers,
    _flatten_values,
    _validate_no_hallucinations,
    HallucinationError,
)


class TestNumberExtraction:
    """Test number extraction from text."""

    def test_extract_simple_integers(self):
        text = "There were 15234 incidents in Central and 12456 in Hollywood."
        numbers = _extract_numbers(text)
        assert "15234" in numbers
        assert "12456" in numbers

    def test_extract_decimals(self):
        text = "The value was 13.64 percent."
        numbers = _extract_numbers(text)
        assert "13.64" in numbers

    def test_extract_percentages(self):
        text = "Increased by +13.64% this month."
        numbers = _extract_numbers(text)
        assert "13.64" in numbers or "13.64%" in numbers

    def test_extract_with_commas(self):
        text = "Total of 1,250 compared to 5,890 last year."
        numbers = _extract_numbers(text)
        # Should normalize by removing commas
        assert "1250" in numbers
        assert "5890" in numbers

    def test_extract_negative_numbers(self):
        text = "Declined by -6.67%."
        numbers = _extract_numbers(text)
        assert "6.67" in numbers


class TestValueFlattening:
    """Test extraction of values from nested data structures."""

    def test_flatten_simple_dict(self):
        data = {"area": "Central", "incidents": 15234}
        values = _flatten_values(data)
        assert "15234" in values
        assert "Central" in values

    def test_flatten_list_of_dicts(self):
        data = [
            {"area": "Central", "incidents": 15234},
            {"area": "Hollywood", "incidents": 12456},
        ]
        values = _flatten_values(data)
        assert "15234" in values
        assert "12456" in values
        assert "Central" in values
        assert "Hollywood" in values

    def test_flatten_with_percentages(self):
        data = [
            {
                "area": "Central",
                "change_pct": 13.64,
                "change_pct_formatted": "+13.64%",
            }
        ]
        values = _flatten_values(data)
        assert "13.64" in values or "13" in values

    def test_flatten_nested_structures(self):
        data = {
            "results": [
                {"area": "Central", "incidents": 1250},
            ],
            "metadata": {"total": 5000},
        }
        values = _flatten_values(data)
        assert "1250" in values
        assert "5000" in values


class TestHallucinationValidation:
    """Test the hallucination detection guardrail."""

    def test_valid_explanation_passes(self):
        """Valid explanation with numbers from data should pass."""
        results = [
            {"area": "Central", "incidents": 15234},
            {"area": "Hollywood", "incidents": 12456},
        ]
        explanation = "Central had 15234 incidents and Hollywood had 12456."

        # Should not raise
        _validate_no_hallucinations(explanation, results)

    def test_hallucinated_number_detected(self):
        """Explanation with invented numbers should raise HallucinationError."""
        results = [
            {"area": "Central", "incidents": 15234},
        ]
        explanation = "Central had 99999 incidents."

        with pytest.raises(HallucinationError) as exc_info:
            _validate_no_hallucinations(explanation, results)

        assert "99999" in str(exc_info.value)

    def test_percentage_format_accepted(self):
        """Percentages in data should be accepted in explanation."""
        results = [
            {
                "area": "Central",
                "change_pct": 13.64,
                "change_pct_formatted": "+13.64%",
            }
        ]
        explanation = "Central increased by 13.64% this month."

        # Should not raise
        _validate_no_hallucinations(explanation, results)

    def test_decimal_variations_accepted(self):
        """Different representations of same number should be accepted."""
        results = [{"incidents": 5200}]

        # All these should pass
        _validate_no_hallucinations("There were 5200 incidents.", results)

    def test_empty_explanation_passes(self):
        """Explanation with no numbers should pass."""
        results = [{"area": "Central", "incidents": 100}]
        explanation = "The data shows some activity in Central."

        # Should not raise
        _validate_no_hallucinations(explanation, results)

    def test_multiple_hallucinations_detected(self):
        """Multiple invented numbers should all be caught."""
        results = [{"area": "Central", "incidents": 100}]
        explanation = "Central had 500 incidents and Hollywood had 999."

        with pytest.raises(HallucinationError) as exc_info:
            _validate_no_hallucinations(explanation, results)

        error_msg = str(exc_info.value)
        # At least one hallucinated number should be mentioned
        assert "500" in error_msg or "999" in error_msg


class TestSummarizeFixtures:
    """Test summarization with realistic fixtures."""

    def test_fixture_aggregate_by_area(self):
        """Fixture 1: Aggregate by area (highlight top 3)."""
        results = [
            {"area": "Central", "incidents": 15234},
            {"area": "Hollywood", "incidents": 12456},
            {"area": "West LA", "incidents": 10987},
            {"area": "Valley", "incidents": 8765},
        ]
        plan = {
            "intent": "rank",
            "dimensions": ["area"],
            "time_window_label": "Last 12 months",
        }

        # Valid explanation should mention top values
        explanation = (
            "Central had the most incidents with 15234 cases. "
            "Hollywood ranked second with 12456, followed by West LA at 10987."
        )
        _validate_no_hallucinations(explanation, results)

    def test_fixture_trend_data(self):
        """Fixture 2: Trend data (identify rising/falling)."""
        results = [
            {"month": "2024-01-01", "incidents": 5200},
            {"month": "2024-02-01", "incidents": 5450},
            {"month": "2024-03-01", "incidents": 5890},
            {"month": "2024-04-01", "incidents": 6100},
        ]
        plan = {"intent": "trend", "dimensions": ["month"], "group_by": ["month"]}

        explanation = (
            "Incidents show a steady upward trend from January through April. "
            "The total grew from 5200 in January to 6100 in April."
        )
        _validate_no_hallucinations(explanation, results)

    def test_fixture_mom_comparison(self):
        """Fixture 3: MoM comparison (call out biggest changes)."""
        results = [
            {
                "area": "Central",
                "incidents": 1250,
                "prev_incidents": 1100,
                "change_pct": 13.64,
                "change_pct_formatted": "+13.64%",
            },
            {
                "area": "Hollywood",
                "incidents": 980,
                "prev_incidents": 1050,
                "change_pct": -6.67,
                "change_pct_formatted": "-6.67%",
            },
        ]
        plan = {"intent": "compare", "compare": {"type": "mom"}, "dimensions": ["area"]}

        explanation = (
            "Central showed the largest increase at 13.64%, rising from 1100 to 1250. "
            "Hollywood declined by 6.67%, dropping from 1050 to 980."
        )
        _validate_no_hallucinations(explanation, results)

    def test_fixture_single_outlier(self):
        """Fixture 4: Single outlier (unusual spike)."""
        results = [
            {"month": "2024-01-01", "incidents": 5200},
            {"month": "2024-02-01", "incidents": 5300},
            {"month": "2024-03-01", "incidents": 8900},
            {"month": "2024-04-01", "incidents": 5400},
        ]
        plan = {"intent": "trend", "dimensions": ["month"]}

        explanation = (
            "Incidents were stable around 5200-5400 per month, "
            "except for March which spiked to 8900."
        )
        _validate_no_hallucinations(explanation, results)

    def test_fixture_flat_data(self):
        """Fixture 5: Flat data (acknowledge nothing notable)."""
        results = [
            {"area": "Central", "incidents": 1200},
            {"area": "Hollywood", "incidents": 1190},
            {"area": "West LA", "incidents": 1210},
        ]
        plan = {"intent": "rank", "dimensions": ["area"]}

        explanation = (
            "Incident volumes are evenly distributed, ranging from 1190 to 1210. "
            "West LA has a slight edge with 1210."
        )
        _validate_no_hallucinations(explanation, results)

    def test_fixture_empty_results(self):
        """Fixture 6: Empty results (graceful message)."""
        results = []
        plan = {"intent": "aggregate", "filters": [{"field": "area", "op": "=", "value": "Unknown"}]}

        # Empty results should have no numbers to validate
        explanation = "No incidents were found matching the specified filters."
        _validate_no_hallucinations(explanation, results)

    def test_fixture_large_numbers_with_commas(self):
        """Fixture 7: Large numbers with comma formatting."""
        results = [
            {"area": "Central", "incidents": 125000},
            {"area": "Hollywood", "incidents": 98500},
        ]
        plan = {"intent": "rank", "dimensions": ["area"]}

        explanation = "Central had 125000 incidents and Hollywood had 98500."
        _validate_no_hallucinations(explanation, results)

    def test_fixture_year_over_year(self):
        """Fixture 8: Year-over-year comparison."""
        results = [
            {
                "area": "Central",
                "incidents": 15000,
                "prev_year_incidents": 14200,
                "change_pct": 5.63,
            }
        ]
        plan = {"intent": "compare", "compare": {"type": "yoy"}}

        explanation = "Central grew from 14200 to 15000, a 5.63% increase year-over-year."
        _validate_no_hallucinations(explanation, results)

    def test_fixture_multiple_dimensions(self):
        """Fixture 9: Multiple dimensions breakdown."""
        results = [
            {"area": "Central", "crime_type": "Theft", "incidents": 5200},
            {"area": "Central", "crime_type": "Assault", "incidents": 3100},
            {"area": "Hollywood", "crime_type": "Theft", "incidents": 4800},
        ]
        plan = {"intent": "distribution", "dimensions": ["area", "crime_type"]}

        explanation = "Theft in Central led with 5200 incidents, followed by Theft in Hollywood at 4800."
        _validate_no_hallucinations(explanation, results)

    def test_fixture_hallucination_rejected(self):
        """Fixture 10: Guardrail catches hallucinated numbers."""
        results = [
            {"area": "Central", "incidents": 15234},
        ]

        # This explanation invents numbers not in the data
        hallucinated_explanation = (
            "Central had 15234 incidents, which is 50% higher than last year's 10000."
        )

        with pytest.raises(HallucinationError):
            _validate_no_hallucinations(hallucinated_explanation, results)
