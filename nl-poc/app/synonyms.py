"""Domain-specific synonyms used by the planner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class SynonymBundle:
    metric_aliases: Dict[str, str]
    dimension_aliases: Dict[str, str]
    compare_keywords: Dict[str, str]


def _build_metric_aliases() -> Dict[str, str]:
    base = {
        "incident": "incidents",
        "incidents": "incidents",
        "crime": "incidents",
        "crimes": "incidents",
        "cases": "incidents",
        "events": "incidents",
        "reports": "incidents",
    }
    return base


def _build_dimension_aliases() -> Dict[str, str]:
    mapping = {
        "area": "area",
        "district": "area",
        "division": "area",
        "neighborhood": "area",
        "region": "area",
        "borough": "area",
        "crime type": "crime_type",
        "offense": "crime_type",
        "offence": "crime_type",
        "category": "crime_type",
        "type": "crime_type",
        "premise": "premise",
        "location": "premise",
        "place": "premise",
        "weapon": "weapon",
        "victim age": "vict_age",
        "age": "vict_age",
        "month": "month",
        "date": "month",
    }
    return mapping


def _build_compare_keywords() -> Dict[str, str]:
    return {
        "mom": "mom",
        "month over month": "mom",
        "month-over-month": "mom",
        "mom%": "mom",
        "qoq": "mom",
        "compare to last month": "mom",
        "last month": "mom",
        "yoy": "yoy",
        "year over year": "yoy",
        "year-over-year": "yoy",
        "compare to last year": "yoy",
    }


def load_synonyms() -> SynonymBundle:
    return SynonymBundle(
        metric_aliases=_build_metric_aliases(),
        dimension_aliases=_build_dimension_aliases(),
        compare_keywords=_build_compare_keywords(),
    )


def find_dimension(keyword: str, bundle: SynonymBundle) -> str | None:
    keyword_l = keyword.lower().strip()
    if keyword_l in bundle.dimension_aliases:
        return bundle.dimension_aliases[keyword_l]
    # handle plural forms
    if keyword_l.endswith("s") and keyword_l[:-1] in bundle.dimension_aliases:
        return bundle.dimension_aliases[keyword_l[:-1]]
    return None


def canonical_metric(token: str, bundle: SynonymBundle) -> str | None:
    return bundle.metric_aliases.get(token.lower().strip())


def detect_compare(text: str, bundle: SynonymBundle) -> str | None:
    text_lower = text.lower()
    for key, value in bundle.compare_keywords.items():
        if key in text_lower:
            return value
    return None
