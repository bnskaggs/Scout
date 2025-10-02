"""LLM-powered result summarizer with hallucination guardrails."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .llm_client import _load_env_once

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover
    OpenAI = None

try:  # pragma: no cover - optional dependency
    from openai import OpenAIError  # type: ignore[attr-defined]
except (ModuleNotFoundError, ImportError):  # pragma: no cover
    try:  # pragma: no cover
        from openai import APIError as OpenAIError  # type: ignore[attr-defined]
    except (ModuleNotFoundError, ImportError):  # pragma: no cover
        OpenAIError = Exception


logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "llm_prompt_summarize.txt"


class SummarizerError(Exception):
    """Raised when summarization fails."""


class HallucinationError(SummarizerError):
    """Raised when the LLM invents numbers not in the data."""


def _extract_numbers(text: str) -> Set[str]:
    """Extract all numbers from text, including decimals and percentages."""
    # Match integers, decimals, and percentages (including those with commas)
    # Pattern: optional sign, digits with optional commas, optional decimal, optional percent
    pattern = r'[+-]?\d+(?:,\d{3})*(?:\.\d+)?%?'
    matches = re.findall(pattern, text)
    # Normalize by removing commas and storing both with and without % sign
    normalized: Set[str] = set()
    for match in matches:
        # Add the normalized version (no commas)
        clean = match.replace(',', '')
        normalized.add(clean)
        # Also add without percent sign if present
        if clean.endswith('%'):
            normalized.add(clean.rstrip('%'))
        # Also add without +/- sign if present
        if clean.startswith(('+', '-')):
            normalized.add(clean[1:])
            if clean.endswith('%'):
                normalized.add(clean[1:].rstrip('%'))
    return normalized


def _flatten_values(obj: Any) -> Set[str]:
    """Recursively extract all numeric values from a nested structure."""
    values: Set[str] = set()

    if isinstance(obj, dict):
        for value in obj.values():
            values.update(_flatten_values(value))
    elif isinstance(obj, list):
        for item in obj:
            values.update(_flatten_values(item))
    elif isinstance(obj, (int, float)):
        # Convert to string, handling both integers and floats
        str_val = str(obj)
        values.add(str_val)
        # Also add integer representation of floats like 13.64 → "13"
        if '.' in str_val:
            int_part = str_val.split('.')[0]
            values.add(int_part)
    elif isinstance(obj, str):
        # Extract numbers from formatted strings like "+13.64%" → "13.64", "13"
        numbers = _extract_numbers(obj)
        values.update(numbers)
        # Also add the original string in case it's referenced
        values.add(obj)

    return values


def _validate_no_hallucinations(explanation: str, results: List[Dict[str, Any]]) -> None:
    """Verify all numbers in explanation exist in results data.

    Raises HallucinationError if any number is not found in the input data.
    """
    explained_numbers = _extract_numbers(explanation)

    if not explained_numbers:
        # No numbers mentioned, nothing to validate
        return

    # Extract all values from results
    allowed_values = _flatten_values(results)

    hallucinated: List[str] = []
    for num in explained_numbers:
        # Check exact match or close match (e.g., "13.64" vs "13")
        num_clean = num.rstrip('%')
        found = False

        for allowed in allowed_values:
            allowed_clean = str(allowed).rstrip('%')
            # Exact match
            if num_clean == allowed_clean:
                found = True
                break
            # Check if it's a substring match for formatted numbers
            if num_clean in allowed_clean or allowed_clean in num_clean:
                found = True
                break
            # Check decimal vs integer match (e.g., "5200.0" vs "5200")
            try:
                if float(num_clean) == float(allowed_clean):
                    found = True
                    break
            except (ValueError, TypeError):
                pass

        if not found:
            hallucinated.append(num)

    if hallucinated:
        logger.warning(
            "Hallucination detected in explanation",
            extra={
                "hallucinated_numbers": hallucinated,
                "explanation": explanation,
                "allowed_values_sample": list(allowed_values)[:20],
            },
        )
        raise HallucinationError(
            f"LLM hallucinated numbers not in data: {', '.join(hallucinated)}"
        )


def _call_summarizer_llm(
    results: List[Dict[str, Any]], plan: Dict[str, Any]
) -> Dict[str, Any]:
    """Call LLM to generate explanation and follow-ups."""
    import os

    _load_env_once()

    provider = os.getenv("LLM_PROVIDER", "").lower()
    model = os.getenv("LLM_MODEL", "")
    api_key = os.getenv("LLM_API_KEY", "")

    if not provider or not model or not api_key:
        raise SummarizerError("Missing LLM_PROVIDER/LLM_MODEL/LLM_API_KEY")

    if provider != "openai":  # pragma: no cover
        raise SummarizerError(f"Unsupported LLM provider: {provider}")

    if OpenAI is None:  # pragma: no cover
        raise SummarizerError("openai SDK is not installed")

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    user_payload = {
        "results": results[:100],  # Limit to first 100 rows to avoid token overflow
        "plan": {
            "intent": plan.get("intent", "aggregate"),
            "dimensions": plan.get("dimensions", []),
            "group_by": plan.get("group_by", []),
            "time_window_label": plan.get("time_window_label", ""),
            "compare": plan.get("compare"),
            "filters": plan.get("filters", []),
        },
    }

    user_content = json.dumps(user_payload, indent=2)

    try:  # pragma: no cover - networked call
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            temperature=0.3,  # Slight creativity for natural language
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        raw_response = resp.choices[0].message.content.strip()
        logger.info("Summarizer LLM call succeeded", extra={"response_id": getattr(resp, "id", None)})
    except OpenAIError as exc:  # pragma: no cover
        logger.exception("Summarizer LLM call failed")
        raise SummarizerError("LLM call failed") from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error in summarizer LLM call")
        raise SummarizerError("LLM call failed") from exc

    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned non-JSON response", extra={"response": raw_response})
        raise SummarizerError("LLM returned invalid JSON") from exc

    return parsed


def summarize_results(
    results: List[Dict[str, Any]], plan: Dict[str, Any], *, max_retries: int = 2
) -> Dict[str, Any]:
    """Generate explanation and follow-ups for query results.

    Args:
        results: Query result rows
        plan: Query plan metadata
        max_retries: Number of times to retry if hallucination detected

    Returns:
        {
            "explanation": str,
            "followups": List[str]
        }

    Raises:
        SummarizerError: If LLM call fails
        HallucinationError: If all retries produce hallucinated numbers
    """
    if not results:
        return {
            "explanation": "No results were found matching your query criteria. Try adjusting your filters or expanding the time window.",
            "followups": [
                "Remove filters to see all data",
                "Expand time window to last 12 months",
                "Try a different dimension breakdown",
            ],
        }

    last_error: Optional[HallucinationError] = None

    for attempt in range(max_retries):
        try:
            summary = _call_summarizer_llm(results, plan)

            explanation = summary.get("explanation", "")
            followups = summary.get("followups", [])

            if not explanation:
                raise SummarizerError("LLM returned empty explanation")

            # Validate no hallucinations
            _validate_no_hallucinations(explanation, results)

            logger.info(
                "Summarization succeeded",
                extra={
                    "attempt": attempt + 1,
                    "explanation_length": len(explanation),
                    "followup_count": len(followups),
                },
            )

            return {
                "explanation": explanation,
                "followups": followups[:3],  # Limit to 3 follow-ups
            }

        except HallucinationError as exc:
            last_error = exc
            logger.warning(
                "Hallucination detected, retrying",
                extra={"attempt": attempt + 1, "max_retries": max_retries},
            )
            continue

    # All retries exhausted
    if last_error:
        raise last_error

    raise SummarizerError("Summarization failed after all retries")


__all__ = [
    "summarize_results",
    "SummarizerError",
    "HallucinationError",
]
