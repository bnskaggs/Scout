# NQL v0.2 Specification

## Overview

NQL v0.2 extends v0.1 with advanced analytical operators for comparisons, aggregations, bucketing, and ranking. All v0.1 functionality remains intact. Enable v0.2 features via the `NQL_V2_ENABLED=true` environment variable.

## Key Features

### 1. Enhanced Compare Operators

#### Month-over-Month (MoM)
Returns **both current and baseline** values with difference calculations.

```json
{
  "nql_version": "0.2",
  "compare": {
    "baseline": "previous_period",
    "method": "diff_pct"  // or "diff_abs"
  },
  "time": {
    "window": {"type": "single_month", "start": "2023-12-01"}
  }
}
```

**Output columns**: `current`, `baseline`, `diff_pct` (or `diff_abs`)

#### Year-over-Year (YoY)
```json
{
  "compare": {
    "baseline": "same_period_last_year",
    "method": "diff_pct"
  }
}
```

#### Pre/Post (Absolute Baseline)
For A/B testing or before/after event analysis:

```json
{
  "compare": {
    "baseline": "absolute",
    "start": "2023-01-01",
    "end": "2023-06-15",
    "method": "diff_abs"
  },
  "time": {
    "window": {"type": "absolute", "start": "2023-06-15", "end": "2023-12-01"}
  }
}
```

#### Compare Entities (via panel_by)
Side-by-side comparison of areas, categories, etc.:

```json
{
  "filters": [{"field": "area", "op": "in", "value": ["Hollywood", "Wilshire"]}],
  "panel_by": "area"
}
```

**Visualization**: Small multiples or compare panels.

### 2. Top-K Within Group

Rank top-K items **within each partition** using window functions:

```json
{
  "group_by": ["area", "crime_type"],
  "top_k_within_group": {
    "k": 3,
    "by": "incidents"
  }
}
```

**SQL Pattern**:
```sql
ROW_NUMBER() OVER (PARTITION BY area ORDER BY incidents DESC) <= 3
```

### 3. Bucketing (Quantiles & Custom)

#### Quantile Bucketing
Automatically compute quartiles, deciles, or custom quantiles:

```json
{
  "bucket": {
    "field": "incidents",
    "method": "quantile",
    "params": {"q": [0, 0.25, 0.5, 0.75, 1]}  // Quartiles
  }
}
```

**SQL**: Uses `PERCENTILE_DISC()` to compute edges, then labels buckets.

#### Custom Edges
```json
{
  "bucket": {
    "field": "incidents",
    "method": "custom",
    "params": {"edges": [0, 100, 500, 1000, 5000]}
  }
}
```

### 4. Advanced Aggregates

#### Median
```json
{
  "aggregate_v2": {
    "median_of": "Vict Age",
    "estimator": "exact"  // or "approx"
  }
}
```

**SQL**: `PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY "Vict Age")`

#### Distinct Count
```json
{
  "aggregate_v2": {
    "distinct_of": "DR_NO",
    "estimator": "exact"
  }
}
```

**SQL**: `COUNT(DISTINCT "DR_NO")`

#### Combined
```json
{
  "aggregate_v2": {
    "median_of": "Vict Age",
    "distinct_of": "DR_NO"
  }
}
```

## Schema Reference

### Compare
```typescript
{
  baseline: "previous_period" | "same_period_last_year" | "absolute"
  start?: string         // Required if baseline="absolute"
  end?: string           // Required if baseline="absolute"
  method: "diff_abs" | "diff_pct"
}
```

### Bucket
```typescript
{
  field: string
  method: "quantile" | "custom"
  params: {
    q?: number[]       // For quantile: [0, 0.25, 0.5, 0.75, 1]
    edges?: number[]   // For custom: [0, 100, 500, 1000]
  }
}
```

### Aggregate
```typescript
{
  median_of?: string
  distinct_of?: string
  estimator: "exact" | "approx"
}
```

### TopKWithinGroup
```typescript
{
  k: number
  by: string  // Metric to rank by
}
```

### NQL Root (v0.2 additions)
```typescript
{
  nql_version: "0.2"
  panel_by?: string         // NEW: Creates small multiples
  compare?: Compare         // EXTENDED
  bucket?: Bucket           // NEW
  aggregate_v2?: Aggregate  // NEW
  top_k_within_group?: TopKWithinGroup  // NEW
  // ... all v0.1 fields
}
```

## Validation Rules

