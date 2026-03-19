# TASKS.md

# Current work — batch 4: schema extensions + evolution chain

**Status:** ✅ ALL COMPLETE — batch 4 done

Three tickets. Pythonmon-28 and Pythonmon-27 are schema extensions to
existing fetches — no new API endpoints, but both require a cache version
bump and a migration note. Pythonmon-9 is a new endpoint + new cache layer.

Recommended implementation order: 28 → 27 → 9.
- §28 is the smallest scope (one field, one file, one display change).
- §27 builds on the same species-fetch pattern as §28.
- §9 depends on nothing from the others but is the most complex; doing it
  last keeps the earlier tickets clean and mergeable independently.

Ticket IDs reference ROADMAP.md identifiers. Each step must include:
1. Implementation
2. `_run_tests()` additions (where testable logic exists)
3. Documentation updates (`HISTORY.md`, `ROADMAP.md`, `TASKS.md`)

---

# Pythonmon-28 — Move effect description in lookup

**Status:** ✅ COMPLETE (§84)
**Files:** `pkm_pokeapi.py`, `pkm_cache.py`, `feat_move_lookup.py`
**Complexity:** 🟢 Low
**New API call:** No — `effect_entries` is already returned by `GET move/{slug}`
  and already fetched in `fetch_move`, but the field is currently discarded.
**Cache structure change:** Yes — `MOVES_CACHE_VERSION` bump (2 → 3); new
  `"effect"` field added to every versioned move entry.

## Root cause

`fetch_move` builds a `current` dict from the PokeAPI response and passes it
to `_build_versioned_entries`. The `effect_entries` field is present in the
response but never read. As a result `moves.json` has no effect text, and
`feat_move_lookup._display_move` has nothing to show.

## What

Show the move's full English effect description in the move lookup output
(key M), e.g.:

```
  Flamethrower  [Scarlet / Violet]
  ──────────────────────────────────────────────
  Type      : Fire
  Category  : Special
  Power     : 90
  Accuracy  : 100%
  PP        : 15
  Effect    : Inflicts regular damage. Has a 10% chance to burn the target.

  Super-effective vs : Grass / Ice / Bug / Steel
  ...
```

## Design

### Step 1 — `pkm_pokeapi.fetch_move`

Add `"effect"` to the `current` dict:

```python
effect = ""
for entry in data.get("effect_entries", []):
    if entry.get("language", {}).get("name") == "en":
        # Use short_effect — concise, ~1 sentence. effect is multi-paragraph.
        effect = entry.get("short_effect", "").replace("\n", " ").strip()
        break
current["effect"] = effect
```

Use `short_effect` (not `effect`): `effect` is multi-paragraph and verbose;
`short_effect` is one sentence, consistent with how abilities are displayed.

The `effect` field is constant across all generations (PokeAPI does not
provide past `short_effect` values), so it lives once in `current` and
propagates to every versioned entry via `**current` in
`_build_versioned_entries`.

### Step 2 — `pkm_cache.py`

Bump `MOVES_CACHE_VERSION` from 2 to 3. The version mismatch check in
`get_moves()` will treat the old cache as a miss — all moves will be lazily
re-fetched with the new schema on next use.

Update the version history comment:
```python
#   3 — Pythonmon-28: added short_effect text field
```

### Step 3 — `feat_move_lookup._display_move`

Add an Effect line after PP, before the coverage block:

```python
effect = entry.get("effect", "")
if effect:
    # Wrap long effect text at ~60 chars for readability
    print(f"  Effect    : {effect}")
```

No wrapping needed for `short_effect` — it is typically 60–80 characters.
If it exceeds the terminal width, it wraps naturally.

## Cache migration

After deploying: `MOVES_CACHE_VERSION` mismatch causes `get_moves()` to
return `None`, triggering a lazy re-fetch of each move on first access. No
manual action required — the user will see "Fetching details for N move(s)
not yet in cache..." on first use of each affected screen.

Alternatively: press MOVE → R to re-fetch all moves at once.

## Tests

### `pkm_pokeapi.py` (offline, mock `_get`)
- `fetch_move` with a response containing `effect_entries` → returned list
  contains `"effect"` field with the English `short_effect`
- `fetch_move` with empty `effect_entries` → `"effect"` field is `""`
- `fetch_move` with non-English entries only → `"effect"` field is `""`

### `feat_move_lookup.py` (stdout capture)
- `_display_move` with entry containing `"effect"` → "Effect" line present
  in output
- `_display_move` with `"effect": ""` → no "Effect" line printed

