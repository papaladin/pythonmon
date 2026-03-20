# HISTORY.md
# Development history — append-only session log

> This file records what was built, why, and what was discovered.
> Each section corresponds to one or more development sessions.
> Never edit past entries. Only append new ones.
> For current architecture, see ARCHITECTURE.md. For roadmap, see ROADMAP.md.

---

## §1–§11 — Web scraping phase (pokemondb.net + Bulbapedia)

Initial implementation using web scraping. Pokemon data from pokemondb.net,
move data and version history from Bulbapedia. Built a 3-pass pipeline:
Pass 1 = current move stats, Pass 2 = historical modifications, Pass 3 = Gen1-3
type-based category correction.

Key decisions:
- Per-Pokemon JSON files (not a single monolithic file) — isolation + performance
- `from_gen` / `to_gen` range schema for move versioning (rejected explicit gen list)
- Single flat folder, no package structure
- No external dependencies beyond stdlib

---

## §12–§13 — PokeAPI migration decision and `past_values` semantics

Investigated PokeAPI as a replacement for the Bulbapedia scraper.
Key finding: `past_values` in PokeAPI uses game-version timestamps, not generation numbers.
Mapping table built: version-group slug → generation integer.

Decision: migrate fully to PokeAPI. Web scraper files kept but marked obsolete.
Gen1-3 type-based category rule is NOT modelled by PokeAPI — must apply it in post-processing.

---

## §14 — Four-state menu UX redesign

**Why:** the old design forced re-entering the Pokemon name every time game changed.
Real usage pattern: pick a game for the session, swap Pokemon frequently.

New design: `game_ctx` and `pkm_ctx` are independent. Either can be None.
Chaining: when a feature needs a missing context, prompt for it inline and then run the feature.
State stored as top-level locals in `pokemain.py main()`, not in a nested dict.

Feature gate rules:
- Options 1–4: need both pkm_ctx AND game_ctx
- Move lookup (M): needs game_ctx only
- Type browser, nature browser, ability browser: need nothing
- Refresh data: needs pkm_ctx

---

## §15 — matchup_calculator.py architecture

Type chart data (ERA1/2/3) + multiplier logic isolated into a standalone library.
Three ERA keys: era1 (15 types, Gen 1), era2 (17 types, Gen 2–5), era3 (18 types, Gen 6+).

Layering decision: keep as a pure standalone library. No imports from this project.
`matchup_calculator.py` is imported by pkm_session, pokemain, feat_type_matchup, feat_team_analysis.
Merging into feat_type_matchup would create a layering violation.

---

## §16–§19 — Learnset fetch and PokeAPI migration complete

`fetch_learnset()` fetches per variety_slug × game_slug. One cache file per combination.
Known limitation at this stage: fetching base-form slug only (regional forms not yet separated).
`machines.json` built once on first learnset fetch, shared across all games.

---

## §20 — Post-migration decisions

Tutor location data abandoned: PokeAPI does not provide it reliably.
Move table warm-up split into two keys: T (move table) and W (TM/HM machines).

---

## §21–§36 — Moveset recommendation: design, scoring, and refinement

Scoring formula v1: base_power × stat_weight × stab_bonus × accuracy_factor.
Iterative refinements across many sessions:

- R1 (§22–§25): priority penalty added (negative priority degrades score)
- R2 (§26–§34): combo weight calibration; coverage bonus (marginal contribution model);
  redundancy penalty (−30 per duplicate move type)
- R3 (§38): recoil penalty + secondary effect bonus
- §36: COMBO_EXCLUDED list (16 moves never auto-recommended: self-KO, setup-dependent, etc.)
- §47: Counter mode coverage-first sort `(gap, -score)` — coverage completeness > raw score
- §48: Mode-specific pool strategies — counter: all covering moves (no cap); coverage: best-per-type (cap 18); STAB: cap 25
- §50: CONDITIONAL_PENALTY for situational moves; POWER_OVERRIDE for unscoreable moves;
  Fling / Natural Gift / Last Resort excluded as unscoreable

Key design principle: scoring optimises a single Pokemon's moveset in isolation.
Does not account for team composition or opponent AI.

---

## §37, §39 — Marginal coverage model + `save_learnset` upsert bugfix

§37: Coverage bonus changed from flat per-type to marginal: bonus only for types not already
covered by higher-ranked moves. Redundancy penalty raised from −20 to −30.

§39: Bug in `save_learnset()` — `_update_index()` was being called on every learnset save,
corrupting the Pokemon index. Fixed by removing the index update from that path.

---

## §40 — matchup_calculator.py standalone self-tests (79 tests)

Gap: no tests existed for the type chart. Added `_run_tests()` with 79 offline tests.
Covers all multiplier combinations across all 3 eras, edge cases (Ghost/Normal Gen1 immunity,
Fairy absent from era1/era2, Steel/Dark added in era2).

---

## §41 — Main menu restructure

Option 3 added: "Learnable move list (scored)" — same pool as option 2 but sorted by score.
`run_scored_pool()` added to `feat_moveset.py`.
PKM_FEATURES schema in pokemain updated.

---

## §42–§43 — Per-variety learnset cache (regional form fix)

**Problem:** Alolan Sandslash was showing Sandslash's (Kanto) learnset.
**Root cause:** cache key was `pokemon_game.json`, not form-aware.
**Fix (§42):** cache key changed to `variety_slug_game_slug.json`. Regional forms get
their own cache file with their correct learnset.
**Fix (§43):** auto-upgrade of old pokemon cache entries that are missing `variety_slug`.
Detection: missing key → silent re-fetch. Transparent to the user.

---

## §44 — Menu box overflow fix + type coverage display

Menu box width hardcoded at 44 chars was overflowing long game names. Fixed to dynamic width.
Added type coverage summary to moveset recommendation output: lists types the combo hits SE.

---

## §45–§46 — Self-test audit + consolidated test runner

§45: Audited all modules for test coverage. Added `--autotest` to feat files that lacked it.
§46: `run_tests.py` created — runs all suites, handles cache warm-up for cache-dependent tests,
supports `--offline` (skip cache tests) and `--quiet` (summary only).

---

## §47–§49 — Counter mode + pool strategies

§47: Counter mode sort changed to `(gap, -score)` — a move that covers more of the Pokemon's
weaknesses always ranks above a higher-scoring move that covers fewer.

