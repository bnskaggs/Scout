# Manual Test: Suggestion Pills Replace Only Incorrect Word

## Test Setup
1. Start the backend: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
2. Open `frontend/index.html` in a browser

## Test Case 1: Simple Typo in Area Name

**Steps:**
1. Enter query: "Incidents in Hoolywood in 2024"
2. Click "Ask"
3. Observe error: "Could not find value 'Hoolywood' for area"
4. Click suggestion pill "Hollywood"

**Expected Result:**
- Input box should show: "Incidents in Hollywood in 2024" (only "Hoolywood" replaced)
- Query should auto-submit with corrected value

**Before Fix:**
- Input box would show: "Hollywood" (entire query replaced)

---

## Test Case 2: Typo in Premise Name

**Steps:**
1. Enter query: "Show me crimes at Singel Family Dwellings in March 2024"
2. Click "Ask"
3. Observe error with suggestions
4. Click a suggestion pill

**Expected Result:**
- Only "Singel Family Dwellings" should be replaced with the suggestion
- Rest of query ("Show me crimes at ... in March 2024") remains intact

---

## Test Case 3: Multiple Word Value

**Steps:**
1. Enter query: "Incidents in West LA in 2024-05"
2. If "West LA" is misspelled as "West L A":
3. Click suggestion "West LA"

**Expected Result:**
- Query corrected to: "Incidents in West LA in 2024-05"
- Handles multi-word values correctly

---

## Implementation Details

### Frontend Changes (index.html)

1. **Added state variable:**
   - `lastFailedQuery` - stores the original query when an error occurs

2. **Modified `showErrorPanel` function:**
   - Extracts incorrect value from error message using regex: `/value ['"]([^'"]+)['"]/i`
   - Creates targeted replacement: only replaces the incorrect word/value
   - Uses word boundary regex for safe replacement
   - Fallback: if extraction fails, uses suggestion as-is

3. **Modified error handling:**
   - Saves failed query to `lastFailedQuery` before showing error panel

### Backend (no changes needed)
- Backend already provides correct format:
  - Error message: "Could not find value 'X' for field"
  - Suggestions: ["Value1", "Value2", ...]

---

## Edge Cases Handled

1. **No match found:** Falls back to suggestion as-is
2. **Special characters in value:** Escaped properly with `replace(/[.*+?^${}()|[\]\\]/g, '\\$&')`
3. **Case insensitive:** Uses `i` flag in regex
4. **Word boundaries:** Uses `\b` to avoid partial matches

---

## Verification Checklist

- [ ] Single word typo replaced correctly
- [ ] Multi-word values handled
- [ ] Rest of query preserved
- [ ] Auto-submission works
- [ ] Case insensitive matching works
- [ ] Special characters don't break replacement
