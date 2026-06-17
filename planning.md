# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset and returns items that match the user's description, size, and price ceiling. Results are sorted by relevance (style tag and keyword overlap with the description).

**Input parameters:**
- `description` (str): A natural-language description of what the user is looking for (e.g., "vintage graphic tee", "chunky knit cardigan"). Used to match against `title`, `description`, and `style_tags` fields.
- `size` (str): The size the user wears. Matched against the listing's `size` field (case-insensitive, partial match allowed).
- `max_price` (float): The maximum price the user is willing to pay. Only listings with `price <= max_price` are returned.

**What it returns:**
A list of matching listing dicts, each containing: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Sorted by relevance score (number of keyword/tag matches). Returns an empty list if no items match.

**What happens if it fails or returns nothing:**
If the list is empty, the agent informs the user that no listings matched their query and suggests adjustments (e.g., try a higher price, drop the size filter, or broaden the description). The agent does **not** proceed to `suggest_outfit` with an empty result.

---

### Tool 2: suggest_outfit

**What it does:**
Given a newly found thrift item and the user's current wardrobe, uses the LLM to suggest one or more complete outfit combinations that incorporate the new piece.

**Input parameters:**
- `new_item` (dict): A single listing dict returned by `search_listings` (contains `title`, `colors`, `style_tags`, `category`, `condition`, `price`, `platform`).
- `wardrobe` (dict): A wardrobe object in the schema format, with an `items` list. Each item has `name`, `category`, `colors`, `style_tags`, and optional `notes`.

**What it returns:**
A string containing one or more outfit suggestions in natural language — e.g., "Pair this with your baggy dark-wash jeans and chunky white sneakers for a classic streetwear look. Tuck the front of the tee for shape."

**What happens if it fails or returns nothing:**
If the wardrobe is empty (`items` list has zero entries), the agent skips wardrobe-based suggestions and instead provides general styling advice for the item (e.g., "This piece works well with wide-leg bottoms or straight-leg denim"). If the LLM call fails, the agent surfaces a short fallback suggestion based on the item's `style_tags` alone.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, shareable social-media-style caption describing the complete outfit — the kind of thing someone would post on Instagram or TikTok alongside a fit photo.

**Input parameters:**
- `outfit` (str): The outfit suggestion text produced by `suggest_outfit`.
- `new_item` (dict): The listing dict for the thrifted piece (used to pull in real details like price, platform, title for authenticity).

**What it returns:**
A 1–3 sentence caption string in a casual, first-person social voice. It should mention the thrifted item and price, reference the styling, and feel shareable — not like a product description.

**What happens if it fails or returns nothing:**
If `outfit` is an empty string or `new_item` is missing required fields, the agent falls back to a minimal caption using only the `new_item` data (e.g., "just copped this [title] off [platform] for $[price] 🔥"). If the LLM call itself fails, the agent surfaces this fallback instead of crashing.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop maintains a session `state` dict and proceeds step by step, checking what has been collected before deciding what to do next:

1. **No results yet** → call `search_listings` with the user's description, size, and max_price.
   - If the result list is **empty**: inform the user, stop here (do not continue to step 2).
   - If results are returned: store the top result in `state["selected_item"]` and move to step 2.
2. **Item selected, no outfit yet** → call `suggest_outfit(state["selected_item"], state["wardrobe"])`.
   - If the wardrobe is empty: generate general styling advice and note this to the user.
   - Store the returned suggestion in `state["outfit_suggestion"]` and move to step 3.
3. **Outfit suggested, no fit card yet** → call `create_fit_card(state["outfit_suggestion"], state["selected_item"])`.
   - Store the result in `state["fit_card"]` and surface it to the user as the final output.
4. **Fit card exists** → the interaction is complete. The agent presents the fit card and stops.

The loop never skips a step or calls a later tool without a valid result from the prior step.

---

## State Management

**How does information from one tool get passed to the next?**

The agent maintains a single `state` dictionary for the duration of each user session. Keys are added as tools complete:

| Key | Set by | Used by |
|-----|--------|---------|
| `state["wardrobe"]` | User input (or `get_example_wardrobe()`) | `suggest_outfit` |
| `state["search_results"]` | `search_listings` | Planning loop (to pick top item) |
| `state["selected_item"]` | Planning loop (top result from search) | `suggest_outfit`, `create_fit_card` |
| `state["outfit_suggestion"]` | `suggest_outfit` | `create_fit_card` |
| `state["fit_card"]` | `create_fit_card` | Final user output |

The user never has to re-enter the item details — each tool reads from `state` rather than from user input. Between turns in a multi-turn chat, the `state` dict is passed along with the conversation history.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Tell the user nothing matched; suggest broadening description, raising max_price, or removing size filter. Do not call suggest_outfit. |
| suggest_outfit | Wardrobe is empty (zero items) | Skip wardrobe-specific pairings; return general styling advice based on the item's style_tags and category. Inform user the advice is general because no wardrobe was provided. |
| create_fit_card | outfit string is empty or new_item missing fields | Fall back to a minimal caption using only available new_item fields (title, price, platform). Do not crash — always return something. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     Use ASCII art or a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html).
     Do NOT embed an image — graders need to read your diagram directly in the file;
     an embedded image or screenshot cannot be evaluated.
     You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

