# ARCHITECTURE.md
# System design, module roles, data structures, and interface contracts

---

## 1. High-level structure

```
pokemon-toolkit/
  pokemain.py               Entry point and menu loop
  pkm_session.py            Game + Pokemon context selection
  pkm_cache.py              All cache reads and writes (single gateway, now uses SQLite)
  pkm_sqlite.py             SQLite database layer (tables, connections, low‑level access)
  pkm_sync.py               One‑time full data import from PokeAPI to SQLite (`--sync`)
  pkm_pokeapi.py            PokeAPI adapter (fetch + translate raw data)
  matchup_calculator.py     Type chart data + multiplier logic (pure library)
  run_tests.py              Test runner (calls --autotest on each module)
  cache/                    Local cache directory (contains pokemon.db)
  data/trainers.json        Local JSON file with notorious trainers data (gym & league)
  
  # Core logic modules (no I/O, no display)
  core_stat.py              Pure stat functions (compare_stats, total_stats, infer_role, etc.)
  core_egg.py               Pure egg group functions (egg_group_name, format_egg_groups)
  core_evolution.py         Pure evolution chain logic (parse_trigger, flatten_chain, filter)
  core_move.py              Pure move scoring and combo selection (score_move, select_combo, etc.)
  core_team.py              Pure team analysis and builder logic
  core_opponent.py          Pure opponent analysis logic
  
  # Feature modules (thin UI wrappers)
  feat_quick_view.py        Feature: quick view (stats / abilities / egg groups / type chart / evolution chain)
  feat_move_lookup.py       Feature: move lookup by name
  feat_movepool.py          Feature: learnable move list with learn conditions
  feat_moveset.py           Feature: scored pool + moveset recommendation UI
  feat_moveset_data.py      Data fetching for moveset recommendation (I/O)
  feat_type_browser.py      Feature: browse Pokemon by type
  feat_nature_browser.py    Feature: nature & EV build advisor + nature browser (key N)
  feat_ability_browser.py   Feature: ability browser + Pokemon roster drill-in
  feat_team_loader.py       Feature: team context management (add/remove/view)
  feat_team_analysis.py     Feature: team defensive vulnerability table
  feat_team_offense.py      Feature: team offensive type coverage (key O)
  feat_team_moveset.py      Feature: team moveset synergy (key S)
  feat_egg_group.py         Feature: egg group browser + breeding partners (key E)
  feat_learnset_compare.py  Feature: stats and learnset comparison between two Pokémon (key L)
  feat_team_builder.py      Feature: team slot suggestion — gap analysis + ranked candidates (key H)
  feat_opponent.py          Feature: team coverage vs in‑game opponents (key X)

```

All files live in a **single flat folder**. No package structure, no `__init__.py`.
All cross-module imports use plain `import <module>` (no relative imports).

---

## 2. Layer model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              pokemain.py                                    │
│  (entry point, menu loop, UI selection)                                     │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              UI layer                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  ui_base.py (abstract)                                                │  │
│  │      ▲                                                                │  │
│  │      │                                                                │  │
│  │  ┌───┴──────────┐          ┌────────────────────┐                     │  │
│  │  │   ui_cli.py  │          │     ui_tui.py      │                     │  │
│  │  │   (CLI)      │          │     (TUI)          │                     │  │
│  │  └──────────────┘          └────────────────────┘                     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  Dependencies:                                                              │
│  ┌─────────────────────┐          ┌─────────────────────┐                   │
│  │   menu_builder.py   │          │   pkm_session.py    │                   │
│  │ (menu/context lines)│          │ (context selection) │                   │
│  └─────────────────────┘          └─────────────────────┘                   │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Feature modules (feat_*.py)                         │
│  feat_quick_view.py, feat_move_lookup.py, feat_movepool.py,                 │
│  feat_moveset.py, feat_moveset_data.py, feat_type_browser.py,               │
│  feat_nature_browser.py, feat_ability_browser.py, feat_team_loader.py,      │
│  feat_team_analysis.py, feat_team_offense.py, feat_team_moveset.py,         │
│  feat_team_builder.py, feat_opponent.py, feat_egg_group.py,                 │
│  feat_learnset_compare.py,                                                  │
│                                                                             │
│  Data dependency: data/trainers.json (used by feat_opponent.py)             │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Core logic (core_*.py)                              │
│  core_stat.py, core_egg.py, core_evolution.py, core_move.py,                │
│  core_team.py, core_opponent.py                                             │
│  (pure functions, no I/O)                                                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    matchup_calculator.py                            │    │
│  │  (type chart library, pure)                                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Cache layer (pkm_cache.py)                          │
│  – Single gateway for all cached data                                       │
│  – Calls pkm_sqlite.py for low‑level DB access                              │
│  – Calls pkm_pokeapi.py for network fetches on cache miss                   │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
┌───────────────────────┐   ┌───────────────────────┐
│   pkm_sqlite.py       │   │   pkm_pokeapi.py      │
│   SQLite low‑level    │   │   PokeAPI adapter     │
│   – tables, queries   │   │   – fetch & translate │
└───────────────────────┘   └───────────────────────┘
            │                       │
            ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SQLite database                                │
