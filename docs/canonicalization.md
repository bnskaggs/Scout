# Canonicalization workbench

The workbench is an admin-only surface for curating synonym → canonical value
mappings.  It lives at `/admin/canonical` and consists of an HTML workbench plus
a matching JSON API exposed under `/api/admin/canonical`.  The HTML form lets an
operator search for a token, review fuzzy matched candidates, and promote a
mapping with one click.  The JSON API powers automation and integration tests.

## Storage schema

Canonical mappings are stored in two tables:

- `canonical_map`: `dim`, `synonym`, `canonical`, `score`, and audit metadata.
- `canonical_meta`: a single `version` row incremented on every promotion.

Only `SELECT`, `INSERT`, and `UPDATE` statements are used to respect the
no-destructive-migrations constraint.

## Fuzzy search and scoring

Search builds a candidate set from two sources: distinct values for the selected
dimension in `la_crime_raw` and any existing synonyms already promoted for that
dimension.  The `FuzzyMatcher` ranks candidates using trigram-based cosine
similarity.  Results contain:

- `candidate`: the value we can promote to.
- `score`: similarity score between the query and candidate (`0.0`–`1.0`).
- `canonical`: the canonical value currently mapped to the candidate (if any).

Scores ≥ ~0.80 are generally strong matches; exact or prefix matches typically
hover near `1.0`.

## Promotion + live cache reload

Both the HTML form and JSON API post to `/admin/canonical/promote`.  Promotions
either insert or update the `canonical_map` entry and bump the global version in
`canonical_meta`.  The FastAPI app immediately reloads the in-memory
`Canonicalizer` so callers observe the new mapping without restarting the
service.  A background `CanonicalWatcher` keeps long-lived processes in sync by
polling the version every second.

## Optional basic authentication

Enable `ADMIN_BASIC_AUTH=true` to require HTTP Basic Auth for both the HTML and
JSON routes.  Override `ADMIN_USER` / `ADMIN_PASS` to change credentials.  When
disabled (the default), the workbench remains unsecured for local development.

## Resolver behaviour

The resolver normalises synonyms to lowercase before lookup and only applies a
canonical value when an exact synonym match is found.  Tokens containing SQL
`LIKE` wildcards (e.g. `%firearm%`) bypass canonicalization to preserve analyst
intent.  Callers can inspect the `CanonicalResolution` object to see whether a
mapping was applied and which canonical value was chosen.