§48: Mode-specific pool building. Counter: fetch all covering moves (no cap, sorted by gap then score).
Coverage: best move per target type, max 18 types. STAB: all STAB moves, cap 25.

---

## §50 — Conditional move handling + unscoreable exclusions

CONDITIONAL_PENALTY dict: moves that only work in specific conditions get a score penalty.
POWER_OVERRIDE dict: moves with non-standard power calculations get a manual power value.
Fling, Natural Gift, Last Resort: excluded from auto-recommendation as unscoreable.

---

## §51–§52 — Type browser

New file `feat_type_browser.py`. Enter one or two types; shows all matching Pokemon
with generation derivation (from PokeAPI dex ID ranges) and proper form display names.

§52: Form display names via `pokemon-form` API endpoint. Handles Mr. Mime, Nidoran♀,
Mega Charizard X, etc. `resolve_type_roster_names()` added to pkm_cache.py.

---

## §53 — Nature browser + recommender

New file `feat_nature_browser.py`. All 25 natures with stat effects.
Recommender: input role (physical/special/mixed) and speed tier → top 3 natures ranked
by `_role_score()` combining `_infer_role()` and `_infer_speed_tier()`.

---

## §54–§56 — Moveset UX improvements

§54: Weakness coverage annotation added: `✗ Electric (no move in pool)` for weaknesses
that genuinely cannot be covered by any learnable move.
§55: Short combo note shown when fewer than 4 move types are available (e.g. Zapdos in RBY).
§56: Moveset mode sub-menu removed — all three modes shown simultaneously in one output.

---

## §57 — Ability browser

New file `feat_ability_browser.py`. Browse all ~307 abilities; drill in to see full
effect text + complete Pokemon roster for each ability. `A` key in pokemain.
Ability browser also invoked from option 1 (quick view) for the current Pokemon's abilities.

---

## §58 — Quick view (option 1 expanded)

`feat_type_matchup.py` expanded into a full quick-view screen:
base stats bar chart + abilities with drill-in + type chart.
Previously option 1 showed only the type chart.

---

## §59 — Team context + menu overhaul (Step 1)

New file `feat_team_loader.py`. Team is session-only (no persistence) — a list of 6
slots, each `pkm_ctx | None`. Rationale: keep it simple; save/load complexity deferred.

Public API: `new_team`, `team_size`, `team_slots`, `add_to_team`, `remove_from_team`,
`clear_team`, `team_summary_line`, `run`.

pokemain changes:
- `team_ctx` added as third context, initialised to `new_team()` in `main()`
- `T` key → team management (old T = pre-load move table → renamed to `MOVE`)
- Menu header shows team summary: `Team (N/6): Slot1 / Slot2 / ...`

Bug found (§59 addendum): `pkm_cache.py` self-test missing path redirects for
`_MACHINES_FILE`, `_TYPES_DIR`, `_NATURES_FILE`, `_ABILITIES_FILE`, `_ABILITIES_DIR`.
Caused `FileNotFoundError` in clean environment. Fixed.

Tests: 28 offline. Full suite: 434 tests, 0 failures.

---

## §60 — Team defensive vulnerability analysis (Step 2)

New file `feat_team_analysis.py`.

Core function: `build_team_defense(team_ctx, era_key)` — for each attacking type in the
era, collects each team member's defensive multiplier using `calc.compute_defense()`.

Supporting functions: `weakness_summary`, `resistance_summary`, `critical_gaps`,
`build_unified_rows`.

Initial display: separate weakness table (bar chart) + resistance/immunity table.
`V` key in pokemain, shown only when team has ≥1 member and game is selected.

Bug found during testing: test fixtures assumed Pikachu and Snorlax were Rock-weak.
Neither is. Fixed by using Lapras (Water/Ice) and Butterfree (Bug/Flying) instead.

Tests: 36 offline. Full suite: 478 tests, 0 failures.

---

## §61 — Team analysis: unified type table + display overhaul

**Motivation:** two separate tables (weakness / resistance) made it hard to see the full
picture for a single type at a glance, and didn't show neutral types at all.

**New layout:** single unified table. One row per attacking type in the era. All types
always shown (including fully neutral ones).

Columns: Type | Weakness (count + names, ×4 suffix) | Resistance (count + names, ×0.25 suffix)
| Immunity (count + names) | Comments (gap label)

Gap rules:
- `!! CRITICAL` — 3+ weak, 0 resist+immune
- `!  MAJOR` — 3+ weak, ≤1 resist+immune
- `.  MINOR` — 2 weak, 0 resist+immune

Column header refinements (same session):
- "Wk / Who weak" → "Weakness"; "Rs / Who resists" → "Resistance"; "Im / Who immune" → "Immunity"
- "Ne" (neutral count) removed from Comments column entirely

Name abbreviation: all Pokemon names in table cells truncated to 4 characters via `_abbrev()`.
Suffix tags (×4, ×0.25) appended after the abbreviated name.

New functions: `build_unified_rows`, `gap_label`, `_abbrev`, `_weak_tag`, `_resist_tag`,
`_names_cell`, `_print_unified_table`.

Bug found during testing: assumed Rock would sort first for single-Charizard team.
Electric/Rock/Water all have weak=1 and sort alphabetically → Electric first.
Test fixed to assert structural invariant (weak rows before non-weak rows) not specific type.

Tests: 58 total. Full suite: 500 tests, 0 failures.

---

## §62 — Documentation restructure

Split the single README + notes.md into a proper multi-document structure:

| File | Content |
|---|---|
| `README.md` | User-facing: features, menu, outputs, limitations, troubleshooting |
| `ARCHITECTURE.md` | Module map, layer model, context schemas, cache layout, interface contracts |
| `ROADMAP.md` | Long-term feature goals with status |
| `TASKS.md` | Current active task with granular steps |
| `HISTORY.md` | This file — append-only development log |
| `AI_WORKFLOW.md` | Step-by-step workflow for AI-assisted development |
| `DEVELOPMENT_RULES.md` | Coding standards and conventions |

Source content: README.md (301 lines) and notes.md (2428 lines) were the inputs.
The old notes.md is superseded by HISTORY.md + ARCHITECTURE.md.
The old README.md is superseded by README.md + ROADMAP.md + TASKS.md.

---

## §62 — Team offensive coverage by type (Step 3a)

