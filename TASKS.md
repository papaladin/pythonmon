# TASKS.md
# Current work — V2 Package 1: Core Library / Presentation Separation

**Status:** 🔄 PLANNED  
**Complexity:** 🟡 Medium  
**Goal:** Extract all pure logic (no I/O, no print statements) from the existing feature modules into a set of core modules. The core modules will be independently testable and reusable by alternative frontends (e.g., a TUI). After this package, the existing CLI will remain unchanged, but its internal structure will be cleanly separated.

---

## Design decisions

1. **Core modules will live in the same folder with a `core_` prefix** (e.g., `core_move.py`). This avoids import path changes and makes the separation visible.
2. **The existing `feat_*.py` files will become thin UI wrappers** that fetch data via `pkm_cache`, call core functions, and display results. Display functions will stay in the `feat_*.py` files.
3. **All pure logic will be moved to core modules**. Each core module will have its own `_run_tests()` for offline testing.
4. **The data access layer (`pkm_cache.py`) remains the single gateway to cached data**. Core modules will **not** import `pkm_cache`; they will only operate on plain data structures passed from the UI layer.
5. **After each step, run `python run_tests.py` to ensure no regression.** New tests for core modules will be added to `run_tests.py`.

---

## Step 1: Core stat functions

**Goal:** Extract stat‑related pure functions from `feat_stat_compare.py` and `feat_quick_view.py`.

### 1.1 Create `core_stat.py`
- Move pure functions:
  - `compare_stats(stats_a, stats_b) → list[dict]`
  - `total_stats(base_stats) → int`
  - `infer_role(base_stats) → str`
  - `infer_speed_tier(base_stats) → str`
  - `_stat_bar(value) → str` (now public as `stat_bar(value)`)
- Add docstrings and a `_run_tests()` function with tests for each function (reuse existing tests from `feat_stat_compare.py` and `feat_quick_view.py`).
- Update `feat_stat_compare.py` to import from `core_stat` and remove the original definitions.
- Update `feat_quick_view.py` to import `stat_bar`, `infer_role`, `infer_speed_tier` from `core_stat`.
- Update `feat_nature_browser.py` to import `infer_role`, `infer_speed_tier` from `core_stat` (already done in §83, but ensure import is from core now).
- Add `core_stat.py` to `run_tests.py` SUITES (offline suite, no cache needed).

**Verify:** `python run_tests.py` passes; all stat‑related features (key C, option 1, nature browser) work as before.

---

## Step 2: Core egg group functions

**Goal:** Extract pure egg‑group functions from `feat_egg_group.py`.

### 2.1 Create `core_egg.py`
- Move pure functions:
  - `egg_group_name(slug) → str`
  - `format_egg_groups(egg_groups) → str`
- Keep `_EGG_GROUP_NAMES` mapping as module‑level constant.
- Add `_run_tests()` with tests for both functions.
- Update `feat_egg_group.py` to import from `core_egg` and remove the original definitions.
- Update `feat_quick_view.py` to import `format_egg_groups` from `core_egg`.
- Add `core_egg.py` to `run_tests.py` SUITES.

**Verify:** `python run_tests.py` passes; egg group display in option 1 and key E unchanged.

---

## Step 3: Core evolution functions

**Goal:** Extract pure evolution‑chain logic from `feat_evolution.py`.

### 3.1 Create `core_evolution.py`
- Move pure functions:
  - `_parse_trigger(details) → str` (rename to `parse_trigger` in core)
  - `_flatten_chain(node, max_depth=20) → list[list[dict]]` (rename to `flatten_chain`)
