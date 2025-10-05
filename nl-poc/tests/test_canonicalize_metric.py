from pathlib import Path
import sys

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rewriter.canonicalize_metric import canonicalize_metric
from app.synonyms import load_synonyms


@pytest.fixture(scope="module")
def bundle():
    return load_synonyms()


def test_canonicalize_metric_preserves_domain_metric(bundle):
    plan = {"metrics": ["count"], "group_by": [], "filters": []}
    result = canonicalize_metric("How many incidents citywide?", plan, bundle)
    assert result["metrics"] == ["incidents"]
    assert result["aggregate"] == "count"


def test_canonicalize_metric_sets_row_count(bundle):
    plan = {"metrics": ["count"], "group_by": ["area"], "filters": []}
    result = canonicalize_metric("count by area in 2024", plan, bundle)
    assert result["metrics"] == ["*"]
    assert result["aggregate"] == "count"
    assert result["group_by"] == ["area"]


def test_canonicalize_metric_adds_fallback_diagnostic(bundle):
    plan = {"metrics": ["count"], "filters": []}
    result = canonicalize_metric("number of stabbings last month", plan, bundle)
    assert result["aggregate"] == "count"
    extras = result.get("extras", {})
    diagnostics = extras.get("diagnostics", [])
    assert any(diag.get("type") == "unknown_metric_fallback" for diag in diagnostics)