### What changed
- New file: `feat_team_offense.py` — offensive coverage analysis, key O in pokemain
- Modified: `pokemain.py` — import + O key menu entry + handler
- Modified: `run_tests.py` — feat_team_offense suite added

### Why
Complement to the defensive analysis (V). Shows which types each team member
can hit super-effectively using their own types (STAB-based, no learnset lookup).

### Key decisions
- `get_multiplier(era_key, member_type, target_type)` used offensively:
  same function, attacker/defender roles reversed from the defensive screen.
- Dual-type attackers: `max(type1_mult, type2_mult) >= 2` to determine SE.
  Both types are tracked independently — shown as letter tags in the table.
- Type-letter annotation: first letter of each hitting type shown in parentheses
  after the abbreviated name. e.g. `Char(F,F)` = Fire + Flying both hit SE;
  `Geng(P)` = Poison only (Ghost does not hit the target type SE).
- Sort: most-covered types first, gaps at bottom — mirrors defensive table convention.
- Single GAP label (no gradations) — offense is already simpler than defense.

### Tests
38 offline tests. Full suite: 538 tests, 0 failures.

---

## §63 — Step 3b: best scored move inline in offensive coverage table

### What changed
- Modified: `feat_team_offense.py` — extended O screen table with best-move enrichment

### Why
User requested option C: add the name of the best attacking move directly into
the existing O table, next to each hitter's type-letter tag. The move scorer
(`feat_moveset_data.score_move`) is used to pick the highest-scored STAB move of
the hitting type from each member's learnset.

### Key decisions
- **Inline format** `Char(F,F):Flamethrower` — move name appended to the existing
  hitter tag with `:` separator. Truncated to `_MOVE_NAME_LEN = 12` characters.
  Keeps the table on a single row per type without a new column.
- **`build_candidate_pool` reuse** — instead of re-implementing learnset scoring,
  `_build_member_pools` calls `feat_moveset_data.build_candidate_pool` for each
  hitter. The damage pool is already sorted by score descending; the first match
  for the target type is the best move. Zero code duplication of the scoring formula.
- **Best across hitting types** — when a dual-type member hits via multiple types
  (e.g. Charizard vs Grass via Fire and Flying), both types are checked and the
  single highest-scored move across all is shown.
- **Graceful degradation** — if learnset or moves cache is unavailable, `best_move`
  is None and the tag falls back to the original `Char(F,F)` format with no error.
- **`hitting_types` field added** to `build_team_offense` hitter dicts alongside
  the existing `hitting_letters`. Full type names are needed for move-type matching;
  letters are kept for display. Backward compatible — new field only, no removals.
- **Column width** widened: `_COL_HITTERS` 50 → 70, sized for ~3 hitters with names.
- **Progress message** printed before learnset fetch: "Loading move data for N member(s)..."
- **Only hitters fetched** — `_build_member_pools` skips members with no SE coverage,
  avoiding unnecessary network calls.

### Bugs found during testing
None. All 50 tests passed on first run.

### Test count
50 tests in this module (38 original + 12 new).
New tests cover: `_best_move_for_type` (4), `build_team_offense` hitting_types (3),
`_hitter_tag` with/without best_move and truncation (3), `_hitters_cell` with moves (1),
`_print_offense_table` move names in output (1).
Full suite: 550 offline tests, 0 failures.

---

## §64 — Refine O screen: one move per hitting type, drop type letters

### What changed
- Modified: `feat_team_offense.py` — updated tag format and enrichment logic

### Why
Type letters inside parentheses became redundant once move names were shown.
User requested: drop the letters and instead show one recommended move per
hitting type, comma-separated after the member abbreviation.

### Key decisions
- **New format** `Char:Fire Blast, Wing Attack` — one move entry per hitting type
  in the order they appear in `hitting_types`. Old format was `Char(F,F):Fire Blast`
  (single best move across all hitting types). New format is more informative.
- **Type-letter fallback per slot** — if no move is found for a specific hitting type
  (e.g. no Flying-type damaging move in the learnset), that slot falls back to the
  type's first letter: `Char:Fire Blast, F`. This preserves information.
- **Full fallback** — if no move data at all (`best_moves` absent or all-None),
  the original `Char(F,F)` bracket format is shown unchanged. Graceful degradation.
- **`_hitter_tag` signature change** — takes `hitting_types` (full names) instead of
  `hitting_letters`. Letters are derived as `type[0]` internally when needed for fallback.
- **`_enrich_rows_with_moves`** — now populates `h["best_moves"]` (list, one entry per
  hitting type) instead of `h["best_move"]` (single string). Aligned with `hitting_types`.
- **`_hitters_cell`** — passes `h["hitting_types"]` and `h.get("best_moves")` to `_hitter_tag`.

### Tests
44 tests in this module. Full suite: 544 offline tests, 0 failures.

---

## §65 — Step 4.1: feat_team_moveset.py stub created

### What changed
- New file: `feat_team_moveset.py` — team moveset synergy module (stub)
- Modified: `run_tests.py` — new suite added
- Modified: `ARCHITECTURE.md` — new module documented

### Why
Step 4.1 per TASKS.md: create the module skeleton and wire it into the test runner
before implementing the full scoring logic (step 4.2).

### Key decisions
- **Stub approach**: `recommend_team_movesets` iterates team slots and returns
  `_empty_member_result` dicts (correct shape, empty move lists). Full scoring deferred to 4.2.
- **`_empty_member_result(form_name)`** defines the agreed member result structure:
  `form_name`, `moves`, `weakness_types`, `se_types`. Shape is tested offline.
- **`_mode_prompt()`** implemented now: `(C)overage / co(U)nter / (S)TAB`.
- **`run()`** entry point exists and guards empty team; calls `_mode_prompt()` then prints a stub message.
- **`_MODES` constant** maps key letters to mode strings — tested for completeness.
- No menu wiring in `pokemain.py` yet — deferred to step 4.4.

### Test count
11 tests in this module. Full suite: 555 offline tests, 0 failures.


---

## §66–§71 — Step 4.2–4.5: feat_team_moveset.py full implementation

### What changed
- Modified: `feat_team_moveset.py` — full engine (`recommend_team_movesets`,
  `_weakness_types`, `_se_types`), display (`display_team_movesets`,
  `_display_member_block`, `_display_coverage_summary`, formatters),
  coverage aggregation (`build_offensive_coverage`), and menu wiring
