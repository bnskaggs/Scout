# Telemetry dashboard operations

## Log locations
- Raw telemetry events are appended to `var/log/telemetry.ndjson` (newline-delimited JSON).
- Weekly aggregates are written to `var/log/weekly_summary.json` by the rollup script.

Both files live at the repository root (or the path configured via `TELEMETRY_LOG_PATH` for tests).

## Running the weekly rollup
```
python scripts/weekly_rollup.py
```
- Optional flags:
  - `--log-path PATH` to override the input NDJSON file.
  - `--output-path PATH` to override the JSON summary destination.
  - `--top N` to change how many queries/synonyms are surfaced (default 20).

The command will regenerate `weekly_summary.json` with deterministic ordering, suitable for dashboards or audits.
