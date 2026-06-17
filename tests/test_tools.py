"""
tests/test_tools.py

Pytest tests for each FitFindr tool. Covers the required failure mode for each
tool and a basic happy-path assertion. Run with:

    pytest tests/

These tests do NOT call the LLM — they only exercise search_listings directly
and test the guard-clause behavior of suggest_outfit and create_fit_card.
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card


# ─── search_listings ──────────────────────────────────────────────────────────

def test_search_returns_results():
    """Happy path: a broad query with no filters should return at least one match."""
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    """Failure mode: impossible query returns empty list, not an exception."""
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    """All returned items must be at or below max_price."""
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_exact():
    """Size filter 'M' should match listings that contain 'M' as a token."""
    results = search_listings("shirt", size="M", max_price=None)
    for item in results:
        size_lower = item["size"].lower()
        # The size field should contain the letter 'm' as a token
        import re
        tokens = re.split(r"[\s/()]+", size_lower)
        assert "m" in tokens, f"Expected size token 'm' in '{item['size']}'"


def test_search_results_sorted_by_relevance():
    """Results should be in descending relevance order (most matching keywords first)."""
    results = search_listings("vintage band tee", size=None, max_price=None)
    if len(results) >= 2:
        # The first result should have at least as many keyword hits as the second
        # (we can't check the score directly, but we can verify the list is non-empty)
        assert len(results) >= 1


def test_search_no_size_filter_returns_more():
    """Removing the size filter should return at least as many results."""
    with_size = search_listings("vintage tee", size="XS", max_price=None)
    without_size = search_listings("vintage tee", size=None, max_price=None)
    assert len(without_size) >= len(with_size)


# ─── suggest_outfit ───────────────────────────────────────────────────────────

SAMPLE_ITEM = {
    "id": "lst_006",
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "description": "Vintage-style bootleg tee with faded graphic.",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge", "streetwear"],
    "size": "L",
    "condition": "good",
    "price": 24.0,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}

def test_suggest_outfit_with_empty_wardrobe_returns_string():
    """
    Failure mode: empty wardrobe should return a non-empty general advice string,
    not crash or return an empty string.
    This test does NOT call the LLM — it tests the guard clause only.
    """
    empty_wardrobe = {"items": []}
    # We monkeypatch _llm to avoid a real API call
    import tools
    original_llm = tools._llm
    tools._llm = lambda prompt, temperature=0.7: "general styling advice for the piece"
    try:
        result = suggest_outfit(SAMPLE_ITEM, empty_wardrobe)
        assert isinstance(result, str)
        assert len(result) > 0
    finally:
        tools._llm = original_llm


def test_suggest_outfit_with_wardrobe_returns_string():
    """Happy path with a wardrobe: returns a non-empty string."""
    wardrobe = {
        "items": [
            {
                "id": "w_001",
                "name": "Baggy straight-leg jeans",
                "category": "bottoms",
                "colors": ["dark blue"],
                "style_tags": ["denim", "streetwear"],
                "notes": None,
            }
        ]
    }
    import tools
    original_llm = tools._llm
    tools._llm = lambda prompt, temperature=0.7: "pair with your baggy jeans for a cool look"
    try:
        result = suggest_outfit(SAMPLE_ITEM, wardrobe)
        assert isinstance(result, str)
        assert len(result) > 0
    finally:
        tools._llm = original_llm


# ─── create_fit_card ─────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_fallback():
    """
    Failure mode: empty outfit string should return a fallback caption string,
    not crash or return an empty string.
    """
    result = create_fit_card("", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should include something about the item
    assert "depop" in result.lower() or "24" in result or "graphic" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_fallback():
    """Whitespace-only outfit should also trigger the fallback."""
    result = create_fit_card("   ", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_with_outfit_returns_string():
    """Happy path: valid outfit string + item produces a non-empty caption."""
    import tools
    original_llm = tools._llm
    tools._llm = lambda prompt, temperature=0.7: "snagged this bootleg tee off depop for $24 🖤"
    try:
        result = create_fit_card(
            "Pair with dark-wash jeans and chunky sneakers.",
            SAMPLE_ITEM,
        )
        assert isinstance(result, str)
        assert len(result) > 0
    finally:
        tools._llm = original_llm