- Modified: `pokemain.py` — S key handler added; guards for empty team and
  missing game context
- Modified: `feat_moveset_data.py` — cache key bug fixed (§69): moves were
  being saved under the API canonical name instead of the learnset display
  name, causing perpetual re-fetching; 2 regression tests added
- Modified: `run_tests.py` — feat_team_moveset suite registered

### Why
Steps 4.2–4.5 completing the team moveset synergy feature:
- **4.2** — scoring engine: calls `build_candidate_pool` + `select_combo`
  per slot; graceful degradation on empty pool
- **4.3** — display: per-member blocks (weaknesses, 4 moves, SE count)
- **4.4** — coverage summary: `build_offensive_coverage` aggregates `se_types`
  across all member results; shows Covered / Gaps / Overlap
- **4.5** — menu wiring: S key in `pokemain.py`

### Key decisions
- **`build_offensive_coverage` is pure**: reads `se_types` from result dicts
  already computed by `recommend_team_movesets`; does not re-run the engine.
- **Overlap threshold = 3**: types covered by 3+ members flagged as potential
  redundancy, sorted descending by count.
- **`_empty_member_result` shape preserved**: graceful degradation path keeps
  the same dict structure with empty lists so display code never branches on
  missing keys.
- **§69 cache key fix**: `build_candidate_pool` was calling
  `cache.upsert_move(canonical, entries)` where `canonical` came from a
  second PokeAPI call to get the English display name. This caused a key
  mismatch: the learnset uses `_slug_to_display` names (e.g. "Double Edge"),
  the cache stored the API canonical name ("Double-Edge"). Fixed by saving
  under `name` (the learnset display name) and removing the redundant API call.

### Test count
61 tests in `feat_team_moveset.py`. Full suite: 610 offline tests, 0 failures.


---

## §72 — Pythonmon-1: S screen loading indicator

### What changed
- Modified: `feat_team_moveset.py` — added one `print()` line in `run()`
  between the mode prompt and `recommend_team_movesets` call

### Why
On a cold cache with a 6-member team, the S screen was silent for several
seconds while learnsets and moves were being fetched. The O screen already
shows "Loading move data for N member(s)..." — the S screen now matches
that pattern with "Computing movesets for N member(s)...".

### Key decisions
- Line goes in `run()`, not in `display_team_movesets` or
  `recommend_team_movesets` — display functions stay side-effect-free with
  respect to loading state.
- `team_size()` already called earlier (empty-team guard); called again here
  to get the count for the message rather than threading it through.

### Test count
No new tests (display-only change). 61 tests in module; full suite unchanged.


---

## §73 — Pythonmon-2: fuzzy Pokemon name matching

### What changed
- Modified: `pkm_session.py` — new `_index_search()` helper and updated
  `_lookup_pokemon_name()` to offer suggestions; 9 new tests (14 → 23)

### Why
Typing exact Pokemon names is error-prone, especially for hyphenated or
compound names ("Mr. Mime", "Ho-Oh", "Tapu Koko"). The index already exists
and is populated on every cache hit — searching it before going to PokeAPI
is a natural improvement with no new API calls.

### Key decisions
- **Pure helper `_index_search(needle, index) → list`**: takes a slug dict
  and returns ranked matches. Tested independently of I/O. Same design as
  `match_move` in `feat_moveset.py`.
- **Priority order**: exact slug first (skips the picker entirely); prefix
  matches before substring matches within each group; both groups sorted
  alphabetically; capped at `_MAX_SUGGESTIONS = 8`.
- **Escape hatch**: option `0` in the picker always falls through to PokeAPI
  with the original typed string — covers Pokemon not yet in the local cache.
- **Hint on no-match**: when the index is populated but yields nothing, a
  `(not in local cache — searching PokeAPI...)` note is shown before the
  network call.
- **Single-form display name**: when the index entry has exactly one form,
  the form's display name (e.g. "Charizard") is shown rather than the raw
  slug. For multi-form entries, fall back to title-cased slug.
- **`_lookup_pokemon_name` prompt updated**: example names changed to hint
  that partial input is accepted.

### Test count
23 tests in `pkm_session.py`. Full suite: 614 offline tests, 0 failures.

---

## §74 — Pythonmon-3: batch move upserts

### What changed
- Modified: `pkm_cache.py` — new `upsert_move_batch(batch: dict)` function;
  docstring updated; 4 new tests (33 → 37)
- Modified: `feat_moveset_data.py` — `build_candidate_pool` fetch loop
  converted to batch write; §69 key fix re-applied; 4 regression tests added
  (152 → 156)
- Modified: `feat_movepool.py` — `_prefetch_missing` loop converted to batch
  write; §69 key fix applied (was still using canonical name in this file)

### Why
`build_candidate_pool` was calling `upsert_move()` once per missing move —
one full read + write of `moves.json` per iteration. With 20 uncached moves
and a ~900-entry `moves.json`, that is 20 × (read 900 entries + write 920
entries). The batch approach reads once and writes once regardless of how
many moves are missing.

### Key decisions
- **`upsert_move` kept unchanged**: it is used by `run_tests.py` cache
  warm-up, `feat_move_lookup.py`, and other single-miss paths. No callers
  were removed — only the loop callers upgraded.
- **`feat_movepool._prefetch_missing` also fixed**: it had the same two bugs
  (per-move writes + canonical key) independently. Fixed in the same pass
  since touching the same area.
- **`feat_move_lookup.py` not changed**: its single-miss `upsert_move` call
  is correct as-is — it only ever fetches one move at a time.
- **Empty batch is a no-op**: `upsert_move_batch({})` returns immediately
  without touching disk.
- **§69 key fix consolidated**: the per-move canonical-name bug (§69) was
  still present in `feat_movepool.py` and in the pre-§69 state of
  `feat_moveset_data.py`. Both are corrected here under the same pass.

### Test count
`pkm_cache.py`: 37 tests. `feat_moveset_data.py`: 156 tests.
Full suite: 623 offline tests, 0 failures.

---

## §75 — Pythonmon-16: fix get_form_gen substring false-positive

### What changed
- Modified: `pkm_session.py` — `get_form_gen` uses word-split instead of
  substring check; 5 new tests (23 → 28)

### Why
`get_form_gen("Meganium", 2)` was returning 6 because `"mega" in "meganium"`
is True. This caused Meganium to be rejected in any game before Gen 6, with
the error "Meganium was introduced in Generation 6".