│  cache/pokemon.db                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

```

**Strict layering rule:** lower layers must not import from upper layers.
`pkm_cache.py` never imports `feat_*.py`. `pkm_pokeapi.py` never imports `pkm_cache.py`
directly (cache calls it). `matchup_calculator.py` imports nothing from this project.

The one intentional exception: `feat_moveset_data.py` is a pure logic module at the
same level as `feat_moveset.py` — it is a data/logic sibling, not a sub-layer.

---

## 3. Context objects

Context objects are plain Python dicts. No classes. They are created in
`pkm_session.py` and threaded through function arguments. Never store them
in module-level globals.

### 3.1 game_ctx

```python
{
    "game"        : str,   # Display name  e.g. "Scarlet / Violet"
    "era_key"     : str,   # "era1" | "era2" | "era3"
    "game_gen"    : int,   # Generation number 1–9
    "game_slug"   : str,   # PokeAPI slug  e.g. "scarlet-violet"
    "version_slugs": list[str],  # All PokeAPI version slugs for this game group
                                 # e.g. ["red-blue", "yellow"] for Red/Blue/Yellow
}

### 3.2 pkm_ctx

```python
{
    "pokemon"      : str,        # Species slug / search key  e.g. "sandslash"
    "variety_slug" : str,        # PokeAPI form slug used to key the learnset cache
                                 # and fetch the correct move list. Equals the variety
                                 # slug in most cases (e.g. "sandslash-alola") but uses
                                 # the form slug when the two differ (§80).
    "form_name"    : str,        # Display name  e.g. "Alolan Sandslash"
    "types"        : list[str],  # e.g. ["Ice", "Steel"]
    "type1"        : str,        # e.g. "Ice"
    "type2"        : str,        # "None" (STRING, not Python None) if single-typed
    "species_gen"  : int,        # Generation the species was introduced
    "form_gen"     : int,        # Generation this form was introduced
    "base_stats"   : dict,       # keys: hp, attack, defense,
                                 #       special-attack, special-defense, speed
    "abilities"    : list[dict], # [{"slug": str, "is_hidden": bool}, ...]
    "egg_groups"        : list[str],  # PokeAPI slugs e.g. ["monster", "dragon"]; [] if unknown
    "evolution_chain_id": int | None, # PokeAPI chain ID; None for event Pokemon with no chain
}
```

**Critical:** `type2` is always a string. It is `"None"` for single-typed Pokemon,
never Python `None`. Every function that tests for dual-type checks `type2 != "None"`.

### 3.3 team_ctx

```python
team_ctx = [pkm_ctx_or_None, pkm_ctx_or_None, ..., pkm_ctx_or_None]  # always 6 elements
```

A list of exactly 6 slots. Empty slots are Python `None`. Team is session-only —
no persistence to disk.

---

## 4. Cache layout


All cache data is stored in a single SQLite database file:
```
cache/pokemon.db Main database (tables listed below)
```
The database is created on first access. Tables are created automatically. 
All data is stored as JSON text in the appropriate columns, preserving the original data structures.

### SQLite database schema

The SQLite database (`pokemon.db`) replaces all JSON cache files. It is stored in the same cache directory and created automatically on first use.

