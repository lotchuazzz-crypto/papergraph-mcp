"""Built-in scholarly reference search providers."""

from __future__ import annotations


def default_reference_search_providers() -> list:
    """Return default provider instances.

    Imports stay lazy so tests can use the ranking and persistence layer without
    importing HTTP adapters.
    """

    from papergraph.reference_providers.arxiv import ArxivReferenceProvider
    from papergraph.reference_providers.crossref import CrossrefReferenceProvider
    from papergraph.reference_providers.openalex import OpenAlexReferenceProvider

    return [
        CrossrefReferenceProvider(),
        OpenAlexReferenceProvider(),
        ArxivReferenceProvider(),
    ]
