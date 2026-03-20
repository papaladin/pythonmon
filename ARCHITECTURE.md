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
  feat_quick_view.py        Feature: quick view (stats / abilities / egg groups / type chart)
  feat_move_lookup.py       Feature: move lookup by name
  feat_movepool.py          Feature: learnable move list with learn conditions
  feat_moveset.py           Feature: scored pool + moveset recommendation UI
  feat_moveset_data.py      Scoring engine (pure logic, no I/O)
  feat_type_browser.py      Feature: browse Pokemon by type
  feat_nature_browser.py    Feature: nature & EV build advisor + nature browser (key N)
  feat_ability_browser.py   Feature: ability browser + Pokemon roster drill-in
  feat_team_loader.py       Feature: team context management (add/remove/view)
  feat_team_analysis.py     Feature: team defensive vulnerability table
  feat_team_offense.py      Feature: team offensive type coverage (key O)
  feat_team_moveset.py      Feature: team moveset synergy (key S)
  feat_stat_compare.py      Feature: side-by-side base stat comparison (key C)
  feat_egg_group.py         Feature: egg group browser + breeding partners (key E)
  feat_evolution.py         Feature: evolution chain display (embedded in option 1)
  feat_learnset_compare.py  Feature: learnset comparison between two Pokémon (key L)
  feat_team_builder.py      Feature: team slot suggestion — gap analysis + ranked candidates (key H)
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

  egg_groups/
    monster.json           Per-group roster: list of {slug, name} dicts, sorted by name
    dragon.json            One file per group; fetched once, cached indefinitely

  evolution/
    1.json                 Per-chain flattened paths: list[list[{slug, trigger}]]
    67.json                One file per chain ID; fetched once, cached indefinitely
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
`feat_quick_view.py`, `feat_team_analysis.py`, `feat_team_offense.py`,
`feat_team_moveset.py`, `feat_moveset_data.py`.

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

### pkm_session.py
Handles all interactive context selection.

- `select_game(preselect=None) → game_ctx | None`
- `select_pokemon(game_ctx=None, preselect=None) → pkm_ctx | None`
- `build_session(game_ctx=None) → (pkm_ctx, game_ctx) | (None, None)`

Called by feature standalone `main()` functions and by pokemain.

### pkm_cache.py
Single gateway to all cached data. Feature files never open cache files directly.

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

### feat_team_offense.py
Team offensive coverage table (key O).

- `build_team_offense(team_ctx, era_key) → dict`  Per-type hitter list
- `build_offense_rows(team_offense, era_key) → list`  One row per era type, sorted
- `coverage_gaps(rows) → list`  Types with zero SE coverage across the team
- `display_team_offense(team_ctx, game_ctx, pool_cache=None)`  Full table to stdout (fetches learnsets)
- `run(team_ctx, game_ctx, pool_cache=None)`  Called from pokemain; key O

### feat_team_moveset.py
Team moveset synergy (key S).

- `_weakness_types(pkm_ctx, era_key) → list[str]`  Types that hit this Pokemon SE
- `_se_types(combo, era_key) → list[str]`  Types hit SE by at least one combo move
- `_format_weak_line(weakness_types) → str`  Weak line string for display
- `_format_move_pair(left, right) → str`  Side-by-side move pair, left col 22 chars
- `_format_se_line(se_types, era_key) → str`  SE count / total string
- `build_offensive_coverage(member_results, era_key) → dict`
  Aggregates `se_types` from all member result dicts. Returns `covered`,
  `gaps`, `overlap` (≥3 members, sorted desc), `counts`, `total_types`.
  Pure — does not recompute movesets or call the scoring engine.
- `recommend_team_movesets(team_ctx, game_ctx, mode, pool_cache=None) → list[dict]`
  One member result dict per filled slot. Calls `build_candidate_pool` +
  `select_combo` from `feat_moveset_data`; no scoring logic duplicated.
  Graceful degradation: empty pool → shaped result with empty lists.
- `display_team_movesets(results, game_ctx, mode)`  Full screen to stdout;
  member blocks + coverage summary
- `run(team_ctx, game_ctx, pool_cache=None)`  Called from pokemain; key S

Member result dict keys: `form_name`, `types` (list[str]), `moves` (list[dict]),
`weakness_types` (list[str]), `se_types` (list[str]).

Depends on: `feat_team_loader` (team_slots, team_size), `feat_moveset_data`
(build_candidate_pool, select_combo), `matchup_calculator` (compute_defense,
get_multiplier, CHARTS).

---

### feat_stat_compare.py
Side-by-side base stat comparison (key C). Also the canonical home for
pure stat-analysis helpers used by other feature modules.

- `compare_stats(stats_a, stats_b) → list[dict]`  Per-stat winner annotation;
  each dict: `key`, `label`, `val_a`, `val_b`, `winner` ("a"|"b"|"tie")
- `total_stats(base_stats) → int`  Sum of all 6 base stats
- `infer_role(base_stats) → str`  "physical" | "special" | "mixed"
  (Atk vs SpA, 1.2× threshold)
- `infer_speed_tier(base_stats) → str`  "fast" | "mid" | "slow"
  (Speed ≥90 / ≥70 / <70)
- `display_comparison(pkm_a, pkm_b, game_ctx)`  Side-by-side bar chart with ★/•
- `run(pkm_ctx, game_ctx)`  Called from pokemain; key C; prompts for second Pokemon

Imported by: `feat_nature_browser` (for `infer_role`, `infer_speed_tier`),
`feat_quick_view` (deferred import of same).