| Table | Columns | Purpose |
|-------|---------|---------|
| `metadata` | `key TEXT PRIMARY KEY`, `value TEXT` | Global metadata: schema version, moves schema version, etc. |
| `pokemon` | `slug TEXT PRIMARY KEY`, `data TEXT NOT NULL`, `scraped_at TEXT` | One row per Pokémon species. `data` contains the full Pokémon dict (forms, stats, etc.) as JSON. |
| `learnsets` | `variety_slug TEXT`, `game_slug TEXT`, `data TEXT NOT NULL`, `scraped_at TEXT`, PRIMARY KEY (variety_slug, game_slug) | One row per (variety, game) combination. `data` contains the learnset JSON (level-up, machine, tutor, egg). |
| `moves` | `name TEXT PRIMARY KEY`, `data TEXT NOT NULL`, `version INTEGER` | One row per move. `data` contains the versioned entries list as JSON. `version` stores `MOVES_CACHE_VERSION`. |
| `machines` | `url TEXT PRIMARY KEY`, `label TEXT NOT NULL` | Mapping from machine resource URL to TM/HM label (e.g., `"TM35"`). |
| `types` | `type_name TEXT PRIMARY KEY`, `data TEXT NOT NULL` | One row per type. `data` contains the list of Pokémon entries for that type (slug, slot, id, name). |
| `natures` | `id INTEGER PRIMARY KEY CHECK (id = 1)`, `data TEXT NOT NULL` | Single row containing the full natures dict. |
| `abilities_index` | `id INTEGER PRIMARY KEY CHECK (id = 1)`, `data TEXT NOT NULL` | Single row containing the abilities index dict. |
| `abilities` | `slug TEXT PRIMARY KEY`, `data TEXT NOT NULL` | One row per ability. `data` contains the full ability detail (effect, Pokémon list). |
| `egg_groups` | `slug TEXT PRIMARY KEY`, `data TEXT NOT NULL` | One row per egg group. `data` contains the roster list of Pokémon in that group. |
| `evolution` | `chain_id INTEGER PRIMARY KEY`, `data TEXT NOT NULL` | One row per evolution chain. `data` contains the flattened list of paths. |
| `sync_status` | `key TEXT PRIMARY KEY`, `value TEXT` | Tracks which sync sections have been completed (used by `--sync`). |

**Relationships** (implied by the data stored in JSON blobs):
- A Pokémon (row in `pokemon`) has one evolution chain (referenced by `evolution_chain_id` inside the JSON data).
- A learnset row (`learnsets`) belongs to one Pokémon variety (`variety_slug`) and one game (`game_slug`).
- Moves are independent; learnsets reference move names (stored in the JSON).
- Type rosters (`types`) reference Pokémon slugs.

**Future normalisation:** For more complex queries (e.g., “all Fire‑type Pokémon with base Speed > 100”), the database could be normalised into separate tables for forms, stats, etc. This is a potential future enhancement.




---

## 5. Type chart system (matchup_calculator.py)

Three eras, each a complete type chart:

| Era key | Games | # Types |
|---|---|---|
| `era1` | Gen 1 (RBY) | 15 |
| `era2` | Gen 2–5 | 17 |
| `era3` | Gen 6+ | 18 |

`CHARTS` dict structure:
```python
CHARTS = {
    "era1": (chart_dict, valid_types_tuple, name),
    "era2": (...),
    "era3": (...),
}
```

Key functions:
- `get_multiplier(era_key, atk_type, def_type) → float`  Single attacker vs single defender
- `compute_defense(era_key, type1, type2) → {atk_type: multiplier}`  Full defensive chart for a Pokemon
- `print_results(type1, type2, game_name, era_key)`  Standalone display

This module is a pure library. It has no imports from this project.
`matchup_calculator.py` is imported by: `pkm_session.py`, `pokemain.py`,
`feat_quick_view.py`, `feat_team_analysis.py`, `feat_team_offense.py`,
`feat_team_moveset.py`, `feat_moveset_data.py`, and core_*.py.

---

## 6. Move versioning schema

Each entry in `moves.json` is a list of versioned sub-entries keyed directly
by the move's display name:

```python
{
  "Tackle": [
    {"from_gen": 1, "to_gen": 5, "type": "Normal", "category": "Physical",
     "power": 35, "accuracy": 95, "pp": 35, "priority": 0,
     "drain": 0, "effect_chance": 0, "ailment": "none", "effect": "Inflicts regular damage."},
    {"from_gen": 6, "to_gen": None, "type": "Normal", "category": "Physical",
     "power": 40, "accuracy": 100, "pp": 35, "priority": 0,
     "drain": 0, "effect_chance": 0, "ailment": "none", "effect": "Inflicts regular damage."}
  ]
}
```

`to_gen: None` means "current generation". `from_gen` and `to_gen` are inclusive.
Resolution: find the entry where `from_gen <= game_gen <= to_gen`.