### `pkm_cache.py`
- `MOVES_CACHE_VERSION == 3` (constant value test)

---

# Pythonmon-27 — Egg group browser

**Status:** ✅ COMPLETE (§86–§88)
**Files:** `pkm_pokeapi.py`, `pkm_cache.py`, new `feat_egg_group.py`,
  `feat_type_matchup.py`, `pokemain.py`, `run_tests.py`
**Complexity:** 🟡 Medium
**New API call:** Partial — `egg_groups` is already in the
  `pokemon-species/{slug}` response (no new call for species data), but
  `GET egg-group/{slug}` for the roster IS a new endpoint.
**Cache structure change:** Yes — new `"egg_groups"` field in pokemon cache
  entries; new `cache/egg_groups/` directory for roster files.

## What

Two surfaces:

**1. Option 1 (quick view)** — egg group names shown inline below the
abilities block for the loaded Pokemon. No roster, just the group names.
Compact, requires only the `egg_groups` field already on `pkm_ctx`.

```
  Egg groups — Charizard
  ──────────────────────────────────────────────
  Monster  /  Dragon
```

**2. Key `E` (egg group browser)** — dedicated screen showing the full
roster of breeding partners for each of the Pokemon's egg groups.

```
  Egg groups  |  Charizard
  ══════════════════════════════════════════════════════
  Groups: Monster  /  Dragon

  Monster group  (98 Pokemon)
    Bulbasaur    Ivysaur      Venusaur     Charmander   Charmeleon
    Squirtle     Wartortle    Blastoise    Chikorita    ...

  Dragon group  (51 Pokemon)
    Charmander   Charmeleon   Charizard    Dratini      ...
```

## Implementation — broken into testable iterations

The feature is split into 3 iterations so each step produces a working,
testable result before the next begins.

---

### Iteration A — Schema + cache + quick view display

**Deliverable:** egg group names appear in option 1 for any freshly loaded
Pokemon. No browser yet. Fully testable offline.

**A1 — `pkm_pokeapi.fetch_pokemon`**

Extract `egg_groups` from the species response (already fetched, currently
discarded):

```python
egg_groups = [g["name"] for g in species.get("egg_groups", [])]
return {
    "pokemon"    : slug,
    "species_gen": species_gen,
    "egg_groups" : egg_groups,   # e.g. ["monster", "dragon"]
    "forms"      : forms,
}
```

**A2 — `pkm_cache.py`**

Add silent re-fetch trigger in `get_pokemon` (same pattern as `variety_slug`
auto-upgrade in §42):

```python
if "egg_groups" not in data:
    return None   # triggers transparent re-fetch on next access
```

Note: if Pythonmon-9 is implemented in the same pass, add both
`"egg_groups"` and `"evolution_chain_id"` to the same check to avoid
double auto-fetches.

**A3 — `feat_egg_group.py` (new file — name dict + display helper)**

Create the file with the name mapping and the inline display function used
by option 1:

```python
_EGG_GROUP_NAMES = {
    "monster"      : "Monster",
    "water1"       : "Water 1",
    "water2"       : "Water 2",
    "water3"       : "Water 3",
    "bug"          : "Bug",
    "flying"       : "Flying",
    "ground"       : "Field",        # PokeAPI slug ≠ in-game name
    "fairy"        : "Fairy",
    "plant"        : "Grass",        # PokeAPI slug ≠ in-game name
    "humanshape"   : "Human-Like",
    "mineral"      : "Mineral",
    "indeterminate": "Amorphous",
    "ditto"        : "Ditto",
    "dragon"       : "Dragon",
    "no-eggs"      : "Undiscovered",
}

def egg_group_name(slug: str) -> str:
    """Return in-game display name for a PokeAPI egg group slug."""
    return _EGG_GROUP_NAMES.get(slug, slug.replace("-", " ").title())

def format_egg_groups(egg_groups: list) -> str:
    """Return a formatted string of egg group names, e.g. 'Monster  /  Dragon'."""
    return "  /  ".join(egg_group_name(s) for s in egg_groups)
```

**A4 — `feat_type_matchup.py`**

Add egg group block at the end of `run()`, after abilities and before the
type chart:

```python
import feat_egg_group as egg
groups = pkm_ctx.get("egg_groups", [])
if groups:
    print(f"\n  Egg groups — {pkm_ctx['form_name']}")
    print("  " + "─" * 46)
    print(f"  {egg.format_egg_groups(groups)}")
```

