# Issue #4 Fix Summary: Misleading "led with" for Bottom Queries

## Problem

**Query:** "List the bottom 5 areas by incidents in 2024-05"

**ACTUAL:** Header says "Hollenbeck led with 271 incidents"

**EXPECTED:** "Hollenbeck had the fewest with 271 incidents" (or similar)

**Issue:** "led with" implies highest/best, but query asked for "bottom 5" (lowest). The language should match the query intent.

## Root Cause

**app/viz.py `build_narrative()` function:**
- Always used "led with" regardless of sort direction
- Didn't check if query was asking for top (descending) or bottom (ascending)
- The planner correctly sets `order_by: {dir: "asc"}` for "bottom" queries
- Narrative just needed to inspect this flag

## Solution

### Changes to app/viz.py

**Added logic to detect ascending vs descending sort:**
```python
# Check if this is a "bottom/lowest" query (ascending sort order)
order_by = plan.get("order_by", [])
is_ascending = any(
    isinstance(o, dict) and o.get("dir") == "asc"
    for o in order_by
)

if is_ascending:
    parts.append(f"{label} had the fewest with {value} incidents")
else:
    parts.append(f"{label} led with {value} incidents")
```

## Before/After Examples

### Example 1: Bottom 5 query

**Query:** "List the bottom 5 areas by incidents in 2024-05"

**Data (sorted ascending):**
```
Hollenbeck:    271 incidents ← LOWEST
Foothill:      285 incidents
Devonshire:    301 incidents
West Valley:   315 incidents
Topanga:       330 incidents
```

**Before:**
> "Hollenbeck led with 271 incidents."

**After:**
> "Hollenbeck had the fewest with 271 incidents."

### Example 2: Top query (no change)

**Query:** "Show me the top 3 areas by incidents"

**Data (sorted descending):**
```
Central:     850 incidents ← HIGHEST
Hollywood:   780 incidents
77th Street: 720 incidents
```

**Before & After (unchanged):**
> "Central led with 850 incidents."

### Example 3: Bottom with MoM comparison

**Query:** "Which areas had the lowest incidents MoM in 2024-05?"

**Data:**
```
Hollenbeck:  100 incidents, down 5%
Foothill:    120 incidents, up 10% ← MAX CHANGE
```

**After:**
> "Foothill had the fewest with 120 incidents; (up 10.0% vs prior period)."

**Note:** For comparison queries, the narrative picks the record with max change_pct (Issue #3 fix), but still uses "had the fewest" language because order_by is ascending.

## Language Options Considered

1. **"had the fewest"** ✓ (chosen)
   - Clear and natural
   - Mirrors "led with" structure

2. "ranked lowest with"
   - More formal
   - Also accurate

3. "Hollenbeck: 271 incidents (lowest)"
   - More compact
   - Less narrative-style

We chose "had the fewest" for consistency with the existing "led with" pattern.

## Test Coverage

**File:** `tests/test_bottom_query_header.py`

Tests:
- ✓ Bottom queries use "had the fewest" language
- ✓ Top queries still use "led with" language
- ✓ Queries without order_by default to "led with"
- ✓ Bottom queries with MoM comparison handled correctly

All tests passing.

## User Impact

**Before:** Confusing language
- Query asks for "bottom/lowest" but header says "led with"
- Implies the opposite of what was requested

**After:** Clear and accurate language
- "had the fewest" for bottom/lowest queries
- "led with" for top/highest queries
- Language matches user intent

## Files Modified

**app/viz.py:**
- Modified `build_narrative()` to check `order_by` direction
- Uses "had the fewest" for ascending sort, "led with" for descending/default
