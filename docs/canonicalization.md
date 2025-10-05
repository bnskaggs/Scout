# Canonicalization workbench

The canonicalization workbench provides a lightweight flow for mapping free-form
synonyms to canonical dimension values.  Admins can search for a token, review
ranked candidates, and promote a mapping with a single click.  Resolver
components consume the canonical map without requiring a process restart.

## Fuzzy search and scoring

The search endpoint builds a list of potential canonical values by querying the
configured dimension column (distinct values, capped at 500 rows for
performance).  Each candidate is scored using trigram-based cosine similarity
between the query token and the candidate string.

Scores fall in the `[0.0, 1.0]` range.  By default only matches whose cosine
score is at least `0.75` are surfaced; this threshold can be tuned via the
`FuzzyMatcher` instance that powers the store.  Results are sorted by score in
descending order.  In the UI we display the top ranked matches alongside their
scores and whether the candidate already has a canonical mapping.

Practical guidelines:

- Scores below `0.70` are treated as noise and will not be suggested.
- Scores `≥ 0.80` typically represent strong matches and appear in the top
  positions, making them ideal candidates for promotion.
- Exact and near-exact matches generally produce scores very close to `1.0`.

## Promotion lifecycle and versioning

Promoting a synonym writes a row into the `canonical_map` table with the
observed score, promoter metadata, and a monotonically increasing version.
Every promotion increments the global version, allowing downstream caches to
invalidate themselves without requiring any coordination beyond the database.

The `CanonicalWatcher` polls the version at a configurable interval (default 1
second), reloading the in-memory map whenever it observes a change.  The
resolver shares the same canonicalizer instance and therefore sees updates
within the next poll cycle.

## LIKE bypass semantics

Canonicalization is intentionally skipped when the raw value contains SQL `LIKE`
patterns.  If a synonym includes the `%` wildcard (for example `%firearm%`) the
canonicalizer treats it as an explicit pattern provided by the analyst.  In this
scenario the resolver leaves the value untouched and records
`like_bypass = true` while also setting `canonicalization_applied = false`.  The
lineage metadata surfaces both flags so downstream consumers can understand why a
value did or did not canonicalize.
