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
  menu_builder.py           Builds context and menu lines from current state
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

  # UI abstraction layer
  ui_base.py                Abstract base class for all UI implementations
  ui_cli.py                 CLI implementation (prints to stdout, reads from stdin)
  ui_tui.py                 TUI implementation using textual (split pane, modals, progress bar)
  ui_dummy.py               Dummy UI for standalone feature execution (uses builtins)
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
│  │  │   ui_cli.py  │          │     ui_tui.py      │      ui_dummy.py    │  │
│  │  │   (CLI)      │          │     (TUI)          │    (for standalone) │  │
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

Modules are grouped by layer. All live in a single flat folder.

### 7.1 Entry point and UI

| Module | Public API | Role / Purpose |
|--------|------------|----------------|
| `pokemain.py` | `main()` | Entry point; handles flags, selects UI, launches main loop. |
| `ui_base.py` | `UI` (abstract class) | Defines the interface for all user interaction. |
| `ui_cli.py` | `CLI` (implements `UI`) | CLI implementation using standard `print`/`input`. |
| `ui_tui.py` | `TUI` (implements `UI`) | TUI implementation using `textual`. |
| `ui_dummy.py` | `DummyUI` (implements `UI`) | Dummy UI for standalone runs; uses `print`/`input` and delegates interactive functions to `pkm_session`. |
| `menu_builder.py` | `build_context_lines()`, `build_menu_lines()` | Builds the context and menu lines shown in both UIs. |

### 7.2 Context and cache (infrastructure)

| Module | Public API | Role / Purpose |
|--------|------------|----------------|
| `pkm_session.py` | `select_game()`, `select_pokemon()`, `make_game_ctx()`, `refresh_pokemon()` | Interactive context selection and building of `game_ctx`/`pkm_ctx`. |
| `pkm_cache.py` | `get_move()`, `upsert_move()`, `get_pokemon()`, `get_learnset()`, `get_type_roster()`, `get_natures()`, `get_abilities_index()`, `get_ability()`, `get_index()`, `check_integrity()`, … | Single gateway to all cached data. Now backed by SQLite. |
| `pkm_sqlite.py` | `get_connection()`, `get_pokemon()`, `save_pokemon()`, `get_learnset()`, `save_learnset()`, … | Low‑level SQLite database layer. Used only by `pkm_cache.py`. |
| `pkm_pokeapi.py` | `fetch_pokemon()`, `fetch_move()`, `fetch_learnset()`, `fetch_type_roster()`, `fetch_natures()`, `fetch_abilities_index()`, `fetch_machines()`, … | PokeAPI adapter; translates raw API responses to cache schema. Called by `pkm_cache.py`. |
| `pkm_sync.py` | `sync_all()` | One‑time full data import from PokeAPI to SQLite. |
| `matchup_calculator.py` | `get_multiplier()`, `compute_defense()`, `print_results()`, `CHARTS` | Pure type‑chart library. No project imports. |
| `run_tests.py` | `main()` | Test runner that executes `--autotest` on all modules. |

### 7.3 Feature modules (thin UI wrappers)

| File | Entry point(s) | Role / Purpose |
|------|----------------|----------------|
| `feat_quick_view.py` | `run(pkm_ctx, game_ctx, ui)` | Quick view (option 1): stats, abilities, egg groups, type chart, evolution chain. |
| `feat_move_lookup.py` | `run(game_ctx, ui)` | Move lookup by name (key M). |
| `feat_movepool.py` | `run(pkm_ctx, game_ctx, constraints, ui)` | Learnable move list (option 2) with filter. |
| `feat_moveset.py` | `run_scored_pool(pkm_ctx, game_ctx, ui)`, `run(pkm_ctx, game_ctx, constraints, ui)` | Scored pool (option 3) and moveset recommendation (option 4). |
| `feat_moveset_data.py` | `build_candidate_pool(pkm_ctx, game_ctx, ui)` | I/O for moveset recommendation: fetches learnset and move details. |
| `feat_type_browser.py` | `run(game_ctx, ui)` | Browse Pokémon by type (key B). |
| `feat_nature_browser.py` | `run(game_ctx, pkm_ctx, ui)` | Nature & EV build advisor (key N). |
| `feat_ability_browser.py` | `run(game_ctx, pkm_ctx, ui)` | Ability browser with drill‑in (key A). |
| `feat_team_loader.py` | `run(ui, game_ctx, team_ctx)` | Team management (key T). |
| `feat_team_analysis.py` | `run(team_ctx, game_ctx, ui)` | Team defensive vulnerability analysis (key V). |
| `feat_team_offense.py` | `run(team_ctx, game_ctx, pool_cache, ui)` | Team offensive coverage (key O). |
| `feat_team_moveset.py` | `run(team_ctx, game_ctx, pool_cache, ui)` | Team moveset synergy (key S). |
| `feat_egg_group.py` | `run(pkm_ctx, ui)` | Egg group browser (key E). |
| `feat_learnset_compare.py` | `run(pkm_ctx, game_ctx, ui)` | Compare learnsets and stats of two Pokémon (key L). |
| `feat_team_builder.py` | `run(team_ctx, game_ctx, ui)` – slot suggestion (H); `run_joint_team(team_ctx, game_ctx, ui)` – full team GA (J) | Team builder — suggests next slot or full 6‑member team via genetic algorithm. |
| `feat_opponent.py` | `run(team_ctx, game_ctx, ui)` | Team vs in‑game opponent (key X). |

