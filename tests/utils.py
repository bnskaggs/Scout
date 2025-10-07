from __future__ import annotations

import json
from typing import Any


def assert_sorted_json(obj: Any) -> str:
    """Return a deterministic JSON representation with sorted keys."""

    return json.dumps(obj, sort_keys=True)
