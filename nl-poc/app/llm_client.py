
import json
import os
from datetime import date

try:  # pragma: no cover - optional dependency for runtime environments
    from dateutil.relativedelta import relativedelta
except ModuleNotFoundError:  # pragma: no cover
    relativedelta = None



class LLMNotConfigured(Exception):
    pass


def current_month_start(today=None):
    today = today or date.today()
    return date(today.year, today.month, 1)


def month_start(dt):
    return date(dt.year, dt.month, 1)



def _shift_months(dt: date, months: int) -> date:
    year_offset, new_month_index = divmod(dt.month - 1 + months, 12)
    return date(dt.year + year_offset, new_month_index + 1, 1)



def fill_time_tokens(prompt: str, today=None) -> str:
    today = today or date.today()
    cur = current_month_start(today)

    if relativedelta is not None:
        prev = month_start(cur - relativedelta(months=1))
        cur_m2 = month_start(cur - relativedelta(months=2))
    else:  # pragma: no cover - fallback when python-dateutil is unavailable
        prev = _shift_months(cur, -1)
        cur_m2 = _shift_months(cur, -2)

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
    # columns = ", ".join(column_catalog)
    # user_payload = (
    #     "Semantic spec:\n```yaml\n"
    #     + semantic_yaml
    #     + "\n```\n\nColumns:\n"
    #     + columns
    #     + "\n\nQuestion:\n"
    #     + question
    # )
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
