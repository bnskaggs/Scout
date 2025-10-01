# Manual Testing Guide: Codex Features

## Quick Verification Checklist

### Prerequisites
1. Start backend: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
2. Open `frontend/index.html` in browser

---

## Test 1: Filter Chips Display ✓

**Steps:**
1. Enter query: "Incidents in Central during 2024-05"
2. Click "Ask"

**Expected:**
- Results appear
- Below the answer header, you see filter chips:
  - `month: 2024-05-01` [×]
  - `area: Central` [×]
- Chips are blue with × buttons

**Screenshot areas to check:**
- [ ] Filter chips visible
- [ ] Correct labels
- [ ] × buttons present

---

## Test 2: Chip Removal & Re-run ✓

**Steps:**
1. From Test 1 results, click × on "area: Central" chip
2. Observe behavior

**Expected:**
- Input box updates to reconstructed query
- Query automatically re-runs
- New results show without "area: Central" filter
- Only `month: 2024-05-01` chip remains
- Results now include ALL areas, not just Central

**Verification:**
- [ ] Query re-ran automatically
- [ ] "area: Central" chip removed
- [ ] Results changed (more rows)
- [ ] Input box shows new query

---

## Test 3: Copy SQL Button ✓

**Steps:**
1. Run any query
2. Click "Copy SQL" button
3. Paste into a text editor (Ctrl+V / Cmd+V)

**Expected:**
- Button briefly shows "✓ Copied!"
- Pasted content is SQL query starting with "WITH base AS..."
- SQL is readable and complete

**Verification:**
- [ ] Button shows confirmation
- [ ] Clipboard contains SQL
- [ ] SQL looks valid

---

## Test 4: Copy JSON Plan Button ✓

**Steps:**
1. Run any query
2. Click "Copy JSON Plan" button
3. Paste into a text editor

**Expected:**
- Button briefly shows "✓ Copied!"
- Pasted content is JSON with structure:
```json
{
  "metrics": [...],
  "group_by": [...],
  "filters": [...],
  ...
}
```

**Verification:**
- [ ] Button shows confirmation
- [ ] Clipboard contains JSON
- [ ] JSON is pretty-printed (indented)

---

## Test 5: Download CSV Button ✓

**Steps:**
1. Run query: "Top 5 areas by incidents in 2024"
2. Click "Download CSV" button
3. Check Downloads folder

**Expected:**
- Browser download dialog appears
- File `scout-results.csv` downloads
- Open file in Excel/text editor
- Contains headers + data rows
- Data matches the table on screen

**Verification:**
- [ ] File downloaded
- [ ] CSV has correct headers
- [ ] Data rows present
- [ ] Commas/quotes escaped properly

---

## Test 6: History - Add Entries ✓

**Steps:**
1. Run these queries in order:
   - "Incidents in Central"
   - "Crimes in Hollywood"
   - "Show burglaries in 2024"

2. Scroll down to "Recent Queries" section

**Expected:**
- History panel shows 3 entries
- Most recent on top ("Show burglaries in 2024")
- Each shows:
  - "Just now" or "1m ago" timestamp
  - Full query text
  - [Re-run] button

**Verification:**
- [ ] All 3 queries visible
- [ ] Correct order (newest first)
- [ ] Timestamps present
- [ ] Re-run buttons visible

---

## Test 7: History - Re-run ✓

**Steps:**
1. From Test 6, click "Re-run" on middle entry ("Crimes in Hollywood")

**Expected:**
- Input box populates with "Crimes in Hollywood"
- Query automatically executes
- Results appear for Hollywood
- History updates (this query moves to top)

**Verification:**
- [ ] Input box updated
- [ ] Query executed
- [ ] Results match query
- [ ] History reordered

---

## Test 8: History - Persistence ✓

**Steps:**
1. Note the queries in history
2. **Refresh the page** (F5 or Ctrl+R)
3. Scroll to "Recent Queries"

**Expected:**
- History still shows all previous queries
- Order preserved
- Timestamps updated (now show "2m ago" etc.)

**Verification:**
- [ ] History survived refresh
- [ ] All queries still present
- [ ] Order maintained

---

## Test 9: History - 10 Entry Limit ✓

**Steps:**
1. Run 15 different queries (vary the text)
2. Check history

**Expected:**
- History shows only last 10 queries
- Oldest 5 dropped
- Still in reverse chronological order