Schema version history (see `MOVES_CACHE_VERSION` in `pkm_cache.py`):
- v1 — type, category, power, accuracy, pp, priority
- v2 — added drain, effect_chance, ailment
- v3 — added effect (English short_effect text, §84)

---

## 7. Module roles and public API

### pokemain.py
Entry point only. Contains the main menu loop, context variables, and key dispatch.
Has almost no logic of its own. Wires features together.

Key internal functions:
- `_print_menu(pkm_ctx, game_ctx, team_ctx)` — builds the visible menu
- `_print_context_lines(pkm_ctx, game_ctx, team_ctx)` — header block

**Command‑line flags:** Supports `--help` (or `-h`), `--game <name>`, `--cache-info`, `--check-cache`, `--refresh-moves`, `--refresh-pokemon <name>`, `--refresh-learnset <name> <game>`, `--refresh-all <name>`, and `--refresh-evolution <n>`.

### pkm_session.py
Handles all interactive context selection.

- `select_game(pkm_ctx=None) → game_ctx | None`
- `select_pokemon(game_ctx=None) → pkm_ctx | None`
- `make_game_ctx(game_name) → game_ctx` (raises ValueError if game not found)
- `refresh_pokemon(pkm_ctx, game_ctx) → pkm_ctx`

Called by feature standalone `main()` functions and by pokemain.

### pkm_cache.py
Single gateway to all cached data. Feature files never open cache files directly. Now uses SQLite via `pkm_sqlite.py`. All public functions remain unchanged.

Key functions:
- `get_move(name) → list | None`
- `upsert_move(name, entries) → None`
- `upsert_move_batch(batch) → None`
- `check_integrity() → list[str]`  (empty list = clean cache)
- `get_pokemon(slug) → dict | None`
- `get_learnset(variety_slug, game_slug) → dict | None`
- `get_type_roster(type_name) → list | None`
- `get_natures() → dict | None`
- `get_ability(slug) → dict | None`
- `get_abilities_index() → dict | None`
- `save_*` counterparts for each
- `get_index() → dict`  (compact index of all Pokémon, used by fuzzy search)

### pkm_pokeapi.py
Fetches data from PokeAPI and translates it to the cache schema.
Never called directly by feature files — always called by pkm_cache.py or pkm_session.py.

- `fetch_pokemon(slug) → dict`
- `fetch_learnset(variety_slug, game_slug) → dict`
- `fetch_move(name) → dict`
- etc.

### matchup_calculator.py
Pure type chart library. No project imports. See section 5.

### pkm_sqlite.py
Low‑level SQLite database layer. Manages the connection, table creation, and basic CRUD operations. It is used exclusively by `pkm_cache.py`.

- `set_base(base_path)` – sets the directory for the database file.
- `get_connection()` – context manager that yields a connection (creates tables if needed).
- `get_pokemon(slug)`, `save_pokemon(...)`, `invalidate_pokemon(...)` – direct database access.
- Similar functions for moves, learnsets, machines, types, natures, abilities, egg groups, evolution chains, metadata, and sync status.
- `get_cache_info()`, `check_integrity()` – high‑level database inspection.

### pkm_sync.py
One‑time full data import script. Fetches all Pokémon, moves, type rosters, natures, abilities, egg groups, and evolution chains from PokeAPI and stores them in the SQLite database. Progress is tracked in the `sync_status` table, allowing resumption if interrupted.

- `sync_all(force=False)` – main entry point. If `force` is True, deletes the existing database and starts fresh; otherwise, resumes from the last completed section.



### Core library modules

These modules contain pure logic with no I/O, no print statements, and no user input.
They are imported by feature modules.

| Module | Public API | Purpose |
|--------|------------|---------|
| `core_stat.py` | `stat_bar`, `total_stats`, `infer_role`, `infer_speed_tier`, `compare_stats` | Stat calculations |
| `core_egg.py` | `egg_group_name`, `format_egg_groups` | Egg group display |
| `core_evolution.py` | Evolution chain parsing (`parse_trigger`, `flatten_chain`, `filter_paths_for_game`). Also provides `trigger_is_pure_level_up` and `is_pure_level_up_chain` to identify whether an evolution path consists entirely of level‑up triggers (used by the team builder to filter redundant stages). |
| `core_move.py` | `score_move`, `rank_status_moves`, `select_combo`, `combo_score`, `build_counter_pool`, `build_coverage_pool`, `score_learnset`, and static tables | Move scoring and combo selection |
| `core_team.py` | `build_team_defense`, `build_unified_rows`, `gap_label`, `build_weakness_pairs`, `weakness_types`, `se_types`, `build_offensive_coverage`, `team_offensive_gaps`, `team_defensive_gaps`, `score_candidate`, `rank_candidates`, and many others | Team analysis and builder |
| `core_opponent.py` | `analyze_matchup`, `uncovered_threats`, `recommended_leads` | Opponent analysis |