### Root cause
The keyword loop used `if keyword in name_lower` (substring). The word
`"mega"` is embedded in `"meganium"` at positions 0–3. The other keywords
(`alolan`, `galarian`, `hisuian`, `paldean`) are long enough that no real
Pokémon name contains them as embedded substrings, so only `"mega"` was
affected in practice.

### Fix
```python
# Before
name_lower = form_name.lower()
if "mega" in name_lower and ...:
for keyword, gen in _FORM_GEN_KEYWORDS:
    if keyword in name_lower:

# After
words = form_name.lower().split()
if "mega" in words and ...:
for keyword, gen in _FORM_GEN_KEYWORDS:
    if keyword in words:
```

Word-split means `"Meganium".lower().split()` → `["meganium"]`, which
does not contain `"mega"` as an element. `"Mega Charizard X"` →
`["mega", "charizard", "x"]`, which does.

### Cache cleanup note
Users who previously loaded Meganium may have a corrupted
`cache/pokemon/meganium.json` containing a fabricated "Mega Meganium"
form. Deleting that file and reloading Meganium will fetch the correct
single-form data from PokeAPI.

### Test count
28 tests in `pkm_session.py`. Full suite: 628 offline tests, 0 failures.

---

## §81 — Pythonmon-6: move filter in pool

### What changed
- Modified: `feat_movepool.py` — 4 new functions, updated `_display_learnset`,
  updated `run()`; 7 new tests (9 → 16)

### Why
A Charizard learnset in Scarlet/Violet has 60+ moves. When planning a moveset
the user often wants to see only, say, Special Fire moves above 80 power — not
scroll the full list. The filter makes that a two-keypress operation after the
table is already on screen.

### Key decisions
- **Full table first**: pressing `2` always shows the complete unfiltered list.
  The filter prompt appears at the bottom. Pressing Enter returns to the menu
  immediately — the common case has zero extra keypresses (Option B).
- **`_apply_filter` is pure**: takes `(label, name, details)` tuples and a
  filter dict, returns the filtered subset. No I/O, fully testable offline.
- **`_passes_filter` rules**:
  - `details=None` (move not yet in cache) always passes — graceful fallback.
  - Status moves (`power=None`) are excluded by any `min_power` constraint,
    included when `min_power` is `None`.
  - Type match is case-insensitive.
  - Category accepts short inputs: `p` → Physical, `s` → Special, `t` → Status.
- **Section headers suppressed when empty**: if a filter leaves a section with
  zero rows, its header is not printed — cleaner output.
- **Filtered summary line**: `Showing X of Y moves (filtered)` replaces the
  normal total when a filter is active. The `[ filter: type=Fire | pwr≥80 ]`
  line appears directly below the session header.
- **Re-display, not in-place mutation**: filtered view is a fresh call to
  `_display_learnset` with `filter_spec` set. Original learnset data is
  never modified.
- **`run()` signature unchanged**: pokemain requires no changes.

### Test count
16 tests in `feat_movepool.py`. Full suite: 648 offline tests, 0 failures.

---

## §82 — Pythonmon-8: stat comparison (key C)

### What changed
- New file: `feat_stat_compare.py` — 13 tests
- Modified: `pokemain.py` — import added; `C` menu line; `elif choice == "c"` handler
- Modified: `run_tests.py` — `feat_stat_compare` added to SUITES (offline)

### Why
Choosing between two Pokemon for the same team slot often comes down to a
stat trade-off (e.g. Garchomp's Attack vs Charizard's SpA). The O and S
screens already exist for team-level analysis; key C fills the single-Pokemon
comparison gap with no new API calls.

### Key decisions
- **No new API data**: `base_stats` is already in the pokemon cache from the
  initial `P` load. The second Pokemon is fetched via the existing
  `select_pokemon()` picker, including fuzzy matching.
- **`compare_stats` and `total_stats` are pure**: no I/O, fully testable
  offline. `display_comparison` is the only function that prints.
- **`_stat_bar` duplicated from `feat_type_matchup`**: private helpers are
  not shared across feature modules (project convention). Same formula and
  constants (`_BAR_MAX=255`, `_BAR_WIDTH=18` — slightly narrower than the
  single-column view to fit two bars side by side).
- **Header layout**: both Pokemon names sit on the same line, left name
  left-padded to the exact width of the stat row's left half so each name
  sits directly above its column of bars.
- **Winner markers**: `★` for the higher value, `•` for a tie, blank for
  the lower. Applied per stat and on the Total line.
- **`run()` guards**: missing pkm_ctx or game_ctx each print a clear message
  and return without crashing.
- **`run()` signature**: `run(pkm_ctx, game_ctx)` — standard single-Pokemon
  feature signature, consistent with ARCHITECTURE.md §8.

### Test count
13 tests in `feat_stat_compare.py`. Full suite: 654 offline tests, 0 failures.

---

## §83 — Pythonmon-32: role & speed tier in quick view and stat compare

### What changed
- Modified: `feat_stat_compare.py` — `infer_role(base_stats) → str` and
  `infer_speed_tier(base_stats) → str` added as public functions; Role line
  added to `display_comparison`; 13 new tests (13 → 26)
- Modified: `feat_nature_browser.py` — `_infer_role` and `_infer_speed_tier`
  definitions removed; `from feat_stat_compare import infer_role,
  infer_speed_tier` added; all internal callers updated (no logic change)
- Modified: `feat_type_matchup.py` — `_print_base_stats` appends a
  `Role: X attacker  |  Speed: Y (base N)` line after the Total

### Why
The nature recommender already computed role and speed tier to rank natures,
but that context was never surfaced to the user. Two screens already show
base stats — option 1 (quick view) and option C (stat compare) — and both
are natural places to display this derived information.

### Key decisions
- **`feat_stat_compare.py` as the home**: role and speed tier are pure
  functions derived from base stats — the same category as `compare_stats`,
  `total_stats`, and `_stat_bar`. Centralising all stat analysis in one
  module gives `feat_nature_browser` a clean dependency direction (consumer
  of stat analysis, not provider of it).
- **`feat_nature_browser` becomes a consumer**: the two private functions
  are removed entirely from that module and replaced with an import. No
  logic change — exact same thresholds.
