# FitFindr

A multi-tool AI agent that helps you find secondhand clothing and figure out how to wear it. You describe what you're looking for; FitFindr searches a mock dataset of thrift listings, builds an outfit from your existing wardrobe, and writes a shareable social-media caption — all in one flow.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit this):

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com) — no credit card required.

**Run the app:**

```bash
python app.py
```

Open the URL shown in your terminal (typically `http://localhost:7860`).

**Run the tests:**

```bash
pytest tests/ -v
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Searches the 40-item mock listings dataset and returns items that match the user's description, size, and price ceiling. Results are sorted by relevance so the best match is always first.

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Natural-language keywords for the item (e.g., `"vintage graphic tee"`). Matched against title, description, style tags, colors, and brand. |
| `size` | `str \| None` | Clothing size to filter by, or `None` to skip size filtering. Case-insensitive token match (e.g., `"M"` matches `"S/M"` and `"M/L"`). |
| `max_price` | `float \| None` | Maximum price (inclusive), or `None` to skip. |

**Returns:** `list[dict]` — matching listing dicts sorted by relevance score (keyword overlap count), highest first. Each dict has: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. Returns `[]` on no match — never raises an exception.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Given a thrifted item the user is considering and their current wardrobe, uses an LLM to suggest 1–2 complete outfit combinations. If the wardrobe is empty, returns general styling advice instead.

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict from `search_listings` (the item being considered). |
| `wardrobe` | `dict` | A wardrobe object with an `"items"` key containing a list of wardrobe item dicts (each with `name`, `category`, `colors`, `style_tags`, optional `notes`). |

**Returns:** `str` — outfit suggestion in natural language. If the wardrobe has zero items, returns general styling advice and notes that personalized suggestions require a wardrobe. Never returns an empty string or raises an exception.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Generates a short, casual social-media caption (Instagram/TikTok style) for the complete outfit. Mentions the thrifted item's name, price, and platform naturally. Uses a high LLM temperature (1.1) so each call produces a different result.

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit`. |
| `new_item` | `dict` | The listing dict for the thrifted item (provides title, price, platform). |

**Returns:** `str` — a 2–4 sentence caption in a casual first-person voice. If `outfit` is empty or whitespace, returns a minimal fallback caption built from `new_item` alone — never crashes.

---

## How the Planning Loop Works

The agent parses the user's query with the LLM (extracting `description`, `size`, and `max_price` as structured JSON), then runs a sequential planning loop that gates each step on the result of the previous one:

```
1. Parse query → extract description, size, max_price
         │
         ▼
2. search_listings(description, size, max_price)
         │
   empty list? ──► set session["error"], return early (do NOT call suggest_outfit)
         │
   results found → session["selected_item"] = results[0]
         │
         ▼
3. suggest_outfit(selected_item, wardrobe)
         │
         → session["outfit_suggestion"]
         │
         ▼
4. create_fit_card(outfit_suggestion, selected_item)
         │
         → session["fit_card"]
         │
         ▼
5. Return session to caller
```

The key design decision: **the loop stops at step 2 if `search_listings` returns nothing.** It never calls `suggest_outfit` with empty input — that's the branch that keeps the agent from crashing or producing nonsense. Later tools only run if the earlier ones produced a valid result.

---

## State Management

All state for one interaction lives in a single `session` dict initialized in `_new_session()`. Each tool writes its output to a named key; the next tool reads from that same dict:

| Key | Written by | Read by |
|-----|-----------|---------|
| `session["query"]` | `run_agent` on entry | `_parse_query` |
| `session["parsed"]` | `_parse_query` | `search_listings` call |
| `session["search_results"]` | `search_listings` | Planning loop (picks top result) |
| `session["selected_item"]` | Planning loop | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | User input | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` | Final output to user |
| `session["error"]` | Planning loop on failure | `handle_query` (surfaces to UI) |

The user never has to re-enter the thrifted item between steps — it flows automatically from `search_listings` through `suggest_outfit` into `create_fit_card` via `session["selected_item"]`.

---

## Error Handling

| Tool | Failure mode | Agent response | Concrete example from testing |
|------|-------------|----------------|-------------------------------|
| `search_listings` | No listings match the query | Sets `session["error"]` with a specific message naming what didn't match; suggests concrete adjustments (raise price, remove size filter, broaden keywords). Returns early — never calls `suggest_outfit`. | Query `"designer ballgown size XXS under $5"` → *"No listings matched 'designer ballgown' in size XXS under $5. You could: try removing the size filter; or try raising your budget (e.g., $25); or broaden your description."* |
| `suggest_outfit` | `wardrobe["items"]` is empty | LLM prompt switches to ask for general styling advice (silhouettes, vibe, shoe types) rather than naming wardrobe pieces. Appends a note that personalized suggestions require a wardrobe. | Query with `get_empty_wardrobe()` → *"Pair the Y2K Baby Tee with high-waisted mom jeans and chunky sandals for a retro vibe… These are general suggestions — share your wardrobe for personalized ideas."* |
| `create_fit_card` | `outfit` is empty or whitespace | Returns a minimal fallback caption built from `new_item` title, price, and platform — no LLM call needed. | `create_fit_card('', results[0])` → *"just copped the Y2K Baby Tee — Butterfly Print off depop for $18.0 🔥 no outfit ideas yet but the piece speaks for itself"* |

---

## Interaction Walkthrough

**User query:** `"vintage graphic tee under $30"`

**Step 1 — search_listings**
- **Tool:** `search_listings`
- **Input:** `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- **Why:** The agent always starts here — it can't suggest an outfit or write a caption without a real item. The query is parsed by the LLM to extract these three parameters before the call.
- **Output:** List of matching listings sorted by keyword overlap. Top result: *Y2K Baby Tee — Butterfly Print, $18.00, depop, size S/M, excellent condition.* Stored as `session["selected_item"]`.