### Feature modules (thin UI wrappers)

Each feature module now imports the necessary core functions and handles only:
- fetching data from `pkm_cache`
- calling core functions
- displaying results (print statements) and user input

The following is a representative list; each file's docstring describes its entry points.

| File | Role |
|---|---|
| `feat_quick_view.py` | Quick view (option 1) |
| `feat_move_lookup.py` | Move lookup (key M) |
| `feat_movepool.py` | Learnable move list (option 2) |
| `feat_moveset.py` | Scored pool (option 3) and moveset recommendation (option 4) |
| `feat_moveset_data.py` | I/O for `build_candidate_pool` (fetches learnset and move details) |
| `feat_type_browser.py` | Type browser (key B) |
| `feat_nature_browser.py` | Nature & EV advisor (key N) |
| `feat_ability_browser.py` | Ability browser (key A) |
| `feat_team_loader.py` | Team management (key T) |
| `feat_team_analysis.py` | Team defensive analysis (key V) |
| `feat_team_offense.py` | Team offensive coverage (key O) |
| `feat_team_moveset.py` | Team moveset synergy (key S) |
| `feat_egg_group.py` | Egg group browser (key E) |
| `feat_learnset_compare.py` | Learnset comparison (key L) |
| `feat_team_builder.py` | Team builder (key H) |
| `feat_opponent.py` | Team vs opponent (key X) |


---

## 8. Core library modules

The project has been refactored to separate pure logic from display and I/O. The following core modules contain no I/O, no print statements, and no user input; they operate only on plain data structures passed as arguments.

| File | Purpose |
|------|---------|
| `core_stat.py` | Stat-related functions: `compare_stats`, `total_stats`, `infer_role`, `infer_speed_tier`, `stat_bar` |
| `core_egg.py` | Egg group logic: `egg_group_name`, `format_egg_groups` |
| `core_evolution.py` | Evolution chain parsing and filtering: `parse_trigger`, `flatten_chain`, `filter_paths_for_game` |
| `core_move.py` | Move scoring and combo selection: `score_move`, `rank_status_moves`, `select_combo`, `combo_score`, `score_learnset`, plus static tables (`TWO_TURN_MOVES`, `STATUS_MOVE_TIERS`, etc.) |
| `core_team.py` | Team analysis and builder logic: defensive/offensive analysis, weakness pairs, candidate scoring, ranking |
| `core_opponent.py` | Opponent analysis: `analyze_matchup`, `uncovered_threats`, `recommended_leads` |

These modules are independently testable via `--autotest` and are reused by the UI layer (`feat_*.py`). All I/O (cache access, network requests, user prompts) remains in the `feat_*.py` files, which now act as thin wrappers.


---

## 9. Interface contracts

These are the cross-module contracts that must not be broken silently.
If any of these change, update this section and log in HISTORY.md.

### type2 is always a string

Every module that reads `pkm_ctx["type2"]` checks `type2 != "None"` (string comparison).
Never `type2 is not None` (identity). This is load-bearing — changing it would break
`compute_defense()`, `build_team_defense()`, all display functions, and learnset lookups.

### team_ctx is always a 6-element list

Every function that receives `team_ctx` may assume `len(team_ctx) == 6`.
Use `team_slots()` to iterate filled slots. Never iterate team_ctx directly.

### feat_*.run() signature

All feature run() functions called from pokemain follow one of two signatures:
```python
run(pkm_ctx, game_ctx)              # single-Pokemon features
run(team_ctx, game_ctx)             # team features
run(game_ctx)                       # game-only features (move lookup, browsers)
```
They print to stdout and return None (or an updated context for feat_team_loader).

### Cache miss returns None

Every `pkm_cache.get_*()` returns `None` on miss or error — never raises.
Callers must check for None before using the result.

### era_key values

Only three valid values: `"era1"`, `"era2"`, `"era3"`.
Any function that receives era_key and passes it to `calc.CHARTS[era_key]` will
KeyError if an invalid value is passed. Validate at the source (pkm_session.py).

### _abbrev(name) — 4-character name truncation