Deferred import inside `run()` to avoid circular risk at load time.
Gracefully skipped if `egg_groups` absent (pre-migration cache entry).

**Iteration A tests:**

`feat_egg_group.py`:
- `egg_group_name("monster")` → `"Monster"`
- `egg_group_name("ground")` → `"Field"` (slug ≠ in-game name)
- `egg_group_name("plant")` → `"Grass"` (slug ≠ in-game name)
- `egg_group_name("no-eggs")` → `"Undiscovered"`
- `egg_group_name("unknown-slug")` → title-cased fallback
- `format_egg_groups(["monster", "dragon"])` → `"Monster  /  Dragon"`
- `format_egg_groups([])` → `""`
- `_EGG_GROUP_NAMES` has exactly 15 keys

`pkm_pokeapi.py` (offline mock):
- `fetch_pokemon` with `egg_groups` in species response → dict includes
  `"egg_groups": ["monster", "dragon"]`
- `fetch_pokemon` with empty `egg_groups` → `"egg_groups": []`

`pkm_cache.py`:
- `get_pokemon` on entry missing `"egg_groups"` → returns `None`
- `get_pokemon` on entry with `"egg_groups"` → returns normally

---

### Iteration B — Roster fetch + cache layer

**Deliverable:** `fetch_egg_group` and the cache read/write functions exist
and are tested. The browser can now fetch rosters. No display or menu yet.

**B1 — `pkm_pokeapi.fetch_egg_group`**

New function:

```python
def fetch_egg_group(slug: str) -> list:
    """
    Fetch the roster of species in an egg group from PokeAPI.
    Returns list of {"slug": str, "name": str} dicts (English name).
    Raises ValueError on unknown slug, ConnectionError on network failure.
    """
    data = _get(f"egg-group/{slug}")
    roster = []
    for entry in data.get("pokemon_species", []):
        species_slug = entry["name"]
        # Get English display name from the species names list
        name = _en_name(entry.get("names", []), None)
        if not name:
            name = species_slug.replace("-", " ").title()
        roster.append({"slug": species_slug, "name": name})
    return sorted(roster, key=lambda x: x["name"])
```

Note: the egg-group endpoint returns `pokemon_species[]` with `name` (slug)
but the names list may be empty on this endpoint — a second call to
`pokemon-species/{slug}` per entry would be expensive. Instead, use the slug
title-cased as fallback, or fetch the full `names` array from the response.
Check the actual API response structure first.

**B2 — `pkm_cache.py`**

New cache directory and functions:

```python
_EGG_GROUP_DIR = os.path.join(_BASE, "egg_groups")

def get_egg_group(slug: str) -> list | None:
    path = os.path.join(_EGG_GROUP_DIR, f"{slug}.json")
    data = _read(path)
    if not isinstance(data, list):
        return None
    return data

def save_egg_group(slug: str, roster: list) -> None:
    os.makedirs(_EGG_GROUP_DIR, exist_ok=True)
    path = os.path.join(_EGG_GROUP_DIR, f"{slug}.json")
    _write(path, roster)
```

Also add `_EGG_GROUP_DIR` to `check_integrity()` scan.

**Iteration B tests:**

`pkm_pokeapi.py` (offline mock):
- `fetch_egg_group` with valid response → list of `{slug, name}` dicts
- `fetch_egg_group` with empty `pokemon_species` → `[]`
- `fetch_egg_group` with unknown slug (mock raises ValueError) → propagated

`pkm_cache.py`:
- `get_egg_group` / `save_egg_group` round-trip
- `get_egg_group` on missing file → `None`
- `get_egg_group` on non-list data → `None`

---

### Iteration C — Browser display + menu wiring

**Deliverable:** key `E` works end-to-end. `feat_egg_group.py` complete.

**C1 — `feat_egg_group.py`**

Add the browser functions:

```python
def get_or_fetch_roster(slug: str) -> list | None:
    """Return roster from cache, fetching from PokeAPI on miss."""
    import pkm_cache as cache
    import pkm_pokeapi as pokeapi
    roster = cache.get_egg_group(slug)
    if roster is not None:
        return roster
    try:
        print(f"  Fetching {egg_group_name(slug)} egg group roster...",
              end=" ", flush=True)
        roster = pokeapi.fetch_egg_group(slug)
        cache.save_egg_group(slug, roster)
        print(f"{len(roster)} Pokemon.")
        return roster
    except (ValueError, ConnectionError):
        return None

def display_egg_group_browser(pkm_ctx: dict) -> None:
    """Full browser display for key E."""

def run(pkm_ctx: dict) -> None:
    """Called from pokemain; key E."""
```

