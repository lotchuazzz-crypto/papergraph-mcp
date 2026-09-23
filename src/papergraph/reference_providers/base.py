"""Shared reference-search provider contracts."""

from __future__ import annotations

from typing import Protocol
import httpx


def failure_result(provider: str, error: Exception, *, parsing: bool = False) -> dict:
    """Never return exception strings containing query URLs or credentials."""
    if isinstance(error, httpx.TimeoutException):
        outcome = 'timeout'
    elif isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429:
        outcome = 'rate_limited'
    else:
        outcome = 'invalid_response' if parsing else 'unavailable'
    return {'provider': provider, 'records': [], 'outcome': outcome, 'warnings': [outcome]}


def parsed_result(provider: str, items, converter) -> dict:
    if not isinstance(items, list):
        return failure_result(provider, ValueError(), parsing=True)
    records, invalid = [], 0
    for item in items:
        try:
            record = converter(item)
            if not record:
                invalid += 1
            else:
                records.append(record)
        except (ValueError, TypeError, AttributeError, KeyError, IndexError):
            invalid += 1
    outcome = ('partial' if records else 'invalid_response') if invalid else ('ok' if records else 'empty')
    return {'provider': provider, 'records': records, 'outcome': outcome,
            'warnings': ['invalid_records'] if invalid else []}


class ReferenceSearchProvider(Protocol):
    """Search one scholarly metadata source for normalized reference records."""

    name: str

    def search(self, query: dict) -> dict:
        """Return a provider result with `provider`, `records`, and `warnings`."""