- Create a new pure version of `filter_paths_for_game` that takes a `species_gen_map` dict (slug → generation) instead of using `_get_species_gen`:
  ```python
  def filter_paths_for_game(paths, game_gen, species_gen_map) -> list 
  
It will use the provided map to filter stages.
- Add `_run_tests()` for these functions (reuse existing tests from `feat_evolution.py`).
- Update `feat_evolution.py` to:
  - Import core functions.
  - In `get_or_fetch_chain`, keep the cache fetch (unchanged).
  - In `display_evolution_block`, pre‑fetch the species generations for all slugs in the paths and build a `species_gen_map` before calling `filter_paths_for_game`.
- Remove the original pure functions from `feat_evolution.py`.
- Add `core_evolution.py` to `run_tests.py` SUITES.

**Verify:** `python run_tests.py` passes; evolution chain display (option 1) works correctly for all games.

---

## Step 4: Core move scoring functions

**Goal:** Extract pure move‑scoring and combo‑selection logic from `feat_moveset_data.py`.

### 4.1 Create `core_move.py`
- Move pure functions:
  - `score_move(move_entry, pkm_ctx, game_ctx) → float`
  - `rank_status_moves(status_pool, top_n=3) → list`
  - `_uncovered_weaknesses(combo, weakness_types) → int` (rename to `uncovered_weaknesses`)
  - `_combo_score(combo, weakness_types, era_key, mode) → float` (rename to `combo_score`)
  - `_build_counter_pool(eligible, weakness_types) → list` (rename to `build_counter_pool`)
  - `_build_coverage_pool(eligible) → list` (rename to `build_coverage_pool`)
  - `select_combo(damage_pool, mode, weakness_types, era_key, locked=None) → list`
- Also move `_score_learnset` as a pure function that takes:
  - `form_data` (learnset dict with move names)
  - `move_entries_map` (dict mapping move name → resolved versioned entry dict)
  - `pkm_ctx`, `game_ctx`, `weakness_types`, `era_key`
  Returns `(damage_pool, status_pool)`.
- Add `_run_tests()` for all functions (reuse existing tests).
- Update `feat_moveset_data.py` to import core functions; keep data‑fetching logic.
- Update `feat_moveset.py` and `feat_team_moveset.py` to continue using the same public API.
- Add `core_move.py` to `run_tests.py` SUITES.

**Verify:** `python run_tests.py` passes; moveset recommendation (options 3 and 4) and team moveset synergy (key S) unchanged.

---

## Step 5: Core team analysis functions

**Goal:** Extract pure team‑related logic from multiple files into `core_team.py`.

### 5.1 Create `core_team.py`
- Move pure functions:

  **From `feat_team_analysis.py`:**
  - `build_team_defense(team_ctx, era_key) → dict`
  - `build_unified_rows(team_defense, era_key) → list`
  - `gap_label(weak_count, cover_count) → str`
  - `build_weakness_pairs(team_ctx, era_key) → list`
  - `gap_pair_label(shared_count) → str`

  **From `feat_team_offense.py`:**
  - `_hitting_types(era_key, type1, type2, target) → list` (rename to `hitting_types`)
  - `build_team_offense(team_ctx, era_key) → dict`
  - `build_offense_rows(team_offense, era_key) → list`
  - `coverage_gaps(rows) → list`

  **From `feat_team_moveset.py`:**
  - `_weakness_types(pkm_ctx, era_key) → list` (rename to `weakness_types`)
  - `_se_types(combo, era_key) → list` (rename to `se_types`)
  - `build_offensive_coverage(member_results, era_key) → dict`
  - `_empty_member_result(form_name) → dict` (rename to `empty_member_result`)
  - `_format_weak_line(weakness_types) → str` (rename to `format_weak_line`)
  - `_format_move_pair(left, right) → str` (rename to `format_move_pair`)
  - `_format_se_line(se_types, era_key) → str` (rename to `format_se_line`)

  **From `feat_team_builder.py`:**
  - `team_offensive_gaps(team_ctx, era_key) → list`
  - `team_defensive_gaps(team_ctx, era_key) → list`
  - `candidate_passes_filter(candidate_types, off_gaps, def_gaps, era_key) → bool`
  - `patchability_score(remaining_off_gaps, era_key) → float`
  - `_shared_weakness_count(candidate_types, team_ctx, era_key) → int` (rename to `shared_weakness_count`)
  - `_new_weak_pairs(candidate_types, team_ctx, era_key) → list` (rename to `new_weak_pairs`)
  - `score_candidate(candidate_types, team_ctx, era_key, off_gaps, def_gaps, slots_remaining, base_stats=None) → float`
  - `rank_candidates(candidates, team_ctx, era_key, off_gaps, def_gaps, slots_remaining, top_n=6) → list`

- Add `_run_tests()` in `core_team.py` with tests for all functions.
- Update original files to import from `core_team` and remove definitions.
- Add `core_team.py` to `run_tests.py` SUITES.

**Verify:** `python run_tests.py` passes; all team features (V, O, S, H) work unchanged.

--- 

## Step 6: Core opponent analysis functions

**Goal:** Extract pure opponent‑analysis logic from `feat_opponent.py`.

### 6.1 Create `core_opponent.py`
- Move pure functions:
  - `analyze_matchup(team_ctx, opponent_team, era_key) → list` – where `opponent_team` is a list of dicts, each containing `name`, `types`, `level`, `move_types` (list of type strings). This makes it pure.
  - `uncovered_threats(matchup_results) → list`
  - `recommended_leads(matchup_results, team_ctx) → list`
- Add `_run_tests()` with tests (reuse from `feat_opponent.py`, adjusting to the new signature).
- Update `feat_opponent.py` to:
  - Keep data loading and trainer selection.
  - Resolve move types for each opponent Pokémon using `get_move_type` and build `opponent_team`.
  - Call `core_opponent.analyze_matchup` with resolved data.
  - Keep display functions in `feat_opponent.py`.
- Add `core_opponent.py` to `run_tests.py` SUITES.

**Verify:** `python run_tests.py` passes; opponent analysis (key X) unchanged.

--- 

## Step 7: Consolidate data access (optional)

**Goal:** Move remaining I/O‑intensive code into a dedicated module, leaving core modules pure.

**Decision:** Postpone to a later V2 package (e.g., SQLite migration). The `feat_*.py` files already act as thin UI layers after steps 1–6, so they are acceptable for now.

No implementation in this step.

---

## Step 8: Update `run_tests.py` and documentation

- Ensure all new core modules are added to the SUITES list in `run_tests.py`.
- Verify that all offline tests pass.
- Update `ARCHITECTURE.md`:
  - Add a new section describing core modules and their responsibilities.
  - Update file list and module descriptions.
- Update `README.md` if any user‑visible changes occurred (none expected, but verify).
- Update `HISTORY.md` with a new section (e.g., §109) describing the refactoring.

**Verify:** All tests pass; documentation is up to date.