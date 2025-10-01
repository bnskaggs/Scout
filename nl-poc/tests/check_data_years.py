"""Check what years of data exist in the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb

db_path = Path(__file__).parent.parent / "data" / "games.duckdb"

print("=" * 60)
print("DATABASE DATA YEAR CHECK")
print("=" * 60)

try:
    # Open in read-only mode to avoid locks
    conn = duckdb.connect(str(db_path), read_only=True)

    # Get min/max dates
    result = conn.execute('''
        SELECT
            MIN(DATE_TRUNC('month', "DATE OCC")) as min_month,
            MAX(DATE_TRUNC('month', "DATE OCC")) as max_month,
            COUNT(*) as total_rows
        FROM la_crime_raw
    ''').fetchone()

    print(f"\nDatabase: {db_path}")
    print(f"Total rows: {result[2]:,}")
    print(f"Date range: {result[0]} to {result[1]}")

    # Get year distribution
    year_dist = conn.execute('''
        SELECT
            YEAR(DATE_TRUNC('month', "DATE OCC")) as year,
            COUNT(*) as count
        FROM la_crime_raw
        GROUP BY year
        ORDER BY year
    ''').fetchall()

    print(f"\nYear distribution:")
    for year, count in year_dist:
        print(f"  {year}: {count:,} records")

    conn.close()

    print("\n" + "=" * 60)
    print("DIAGNOSIS:")
    print("=" * 60)

    max_year = result[1].year if result[1] else None
    if max_year and max_year < 2025:
        print(f"\n✗ Database only has data up to {max_year}")
        print(f"  When YTD query filters for 2025, it returns NO DATA")
        print(f"\nSOLUTION: Need to either:")
        print(f"  1. Add 2024-2025 data to the database, OR")
        print(f"  2. Mock current_date() to return a date in {max_year}, OR")
        print(f"  3. Test with explicit year: '{max_year} YTD' instead of 'YTD'")
    else:
        print(f"✓ Database has data up to {max_year} (current or recent)")

except Exception as e:
    print(f"\nError: {e}")
    print("\nNote: If database is locked, stop the backend server first")

print("\n" + "=" * 60)