**C2 — `pokemain.py`**

- Import `feat_egg_group`
- Menu line: `E. Egg group / breeding partners` (visible when `has_pkm`)
- Handler: `elif choice == "e": feat_egg_group.run(pkm_ctx)`

**C3 — `run_tests.py`**

Add `feat_egg_group` to SUITES (offline).

**Iteration C tests:**

`feat_egg_group.py` (stdout capture):
- `display_egg_group_browser` with a mock roster → group name and members
  appear in output
- `display_egg_group_browser` with `egg_groups: []` → graceful message
- `display_egg_group_browser` with `egg_groups: ["no-eggs"]` → shows
  "Undiscovered" and a note that this group cannot breed

---

## Notes

- `"ground"` → `"Field"` and `"plant"` → `"Grass"`: in-game names differ
  from PokeAPI slugs — critical to get right on day one.
- `"no-eggs"` (Legendary / baby Pokemon) → `"Undiscovered"`. The browser
  for this group should note that these Pokemon cannot breed.
- Egg group rosters are cached indefinitely (same pattern as type rosters).
- The `_EGG_GROUP_DIR` path constant must be added to all the places where
  `_BASE` is redirected in tests.
- **Recommended iteration order: A → B → C**. After iteration A, option 1
  already shows egg groups for any freshly loaded Pokemon. After B, the
  roster infrastructure is testable. C adds the interactive layer.

---

# Pythonmon-9 — Evolution chain

**Status:** ✅ COMPLETE (§89A + §90B + §91C + §91fix)
**Files:** `pkm_pokeapi.py`, `pkm_cache.py`, `pkm_session.py`,
  new `feat_evolution.py`, `feat_quick_view.py`, `pokemain.py`, `run_tests.py`
**Complexity:** 🔴 High
**New API call:** Yes — `GET evolution-chain/{id}` (new endpoint, never
  called). The chain ID is obtained from `pokemon-species/{slug}` which is
  already fetched by `fetch_pokemon`.
**Cache structure change:** Yes — new `"evolution_chain_id"` field added to
  pokemon cache entries; new cache dir `cache/evolution/` with one file per
  chain ID.

## What

Show the evolution chain for the loaded Pokemon as the final block of the
**option 1 quick view** (`feat_quick_view.py`), below the type chart section.

Proposed output:

```
  Evolution chain
  ──────────────────────────────────────────────
  Charmander [Fire]  →  Lv 16  →  Charmeleon [Fire]  →  Lv 36  →  Charizard [Fire / Flying] ★

  ★ = current Pokémon
```

For branching chains, each branch on its own line:

```
  Evolution chain
  ──────────────────────────────────────────────
  Eevee [Normal]  →  Friendship (day)   →  Espeon [Psychic]
  Eevee [Normal]  →  Friendship (night) →  Umbreon [Dark]
  Eevee [Normal]  →  Use Water Stone    →  Vaporeon [Water]
  ...

  ★ = current Pokémon
```

For a Pokemon with no evolution (Kangaskhan, Tauros, etc.):

```
  Evolution chain
  ──────────────────────────────────────────────
  Kangaskhan [Normal] ★  — does not evolve
```

Format is deliberately compact — no stat bars, just species name, type tag,
and trigger. Keeps option 1 from becoming overwhelming for 8-branch chains.

## Implementation — broken into testable iterations

---

### Iteration A — Pure parsing logic

**Deliverable:** `feat_evolution.py` with `_parse_trigger` and `_flatten_chain`
fully tested offline. No other file changes. This is the hardest part of the
ticket; locking it down first means the complex logic is verified before any
schema or display work is built on top.

**A1 — `_parse_trigger(details: dict) → str`**

Converts one PokeAPI `evolution_details` dict to a human-readable trigger
string. Pure function, no I/O.

Key fields in `evolution_details`:
- `trigger.name`: `"level-up"`, `"use-item"`, `"trade"`, `"shed"`, `"other"`
- `min_level`: int or null
- `item.name`: item slug (e.g. `"fire-stone"`)
- `min_happiness`: int or null
- `known_move.name`: move slug
- `location.name`: location slug
- `time_of_day`: `"day"` | `"night"` | `""`

Mapping rules (in priority order):
```
level-up + min_level          → "Level {N}"
level-up + min_happiness      → "High Friendship"
level-up + known_move         → "Level up knowing {Move}"
level-up + time_of_day=day    → "Level up (day)"
level-up + time_of_day=night  → "Level up (night)"
level-up (other conditions)   → "Level up"
use-item + item               → "Use {Item}"
trade (no item)               → "Trade"
trade + item                  → "Trade holding {Item}"
shed                          → "Level 20 (empty slot)"
other / unknown               → "Special condition"
```