```
User Input (description, size, max_price, wardrobe)
        │
        ▼
┌───────────────────┐
│   Planning Loop   │◄─────────────────────────────┐
│  (checks state)   │                              │
└────────┬──────────┘                              │
         │                                         │
         │ state["selected_item"] missing?          │
         ▼                                         │
┌──────────────────────┐    empty list    ┌────────┴────────┐
│   search_listings    │─────────────────►│  Error: inform  │
│ (description, size,  │                  │  user, STOP     │
│   max_price)         │                  └─────────────────┘
└──────────┬───────────┘
           │ results found
           │ → state["selected_item"] = top result
           ▼
┌──────────────────────┐    empty wardrobe   ┌──────────────────────┐
│   suggest_outfit     │────────────────────►│ General styling tip  │
│ (selected_item,      │                     │ (no wardrobe match)  │
│   wardrobe)          │                     └──────────┬───────────┘
└──────────┬───────────┘                               │
           │                                           │
           │ → state["outfit_suggestion"]              │
           └───────────────────┬───────────────────────┘
                               ▼
                  ┌──────────────────────┐    missing fields  ┌──────────────────┐
                  │   create_fit_card    │───────────────────►│  Minimal caption │
                  │ (outfit_suggestion,  │                     │  fallback        │
                  │   selected_item)     │                     └──────────────────┘
                  └──────────┬───────────┘
                             │
                             │ → state["fit_card"]
                             ▼
                     Final output to user
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

- **search_listings**: I'll give GitHub Copilot the Tool 1 spec (inputs, return fields, failure mode) from this file and ask it to implement `search_listings()` using `load_listings()` from `data_loader.py`. I'll test it manually against 3 queries — one that should return results, one that should return empty (no size match), and one at the price boundary — before trusting it.

- **suggest_outfit**: I'll give Copilot the Tool 2 spec plus the `wardrobe_schema.json` structure and ask it to implement `suggest_outfit()` using a Groq LLM call. I'll test it with `get_example_wardrobe()` and then with `get_empty_wardrobe()` to verify the empty-wardrobe fallback path works correctly.

- **create_fit_card**: I'll give Copilot the Tool 3 spec and a sample outfit string and listing dict. I'll verify the output sounds like a social caption (not a product description) and that different inputs produce noticeably different results.

**Milestone 4 — Planning loop and state management:**

- I'll give Copilot the Architecture diagram above and the State Management table, and ask it to implement the planning loop in `agent.py`. I'll trace through two full interactions manually — one happy path and one where `search_listings` returns nothing — to confirm the loop branches correctly and state flows as designed.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent calls `search_listings(description="vintage graphic tee", size="M", max_price=30.0)`. It scans all listings in `listings.json`, filtering for price ≤ $30 and keywords/tags that overlap with "vintage", "graphic tee". It finds, for example, `lst_006` — *"Graphic Tee — 2003 Tour Bootleg Style, $24, depop, size L"* — and stores it as `state["selected_item"]`.

**Step 2:**
The agent calls `suggest_outfit(new_item=state["selected_item"], wardrobe=state["wardrobe"])`. The wardrobe contains baggy straight-leg jeans (`w_001`) and chunky white sneakers (`w_007`). The LLM returns: *"Pair this boxy bootleg tee with your dark-wash baggy jeans and chunky white sneakers for an effortless 90s streetwear look. Leave it untucked and roll the sleeves once to show off the faded graphic."* This is stored as `state["outfit_suggestion"]`.

**Step 3:**
The agent calls `create_fit_card(outfit=state["outfit_suggestion"], new_item=state["selected_item"])`. The LLM returns a short social caption: *"snagged this 2003 bootleg tee off depop for $24 and it was made for my baggy jeans 🖤 the faded graphic does all the work"*. This is stored as `state["fit_card"]`.

**Final output to user:**
The agent presents all three pieces of information in a clean format:
- The found listing (title, price, platform, condition)
- The outfit suggestion
- The shareable fit card caption

**Error path (if Step 1 returns nothing):**
The agent responds: *"No listings matched 'vintage graphic tee' under $30 in size M. Try raising your price to $40, removing the size filter, or searching for 'band tee' or 'boxy tee' instead."* The agent stops — it does not call `suggest_outfit` with no item.

---

## FitFindr: What It Is (Plain English)

FitFindr is an AI agent that helps you find secondhand clothing and figure out how to wear it. When you describe something you're looking for — a piece, your size, and a price limit — FitFindr searches a dataset of thrift listings and picks the best match. It then looks at what you already own and suggests a complete outfit built around the new piece. Finally, it writes a short, social-media-ready caption so you can share the look. If the search comes up empty at any step, FitFindr tells you what went wrong and what to try instead, rather than crashing or silently moving on with nothing.