All display functions that show Pokemon names in table cells use `_abbrev(name)`
(defined in `feat_team_analysis.py`). Short names (<= 4 chars) are returned as-is.
This is the display contract for all team analysis tables.


---

## 10. UI abstraction layer

The toolkit now separates user interface concerns from application logic using an abstract UI class.
All direct `print()` and `input()` calls have been replaced with methods on a `UI` instance.
The current CLI implementation (`ui_cli.py`) provides a text-based interface, but other front‑ends (e.g., a TUI using `textual`) can be added by implementing the same interface.

### UI class (ui_base.py)

The abstract base class defines the following methods:

- `print_header()` – prints the application banner.
- `print_menu(lines)` – prints a boxed menu.
- `print_output(text, end)` – general‑purpose output.
- `print_progress(text, end, flush)` – for progress counters.
- `input_prompt(prompt) -> str` – user input.
- `confirm(prompt) -> bool` – yes/no question.
- `select_from_list(prompt, options, allow_none) -> str | None` – numbered list selection.
- `select_pokemon(game_ctx) -> dict | None` – interactive Pokemon selection.
- `select_game(pkm_ctx) -> dict | None` – interactive game selection.
- `select_form(forms) -> tuple` – choose from a list of Pokemon forms.
- `print_session_header(pkm_ctx, game_ctx, constraints)` – prints the context header.

All interactive functions that were previously in `pkm_session.py` are now part of the UI class.
 The pure context‑building logic remains in `pkm_session.py`.

### CLI implementation (ui_cli.py)

The `CLI` class implements the UI interface using standard console I/O (`print`, `input`).
 The main loop and menu dispatch remain in `pokemain.py` (but could be moved to `ui.run()` in the future).
 Features receive the UI instance as an argument (typically named `ui`) and use it for all user interaction.

### Future extensions

A TUI implementation (e.g., using `textual` or `curses`) would be added by creating a new class that inherits from `UI` and implementing its methods.
The toolkit would then select the appropriate UI based on a command‑line flag or environment setting.



---

## 11. Design constraints (non-negotiable)

- **Single flat folder.** All .py files and cache/ in the same directory.
- **No pip dependencies beyond `requests`.** stdlib only for everything else.
- **No async code.** All operations are synchronous.
- **SQLite database.** The cache is stored in a single SQLite file (`cache/pokemon.db`).
- **Python 3.10+ required.** This is the minimum supported version; do not use syntax or stdlib features introduced after 3.10.
- **Atomic writes.** SQLite transactions ensure atomicity; the old JSON write‑tmp‑move pattern is no longer used.
- **Defensive reads.** All cache reads return None on any error, never raise.

---

## 12. Embedded Data Tables and Constants

This section lists all static data that is **hard‑coded** in the source files (not fetched from PokeAPI or generated at runtime). It is a single‑source inventory to help with refactoring, migration to a database, or understanding where configuration values reside.

### 12.1 Game and generation data

| File | Constant | Purpose |
|------|----------|---------|
| `matchup_calculator.py` | `GENERATIONS` | Maps generation number → label and era key. |
| `matchup_calculator.py` | `GAMES` | Ordered list of all supported games, each as `(display_name, era_key, gen)`. |
| `matchup_calculator.py` | `TYPES_ERA1`, `TYPES_ERA2`, `TYPES_ERA3` | Lists of type names valid in each era. |
| `matchup_calculator.py` | `ERA1_CHART`, `ERA2_CHART`, `ERA3_CHART` | Type‑effectiveness matrices (attacker × defender). |
| `matchup_calculator.py` | `CHARTS` | Dictionary mapping era key → (chart, type list, column map). |
| `matchup_calculator.py` | `_COL1`, `_COL2`, `_COL3` | Column index maps for each era (used internally). |
| `matchup_calculator.py` | `ERA_LABELS` | Human‑readable labels for each era. |
| `pkm_pokeapi.py` | `GAME_TO_VERSION_GROUPS` | Maps game display name → list of PokeAPI version‑group slugs. |
| `pkm_pokeapi.py` | `VERSION_GROUP_TO_GEN` | Reverse mapping: version‑group slug → generation number (built from above). |
| `pkm_pokeapi.py` | `_ROMAN` | Maps Roman numerals to integers (e.g., `"iv"` → 4). |

### 12.2 Move scoring and recommendation data

