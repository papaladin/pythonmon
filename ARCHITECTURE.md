# ARCHITECTURE.md
# System design, module roles, data structures, and interface contracts

---

## 1. High-level structure

```
pokemon-toolkit/
  pokemain.py               Entry point and menu loop
  pkm_session.py            Game + Pokemon context selection
  pkm_cache.py              All cache reads and writes (single gateway)
  pkm_pokeapi.py            PokeAPI adapter (fetch + translate raw data)
  matchup_calculator.py     Type chart data + multiplier logic (pure library)
  feat_type_matchup.py      Feature: quick view (stats / abilities / type chart)
  feat_move_lookup.py       Feature: move lookup by name
  feat_movepool.py          Feature: learnable move list with learn conditions
  feat_moveset.py           Feature: scored pool + moveset recommendation UI
  feat_moveset_data.py      Scoring engine (pure logic, no I/O)
  feat_type_browser.py      Feature: browse Pokemon by type
  feat_nature_browser.py    Feature: nature table + stat recommender
  feat_ability_browser.py   Feature: ability browser + Pokemon roster drill-in
  feat_team_loader.py       Feature: team context management (add/remove/view)
  feat_team_analysis.py     Feature: team defensive vulnerability table
  feat_team_offense.py      Feature: team offensive type coverage (key O)
  feat_team_moveset.py      Feature: team moveset synergy (key S)
  run_tests.py              Test runner (calls --autotest on each module)
  cache/                    Local JSON cache (see section 4)
```

All files live in a **single flat folder**. No package structure, no `__init__.py`.
All cross-module imports use plain `import <module>` (no relative imports).

---

## 2. Layer model

```
┌──────────────────────────────────────────────────────────┐
│  pokemain.py  (entry point, menu loop, context wiring)   │
├──────────┬───────────────────────────────────────────────┤
│ feat_*.py│  Display features (one screen each)           │
├──────────┴──────────────┬────────────────────────────────┤
│  pkm_session.py         │  matchup_calculator.py         │
│  (context selection)    │  (type chart library)          │
├─────────────────────────┴────────────────────────────────┤
│  pkm_cache.py  (all cache reads and writes)              │
├──────────────────────────────────────────────────────────┤
│  pkm_pokeapi.py  (network calls, data translation)       │
└──────────────────────────────────────────────────────────┘
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

### game_ctx

```python
{
    "game"     : str,   # Display name  e.g. "Scarlet / Violet"
    "era_key"  : str,   # "era1" | "era2" | "era3"
    "game_gen" : int,   # Generation number 1–9
    "game_slug": str,   # PokeAPI slug  e.g. "scarlet-violet"
}
```

### pkm_ctx

```python
{
    "pokemon"      : str,        # Species slug / search key  e.g. "sandslash"
    "variety_slug" : str,        # PokeAPI variety slug  e.g. "sandslash-alola"
    "form_name"    : str,        # Display name  e.g. "Alolan Sandslash"
    "types"        : list[str],  # e.g. ["Ice", "Steel"]
    "type1"        : str,        # e.g. "Ice"
    "type2"        : str,        # "None" (STRING, not Python None) if single-typed
    "species_gen"  : int,        # Generation the species was introduced
    "form_gen"     : int,        # Generation this form was introduced
    "base_stats"   : dict,       # keys: hp, attack, defense,
                                 #       special-attack, special-defense, speed
}
```

**Critical:** `type2` is always a string. It is `"None"` for single-typed Pokemon,
never Python `None`. Every function that tests for dual-type checks `type2 != "None"`.

### team_ctx

```python
team_ctx = [pkm_ctx_or_None, pkm_ctx_or_None, ..., pkm_ctx_or_None]  # always 6 elements
```

A list of exactly 6 slots. Empty slots are Python `None`. Team is session-only —
no persistence to disk.

---

## 4. Cache layout

```
cache/
  moves.json               All moves; each entry has versioned sub-entries (from_gen/to_gen)
  machines.json            TM/HM lookup: machine resource URL → display label ("TM38")
  pokemon_index.json       Compact index: species_slug → {forms: [{form_name, types}]}
  natures.json             All 25 natures with stat effects; fetched once
  abilities_index.json     All ~307 abilities: name, gen, short_effect; fetched once

  pokemon/
    charizard.json         Per-species: forms list, types, base_stats, variety_slug per form
    sandslash.json

  learnsets/
    charizard_scarlet-violet.json        Key = variety_slug + "_" + game_slug
    sandslash-alola_scarlet-violet.json  Regional forms get their own file

  types/
    fire.json              All Pokemon with Fire type (slug, slot, id, name)
    water.json             One file per type; fetched once per type, cached indefinitely

  abilities/
    blaze.json             Per-ability detail: full effect text + Pokemon roster list
