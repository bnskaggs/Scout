# Issue #3 Fix Summary: MoM Header Shows Wrong "Leader"

## Problem

**Query:** "Which crime types rose the most month over month in 2023-12?"

**ACTUAL:** Header says "VEHICLE - STOLEN led with 2183 incidents; (down 1.8%)"

**EXPECTED:** Should show the crime type with HIGHEST MoM increase, not highest count

**Issues identified:**
1. Header picking first record (highest count) instead of highest change_pct
2. Showing "down 1.8%" which isn't even an increase!
3. Percentage shown as "0.2%" instead of "2.0%" (wrong scale)

## Root Cause

**app/viz.py `build_narrative()` function:**
1. Always used `records[0]` which is typically sorted by incidents count
2. For MoM/YoY queries, should pick the record with max(change_pct), not first record
3. Percentage formatting was wrong: `round(change_pct, 1)` instead of `round(change_pct * 100, 1)`

## Solution

### Changes to app/viz.py

**1. Pick record with highest change_pct for comparison queries:**
```python
# Before
top = records[0]

# After
if compare and any("change_pct" in rec for rec in records):
    records_with_change = [r for r in records if r.get("change_pct") is not None]
    if records_with_change:
        top = max(records_with_change, key=lambda r: r.get("change_pct", float("-inf")))
    else:
        top = records[0]
else:
    top = records[0]
```

**2. Fix percentage formatting:**
```python
# Before
parts.append(f"({direction} {abs(round(top['change_pct'], 1))}% vs prior period)")

# After
pct_value = abs(round(top['change_pct'] * 100, 1))  # Convert to percentage and round
parts.append(f"({direction} {pct_value}% vs prior period)")
```

## Before/After Examples

### Example 1: "Which crime types rose the most MoM?"

**Data:**
```
VEHICLE - STOLEN:  2183 incidents, change_pct = -0.018 (down 1.8%)
BATTERY:           1450 incidents, change_pct = +0.05  (up 5%)
BURGLARY:           850 incidents, change_pct = +0.25  (up 25% ← HIGHEST!)
THEFT:             1200 incidents, change_pct = +0.12  (up 12%)
```

**Before:**
> "VEHICLE - STOLEN led with 2183 incidents; (down 0.2% vs prior period)."

**After:**
> "BURGLARY led with 850 incidents; (up 25.0% vs prior period)."

### Example 2: All negative changes

**Data:**
```
Central:    500 incidents, change_pct = -0.30 (down 30%)
Hollywood:  400 incidents, change_pct = -0.05 (down 5% ← LEAST NEGATIVE!)
West LA:    350 incidents, change_pct = -0.15 (down 15%)
```

**Before:**
> "Central led with 500 incidents; (down 0.3% vs prior period)."

**After:**
> "Hollywood led with 400 incidents; (down 5.0% vs prior period)."

## Test Coverage

**File:** `tests/test_mom_header_leader.py`

Tests:
- ✓ Header picks max change_pct, not max count
- ✓ Handles all negative changes (picks least negative)
- ✓ Non-comparison queries still use first record
- ✓ Null change_pct records are skipped

All tests passing.

## User Impact

**Before:** Confusing and misleading headers showing the wrong item
- Query asks for "rose the most" but shows item that DECREASED
- Shows highest count, not highest growth
- Wrong percentage scale (0.2% vs 20%)

**After:** Accurate and intuitive headers
- Shows the item with actually the highest change
- Correct percentage scale (25.0% not 0.25%)
- Matches user's query intent

## Files Modified

**app/viz.py:**
- Modified `build_narrative()` to pick record with max change_pct for comparison queries
- Fixed percentage formatting to multiply by 100