All feature modules receive a `ui` parameter and use it for all I/O.  
They import core modules for pure logic and use `pkm_cache` for data access.

### 7.4 Core library modules (pure logic, no I/O)

| Module | Public API | Purpose |
|--------|------------|---------|
| `core_stat.py` | `stat_bar()`, `total_stats()`, `infer_role()`, `infer_speed_tier()`, `compare_stats()` | Stat calculations. |
| `core_egg.py` | `egg_group_name()`, `format_egg_groups()` | Egg group display formatting. |
| `core_evolution.py` | `parse_trigger()`, `flatten_chain()`, `filter_paths_for_game()`, `trigger_is_pure_level_up()`, `is_pure_level_up_chain()` | Evolution chain parsing and filtering. |
| `core_move.py` | `score_move()`, `rank_status_moves()`, `select_combo()`, `combo_score()`, `score_learnset()`, plus static tables (`TWO_TURN_MOVES`, `STATUS_MOVE_TIERS`, …) | Move scoring and combo selection. |
| `core_team.py` | `build_team_defense()`, `build_unified_rows()`, `gap_label()`, `build_weakness_pairs()`, `team_offensive_gaps()`, `team_defensive_gaps()`, `score_candidate()`, `rank_candidates()`, `precompute_pokemon_data()`, `team_fitness()`, `create_individual()`, `crossover()`, `mutate()`, `tournament_selection()`, `run_ga()` | Team analysis, builder logic, and genetic algorithm for joint optimisation. |
| `core_opponent.py` | `analyze_matchup()`, `uncovered_threats()`, `recommended_leads()` | Opponent analysis (trainer battles). |

These modules contain no print statements, no input calls, and no network/cache I/O.  
They operate only on plain data structures passed as arguments.  
Each has a `_run_tests()` function for offline testing via `--autotest`.


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

The toolkit separates user interface concerns from application logic using an abstract `UI` class (`ui_base.py`). All direct `print()` and `input()` calls have been replaced with methods on a `UI` instance.

### 10.1 UI interface (ui_base.py)

| Method | Purpose |
|--------|---------|
| `print_header()` | Prints the application banner. |
| `print_menu(lines)` | Prints a boxed menu. |
| `print_output(text, end)` | General‑purpose output. |
| `print_progress(text, end, flush)` | For progress counters (e.g., `X/Y` patterns). |
| `input_prompt(prompt) -> str` | User input. |
| `confirm(prompt) -> bool` | Yes/no question. |
| `select_from_list(prompt, options, allow_none) -> str | None` | Numbered list selection. |
| `select_pokemon(game_ctx) -> dict | None` | Interactive Pokemon selection. |
| `select_game(pkm_ctx) -> dict | None` | Interactive game selection. |
| `select_form(forms) -> tuple` | Choose a Pokemon form from a list. |
| `print_session_header(pkm_ctx, game_ctx, constraints)` | Prints the session context header. |
| `show_error(message) -> None` | Displays an error message (modal in TUI, simple print in CLI). |
| `run()` | Starts the UI main loop. |

### 10.2 Implementations

| Module | Class | Description |
|--------|-------|-------------|
| `ui_cli.py` | `CLI` | Standard terminal I/O (`print`, `input`). |
| `ui_tui.py` | `TUI` | Terminal UI using `textual` with split‑pane layout, modal dialogs, and persistent input bar. |

The main menu loop and key dispatch reside in the UI implementation. The `UI` instance is passed to all feature functions (`feat_*.py`), which use it exclusively for user interaction.

### 10.3 Feature integration

Every feature module accepts a `ui` parameter (default `None` creates a dummy UI for standalone runs). All feature output and prompts go through `ui` methods, never directly to `print` or `input`. This ensures the same code works with both CLI and TUI.
For standalone execution (e.g., when a feature module is run directly), a `DummyUI` implementation (in `ui_dummy.py`) is used; it prints to stdout and reads from stdin, mimicking the CLI behaviour. This keeps the feature modules independent of the main UI and simplifies testing.

The `menu_builder.py` module generates context and menu lines used by both UI implementations, keeping display logic centralised.


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

The toolkit contains many hard‑coded constants 
(type charts, game mappings, scoring weights, column widths, etc.).
 These are defined in the modules where they are used, typically at the top of the file.
 For a complete list, refer to the source files directly;
 the architecture document does not attempt to enumerate them to avoid duplication and staleness.