```

**All cache access goes through `pkm_cache.py`.** No feature file opens cache files directly.

**Lazy loading:** data is fetched on first use and cached indefinitely.
**Atomic writes:** all writes go to `<path>.tmp` then `shutil.move()` to final path.
**Defensive reads:** every `get_*` wraps JSON parse in try/except; returns None on any error.
**Auto-upgrade:** pokemon files cached before variety_slug was added (§42) are silently
re-fetched on next access. Detection: missing `variety_slug` key in the cached dict.

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
`feat_type_matchup.py`, `feat_team_analysis.py`.

---

## 6. Move versioning schema

Each entry in `moves.json` has a list of versioned sub-entries:

```python
{
  "tackle": {
    "category": "physical",
    "versions": [
      {"from_gen": 1, "to_gen": 5, "power": 35, "accuracy": 95, "pp": 35},
      {"from_gen": 6, "to_gen": null, "power": 40, "accuracy": 100, "pp": 35}
    ]
  }
}
```

`to_gen: null` means "current generation". `from_gen` and `to_gen` are inclusive.
Resolution: find the entry where `from_gen <= game_gen <= to_gen`.

---

## 7. Module roles and public API

### pokemain.py
Entry point only. Contains the main menu loop, context variables, and key dispatch.
Has almost no logic of its own. Wires features together.

Key internal functions:
- `_print_menu(pkm_ctx, game_ctx, team_ctx)` — builds the visible menu
- `_print_context_lines(pkm_ctx, game_ctx, team_ctx)` — header block

### pkm_session.py
Handles all interactive context selection.

- `select_game(preselect=None) → game_ctx | None`
- `select_pokemon(game_ctx=None, preselect=None) → pkm_ctx | None`
- `build_session(game_ctx=None) → (pkm_ctx, game_ctx) | (None, None)`

Called by feature standalone `main()` functions and by pokemain.

### pkm_cache.py
Single gateway to all cached data. Feature files never open cache files directly.

Key functions:
- `get_move(name) → dict | None`
- `get_pokemon(slug) → dict | None`
- `get_learnset(variety_slug, game_slug) → dict | None`
- `get_type_roster(type_name) → list | None`
- `get_natures() → list | None`
- `get_ability(slug) → dict | None`
- `get_abilities_index() → list | None`
- `save_*` counterparts for each

### pkm_pokeapi.py
Fetches data from PokeAPI and translates it to the cache schema.
Never called directly by feature files — always called by pkm_cache.py or pkm_session.py.

- `fetch_pokemon(slug) → dict`
- `fetch_learnset(variety_slug, game_slug) → dict`
- `fetch_move(name) → dict`
- etc.

### matchup_calculator.py
Pure type chart library. No project imports. See section 5.

### feat_moveset_data.py
Pure scoring logic. No print statements, no input() calls.

- `score_move(move, pkm_ctx, game_ctx) → float`
- `build_candidate_pool(pkm_ctx, game_ctx) → list`
- `select_combo(pool, mode, constraints) → list`
- `rank_status_moves(pool) → list`

### feat_team_loader.py
Team context management.

- `new_team() → team_ctx`
- `team_size(team_ctx) → int`
- `team_slots(team_ctx) → [(idx, pkm_ctx), ...]`  Filled slots only
- `add_to_team(team_ctx, pkm_ctx) → (new_team, slot_idx)` raises `TeamFullError`
- `remove_from_team(team_ctx, idx) → new_team`
- `clear_team(team_ctx) → new_team`
- `team_summary_line(team_ctx) → str`
- `run(game_ctx, team_ctx) → team_ctx`  Interactive sub-menu; returns updated team

### feat_team_analysis.py
Team defensive analysis.

- `build_team_defense(team_ctx, era_key) → {atk_type: [{form_name, multiplier}, ...]}`
- `build_unified_rows(team_defense, era_key) → [row, ...]`  One row per era type
- `gap_label(weak_count, cover_count) → str`  "" | "!! CRITICAL" | "!  MAJOR" | ".  MINOR"
- `display_team_analysis(team_ctx, game_ctx)`  Full table to stdout
- `run(team_ctx, game_ctx)`  Called from pokemain; calls display + waits for Enter

---

## 8. Interface contracts

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

## 9. Design constraints (non-negotiable)

- **Single flat folder.** All .py files and cache/ in the same directory.
- **No pip dependencies beyond `requests`.** stdlib only for everything else.
- **No async code.** All operations are synchronous.
- **No database.** Cache is JSON files only.
- **Python 3.10+ required.** This is the minimum supported version; do not use syntax or stdlib features introduced after 3.10.
- **Atomic writes.** All cache writes: write to .tmp, then shutil.move().
- **Defensive reads.** All cache reads return None on any error, never raise.