Item and move slugs are title-cased with hyphens replaced by spaces:
`"fire-stone"` → `"Fire Stone"`, `"solar-beam"` → `"Solar Beam"`.

Note: `evolution_details` is always a list of dicts (one per condition set).
Use the first entry in most cases; if the list is empty return `""`.

**A2 — `_flatten_chain(node: dict, max_depth: int = 20) → list[list[dict]]`**

Recursively flattens the PokeAPI chain tree into a list of linear paths
(one list per branch from root to leaf).

PokeAPI chain structure:
```python
{
  "species": {"name": "bulbasaur", "url": "..."},
  "evolution_details": [],          # empty for stage 0
  "evolves_to": [
    {
      "species": {"name": "ivysaur"},
      "evolution_details": [{"trigger": {"name": "level-up"}, "min_level": 16, ...}],
      "evolves_to": [
        {"species": {"name": "venusaur"}, "evolution_details": [...], "evolves_to": []}
      ]
    }
  ]
}
```

Each stage dict produced:
```python
{
    "slug"   : str,   # species slug e.g. "charizard"
    "trigger": str,   # result of _parse_trigger (empty string for stage 0)
}
```

Algorithm:
1. For each path from current node to leaf, prepend current node's slug
2. For branching nodes, produce one path per branch
3. `max_depth` guard prevents infinite recursion on malformed data

**Iteration A tests** (all pure, no I/O):

`_parse_trigger`:
- `level-up` + `min_level=16` → `"Level 16"`
- `level-up` + `min_happiness` → `"High Friendship"`
- `level-up` + `known_move="solar-beam"` → `"Level up knowing Solar Beam"`
- `level-up` + `time_of_day="day"` → `"Level up (day)"`
- `level-up` + `time_of_day="night"` → `"Level up (night)"`
- `level-up` (no special condition) → `"Level up"`
- `use-item` + `item.name="fire-stone"` → `"Use Fire Stone"`
- `trade` (no item) → `"Trade"`
- `trade` + `item.name="metal-coat"` → `"Trade holding Metal Coat"`
- `shed` → `"Level 20 (empty slot)"`
- empty details list → `""`
- unknown trigger → `"Special condition"`

`_flatten_chain`:
- Linear 3-stage chain (Bulbasaur line) → 1 path, 3 stages
- 2-branch chain (Slowpoke → Slowbro / Slowking) → 2 paths, each 2 stages
- Single-stage (no evolution) → 1 path, 1 stage
- `max_depth` guard: artificially deep mock → truncates gracefully

---

### Iteration B — Schema + API + cache

**Deliverable:** `evolution_chain_id` is populated in `pkm_ctx` for any
freshly loaded Pokemon. Cache infrastructure is in place. Nothing visible to
the user yet.

**B1 — `pkm_pokeapi.fetch_pokemon`**

Extract `evolution_chain_id` from the species response (already fetched,
currently discarded):

```python
chain_url = species.get("evolution_chain", {}).get("url", "")
chain_id  = int(chain_url.rstrip("/").split("/")[-1]) if chain_url else None
```

Add to return dict:
```python
return {
    "pokemon"           : slug,
    "species_gen"       : species_gen,
    "egg_groups"        : [...],
    "evolution_chain_id": chain_id,   # NEW
    "forms"             : forms,
}
```

**B2 — `pkm_cache.get_pokemon` auto-upgrade**

Combine with the existing `egg_groups` check (one condition, one re-fetch):

```python
if "egg_groups" not in data or "evolution_chain_id" not in data:
    return None
```

**B3 — `pkm_pokeapi.fetch_evolution_chain`**

New function — raw fetch only, no parsing:

```python
def fetch_evolution_chain(chain_id: int) -> dict:
    """
    Fetch the raw evolution chain from PokeAPI.
    Returns the `chain` node dict directly (ready for _flatten_chain).
    Raises ValueError on 404, ConnectionError on network failure.
    """
    data = _get(f"evolution-chain/{chain_id}")
    return data["chain"]
```

Note: returns the `chain` node, not the full response — callers only need
the tree, not the metadata wrapper.

**B4 — `pkm_cache.py` evolution cache layer**

