"""Shared reference-search provider contracts."""

from __future__ import annotations

from typing import Protocol


class ReferenceSearchProvider(Protocol):
    """Search one scholarly metadata source for normalized reference records."""

    name: str

    def search(self, query: dict) -> dict:
        """Return a provider result with `provider`, `records`, and `warnings`."""
