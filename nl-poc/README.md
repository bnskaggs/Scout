# NL Analytics Proof of Concept

This project is a local proof of concept that converts natural-language questions about an LA crime-style dataset into SQL, runs it against DuckDB, and returns narrative, tables, charts, and lineage details.

## Project Structure

```
nl-poc/
  app/              # FastAPI service and supporting agents
  config/           # Semantic model definitions
  data/             # CSV input and generated DuckDB database
  eval/             # Sample evaluation prompts
  frontend/         # Minimal HTML front-end
```

## Getting Started

1. **Install dependencies**

   ```bash
   pip install fastapi uvicorn duckdb pyyaml openai
   ```

2. **Add data**

   Place the LA crime CSV (or a compatible dataset) in `nl-poc/data/`. The service automatically loads the first `.csv` file it finds and creates `games.duckdb` with views `la_crime_raw` and `la_crime_month_view`.

3. **Run the API**

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Open the UI**

   Serve `frontend/index.html` with any static HTTP server (or open it directly in the browser) and point it to the running API (defaults to the same origin if served together).

## API Endpoints

- `GET /health` – returns service status.
- `POST /ask` – accepts `{ "question": "..." }` and returns the analysis payload including SQL, plan, narrative, table, chart spec, and lineage.
- `GET /explain_last` – debugging endpoint returning the last executed plan and SQL.

## Semantic Configuration

`config/semantic.yml` defines the available metrics and dimensions. The resolver validates incoming plans against this file, ensuring only supported fields are used.

## Evaluation Prompts

`eval/questions.yaml` contains 20 representative questions for manual or automated testing.

## Enabling LLM Intent Parsing

By default the service uses the heuristic planner. To enable the LLM-powered intent agent:

1. Copy `config/settings.example.env` to `.env` (or export the variables in your shell).
2. Set `INTENT_USE_LLM=true` and provide `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_API_KEY` values for your provider. When using the
   bundled OpenAI integration, `LLM_PROVIDER` must be `openai` and `pip install openai` is required in the runtime environment.
3. Restart the API so the new environment variables take effect.

When the LLM settings are omitted or the call fails, the service automatically falls back to the rule-based planner.

## Notes

- The planner uses heuristic parsing suitable for demonstration purposes.
- Guardrails ensure only SELECT statements with safe limits execute against DuckDB.
- When grouping by victim age, partitions with fewer than five incidents are suppressed and bucketed into `Other (<5)`.
