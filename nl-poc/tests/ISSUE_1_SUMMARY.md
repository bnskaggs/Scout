# Issue #1 Fix Summary: Format change_pct with % sign and 2 decimals

## Problem
Query: "Incidents by weapon for Olympic in 2024-02; include MoM change"
- **ACTUAL:** change_pct shows raw decimal (e.g., `0.156789` or `-0.0234`)
- **EXPECTED:** Formatted as percentage with 2 decimals (e.g., `+15.68%` or `-2.34%`)

## Solution

### Backend Changes (app/main.py)

**Added `_format_change_pct()` function:**
- Processes records after query execution
- Adds `change_pct_formatted` column with formatted values
- Keeps raw `change_pct` for calculations/charts
- Format: `+15.68%` (with sign, 2 decimals)
- Handles null values: `"N/A"`

**Example transformation:**
```python
# Before
{"crime_type": "Assault", "incidents": 150, "change_pct": 0.156789}

# After
{
  "crime_type": "Assault",
  "incidents": 150,
  "change_pct": 0.156789,  # Raw value preserved
  "change_pct_formatted": "+15.68%"  # New formatted column
}
```

### Frontend Changes (index.html)

**Updated `renderTable()` function:**
- Hides raw `change_pct` column if `change_pct_formatted` exists
- Shows only the formatted version in the table
- Raw value still available in data for sorting/charts

## Before/After Examples

| Input (raw change_pct) | Output (change_pct_formatted) |
|------------------------|-------------------------------|
| 0.156789               | +15.68%                       |
| -0.0234                | -2.34%                        |
| 0.0                    | +0.00%                        |
| null                   | N/A                           |
| 0.999                  | +99.90%                       |

## Test Coverage

**File:** `tests/test_format_change_pct.py`

Tests:
- ✓ Positive percentages formatted correctly
- ✓ Negative percentages formatted correctly
- ✓ Null values handled as "N/A"
- ✓ Zero change formatted as "+0.00%"
- ✓ Records without change_pct unchanged
- ✓ Rounding to 2 decimal places

All tests passing.

## Files Modified

1. **app/main.py**
   - Added `_format_change_pct()` function
   - Call formatting after `_apply_small_n()`

2. **frontend/index.html**
   - Modified `renderTable()` to hide raw column

## User Experience

**Before:**
```
crime_type        | incidents | change_pct
------------------|-----------|------------
Assault           | 150       | 0.156789
Burglary          | 80        | -0.0234
```

**After:**
```
crime_type        | incidents | change_pct_formatted
------------------|-----------|---------------------
Assault           | 150       | +15.68%
Burglary          | 80        | -2.34%
```

Much clearer and more intuitive!
