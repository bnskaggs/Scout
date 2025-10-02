"""Domain-specific synonyms used by the planner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


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
        "weapon category": "weapon",
        "weapon categories": "weapon",
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


SHARE_TOKENS = {"share", "percentage", "% of", "percent of"}


_WEAPON_PATTERN_MAP = {
    "firearm": ["%firearm%", "%gun%", "%hand gun%", "%rifle%", "%shotgun%"],
    "firearms": ["%firearm%", "%gun%", "%hand gun%", "%rifle%", "%shotgun%"],
    "gun": ["%gun%", "%firearm%", "%hand gun%"],
    "guns": ["%gun%", "%firearm%", "%hand gun%"],
    "handgun": ["%hand gun%", "%gun%", "%firearm%"],
    "handguns": ["%hand gun%", "%gun%", "%firearm%"],
    "hand gun": ["%hand gun%", "%gun%", "%firearm%"],
    "rifle": ["%rifle%"],
    "rifles": ["%rifle%"],
    "shotgun": ["%shotgun%"],
    "shotguns": ["%shotgun%"],
    "knife": ["%knife%", "%stab%"],
    "knives": ["%knife%", "%stab%"],
    "stabbing": ["%stab%", "%knife%"],
    "stabbings": ["%stab%", "%knife%"],
    "stabbed": ["%stab%", "%knife%"],
    "stab": ["%stab%", "%knife%"],
    "knifing": ["%knife%", "%stab%"],
}


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


def _collect_weapon_patterns(text_lower: str) -> List[str]:
    collected: List[str] = []
    for token, patterns in _WEAPON_PATTERN_MAP.items():
        if token in text_lower:
            collected.extend(patterns)
    # Preserve order while removing duplicates
    deduped: List[str] = []
    seen = set()
    for pattern in collected:
        key = pattern.lower()
        if key in seen:
            continue
        deduped.append(pattern)
        seen.add(key)
    return deduped


def detect_weapon_patterns(text: str) -> Optional[List[str]]:
    patterns = _collect_weapon_patterns(text.lower())
    return patterns or None


def weapon_patterns_from_value(value: str) -> Optional[List[str]]:
    patterns = _collect_weapon_patterns(value.lower())
    return patterns or None
