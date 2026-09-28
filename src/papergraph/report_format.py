"""Small formatting helpers shared by evidence-first reading reports."""

from __future__ import annotations

import json
from typing import Any


def source_position(location: dict[str, Any] | None) -> tuple[int, int, int, str]:
    if not location:
        return (0, 0, 0, "")
    return (
        int(location.get("page") or 0),
        int(location.get("block_index") or 0),
        int(location.get("start_offset") or 0),
        str(location.get("span_id") or ""),
    )


def compact_json(value: Any) -> str:
    if value is None:
        return "`None`"
    return "`" + json.dumps(value, sort_keys=True, ensure_ascii=False) + "`"


def code_or_none(value: str | None) -> str:
    if value is None:
        return "`None`"
    return f"`{value}`"