- **Deferred import in `feat_type_matchup`**: `from feat_stat_compare import
  infer_role, infer_speed_tier` is inside `_print_base_stats` rather than at
  module top to avoid any circular import risk at load time.
- **Display format**: `Role: Special attacker  |  Speed: Fast (base 100)`.
  The actual base Speed value is shown in parentheses so the user can see
  exactly where in the tier boundary their Pokemon sits.
- **"Mixed attacker" not just "Mixed"**: capitalising the role and appending
  "attacker" makes the label self-explanatory without context.

### Test count
`feat_stat_compare.py`: 26 tests. `feat_nature_browser.py`: existing 10
role/speed tests now call through the imported public names — no regressions.
Full suite: 667 offline tests, 0 failures.

---

## §84 — Pythonmon-28: move effect description in lookup

### What changed
- Modified: `pkm_pokeapi.py` — `"effect"` field added to the `current` dict
  in both `fetch_move` and `fetch_all_moves`; extracted from `effect_entries`
  (English `short_effect`), newlines stripped
- Modified: `pkm_cache.py` — `MOVES_CACHE_VERSION` bumped 2 → 3; version
  history comment updated; 1 new test asserting constant == 3 (37 → 38)
- Modified: `feat_move_lookup.py` — `_display_move` prints
  `Effect    : <text>` after the PP line when non-empty; 2 new tests (12 → 14)

### Why
The move lookup screen (key M) already showed type, category, power, accuracy,
PP, and offensive coverage — but no description of what the move actually does.
The `effect_entries` field was already returned by PokeAPI in every `fetch_move`
call and then silently discarded. Storing and displaying it required no new API
endpoint.