```python
_EVOLUTION_DIR = os.path.join(_BASE, "evolution")

def get_evolution_chain(chain_id: int) -> list | None: ...
def save_evolution_chain(chain_id: int, paths: list) -> None: ...
def invalidate_evolution_chain(chain_id: int) -> None: ...
```

File path: `cache/evolution/{chain_id}.json`
Stores the already-flattened list of paths (output of `_flatten_chain`),
not the raw API response — avoids re-parsing on every load.

Also add `_EVOLUTION_DIR` to `check_integrity` scan and to the temp-dir
redirect in the test suite.

**B5 — `pokemain.py` startup flag `--refresh-evolution`**

Add a new startup flag alongside the existing `--refresh-pokemon` flag:

```
python pokemain.py --refresh-evolution <name>
```

Handler in `_handle_refresh_flags`:
1. Look up the Pokemon in cache to get its `evolution_chain_id`
2. Call `cache.invalidate_evolution_chain(chain_id)`
3. Print confirmation and exit

Also extend the **R key handler** in `pokemain.py` to call
`invalidate_evolution_chain` after the existing pokemon invalidation, using
the `evolution_chain_id` stored in `pkm_ctx`.

**B6 — `pkm_session.select_pokemon`**

Add `evolution_chain_id` to `pkm_ctx` (lesson from Pythonmon-27: fields
must be explicitly included or they silently disappear):

```python
"evolution_chain_id": cache.get_pokemon(name).get("evolution_chain_id"),
```

**Iteration B tests:**

`pkm_pokeapi.py` (offline mock):
- `fetch_pokemon` with `evolution_chain` in species response → dict includes
  `"evolution_chain_id": 1`
- `fetch_pokemon` with missing `evolution_chain` → `"evolution_chain_id": None`

`pkm_cache.py`:
- `get_evolution_chain` / `save_evolution_chain` round-trip
- `get_evolution_chain` on missing file → `None`
- `get_pokemon` on entry missing `"evolution_chain_id"` → `None`
  (auto-upgrade trigger; combined with `egg_groups` check)

`pkm_session.py`:
- `pkm_ctx` built by `select_pokemon` contains `"evolution_chain_id"` key
  (update fake_api mock to include the field)

---

### Iteration C — Display + integration

**Deliverable:** evolution chain appears at the bottom of option 1. Full
feature complete.

**C1 — `feat_evolution.get_or_fetch_chain(pkm_ctx) → list | None`**

Cache-aware bridge (same pattern as `get_or_fetch_roster`):

```python
def get_or_fetch_chain(pkm_ctx: dict) -> list | None:
    chain_id = pkm_ctx.get("evolution_chain_id")
    if chain_id is None:
        return None   # event Pokemon, no chain data
    paths = cache.get_evolution_chain(chain_id)
    if paths is not None:
        return paths
    try:
        print("  Loading evolution chain...", end=" ", flush=True)
        node  = pokeapi.fetch_evolution_chain(chain_id)
        paths = _flatten_chain(node)
        cache.save_evolution_chain(chain_id, paths)
        print("done.")
        return paths
    except (ValueError, ConnectionError):
        return None
```

**C2 — `feat_evolution.display_evolution_block(pkm_ctx, paths)`**

Renders the compact inline block:
- Header + separator
- One line per path, format: `Name [Type]  →  Trigger  →  Name [Type] ★`
- Types come from `pkm_ctx` for the current Pokemon (already loaded);
  for other stages types are not available offline — omit the type tag or
  show `[?]` if the Pokemon is not in cache
- `★` marks the stage whose slug matches `pkm_ctx["pokemon"]` (the raw
  species name). Using `variety_slug` would fail for alternate forms:
  `"charizard-mega-x"` is not in the chain, but `"charizard"` is.
- Single-stage chain → `"Name [Type] ★  — does not evolve"`
- Type tags always shown for all stages (fetched on first display, cached)
- Footer: `★ = current Pokémon`

**C3 — `feat_quick_view.run()`**

One call at the very end of `run()`:

```python
from feat_evolution import get_or_fetch_chain, display_evolution_block
paths = get_or_fetch_chain(pkm_ctx)
if paths is not None:
    display_evolution_block(pkm_ctx, paths)
```

Deferred import to avoid circular risk at load time.

**C4 — `pokemain.py`**

Add `import feat_evolution` to the try/except import block.

**C5 — `run_tests.py`**

Add `feat_evolution` to SUITES (offline, no cache keys).

**Iteration C tests** (stdout capture, mock `get_or_fetch_chain`):

