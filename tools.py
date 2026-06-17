"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _llm(prompt: str, temperature: float = 0.7) -> str:
    """Call the LLM and return the response text."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()

    # Step 1: Filter by max_price
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Step 2: Filter by size (case-insensitive token match)
    if size:
        size_lower = size.strip().lower()
        filtered = []
        for listing in listings:
            # Split the listing size into tokens on spaces, slashes, parens
            tokens = re.split(r"[\s/()]+", listing.get("size", "").lower())
            tokens = [t for t in tokens if t]
            if size_lower in tokens:
                filtered.append(listing)
        listings = filtered

    # Step 3: Score each listing by keyword overlap with description
    keywords = set(re.split(r"[\s,\-]+", description.lower()))
    keywords = {k for k in keywords if len(k) > 2}  # drop short stop words

    def _score(listing: dict) -> int:
        searchable = " ".join([
            listing.get("title", ""),
            listing.get("description", ""),
            listing.get("category", ""),
            listing.get("brand", "") or "",
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
        ]).lower()
        return sum(1 for kw in keywords if kw in searchable)

    # Step 4: Drop listings with score 0
    scored = [(l, _score(l)) for l in listings]
    scored = [(l, s) for l, s in scored if s > 0]

    # Step 5: Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return [l for l, _ in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    item_desc = (
        f"Title: {new_item.get('title', 'unknown')}\n"
        f"Category: {new_item.get('category', 'unknown')}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Condition: {new_item.get('condition', 'unknown')}\n"
        f"Price: ${new_item.get('price', '?')}\n"
        f"Platform: {new_item.get('platform', 'unknown')}"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe — general styling advice only
        prompt = (
            "You are a thrift fashion stylist. A user just found this secondhand item:\n\n"
            f"{item_desc}\n\n"
            "They haven't shared their wardrobe yet. Give them 1–2 general outfit ideas: "
            "what types of bottoms, shoes, and outerwear pair well with this piece? "
            "Be specific about silhouettes and vibes (e.g., 'wide-leg jeans and chunky sneakers' "
            "is better than 'jeans and shoes'). Keep it under 100 words. "
            "Note at the end that these are general suggestions — add their wardrobe for personalized ideas."
        )
    else:
        wardrobe_text = "\n".join(
            f"- {item.get('name', '')} [{item.get('category', '')}] "
            f"(colors: {', '.join(item.get('colors', []))}; "
            f"tags: {', '.join(item.get('style_tags', []))})"
            + (f"; notes: {item['notes']}" if item.get("notes") else "")
            for item in wardrobe_items
        )
        prompt = (
            "You are a thrift fashion stylist. A user just found this secondhand item:\n\n"
            f"{item_desc}\n\n"
            "Their current wardrobe contains:\n"
            f"{wardrobe_text}\n\n"
            "Suggest 1–2 complete outfits using the new item combined with specific pieces "
            "from their wardrobe above. Reference pieces by name. Be specific about "
            "styling details — tuck, layer, roll sleeves, etc. Keep it under 120 words."
        )

    try:
        return _llm(prompt, temperature=0.8)
    except Exception as exc:
        # Fallback: synthesize from style_tags without LLM
        tags = new_item.get("style_tags", [])
        category = new_item.get("category", "piece")
        tag_str = ", ".join(tags) if tags else "versatile"
        return (
            f"This {category} has a {tag_str} vibe. "
            "Try pairing it with straight-leg or wide-leg bottoms and clean sneakers or boots. "
            f"(Note: outfit generation encountered an issue — {exc})"
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)
    """
    if not outfit or not outfit.strip():
        # Fallback: build a minimal caption from item data alone
        title = new_item.get("title", "this find")
        price = new_item.get("price", "?")
        platform = new_item.get("platform", "a thrift app")
        return f"just copped the {title} off {platform} for ${price} 🔥 no outfit ideas yet but the piece speaks for itself"

    title = new_item.get("title", "this find")
    price = new_item.get("price", "?")
    platform = new_item.get("platform", "a thrift app")
    condition = new_item.get("condition", "")
    tags = ", ".join(new_item.get("style_tags", []))

    prompt = (
        "You are writing a casual Instagram/TikTok OOTD caption for a thrift find. "
        "Keep it 2–4 sentences. First-person, lowercase, authentic — like a real person posted it, "
        "not a brand. Do NOT use hashtags. Mention the item name, the price, and the platform "
        "each exactly once. Reference the outfit vibe in specific visual terms.\n\n"
        f"The thrifted item: {title} — ${price} from {platform}"
        + (f" ({condition} condition)" if condition else "")
        + (f". Style: {tags}." if tags else "")
        + f"\n\nThe outfit idea: {outfit}\n\n"
        "Write the caption now:"
    )

    try:
        return _llm(prompt, temperature=1.1)
    except Exception as exc:
        # Fallback caption
        return (
            f"thrifted the {title} off {platform} for ${price} and honestly it slaps. "
            f"(Note: caption generation hit an issue — {exc})"
        )