| File | Constant | Purpose |
|------|----------|---------|
| `feat_moveset_data.py` | `TWO_TURN_MOVES` | Dictionary of moves with charge/recharge penalties (`"invulnerable"`, `"penalty"`). |
| `feat_moveset_data.py` | `COMBO_EXCLUDED` | Frozenset of move names never auto‑suggested by `select_combo()`. |
| `feat_moveset_data.py` | `CONDITIONAL_PENALTY` | Penalty factors for moves that require a specific condition (e.g., Dream Eater). |
| `feat_moveset_data.py` | `POWER_OVERRIDE` | Overrides for moves whose base power is not stored in PokeAPI (e.g., Wring Out). |
| `feat_moveset_data.py` | `STATUS_MOVE_TIERS` | Hand‑curated tier and quality for status moves (over 130 entries). |
| `feat_moveset_data.py` | `STATUS_CATEGORIES` | Static mapping of PokeAPI move‑meta‑categories to display labels and tiers. |
| `feat_moveset_data.py` | `LOW_ACCURACY_THRESHOLD` | Display flag: moves with accuracy ≤ this value are marked `(!)`. |
| `feat_moveset_data.py` | `_COVERAGE_BONUS_PER_TYPE`, `_COUNTER_BONUS_PER_WEAK`, `_STAB_BONUS_PER_MOVE`, `_REDUNDANCY_PENALTY` | Weights used in `_combo_score()`. |
| `feat_moveset_data.py` | `_STAB_POOL_CAP` | Maximum number of moves considered in STAB mode (25). |
| `feat_moveset_data.py` | `_COUNTER_FILLER_K` | Number of non‑covering moves kept in counter mode (8). |
| `feat_moveset.py` | `MAX_CONSTRAINTS` | Maximum number of locked moves (4). |
| `feat_moveset.py` | `_MODE_LABELS` | Human‑readable labels for the three recommendation modes. |

### 12.3 Team builder and analysis constants

| File | Constant | Purpose |
|------|----------|---------|
| `feat_team_builder.py` | `_W_OFFENSIVE`, `_W_DEFENSIVE`, `_W_WEAK_PAIR`, `_W_ROLE`, `_LOOKAHEAD_END` | Scoring weights for candidate suggestions. |
| `feat_team_builder.py` | `_GEN_RANGES` | List of `(max_dex_id, generation)` for mapping species IDs to gen (duplicated in `feat_type_browser.py` and `feat_evolution.py`). |
| `feat_team_analysis.py` | `_NAME_ABBREV` | Number of characters to keep when abbreviating Pokémon names in tables (4). |
| `feat_team_analysis.py` | `_COL_TYPE`, `_COL_CNT`, `_COL_WNAMES`, `_COL_RNAMES`, `_COL_INAMES`, `_GAP_WIDTH` | Column widths for the unified type table. |
| `feat_team_loader.py` | `MAX_SLOTS` | Maximum team size (6). |
| `feat_team_offense.py` | `_COL_TYPE`, `_COL_HITTERS`, `_NAME_LEN`, `_MOVE_NAME_LEN` | Column widths for the offensive coverage table. |
| `feat_team_moveset.py` | `_COL_MOVE`, `_BLOCK_SEP` | Layout constants for team moveset synergy. |
| `feat_learnset_compare.py` | `_COL_NAME`, `_COL_TYPE`, `_COL_CAT`, `_COL_PWR`, `_COL_ACC`, `_SEP_W`, `_STAT_W` | Column widths for learnset comparison. |

### 12.4 Nature and EV advisor

| File | Constant | Purpose |
|------|----------|---------|
| `feat_nature_browser.py` | `STAT_SHORT` | Maps stat slugs (e.g., `"special-attack"`) to short labels (`"SpA"`). |
| `feat_nature_browser.py` | `_NATURE_ORDER` | Ordered list of 25 nature names (used for display grouping). |
| `feat_nature_browser.py` | `_NATURE_MIN_GEN` | Generation in which natures were introduced (3). |
| `feat_nature_browser.py` | `_PROFILE_NATURES` | Mapping of `(role, speed_tier)` → list of two (label, nature_name) pairs for EV profiles. |

### 12.5 Egg groups and forms

| File | Constant | Purpose |
|------|----------|---------|
| `feat_egg_group.py` | `_EGG_GROUP_NAMES` | Maps PokeAPI egg‑group slugs to in‑game display names (e.g., `"ground"` → `"Field"`). |
| `pkm_session.py` | `_FORM_GEN_KEYWORDS` | Keywords used to detect form generation (e.g., `"alolan"` → 7). |
| `pkm_session.py` | `_MAX_SUGGESTIONS` | Maximum number of suggestions shown during fuzzy name search (8). |