- Linear chain → all stage names appear in output
- Current Pokemon marked with ★
- Branching chain → one line per branch
- Single-stage chain (no evolution) → "does not evolve" shown
- `chain_id = None` → `get_or_fetch_chain` returns `None` gracefully
- `display_evolution_block` with type info present → type tags shown
- `display_evolution_block` with type info absent → `[?]` shown or omitted

---

## Notes

- `_parse_trigger` and `_flatten_chain` live in `feat_evolution.py`, **not**
  `pkm_pokeapi.py`. They are parsing/display logic, not fetch logic. Only
  the raw HTTP fetch (`fetch_evolution_chain`) belongs in `pkm_pokeapi`.
  This follows the same separation as `fetch_egg_group` vs display logic.
- `_flatten_chain` stores only `slug` and `trigger` per stage — not types.
  Types for all stages are fetched via `fetch_pokemon` at display time (C2).
  On a warm cache this is instant. On first view, each uncached stage triggers
  one API call — acceptable latency for a chain of up to ~10 stages.
  A brief "Loading evolution data..." indicator is shown before fetching.
- The auto-upgrade check for `evolution_chain_id` must be combined with the
  `egg_groups` check in a single condition to avoid two sequential re-fetches
  for entries that predate both fields.
- The `★` marker uses `pkm_ctx["pokemon"]` (raw species slug) not
  `pkm_ctx["variety_slug"]` — alternate forms (Mega, regional) have a
  `variety_slug` that does not appear in the chain tree, but their base
  species name always does.
- Eevee (chain_id=67) is the canonical branching test case. Slowpoke
  (2 branches) is simpler for initial validation.
- `evolution_chain_id = None` is valid for some event Pokemon. Display
  nothing — no error message, no section header.
- **Cache staleness:** evolution chains are cached indefinitely. New evolutions
  added to PokeAPI after the initial fetch will not appear until the chain is
  refreshed. Two invalidation paths:
  1. `--refresh-evolution <name>` startup flag: invalidates the evolution
     chain for that Pokemon and re-fetches on next view.
  2. **Key R (refresh Pokemon):** already re-fetches pokemon data; extend it
     to also call `invalidate_evolution_chain(chain_id)` so pressing R gives
     fully fresh data in one keypress.
  3. `--check-cache` scans `cache/evolution/` as part of the integrity check
     (already planned in B4).

---

# Completion criteria

Batch 4 is complete when:

* Pythonmon-28: Effect line appears in move lookup; `MOVES_CACHE_VERSION == 3`;
  offline tests pass
* Pythonmon-27: Egg group screen accessible via key `E`; existing pokemon
  cache entries without `egg_groups` trigger re-fetch; offline tests pass
* Pythonmon-9: Evolution chain block appears at the bottom of option 1 quick
  view; linear and branching chains displayed correctly in compact inline
  format; offline tests pass
* All offline tests pass (`python run_tests.py --offline`)
* `HISTORY.md`, `ROADMAP.md`, `TASKS.md`, `ARCHITECTURE.md` updated for
  each ticket

---

# Pythonmon-32 — Role & speed tier in quick view and stat compare

**Status:** ✅ COMPLETE (§83)
**Files:** `feat_nature_browser.py`, `feat_type_matchup.py`,
  `feat_stat_compare.py`
**Complexity:** 🟢 Low
**New API call:** No
**Cache structure change:** No

## What

Show the Pokemon's inferred attacking role and speed tier directly below the
base stats block in two places:

**Option 1 (quick view):**
```
  Base stats — Charizard
  ──────────────────────────────────────────────
  HP      78  [██████············]
  Atk     84  [██████············]
  Def     78  [██████············]
  SpA    109  [████████··········]
  SpD     85  [██████············]
  Spe    100  [███████···········]
  ──────────────────────────────────────────────
  Total        534
  Role: Special attacker  |  Speed: Fast (base 100)
```

**Option C (stat compare):**
```
  Charizard  [Fire / Flying]            Garchomp  [Dragon / Ground]
  ════════════════════════════════════════════════════════
  HP    ...
  ...
  ────────────────────────────────────────────────────────
  Total  534  ...  600  ...
  Role:  Special / Fast             Physical / Fast
  ════════════════════════════════════════════════════════
```

## Design decision — function location

`_infer_role` and `_infer_speed_tier` currently live in
`feat_nature_browser.py` as private functions. They need to be accessible
from `feat_type_matchup` and `feat_stat_compare`.

