"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def _regex_parse(query: str) -> dict:
    """Regex-based fallback parser for description, size, and max_price."""
    price_match = re.search(r"under\s+\$?([\d.]+)", query, re.IGNORECASE)
    size_match = re.search(
        r"\bsize\s+([XSML]+\d*|[0-9]{1,2}(?:\.[05])?)\b", query, re.IGNORECASE
    )
    description = re.sub(r"under\s+\$[\d.]+", "", query, flags=re.IGNORECASE)
    description = re.sub(r"\bsize\s+\S+", "", description, flags=re.IGNORECASE).strip()
    # Also strip stray "size" with no following token
    description = re.sub(r"\bsize\b", "", description, flags=re.IGNORECASE).strip()
    return {
        "description": description or query,
        "size": size_match.group(1) if size_match else None,
        "max_price": float(price_match.group(1)) if price_match else None,
    }


def _parse_query(query: str) -> dict:
    """
    Use the LLM to extract description, size, and max_price from a natural
    language query. Returns a dict with keys: description (str), size (str|None),
    max_price (float|None).

    Falls back to regex parsing if no API key is set or if the LLM call fails.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return _regex_parse(query)

    prompt = (
        "Extract search parameters from this thrift shopping query. "
        "Return ONLY a JSON object with exactly these keys:\n"
        '  "description": a short keyword phrase describing the item (string)\n'
        '  "size": the clothing size mentioned, or null if none\n'
        '  "max_price": the maximum price as a float, or null if none\n\n'
        f"Query: {query}\n\n"
        "JSON only, no explanation:"
    )
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        return {
            "description": parsed.get("description") or query,
            "size": parsed.get("size") or None,
            "max_price": float(parsed["max_price"]) if parsed.get("max_price") else None,
        }
    except Exception:
        return _regex_parse(query)


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query to extract description, size, max_price
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Call search_listings
    results = search_listings(description=description, size=size, max_price=max_price)
    session["search_results"] = results

    if not results:
        # Build a helpful, specific error message
        parts = [f"No listings matched \"{description}\""]
        if size:
            parts.append(f"in size {size}")
        if max_price is not None:
            parts.append(f"under ${max_price:.0f}")
        msg = " ".join(parts) + "."
        suggestions = []
        if size:
            suggestions.append("try removing the size filter")
        if max_price is not None:
            suggestions.append(f"try raising your budget (e.g., ${max_price + 20:.0f})")
        suggestions.append("broaden your description (e.g., 'graphic tee' instead of 'vintage band tee')")
        msg += " You could: " + "; or ".join(suggestions) + "."
        session["error"] = msg
        return session

    # Step 4: Pick the top result
    session["selected_item"] = results[0]

    # Step 5: Suggest an outfit
    outfit = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )
    session["outfit_suggestion"] = outfit

    # Step 6: Generate the fit card
    fit_card = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )
    session["fit_card"] = fit_card

    # Step 7: Return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
