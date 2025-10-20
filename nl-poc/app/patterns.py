"""Pattern matching utilities for natural language conversation parsing.

This module contains regex patterns and parsing functions for detecting
user intent in follow-up queries, including filter modifications, dimension
changes, and time adjustments.
"""

import re
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class FilterAddition:
    """Result of matching a filter addition pattern."""
    is_include: bool  # True for "include", False for "only/just/show me"
    values: List[str]  # List of values to add/replace


@dataclass
class FilterRemoval:
    """Result of matching a filter removal pattern."""
    values: List[str]  # List of values to remove


@dataclass
class RangeFilter:
    """Result of matching a numeric range filter pattern."""
    field: str  # Field to filter (e.g., "incidents")
    op: str  # Operator: ">", ">=", "<", "<=", "between"
    value: object  # Number or [min, max] for between


@dataclass
class TopN:
    """Result of matching a top-N pattern."""
    k: int  # Number of results to return
    direction: str  # "desc" for top/highest, "asc" for bottom/lowest
    dimension: Optional[str] = None  # Specific dimension if mentioned


def normalize_text(value: str) -> str:
    """Normalize text by collapsing whitespace and lowercasing."""
    return re.sub(r"\s+", " ", value.strip().lower())


def match_dimension_change(utterance: str) -> Optional[str]:
    """
    Extract dimension change patterns like "by area", "same but by weapon".

    Returns:
        The dimension name if matched, None otherwise.

    Examples:
        >>> match_dimension_change("same but by weapon")
        'weapon'
        >>> match_dimension_change("by area")
        'area'
        >>> match_dimension_change("show total") is None
        True
    """
    lowered = utterance.lower()
    patterns = [
        r"same(?:\s+view)?\s+but\s+by\s+([a-z\s]+)",
        r"by\s+([a-z\s]+)",
        r"break(?:ing|)\s+down\s+by\s+([a-z\s]+)",
        r"group\s+by\s+([a-z\s]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            candidate = match.group(1).strip()
            # Remove common prepositions
            candidate = re.sub(r"\bfor\b", "", candidate).strip()
            return candidate

    return None


def match_filter_removal(utterance: str) -> Optional[FilterRemoval]:
    """
    Detect filter removal patterns like "drop Central", "remove Hollywood and Downtown".

    Supports multi-value removal: "remove Central and Hollywood" removes both values.

    Returns:
        FilterRemoval with list of values to remove, or None.

    Examples:
        >>> result = match_filter_removal("filter out Central")
        >>> result.values
        ['Central']
        >>> result = match_filter_removal("drop Hollywood and Downtown")
        >>> result.values
        ['Hollywood', 'Downtown']
        >>> match_filter_removal("show me all") is None
        True
    """
    lowered = utterance.lower()
    match = re.search(
        r"(?:filter out|exclude|remove|drop)\s+([\w\s'&/-]+(?:\s+and\s+[\w\s'&/-]+)*)",
        lowered
    )

    if match:
        value_str = match.group(1).strip().strip(". ")
        values = parse_multi_values(value_str)
        return FilterRemoval(values=values)

    return None


def parse_multi_values(value_str: str) -> List[str]:
    """
    Parse multiple values separated by "and" or commas.

    Examples:
        >>> parse_multi_values("Central and Hollywood")
        ['Central', 'Hollywood']
        >>> parse_multi_values("Central, Hollywood, Downtown")
        ['Central', 'Hollywood', 'Downtown']
        >>> parse_multi_values("Hollywood")
        ['Hollywood']
    """
    values = re.split(r'\s+and\s+|,\s*', value_str)
    return [v.strip().title() for v in values if v.strip()]


def match_filter_addition(utterance: str) -> Optional[FilterAddition]:
    """
    Detect filter addition patterns.

    "include X" adds to existing filters (OR operation).
    "only X", "just X", "show me X", "switch to X", "change to X" replaces existing filters.

    Returns:
        FilterAddition with is_include flag and list of values, or None.

    Examples:
        >>> result = match_filter_addition("include Hollywood")
        >>> result.is_include
        True
        >>> result.values
        ['Hollywood']

        >>> result = match_filter_addition("only Central and Hollywood")
        >>> result.is_include
        False
        >>> result.values
        ['Central', 'Hollywood']

        >>> result = match_filter_addition("switch to Downtown")
        >>> result.is_include
        False
        >>> result.values
        ['Downtown']
    """
    lowered = utterance.lower()

    # Try "include" pattern first (additive)
    include_match = re.search(
        r"(?:include)\s+([\w\s'&/-]+(?:\s+and\s+[\w\s'&/-]+)*)",
        lowered
    )

    if include_match:
        value_str = include_match.group(1).strip().strip(". ")
        values = parse_multi_values(value_str)
        return FilterAddition(is_include=True, values=values)

    # Try "only/just/show me/switch/change" patterns (replace)
    replace_match = re.search(
        r"(?:only|just|now\s+look\s+at|look\s+at|consider|focus\s+on|show\s+me|switch\s+to|change\s+to|swap\s+to)\s+([\w\s'&/-]+(?:\s+and\s+[\w\s'&/-]+)*)",
        lowered
    )

    if replace_match:
        value_str = replace_match.group(1).strip().strip(". ")
        values = parse_multi_values(value_str)
        return FilterAddition(is_include=False, values=values)

    return None


def match_filter_clear(utterance: str) -> Optional[str]:
    """
    Detect filter clear patterns like "reset filters", "show all areas".

    Returns:
        Field name to clear filters for (e.g., "area"), or "" to clear all filters, or None.

    Examples:
        >>> match_filter_clear("reset filters")
        ''
        >>> match_filter_clear("show all areas")
        'area'
        >>> match_filter_clear("all weapons")
        'weapon'
        >>> match_filter_clear("show me totals") is None
        True
    """
    lowered = utterance.lower()

    # Check for generic clear all patterns
    if re.search(r"(?:reset|clear)\s+(?:all\s+)?filters?", lowered):
        return ""

    if re.search(r"(?:remove|drop)\s+all\s+filters?", lowered):
        return ""

    # Check for field-specific clear patterns
    field_patterns = [
        (r"(?:show\s+)?all\s+areas?", "area"),
        (r"(?:show\s+)?all\s+weapons?", "weapon"),
        (r"(?:show\s+)?all\s+crimes?", "crime_type"),
        (r"(?:show\s+)?all\s+(?:crime\s+)?types?", "crime_type"),
        (r"(?:show\s+)?all\s+premises?", "premise"),
        (r"(?:show\s+)?everything", ""),
    ]

    for pattern, field in field_patterns:
        if re.search(pattern, lowered):
            return field

    return None


def match_range_filter(utterance: str) -> Optional[RangeFilter]:
    """
    Detect numeric range filter patterns like "over 100", "between 50 and 100".

    Returns:
        RangeFilter with field, operator, and value, or None.

    Examples:
        >>> result = match_range_filter("over 100")
        >>> result.op, result.value
        ('>', 100)
        >>> result = match_range_filter("between 50 and 100")
        >>> result.op, result.value
        ('between', [50, 100])
        >>> match_range_filter("show me totals") is None
        True
    """
    lowered = utterance.lower()

    # Pattern for "between X and Y" or "from X to Y"
    between_match = re.search(r"(?:between|from)\s+(\d+)\s+(?:and|to)\s+(\d+)", lowered)
    if between_match:
        min_val = int(between_match.group(1))
        max_val = int(between_match.group(2))
        return RangeFilter(field="incidents", op="between", value=[min_val, max_val])

    # Pattern for "over X", "above X", "more than X", "greater than X"
    gt_match = re.search(r"(?:over|above|more than|greater than)\s+(\d+)", lowered)
    if gt_match:
        value = int(gt_match.group(1))
        return RangeFilter(field="incidents", op=">", value=value)

    # Pattern for "at least X", "X or more"
    gte_match = re.search(r"(?:at least|(\d+)\s+or more)\s+(\d+)", lowered)
    if gte_match:
        value = int(gte_match.group(2) if gte_match.group(2) else gte_match.group(1))
        return RangeFilter(field="incidents", op=">=", value=value)

    # Pattern for "under X", "below X", "less than X", "fewer than X"
    lt_match = re.search(r"(?:under|below|less than|fewer than)\s+(\d+)", lowered)
    if lt_match:
        value = int(lt_match.group(1))
        return RangeFilter(field="incidents", op="<", value=value)

    # Pattern for "at most X", "X or less"
    lte_match = re.search(r"(?:at most|(\d+)\s+or less)\s+(\d+)", lowered)
    if lte_match:
        value = int(lte_match.group(2) if lte_match.group(2) else lte_match.group(1))
        return RangeFilter(field="incidents", op="<=", value=value)

    return None


def match_top_n(utterance: str) -> Optional[TopN]:
    """
    Detect top-N patterns like "top 5", "bottom 3 areas", "highest 10".

    Returns:
        TopN with k, direction, and optional dimension, or None.

    Examples:
        >>> result = match_top_n("top 5")
        >>> result.k, result.direction
        (5, 'desc')
        >>> result = match_top_n("bottom 3 areas")
        >>> result.k, result.direction, result.dimension
        (3, 'asc', 'area')
        >>> result = match_top_n("highest 10 weapons")
        >>> result.k, result.direction, result.dimension
        (10, 'desc', 'weapon')
    """
    lowered = utterance.lower()

    # Dimension mapping
    dimension_map = {
        "area": "area",
        "areas": "area",
        "weapon": "weapon",
        "weapons": "weapon",
        "crime": "crime_type",
        "crimes": "crime_type",
        "type": "crime_type",
        "types": "crime_type",
        "premise": "premise",
        "premises": "premise",
    }

    # Top/highest/best patterns (descending)
    top_match = re.search(r"(?:top|highest|best)\s+(\d+)\s*([a-z]+)?", lowered)
    if top_match:
        k = int(top_match.group(1))
        dimension_word = top_match.group(2)
        dimension = dimension_map.get(dimension_word) if dimension_word else None
        return TopN(k=k, direction="desc", dimension=dimension)

    # Bottom/lowest/worst patterns (ascending)
    bottom_match = re.search(r"(?:bottom|lowest|worst)\s+(\d+)\s*([a-z]+)?", lowered)
    if bottom_match:
        k = int(bottom_match.group(1))
        dimension_word = bottom_match.group(2)
        dimension = dimension_map.get(dimension_word) if dimension_word else None
        return TopN(k=k, direction="asc", dimension=dimension)

    return None


def match_mom_toggle(utterance: str) -> Optional[bool]:
    """
    Detect month-over-month toggle patterns.

    Returns:
        True to enable MoM, False to disable, None if no match.

    Examples:
        >>> match_mom_toggle("turn on mom")
        True
        >>> match_mom_toggle("include month over month")
        True
        >>> match_mom_toggle("turn off mom")
        False
        >>> match_mom_toggle("remove month over month")
        False
        >>> match_mom_toggle("show me totals") is None
        True
    """
    lowered = utterance.lower()

    # Enable patterns
    if re.search(r"(turn on|add|include).*(mom|month over month)", lowered):
        return True

    # Check for standalone "mom" without "turn off"
    if re.search(r"\bmom\b", lowered) and "turn off" not in lowered:
        return True

    # Disable patterns
    if re.search(r"(turn off|remove|drop).*(mom|month over month)", lowered):
        return False

    return None


__all__ = [
    "FilterAddition",
    "FilterRemoval",
    "RangeFilter",
    "TopN",
    "normalize_text",
    "match_dimension_change",
    "match_filter_removal",
    "match_filter_addition",
    "match_filter_clear",
    "match_range_filter",
    "match_top_n",
    "match_mom_toggle",
    "parse_multi_values",
]
