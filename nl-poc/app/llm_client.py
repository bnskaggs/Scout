
import json
import logging
import os
from datetime import date
from pathlib import Path

try:  # pragma: no cover - optional dependency for runtime environments
    from dateutil.relativedelta import relativedelta
except ModuleNotFoundError:  # pragma: no cover
    relativedelta = None

try:  # pragma: no cover - optional dependency for runtime environments
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover
    OpenAI = None

try:  # pragma: no cover - optional dependency for runtime environments
    from openai import OpenAIError  # type: ignore[attr-defined]
except (ModuleNotFoundError, ImportError):  # pragma: no cover
    try:  # pragma: no cover
        from openai import APIError as OpenAIError  # type: ignore[attr-defined]
    except (ModuleNotFoundError, ImportError):  # pragma: no cover
        OpenAIError = Exception


logger = logging.getLogger(__name__)


_ENV_LOADED = False


def _load_env_once() -> None:
    """Populate os.environ from a local .env file if available."""

    global _ENV_LOADED
    if _ENV_LOADED:
        return

    base_dir = Path(__file__).resolve().parents[1]
    env_paths = [base_dir / ".env"]

    cwd_path = Path.cwd() / ".env"
    if cwd_path not in env_paths:
        env_paths.append(cwd_path)

    for env_path in env_paths:
        if not env_path.exists():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            logger.debug("Unable to read .env file at %s", env_path)

    _ENV_LOADED = True



class LLMNotConfigured(Exception):
    logger.debug(Exception)
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
    logger.debug("call_intent_llm entered")
    _load_env_once()

    provider = os.getenv("LLM_PROVIDER", "").lower()
    model = os.getenv("LLM_MODEL", "")
    api_key = os.getenv("LLM_API_KEY", "")

    if not provider or not model or not api_key:
        raise LLMNotConfigured("Missing LLM_PROVIDER/LLM_MODEL/LLM_API_KEY")

    if provider != "openai":  # pragma: no cover - only OpenAI is currently supported
        raise LLMNotConfigured(f"Unsupported LLM provider: {provider}")

    if OpenAI is None:  # pragma: no cover - SDK is optional at install time
        raise LLMNotConfigured("openai SDK is not installed")

    sys_prompt = fill_time_tokens(prompt_text)
    columns = ", ".join(column_catalog)
    user_payload = (
        "Semantic spec:\n```yaml\n"
        + semantic_yaml
        + "\n```\n\nColumns:\n"
        + columns
        + "\n\nQuestion:\n"
        + question
    )

    try:  # pragma: no cover - networked call
        logger.debug("Initializing OpenAI client for provider '%s' with model '%s'", provider, model)
        client = OpenAI(api_key=api_key)
        logger.debug(
            "Sending OpenAI responses request", extra={"model": model, "column_count": len(column_catalog)}
        )
        resp = client.responses.create(
            model=model,
            temperature=0,
            input=[
                {"role": "system", "content": [{"type": "text", "text": sys_prompt}]},
                {"role": "user", "content": [{"type": "text", "text": user_payload}]},
            ],
        )
        logger.info("OpenAI responses request succeeded", extra={"response_id": getattr(resp, "id", None)})
    except OpenAIError as exc:  # pragma: no cover - networked call
        logger.exception("OpenAI responses request raised OpenAIError")
        raise RuntimeError("OpenAI request failed") from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("OpenAI responses request raised unexpected exception")
        raise RuntimeError("OpenAI request failed") from exc

    try:
        return resp.output_text.strip()
    except AttributeError:
        # Fall back to Chat Completions-style payloads for backward compatibility.
        return resp.choices[0].message.content.strip()