**Step 2 — suggest_outfit**
- **Tool:** `suggest_outfit`
- **Input:** `new_item=session["selected_item"]`, `wardrobe=session["wardrobe"]` (example wardrobe with 10 pieces)
- **Why:** A match was found in step 1, so the agent proceeds to build an outfit using the item and the user's existing wardrobe pieces.
- **Output:** *"Pair the Y2K Baby Tee with the Baggy straight-leg jeans for a casual look. Tuck the tee into the jeans and add the Chunky white sneakers. For a layered look, wear the tee over the White ribbed tank top and pair with the Wide-leg khaki trousers and Black combat boots."* Stored as `session["outfit_suggestion"]`.

**Step 3 — create_fit_card**
- **Tool:** `create_fit_card`
- **Input:** `outfit=session["outfit_suggestion"]`, `new_item=session["selected_item"]`
- **Why:** Outfit suggestion exists, so the agent generates the shareable caption as the final step.
- **Output:** *"i just scored this adorable y2k baby tee with a butterfly print on depop for $18.0 and i'm obsessed. i've been styling it two ways — tucked into my baggy straight-leg jeans with chunky white sneakers for a super laid back vibe, or layered over a white ribbed tank top with wide-leg khaki trousers and black combat boots for a cozier look."* Stored as `session["fit_card"]`.

**Final output to user:** All three panels in the Gradio UI populate — the listing details, the outfit suggestion, and the fit card caption.

---

## Spec Reflection

**One way `planning.md` helped during implementation:**

Designing the state management table before writing any code forced me to decide upfront what each tool needed as input and what it would produce as output. This made `run_agent()` straightforward to implement — the session dict keys were already named and defined, so each step just read from and wrote to the same agreed-upon keys. Without that table, I would have discovered mid-implementation that `create_fit_card` needed both the listing dict *and* the outfit string, and likely would have passed them inconsistently.

**One divergence from the spec, and why:**

The original spec described `_parse_query` as either a regex operation or a simple string split. During implementation, I chose to make the LLM the primary parser (extracting description, size, and max_price as structured JSON) with regex as a fallback. This produced significantly better results on natural queries like `"looking for something vintage and graphic, budget around $25"` that regex would have parsed poorly. The spec was written conservatively — the LLM approach was only viable once I confirmed the Groq key was available in the session.

---

## AI Usage

**Instance 1 — search_listings implementation**

I gave GitHub Copilot the Tool 1 block from `planning.md` (inputs, return value, failure mode, scoring approach) and asked it to implement `search_listings()` using `load_listings()` from the data loader. The generated code correctly filtered by price and handled `None` for optional parameters. I overrode the size-matching logic — the original used `in` substring matching (`"M" in "XL"` returns `True`), which was wrong. I replaced it with a token-split approach that splits the listing size field on spaces, slashes, and parentheses and checks exact token membership.

**Instance 2 — suggest_outfit prompts**

I gave Copilot the Tool 2 spec plus the `wardrobe_schema.json` structure and asked it to write both LLM prompts (empty-wardrobe path and populated-wardrobe path). The generated prompts were functionally correct but used generic phrasing like "create an outfit." I revised both prompts to be more directive — specifying "name specific wardrobe pieces by name," "be specific about styling details (tuck, layer, roll sleeves)," and "keep it under 120 words" — which produced noticeably more useful outfit suggestions in testing.

---

## Project Structure

```
├── agent.py              # Planning loop: _parse_query, run_agent
├── app.py                # Gradio UI: handle_query, build_interface
├── tools.py              # search_listings, suggest_outfit, create_fit_card
├── planning.md           # Spec written before implementation
├── tests/
│   └── test_tools.py     # 11 pytest tests covering all failure modes
├── data/
│   ├── listings.json     # 40 mock secondhand listings
│   └── wardrobe_schema.json
└── utils/
    └── data_loader.py    # load_listings, get_example_wardrobe, get_empty_wardrobe
```