---

### feat_egg_group.py
Egg group browser and breeding partner finder (key E). Also provides inline
egg group display for option 1 via `format_egg_groups`.

- `egg_group_name(slug) → str`  PokeAPI slug → in-game display name
  (covers all 15 groups; key mappings: `"ground"`→Field, `"plant"`→Grass)
- `format_egg_groups(egg_groups) → str`  e.g. `["monster","dragon"]` → `"Monster  /  Dragon"`
- `get_or_fetch_roster(slug) → list | None`  Cache-aware; fetches from PokeAPI on miss
- `display_egg_group_browser(pkm_ctx)`  Full browser display; marks current Pokemon with ★
- `run(pkm_ctx)`  Called from pokemain; key E; no game context needed

---

### feat_evolution.py
Evolution chain display, embedded at the bottom of option 1 (feat_quick_view).
No standalone menu key. Chain is filtered by `game_gen` so future-gen evolutions
are not shown for older games (e.g. Eevee in FireRed shows only Gen 1–2 branches).

**Public API:**
- `get_or_fetch_chain(pkm_ctx) → list[list[dict]] | None`  Cache-aware; returns
  `None` for `chain_id=None` (event Pokemon)
- `display_evolution_block(pkm_ctx, paths, game_gen=None)`  Compact inline display;
  fetches types for all stages; ★ on `pkm_ctx["pokemon"]`; filters by game_gen
- `filter_paths_for_game(paths, game_gen) → list[list[dict]]`  Pure — truncates
  branches whose target species was introduced after `game_gen`

**Internal pure helpers (testable offline):**
- `_parse_trigger(details) → str`  PokeAPI evolution_details → human string.
  Key mappings: `min_happiness + time_of_day` → "High Friendship (day/night)";
  trade + `held_item` → "Trade holding X" (PokeAPI field is `held_item`, not `item`)
- `_flatten_chain(node, max_depth=20) → list[list[dict]]`  Recursive tree → list
  of linear paths; each stage: `{slug, trigger}`
- `_get_species_gen(slug) → int | None`  Reads from pokemon cache
- `_get_types_for_slug(slug) → list[str]`  Cache hit instant; API call on miss

**pkm_cache additions (§90B):**
- `get_evolution_chain(chain_id) → list | None`
- `save_evolution_chain(chain_id, paths) → None`
- `invalidate_evolution_chain(chain_id) → None`

**pkm_pokeapi additions (§90B):**
- `fetch_evolution_chain(chain_id) → dict`  Returns the `chain` node from
  `GET evolution-chain/{id}` — the root of the recursive tree

---

### feat_learnset_compare.py
Learnset comparison between two Pokémon in the same game (key L).

- `_flat_moves(learnset, form_name) → set[str]`  Extract flat set of move names
  from one form's learnset across all learn methods
- `compare_learnsets(learnset_a, form_a, learnset_b, form_b) → dict`  Pure;
  returns `{only_a, only_b, shared}` — three sets of move name strings
- `build_rows(move_set, game_ctx) → list[dict]`  Resolve move details for display;
  each row: `{name, type, category, power, accuracy, pp}`
- `display_comparison(pkm_a, pkm_b, game_ctx, only_a, only_b, shared)`  Three-
  section table to stdout (Only A / Only B / Shared)
- `run(pkm_ctx, game_ctx)`  Called from pokemain; key L; prompts for second Pokémon

---

### feat_team_builder.py
Team slot suggestion — gap analysis + scored candidate ranking (key H).
Suggests the best Pokémon to add to the next open team slot based on current
offensive and critical defensive gaps. No API calls at runtime (roster-only
cache reads); fetches missing type rosters on demand before pool build.

**Pure logic (no I/O):**
- `team_offensive_gaps(team_ctx, era_key) → list[str]`  Era types no member hits SE
- `team_defensive_gaps(team_ctx, era_key) → list[str]`  Critical gaps (≥2 weak, 0 cover)
- `candidate_passes_filter(candidate_types, off_gaps, def_gaps, era_key) → bool`
- `patchability_score(remaining_off_gaps, era_key) → float`  Ease of patching gaps
- `score_candidate(candidate_types, team_ctx, era_key, off_gaps, def_gaps,
  slots_remaining, base_stats=None) → float`  Composite intrinsic + lookahead score
- `rank_candidates(candidates, team_ctx, era_key, off_gaps, def_gaps,
  slots_remaining, top_n=6) → list[dict]`

**Pool building (cache reads):**
- `collect_relevant_types(off_gaps, def_gaps, era_key) → set[str]`
- `fetch_needed_rosters(relevant_types, progress_cb=None) → int`
- `build_suggestion_pool(team_ctx, game_ctx, off_gaps, def_gaps) → dict`
  Returns `{candidates, missing_rosters, skipped_forms, skipped_gen, skipped_team}`

**Display:**
- `_format_dots(rating) → str`  1–5 → "●●●●●" etc.
- `_dot_rating(score, all_scores) → int`  Percentile within result set
- `_format_lookahead(remaining_off_gaps, era_key) → str`
- `_print_suggestion(rank, result, era_key, all_scores)`  One suggestion card
- `display_team_builder(team_ctx, game_ctx, results, off_gaps, def_gaps,
  missing_rosters=None)`  Full screen with header, gap summary, suggestion cards

**Entry point:**
- `run(team_ctx, game_ctx)`  Called from pokemain; key H

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