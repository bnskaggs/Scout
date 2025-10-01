"""Debug script to trace where 2023 is coming from in YTD queries."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.time_utils import extract_time_range, current_date
from datetime import date

print("=" * 60)
print("DEBUG: Testing YTD Time Range Extraction")
print("=" * 60)

# Test 1: Check what current_date() returns
print("\n[TEST 1] Checking current_date()...")
today = current_date()
print(f"Result: {today}")

# Test 2: Simple "YTD" query
print("\n[TEST 2] Testing simple 'YTD' query...")
result = extract_time_range("YTD")
print(f"Result: {result}")

# Test 3: "year to date" phrase
print("\n[TEST 3] Testing 'year to date' phrase...")
result = extract_time_range("year to date")
print(f"Result: {result}")

# Test 4: Explicit year YTD
print("\n[TEST 4] Testing '2024 YTD'...")
result = extract_time_range("2024 YTD")
print(f"Result: {result}")

# Test 5: Multi-year YTD
print("\n[TEST 5] Testing '2023 vs 2024 YTD'...")
result = extract_time_range("2023 vs 2024 YTD")
print(f"Result: {result}")

# Test 6: With explicit today parameter
print("\n[TEST 6] Testing YTD with explicit today=2025-10-01...")
result = extract_time_range("YTD", today=date(2025, 10, 1))
print(f"Result: {result}")

print("\n" + "=" * 60)
print("END DEBUG")
print("=" * 60)
