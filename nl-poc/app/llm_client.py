import os
from datetime import date


class LLMNotConfigured(Exception):
    pass


def current_month_start(today=None):
    today = today or date.today()
    return date(today.year, today.month, 1)


def month_start(dt):
    return date(dt.year, dt.month, 1)


def _add_months(dt: date, months: int) -> date:
    year_offset, new_month_index = divmod(dt.month - 1 + months, 12)
    return date(dt.year + year_offset, new_month_index + 1, dt.day)


def fill_time_tokens(prompt: str, today=None) -> str:
    today = today or date.today()
    cur = current_month_start(today)
    prev = month_start(_add_months(cur, -1))
    cur_m2 = month_start(_add_months(cur, -2))
    return (
        prompt.replace("<CURRENT_MONTH_START>", cur.isoformat())
        .replace("<PREV_MONTH_START>", prev.isoformat())
        .replace("<CURRENT_MONTH_MINUS_2>", cur_m2.isoformat())
    )


def call_intent_llm(prompt_text: str, semantic_yaml: str, column_catalog: list, question: str) -> str:
    """
    Returns raw JSON string from the LLM. Raises LLMNotConfigured if env is missing.
    """
    provider = os.getenv("LLM_PROVIDER", "").lower()
    model = os.getenv("LLM_MODEL", "")
    api_key = os.getenv("LLM_API_KEY", "")

    if not provider or not model or not api_key:
        raise LLMNotConfigured("Missing LLM_PROVIDER/LLM_MODEL/LLM_API_KEY")

    # ---- Replace this block with your provider-specific call. ----
    # Pseudocode example for OpenAI Chat Completions:
    #
    # from openai import OpenAI
    # client = OpenAI(api_key=api_key)
    # sys_prompt = fill_time_tokens(prompt_text)
    # user_payload = f"Semantic spec:\n```yaml\n{semantic_yaml}\n```\n\nColumns:\n{column_catalog}\n\nQuestion:\n{question}"
    # resp = client.chat.completions.create(
    #   model=model,
    #   messages=[{"role":"system","content": sys_prompt},
    #             {"role":"user","content": user_payload}],
    #   temperature=0
    # )
    # return resp.choices[0].message.content.strip()
    #
    # --------------------------------------------------------------

    # For now, raise so the caller can fall back to rule-based parsing.
    raise LLMNotConfigured("Stub: wire your provider in app/llm_client.py")