### Key decisions
- **`short_effect` not `effect`**: PokeAPI provides two effect fields.
  `effect` is multi-paragraph verbose text (e.g. "Inflicts regular damage.
  If the target is frozen, it will be thawed before receiving damage. Has a
  \$effect_chance% chance to burn..."). `short_effect` is one sentence
  ("Has a \$effect_chance% chance to burn the target."). `short_effect`
  matches the style used for abilities and fits cleanly on one line.
- **`"effect"` is constant across generations**: PokeAPI does not provide
  historical `short_effect` values in `past_values`. The field lives once in
  `current` and propagates to every versioned entry via `**current` in
  `_build_versioned_entries` — same pattern as `drain`, `ailment`, `priority`.
- **Suppressed when empty**: some moves (e.g. alternate-form moves, obscure
  Z-moves) have no English effect entry. The display line is omitted entirely
  rather than showing a blank or placeholder.
- **`MOVES_CACHE_VERSION` bump to 3**: the schema changed. Existing
  `moves.json` files at v2 are treated as a full miss — moves are lazily
  re-fetched on first use with the new schema. Users can also run
  MOVE → R to bulk re-fetch immediately.

### Cache migration note
After deploying: `moves.json` must be re-fetched to gain the effect field.
Automatic: any `get_moves()` call detects the version mismatch, deletes the
old file, and re-fetches lazily. Manual: MOVE → R.

### Test count
`pkm_cache.py`: 38 tests. `feat_move_lookup.py`: 14 tests.
Full suite: 679 offline tests, 0 failures.

---

## §85 — Rename feat_type_matchup.py → feat_quick_view.py

### Why
`feat_type_matchup.py` was named after the original feature it contained: the
defensive type chart. Over time, option 1 grew into a full single-Pokemon
summary screen: base stats + role/speed tier (§83), abilities, egg groups
(§84/Pythonmon-27A), and type chart. The old name no longer reflected the
file's actual scope and conflicted with the menu label ("Quick view") already
established in the CLI and documentation.

### What changed
- Renamed: `feat_type_matchup.py` → `feat_quick_view.py` (content unchanged)
- Modified: `pokemain.py` — import and all references updated
- Modified: `run_tests.py` — suite entry updated
- Modified: `ARCHITECTURE.md` — §1 file list and §7 module entry updated;
  description extended to include egg groups
- Modified: `README.md` — files table updated

### No logic changes
The rename is purely cosmetic. No functions were added, removed, or modified.
No tests were changed. All behaviour is identical.

### Note
The old filename `feat_type_matchup.py` should be deleted from the project
directory after deploying `feat_quick_view.py` to avoid the old module being
accidentally imported.

---

## §86 — Pythonmon-27A: egg groups schema + quick view display

### What changed
- Modified: `pkm_pokeapi.py` — `"egg_groups"` field added to `fetch_pokemon`
  return dict, extracted from the already-fetched species response; 3 new
  offline mock tests
- Modified: `pkm_cache.py` — `get_pokemon` returns `None` for entries missing
  `"egg_groups"` (transparent re-fetch trigger); all test fixtures updated;
  2 new tests (25 → 27 in temp-dir block)
- New file: `feat_egg_group.py` — `_EGG_GROUP_NAMES` (15 groups including
  ground→Field and plant→Grass corrections); `egg_group_name()`; 
  `format_egg_groups()`; stub `run()`; 11 tests
- Modified: `feat_quick_view.py` — egg group names shown inline below
  abilities block; deferred import of `feat_egg_group`
- Modified: `pokemain.py` — `feat_egg_group` imported; key `E` menu line and
  handler added (stub until §88)
- Modified: `run_tests.py` — `feat_egg_group` added to SUITES
- Modified: `pkm_session.py` — fake_api mock updated to include `egg_groups`
  in test fixtures (was causing T2 and T5 failures)

### Key decisions
- `egg_groups` stored at species level (not per-form) — all forms of a
  species share the same egg groups
- Auto-upgrade pattern: missing `egg_groups` → `get_pokemon` returns `None`
  → transparent re-fetch on next access. Same pattern as `variety_slug` §42.

---

## §87 — Pythonmon-27B: egg group roster fetch + cache layer

### What changed
- Modified: `pkm_cache.py` — `_EGG_GROUP_DIR` path constant;
  `get_egg_group(slug)` / `save_egg_group(slug, roster)` with atomic write;
  `check_integrity()` function (originally §77, now merged); 9 new tests
  (27 → 47 including check_integrity suite and egg group round-trip)
- Modified: `pkm_pokeapi.py` — `fetch_egg_group(slug)` fetching
  `GET egg-group/{slug}`, returning `[{"slug", "name"}]` sorted by name
- Modified: `feat_egg_group.py` — `get_or_fetch_roster(slug)` cache-aware
  bridge function; fetches from PokeAPI on miss, prints progress, caches result

### Key decisions
- Roster stored as a plain list (not wrapped in a dict like type rosters) —
  simpler schema, no metadata needed
- `_en_name` used for display names with slug title-case fallback — consistent
  with all other name resolution in `pkm_pokeapi`
- `check_integrity` also merged here: it was implemented in §77 but never
  reached the user's local file; §87B is the correct merge point

---

## §88 — Pythonmon-27C: full browser display + pkm_ctx bug fix

### What changed
- Modified: `feat_egg_group.py` — `_print_roster_grid` (5-column layout,
  ★ marker for current Pokemon, truncation for long names);
  `display_egg_group_browser` (header, one section per group with count,
  "cannot breed" note for Undiscovered); `run()` replaces stub; 7 new tests
  (11 → 18)
- Modified: `pkm_session.py` — **bug fix**: `egg_groups` added to `pkm_ctx`
  dict in `select_pokemon`; was never included despite being on the raw cache
  entry, causing all egg group displays to show "No egg group data"

### Bug fix detail
`select_pokemon` builds `pkm_ctx` by explicitly listing fields from the
cache. `egg_groups` was added to the cache schema in §86 but never added to
this dict. The fix: `"egg_groups": cache.get_pokemon(name).get("egg_groups", [])`.
`refresh_pokemon` was unaffected — it uses `{**pkm_ctx, ...}` which
preserves all existing keys.

### Display format
```
  Egg groups  |  Charizard
  ══════════════════════════════════════════════════════
  Groups: Monster  /  Dragon

  Monster group  (98 Pokémon)
  ──────────────────────────────────────────────────────
  Bulbasaur         Charmander        Squirtle          ...

  ★ = current Pokémon
  ══════════════════════════════════════════════════════
```

### Test count
`feat_egg_group.py`: 18 tests. `pkm_cache.py`: 47 tests. `pkm_session.py`:
28 tests (unchanged). Full suite: ~900 offline tests, 0 failures.

---

## §89 — Pythonmon-9A: evolution chain pure parsing logic

### What changed
- New file: `feat_evolution.py` — `_parse_trigger` and `_flatten_chain`
  (pure functions, no I/O); stubs for `get_or_fetch_chain` and
  `display_evolution_block` (implemented in B and C); 16 tests

### Why iteration A first
`_parse_trigger` and `_flatten_chain` are the hardest part of the evolution
chain feature — trigger parsing has 12 cases, flatten has recursion and
branching. Implementing and testing them in isolation before any schema,
cache, or display work means the complex logic is verified independently.
Any error in the parsing logic caught here would otherwise be hard to
diagnose once mixed with API calls and display output.

### `_parse_trigger` design
Takes a PokeAPI `evolution_details` list and returns a human-readable string.
Uses the first entry in the list (multi-condition evolutions are rare and
the first condition is always the primary one). Priority order within
`level-up`: `min_level` → `min_happiness` → `known_move` → `time_of_day`
→ bare level-up. Item and move slugs are title-cased via `_slug_to_title`.
Empty list (stage 0, base species) returns `""`.

### `_flatten_chain` design
Recursively walks the PokeAPI chain tree and returns a list of linear paths,
one per branch from root to leaf. Each stage dict contains only `slug` and
`trigger` — types are not stored here (fetched separately at display time
per the design decision in §tasks). `max_depth=20` guards against any
malformed data with unexpected depth; truncates gracefully rather than
raising `RecursionError`.

### Test coverage
12 `_parse_trigger` tests: all trigger types, all level-up sub-cases,
item/move slug conversion, empty list, unknown trigger fallback.
4 `_flatten_chain` tests: linear 3-stage chain (Bulbasaur line), 2-branch
chain (Slowpoke), single-stage (no evolution), max_depth truncation.

### Test count
16 tests in `feat_evolution.py`. Full suite: ~900 offline tests, 0 failures.

---

## §90 — Pythonmon-9B: evolution chain schema + API + cache

### What changed
- Modified: `pkm_pokeapi.py` — `_parse_chain_id(species)` helper; `fetch_evolution_chain(chain_id)`
  returning the raw `chain` node; `evolution_chain_id` added to `fetch_pokemon` return dict;
  offline mock updated to include `evolution_chain` URL; 2 new offline tests (3 → 5)
- Modified: `pkm_cache.py` — `_EVOLUTION_DIR` constant; `get_evolution_chain` /
  `save_evolution_chain` / `invalidate_evolution_chain`; auto-upgrade check combined
  into single condition (`egg_groups` + `evolution_chain_id`); `check_integrity` scans
  `cache/evolution/`; `_EVOLUTION_DIR` in temp-dir redirect; header updated to "6 layers"
  with full public API; 5 new tests (47 → 52)
- Modified: `pkm_session.py` — `evolution_chain_id` added to `pkm_ctx` in `select_pokemon`;
  fake_api mock updated with `"evolution_chain_id": 42`
- Modified: `pokemain.py` — `--refresh-evolution <n>` startup flag; R key extended to call
  `invalidate_evolution_chain` before `refresh_pokemon`

### Key decisions

**`fetch_evolution_chain` returns `chain` node, not full response** — callers only need the
recursive tree; the metadata wrapper (`id`, `url`) is discarded. Same pattern as
`fetch_egg_group` discarding the top-level container.

**Combined auto-upgrade check** — `if "egg_groups" not in data or "evolution_chain_id" not in data`
— single condition, single re-fetch. Avoids two sequential fetches for entries that
predate both fields (all entries cached before §90).

**Stored as flattened paths, not raw tree** — `save_evolution_chain` stores the output of
`_flatten_chain` (list of paths), not the raw PokeAPI tree. Avoids re-parsing the
recursive structure on every load. Consistent with "cache what you compute, not what
you fetched" principle.

**R key integration** — pressing R now invalidates the evolution chain before re-fetching
the Pokemon. No separate menu key needed; a single keypress refreshes all Pokemon data
including the chain. `--refresh-evolution <n>` covers the command-line path.

### Bug found and fixed during testing
All test fixtures in `pkm_cache.py` that were written before §90 (charizard ×2,
mewtwo, newmon) were missing `"evolution_chain_id"`, causing the auto-upgrade check
to return `None` for them and breaking the index repair test. All fixtures updated.

### Cache action required
All files in `cache/pokemon/` must be re-fetched — they are missing `evolution_chain_id`.
The auto-upgrade triggers transparently on next load, or delete the folder to repopulate
on demand.

### Test count
`pkm_cache.py`: 52 tests. `pkm_pokeapi.py`: 5 offline tests. `pkm_session.py`: 28 tests
(unchanged). Full suite: ~900 offline tests, 0 failures.

---

## §91 — Pythonmon-9C: evolution chain display + gen filter + trigger fixes

### What changed
- Modified: `feat_evolution.py` — full implementation of:
  - `_get_species_gen(slug)` — reads species gen from pokemon cache
  - `_get_types_for_slug(slug)` — cache-hit instant; API call + cache write on miss
  - `_type_tag(types)` — `['Fire','Flying']` → `'[Fire / Flying]'`
  - `filter_paths_for_game(paths, game_gen)` — pure filter; truncates branches
    whose target species was introduced after `game_gen`; de-duplicates base-only
    stubs; base-only stub only shown when all evolutions are filtered out
  - `get_or_fetch_chain(pkm_ctx)` — cache-aware bridge; returns `None` for
    `chain_id=None`; fetches and caches on miss
  - `display_evolution_block(pkm_ctx, paths, game_gen=None)` — compact inline
    format; pre-fetches all uncached stage types with loading indicator; ★ on
    `pkm_ctx["pokemon"]`; "does not evolve" vs "no further evolution in this game"
  - `_parse_trigger` bug fixes (see below)
  - 35 tests (16 → 35)
  - Header updated with full public/internal API
- Modified: `feat_quick_view.py` — one deferred import + `display_evolution_block`
  call at end of `run()`, passing `game_ctx["game_gen"]`
- Modified: `pokemain.py` — `import feat_evolution` added to try/except block
- Modified: `run_tests.py` — `feat_evolution` added to SUITES (offline)

### `_parse_trigger` bug fixes
Two bugs discovered after live testing:

**Bug 1 — High Friendship + time of day (Espeon, Umbreon)**
The `min_happiness` branch exited before checking `time_of_day`. Was producing
`"High Friendship"` for both Espeon and Umbreon. Fixed priority order:
`min_happiness` + `time_of_day="day"` → `"High Friendship (day)"`,
`time_of_day="night"` → `"High Friendship (night)"`, no time → `"High Friendship"`.

**Bug 2 — Trade with held item (Steelix, Politoed, Slowking, etc.)**
Code checked `d["item"]` for the held item but PokeAPI uses `d["held_item"]`
for trade-held-item evolutions. `d["item"]` is used for use-item trigger only.
Was producing `"Trade"` instead of `"Trade holding Metal Coat"`. Fixed to read
`d.get("held_item")` for trade triggers.

### `filter_paths_for_game` design
- Each path is truncated at the first stage whose `species_gen > game_gen`
- Stages with unknown gen (not yet cached) are kept — safe default, never over-filters
- Branches that truncate to base-only are collected separately; the base-only
  stub is only surfaced when no valid evolution paths remain (prevents Eevee
  from showing a redundant `[Eevee ★ — no further evolution]` alongside 5 valid branches)
- Eevee in FireRed/LeafGreen (gen 3): shows Vaporeon / Jolteon / Flareon
  (gen 1) + Espeon / Umbreon (gen 2); drops Leafeon / Glaceon (gen 4) and
  Sylveon (gen 6)

### Cache action required
Delete `cache/evolution/` or run `--refresh-evolution <n>` for any Pokemon
with friendship evolutions (Espeon, Umbreon, Sylveon, Togekiss, etc.) or
trade-held-item evolutions (Steelix, Politoed, Slowking, Scizor, etc.).
The cached trigger strings are incorrect due to the bugs fixed in this section.

### Test count
35 tests in `feat_evolution.py`. Full suite: ~930 offline tests, 0 failures.

---

## §104 — Three display bug fixes

### What changed
- Modified: `feat_move_lookup.py` — accuracy/PP null display + version history table
- Modified: `feat_quick_view.py` — press-Enter pause added at end of `run()`
- Modified: `feat_learnset_compare.py` — defensive base_stats fallback in `_print_stat_header`

### Why

**Move lookup (key M):** Two issues.
1. Moves with null accuracy (Aerial Ace, Swift, etc.) showed `--` instead of anything
   meaningful. Same for moves with null PP (Z-moves, G-Max moves). These are valid values
   that mean "always hits" and "no PP" respectively — not missing data.
2. The README described a version history table in the move lookup output but it was never
   implemented. Moves that changed stats across generations (Flamethrower 95→90bp,
   Outrage Special→Physical, etc.) only showed the current-game values with no context.

**Quick view (option 1):** After displaying the full single-Pokemon summary screen
(stats, abilities, egg groups, type chart, evolution chain), the menu returned
immediately without waiting. This made it easy to miss the evolution chain block
at the bottom, especially on longer chains. A standard press-Enter pause is now
shown at the end.

**Learnset compare (key L):** The base stats header for the second pokemon
sometimes showed all zeros despite the data being available in cache. Root cause:
`pkm_b["base_stats"]` could be an empty dict `{}` in edge cases (old list-format
cache entry, or timing race on first load before cache write completes). Added a
defensive fallback that re-reads directly from the pokemon cache by form name
when the base_stats dict is empty or non-dict.

### Key decisions

**Move lookup accuracy/PP:**
- Null accuracy → `"always hits"` (self-explanatory, accurate)
- Null PP → `"n/a"` (cleaner than `--`)
- These show for Status moves too where both fields are null

**Version history table:** Only shown when a move has more than one versioned
entry (i.e. it changed at least once). Single-version moves (majority) are
unaffected. The current game's row is marked with ★. Columns: Gens / Type /
Cat / Pwr / Acc / PP. Compact single-line format fits within the existing
move lookup output width.

**Learnset compare fallback:** Wrapped in try/except so any cache read error
is silently swallowed and an empty dict is used instead — display continues
with zeros rather than crashing. Same defensive pattern as `feat_moveset_data`
which has an identical guard for the same old-format issue.

### Test count
`feat_move_lookup.py`: 18 offline tests (was 14, +4 for new formatters).
No new tests for quick view (display-only) or learnset compare (display-only).
Full suite: unchanged offline count, 0 failures.