1. **single_month_required_for_mom**: MoM requires `single_month` or `relative_months` window
2. **baseline_absolute_requires_bounds**: `baseline="absolute"` must include `start` and `end`
3. **limit_clamp**: v0.2 limits clamped to [5, 100]
4. **select_only_guard**: Enforces SELECT-only SQL
5. **exclusive_bounds**: Month/quarter end is exclusive `[start, end)`

## SQL Patterns

### Compare (MoM with diff_pct)
```sql
WITH base AS (...),
     current AS (SELECT area, COUNT(*) AS value FROM base WHERE month = '2023-12-01' GROUP BY area),
     baseline AS (SELECT area, COUNT(*) AS value FROM base WHERE month = '2023-11-01' GROUP BY area)
SELECT
  c.area,
  c.value AS current,
  b.value AS baseline,
  CASE WHEN b.value = 0 THEN NULL
       ELSE (c.value - b.value) * 100.0 / b.value
  END AS diff_pct
FROM current c LEFT JOIN baseline b ON c.area = b.area
```

### Top-K Within Group
```sql
WITH base AS (...),
     aggregated AS (SELECT area, crime_type, COUNT(*) AS incidents FROM base GROUP BY area, crime_type),
     ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY area ORDER BY incidents DESC) AS rn FROM aggregated)
SELECT * FROM ranked WHERE rn <= 3
```

### Bucket (Quantiles)
```sql
WITH base AS (...),
     edges AS (SELECT PERCENTILE_DISC(0) ... AS q0, PERCENTILE_DISC(0.25) ... AS q25, ... FROM base)
SELECT
  CASE
    WHEN incidents < q25 THEN 'Q1'
    WHEN incidents < q50 THEN 'Q2'
    ...
  END AS bucket,
  COUNT(*) AS count
FROM base, edges
GROUP BY bucket
```

### Median & Distinct
```sql
SELECT
  area,
  PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY "Vict Age") AS median_age,
  COUNT(DISTINCT "DR_NO") AS distinct_cases
FROM base
GROUP BY area
```

## Visualization

### Compare Panels
When `compare.method` is present and results include `current`/`baseline`/`diff_*`:

```json
{
  "type": "compare_bar",
  "y_current": "current",
  "y_baseline": "baseline",
  "y_diff": "diff_pct"
}
```

### Small Multiples
When `panel_by` is set:

```json
{
  "type": "small_multiple",
  "panel_by": "area"
}
```

## Lineage Chips (Metadata)

v0.2 queries include enriched metadata in results:

- **Time window**: `2023-12-01 to 2024-01-01 (exclusive)`
- **Compare context**: `MoM, diff_pct, previous_period`
- **Filters**: Area IN [Hollywood, Wilshire]
- **Row cap**: Limited to 50 rows

## Examples

### Example 1: MoM for December 2023
```json
{
  "nql_version": "0.2",
  "intent": "compare",
  "dataset": "la_crime",
  "metrics": [{"name": "incidents", "agg": "count", "alias": "incidents"}],
  "time": {"grain": "month", "window": {"type": "single_month", "start": "2023-12-01"}},
  "compare": {"baseline": "previous_period", "method": "diff_pct"},
  "group_by": [],
  "filters": []
}
```

**Result**:
```json
[{
  "current": 1250,
  "baseline": 1180,
  "diff_pct": 5.9
}]
```

### Example 2: Compare Hollywood vs Wilshire
```json
{
  "nql_version": "0.2",
  "filters": [{"field": "area", "op": "in", "value": ["Hollywood", "Wilshire"]}],
  "panel_by": "area"
}
```

**Visualization**: Two side-by-side panels.

### Example 3: Top 3 Crimes per Area
```json
{
  "nql_version": "0.2",
  "group_by": ["area", "crime_type"],
  "top_k_within_group": {"k": 3, "by": "incidents"}
}
```

### Example 4: Median Age by Area
```json
{
  "nql_version": "0.2",
  "group_by": ["area"],
  "aggregate_v2": {"median_of": "Vict Age", "estimator": "exact"}
}
```

## Migration from v0.1

1. Set `"nql_version": "0.2"` in payload
2. Enable via `NQL_V2_ENABLED=true`
3. v0.1 queries continue to work unchanged
4. New features are opt-in via explicit fields

## Constraints

- **Python 3.10+**, FastAPI
- **SELECT-only SQL** (no writes)
- **Explicit time windows** required
- **Month/quarter end exclusive**: `[start, end)`
- **Deterministic JSON** (sorted keys in plan output)
- **Limit range**: 5-100 (v0.2), 1-2000 (v0.1)
