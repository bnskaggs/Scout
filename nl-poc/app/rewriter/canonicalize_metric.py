from __future__ import annotations

import re
from typing import Dict, List

from ..synonyms import SynonymBundle


_COUNT_INTENT_RE = re.compile(r"\b(?:how many|count|number of)\b", re.IGNORECASE)


def _detect_domain_metric(question: str, bundle: SynonymBundle) -> str | None:
    lowered = question.lower()
    for token, canonical in bundle.metric_aliases.items():
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return canonical
    return None


def canonicalize_metric(question: str, plan: Dict[str, object], bundle: SynonymBundle) -> Dict[str, object]:
    """Normalise metric selections for count intents."""

    if not isinstance(plan, dict):
        return plan
    if not _COUNT_INTENT_RE.search(question):
        return plan

    metrics = plan.get("metrics") or []
    metrics = [metric for metric in metrics if isinstance(metric, str)]
    domain_metric = next((metric for metric in metrics if metric not in {"count", "*"}), None)
    if not domain_metric:
        domain_metric = _detect_domain_metric(question, bundle)

    updated_metrics: List[str]
    extras = plan.get("extras")
    diagnostics: List[Dict[str, object]] = []
    if isinstance(extras, dict):
        diagnostics = [diag for diag in extras.get("diagnostics", []) if isinstance(diag, dict)]
    existing_diag_keys = {(diag.get("type"), diag.get("message")) for diag in diagnostics}

    if domain_metric:
        updated_metrics = [domain_metric]
    else:
        updated_metrics = ["*"]
        fallback_entry = (
            "unknown_metric_fallback",
            "Using row count for 'count' intent",
        )
        if fallback_entry not in existing_diag_keys:
            diagnostics.append(
                {
                    "type": fallback_entry[0],
                    "message": fallback_entry[1],
                }
            )

    plan["metrics"] = updated_metrics
    plan["aggregate"] = "count"

    if diagnostics:
        extras = extras or {}
        extras["diagnostics"] = diagnostics
        plan["extras"] = extras

    return plan