`feat_stat_compare.py` is the correct home: it is already the
"base stat analysis" module (`compare_stats`, `total_stats`, `_stat_bar`).
Role and speed tier are the same category — pure functions that derive
meaning from base stats. Keeping all stat-derived analysis in one file is
the cleanest design.

`feat_nature_browser` becomes a consumer of `feat_stat_compare` for these
functions. That is the correct dependency direction: nature recommendations
use stat analysis, not the other way around.

## Implementation

### Step 1 — `feat_stat_compare.py`

Add two new public functions after `total_stats`:

```python
def infer_role(base_stats: dict) -> str:
    """
    Return the inferred attacking role based on Atk vs SpA.
    'physical' — Atk >= SpA * 1.2
    'special'  — SpA >= Atk * 1.2
    'mixed'    — neither dominates
    """
    atk = base_stats.get("attack", 1) or 1
    spa = base_stats.get("special-attack", 1) or 1
    if atk >= spa * 1.2:
        return "physical"
    if spa >= atk * 1.2:
        return "special"
    return "mixed"


def infer_speed_tier(base_stats: dict) -> str:
    """
    Return the speed tier based on base Speed.
    'fast' — Speed >= 90
    'mid'  — Speed >= 70
    'slow' — Speed < 70
    """
    spe = base_stats.get("speed", 0)
    if spe >= 90: return "fast"
    if spe >= 70: return "mid"
    return "slow"
```

Same thresholds as the existing private functions in `feat_nature_browser`.

### Step 2 — `feat_nature_browser.py`

Replace the two private function definitions with imports:

```python
from feat_stat_compare import infer_role, infer_speed_tier
```

Remove `_infer_role` and `_infer_speed_tier` entirely. Update internal
callers (`_role_score`) to use the imported names.

### Step 3 — `feat_type_matchup._print_base_stats`

Add two lines after the Total line:

```python
from feat_stat_compare import infer_role, infer_speed_tier
role = infer_role(base_stats)
tier = infer_speed_tier(base_stats)
spe  = base_stats.get("speed", 0)
print(f"  Role: {role.capitalize()} attacker  |  Speed: {tier.capitalize()} (base {spe})")
```

For "mixed", display as `"Mixed attacker"` — not just "Mixed".
Show the actual base Speed value in parentheses so the user can see
exactly where in the tier the Pokemon lands.

### Step 4 — `feat_stat_compare.display_comparison`

Add a Role line after the Total line, showing both Pokemon side by side.
`infer_role` and `infer_speed_tier` are already available in this module:

```python
role_a = infer_role(pkm_a.get("base_stats", {}))
tier_a = infer_speed_tier(pkm_a.get("base_stats", {}))
role_b = infer_role(pkm_b.get("base_stats", {}))
tier_b = infer_speed_tier(pkm_b.get("base_stats", {}))
label_a = f"{role_a.capitalize()} / {tier_a.capitalize()}"
label_b = f"{role_b.capitalize()} / {tier_b.capitalize()}"
print(f"  {'Role':<{_COL_LABEL}}  {label_a:<{_left_w}}{label_b}")
```

## Tests

### `feat_stat_compare.py`
- `infer_role`: Physical when `atk >= spa * 1.2`
- `infer_role`: Special when `spa >= atk * 1.2`
- `infer_role`: Mixed when neither dominates
- `infer_speed_tier`: Fast when `spe >= 90`
- `infer_speed_tier`: Mid when `70 <= spe < 90`
- `infer_speed_tier`: Slow when `spe < 70`
- Edge case: equal Atk and SpA → Mixed
- Edge case: Speed exactly 90 → Fast, exactly 70 → Mid

### `feat_type_matchup.py` (stdout capture)
- Output contains "Role:" line when `base_stats` populated
- "Physical attacker" for Garchomp (Atk 130, SpA 80)
- "Special attacker" for Gengar (Atk 65, SpA 130)
- "Mixed attacker" for a mixed-stat Pokemon

### `feat_stat_compare.py` (stdout capture, display_comparison)
- Output contains "Role" line
- Both Pokemon's role/tier appear on the same line

### `feat_nature_browser.py`
- Existing `_role_score` tests still pass (import swap, no logic change)

## Notes

- The import `from feat_stat_compare import infer_role, infer_speed_tier`
  in `feat_type_matchup._print_base_stats` should be deferred (inside the
  function body) to avoid any circular import risk at module load time.
- `feat_nature_browser` importing from `feat_stat_compare` is a sibling
  import — consistent with existing patterns in the codebase.
- No change to `feat_stat_compare._left_w` needed — the Role line reuses
  the same layout constants as the Total line.