**Example queries to run:**
```
1. Incidents in Central
2. Crimes in Hollywood
3. Burglaries in 2024
4. Assaults in West LA
5. Theft incidents
6. Vandalism reports
7. Vehicle thefts
8. Robberies in 2023
9. Weapons incidents
10. Drug offenses
11. Domestic violence
12. Gang activity
13. Juvenile crimes
14. DUI incidents
15. Fraud cases
```

**Verification:**
- [ ] Only 10 entries visible
- [ ] Shows entries #6-15
- [ ] Entries #1-5 gone

---

## Test 10: History - Deduplication ✓

**Steps:**
1. Run query: "Incidents in Central"
2. Run different query: "Crimes in Hollywood"
3. Run same query again: "Incidents in Central"
4. Check history

**Expected:**
- Only ONE "Incidents in Central" entry
- It moved to the top (most recent position)
- "Crimes in Hollywood" now second

**Verification:**
- [ ] No duplicate entries
- [ ] Recent instance at top
- [ ] Old instance removed

---

## Test 11: Filter Chips - Complex Query ✓

**Steps:**
1. Run query: "Incidents involving firearms in Central during Q1 2024"

**Expected:**
- Multiple filter chips appear:
  - `month: 2024-01-01 to 2024-04-01`
  - `area: Central`
  - `weapon: contains pattern`

**Verification:**
- [ ] All filters shown as chips
- [ ] Date range formatted correctly
- [ ] Pattern filter labeled appropriately

---

## Test 12: Chip Removal - Multiple Removals ✓

**Steps:**
1. From Test 11, remove `weapon: contains pattern` chip
2. Verify results update
3. Remove `area: Central` chip
4. Verify results update again

**Expected:**
- After first removal: Only month + area filters remain
- After second removal: Only month filter remains
- Results progressively broader each time

**Verification:**
- [ ] First removal worked
- [ ] Second removal worked
- [ ] Each removal triggered re-run
- [ ] Results got broader

---

## Test 13: Copy Buttons - No Results Yet ✓

**Steps:**
1. Refresh page (no queries run yet)
2. Try clicking Copy SQL / Copy JSON / Download CSV

**Expected:**
- Buttons don't appear yet (or do nothing if clicked)
- No errors in console

**Verification:**
- [ ] No crashes
- [ ] Graceful handling

---

## Edge Cases to Test

### Empty Result Set
1. Run query with no matches: "Incidents in Fake Area Name"
2. Verify chips still render correctly
3. Verify copy/download buttons handle empty data

### Single Filter
1. Run query: "Incidents in 2024"
2. Should show only one chip
3. Remove it and verify

### No Filters
1. Run query: "Total incidents"
2. Should show no chips (filter chips container hidden)
3. Copy/download buttons still work

---

## Browser Compatibility Testing

Test in multiple browsers:

- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari (if on Mac)

**Features to verify in each:**
- Clipboard API (copy buttons)
- Download functionality
- localStorage
- CSS rendering (chips, buttons, history)

---

## Console Errors

Open browser console (F12) and watch for:
- [ ] No errors during normal operation
- [ ] No errors on chip removal
- [ ] No errors on copy/download
- [ ] No errors on history operations

---

## Acceptance Criteria Final Check

### ✅ Removing "area: Central" chip re-runs without it
- **Test:** Test 2
- **Status:** ___

### ✅ Copy/Download buttons work
- **Test:** Tests 3, 4, 5
- **Status:** ___

### ✅ History persists across refresh
- **Test:** Test 8
- **Status:** ___

---

## Troubleshooting

### Chips don't appear
- Check: Did query return filters in plan?
- Check: Browser console for errors
- Check: `filterChipsContainer.style.display`

### Copy buttons don't work
- Check: Browser supports Clipboard API (HTTPS or localhost only)
- Check: Browser permissions
- Fallback: Use `document.execCommand('copy')` if needed

### CSV doesn't download
- Check: Browser download settings
- Check: Popup blocker
- Check: Console for Blob/URL errors

### History doesn't persist
- Check: Browser allows localStorage
- Check: Not in incognito/private mode
- Check: localStorage quota not exceeded
- Check: Console for storage errors

---

## Success Criteria

All tests pass:
- [ ] Filter chips display correctly
- [ ] Chip removal triggers re-run
- [ ] Copy SQL works
- [ ] Copy JSON works
- [ ] Download CSV works
- [ ] History saves queries
- [ ] History persists across refresh
- [ ] Re-run from history works
- [ ] 10 entry limit enforced
- [ ] Deduplication works

**Date Tested:** ___________
**Tested By:** ___________
**Browser:** ___________
**Result:** PASS / FAIL