### 12.6 Type browser and stat comparison

| File | Constant | Purpose |
|------|----------|---------|
| `feat_type_browser.py` | `_GEN_RANGES` | Same mapping as in `feat_team_builder.py` and `feat_evolution.py`. |
| `feat_type_browser.py` | `_COL_NAME`, `_COL_T1`, `_COL_T2`, `_COL_GEN`, `_TABLE_W` | Column widths for the type‑browser table. |
| `feat_stat_compare.py` | `_BAR_MAX`, `_BAR_WIDTH` | Maximum base stat (255) and bar length (18) for the stat bars (also duplicated in `feat_quick_view.py`). |
| `feat_stat_compare.py` | `_STAT_KEYS` | Ordered list of `(slug, label)` for the six stats. |
| `feat_quick_view.py` | `_STAT_LABELS` | Same as above (duplicated). |

### 12.7 Cache and network

| File | Constant | Purpose |
|------|----------|---------|
| `pkm_cache.py` | `MOVES_CACHE_VERSION` | Schema version for `moves.json` (currently 3). |
| `pkm_cache.py` | `LEARNSET_STALE_DAYS` | Age threshold for showing a staleness note (30). |
| `pkm_cache.py` | `_BASE`, `_POKEMON_DIR`, etc. | Directory paths for cache files (derived at runtime). |
| `pkm_pokeapi.py` | `_TYPE_NAMES` | Maps PokeAPI type slugs to display names (e.g., `"normal"` → `"Normal"`). |
| `pkm_pokeapi.py` | `_CATEGORY_NAMES` | Maps PokeAPI damage‑class slugs to display names. |
| `pkm_pokeapi.py` | `_SPECIAL_TYPES_GEN1_3` | Set of type names that were Special in Generations 1–3. |
| `pkm_pokeapi.py` | `_LEARN_METHODS_KEPT` | Set of learn method slugs that we display (level‑up, machine, tutor, egg). |

### 12.8 User interface layout

| File | Constant | Purpose |
|------|----------|---------|
| `pokemain.py` | `W` | Inner width of the main menu box (52). |
| `pokemain.py` | `_MENU_CHOICES` | Frozenset of all valid menu keys (used for documentation). |
| `pokemain.py` | `PKM_FEATURES` | Registry of single‑Pokemon features (label, module, entry, flags). |
| `pokemain.py` | `_CACHE_SEP_WIDTH` | Separator width for `--cache-info` display (46). |
| `feat_movepool.py` | `_COL_LABEL`, `_COL_NAME`, `_COL_TYPE`, `_COL_CAT`, `_COL_PWR`, `_COL_ACC`, `_COL_PP`, `_SEP_WIDTH` | Column widths for the move list. |
| `feat_movepool.py` | `_CAT_MAP` | Shortcut mapping for category input (e.g., `"p"` → `"Physical"`). |
| `feat_move_lookup.py` | (No dedicated constants; uses inline formatting) | – |
| `feat_evolution.py` | `_SEP_WIDTH` | Separator width for evolution chain display (46). |
| `feat_egg_group.py` | `_W`, `_COLS`, `_COL_WIDTH` | Layout for egg group roster grid. |
| `feat_ability_browser.py` | `_C_NAME`, `_C_GEN`, `_C_EFFECT`, `_GAP` | Column widths for ability browser. |

### 12.9 Duplicated constants (to be unified)

Several constants are defined in multiple files and should eventually be moved to a central location if a database migration is planned:

| Constant | Files | Notes |
|----------|-------|-------|
| `_GEN_RANGES` (dex ID → generation) | `feat_type_browser.py`, `feat_team_builder.py`, `feat_evolution.py` | Identical mapping; used for different purposes. |
| `_BAR_MAX`, `_BAR_WIDTH` | `feat_stat_compare.py`, `feat_quick_view.py` | Used for stat bars in different screens. |
| `_STAT_KEYS` / `_STAT_LABELS` | `feat_stat_compare.py`, `feat_quick_view.py` | Similar lists of stat keys/labels. |
| `W` (menu width) | `pokemain.py`, `feat_moveset.py` | Both use the same width value. |

These duplications are harmless but should be addressed if the data is moved to a database, at which point a single source of truth can be created.

---

This inventory will be updated as new static data is added to the codebase. It serves as a roadmap for future migrations and helps ensure all hard‑coded data is accounted for when changing data storage.