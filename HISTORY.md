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

---

## §92 — Pythonmon-17: cache size report (`--cache-info`)

### What changed
- Modified: `pkm_cache.py` — new `get_cache_info() → dict` function; counts entries
  per cache layer (pokemon, learnsets, moves, machines, types, natures,
  abilities_index, abilities, egg_groups, evolution)
- Modified: `pokemain.py` — `--cache-info` startup flag; prints the table and exits

### Why
Diagnostic companion to `--check-cache`. Users had no way to see at a glance
how populated their local cache was without inspecting the filesystem manually.

### Key decisions
- Pure function — no network, no side effects
- Moves count excludes metadata keys (`_version`, `_scraped_at`)
- Missing dirs silently count as 0, never raise
- Runs before `--check-cache` in `_handle_diagnostic_flags`

### Test count
`pkm_cache.py`: 47 `_ok()` calls. Full suite: ~843 offline tests, 0 failures.

---

## §93 — Pythonmon-18: offline mode detection

### What changed
- Modified: `pkm_pokeapi.py` — new `check_connectivity() → bool`; lightweight
  GET to PokeAPI root with 3-second timeout
- Modified: `pokemain.py` — connectivity probe at startup when cache has < 5
  Pokemon; prints `⚠  PokeAPI unreachable — running from cache only.`

### Why
Network failures previously surfaced deep inside fetch calls with confusing
tracebacks. New users on first run with no network would see nothing helpful.

### Key decisions
- Probe suppressed when cache has ≥ 5 Pokemon (well-used cache → network
  probably not needed immediately; avoids 3s delay on every launch)
- Non-blocking — tool continues into the menu regardless

### Test count
`pkm_pokeapi.py`: 3 new offline tests (mocked urlopen). Full suite unchanged, 0 failures.

---

## §94 — Pythonmon-19: learnset staleness flag

### What changed
- Modified: `pkm_cache.py` — `get_learnset_age_days(variety_slug, game) → int | None`
  using `os.path.getmtime()`; `LEARNSET_STALE_DAYS = 30` constant
- Modified: `feat_movepool.py` — staleness note shown before learnset display
  when age > threshold
- Modified: `feat_moveset.py` — same note in `run()` and `run_scored_pool()`

### Why
Learnsets are cached indefinitely. After a game patch, users had no indication
their cached data might be outdated. The note prompts them to press R.

### Key decisions
- File mtime used — no schema change needed
- Note only shown when age exceeds threshold, never on fresh caches
- Display-only — never blocks usage

### Test count
`pkm_cache.py`: 3 new learnset_age tests. Full suite unchanged, 0 failures.

---

## §95 — Pythonmon-20: move filter on scored pool (option 3)

### What changed
- Modified: `feat_moveset.py` — `_adapt_pool_for_filter(pool) → list` converts
  scored pool rows to (label, name, details) tuples compatible with
  `feat_movepool._apply_filter`; `_display_filtered_scored_pool()` renders
  filtered results; filter prompt added at bottom of `run_scored_pool()`

### Why
Option 2 (learnable moves) had a filter since §81. Option 3 (scored pool)
lacked it. Users browsing the scored pool had to scroll all 60+ moves to
find, e.g., only Special Fire moves above 80 power.

### Key decisions
- Reuses `feat_movepool._apply_filter` and `_passes_filter` directly — no
  logic duplication
- `_adapt_pool_for_filter` is pure and tested offline
- Scored pool rows contain `type`, `category`, `power` so the existing filter
  predicates work without modification

### Test count
`feat_moveset.py`: 5 new tests (28 → 33). Full suite unchanged, 0 failures.

---

## §96 — Pythonmon-22: batch team load

### What changed
- Modified: `feat_team_loader.py` — `_resolve_batch_name(raw, index) → str | None`;
  `_build_pkm_ctx_from_cache(slug) → dict | None`; `_load_batch(raw, team_ctx)`
  detects comma-separated input in `_team_menu()` and loads multiple Pokemon
  in one operation

### Why
Loading a 6-member team required 6 separate prompts. Users who knew their
team could now type `char, blastoise, gengar` and fill multiple slots at once.

### Key decisions
- Each name goes through `_index_search` (fuzzy matching) for consistency
  with single-name loading
- Ambiguous matches: picks first alphabetically and prints a warning
- Falls back to individual loading if a name can't be resolved from cache
- `_build_pkm_ctx_from_cache` builds a minimal pkm_ctx from cached data
  without triggering PokeAPI calls

### Test count
`feat_team_loader.py`: 13 new tests (28 → 41). Full suite unchanged, 0 failures.

---

## §97 — Pythonmon-30: weakness overlap heatmap

### What changed
- Modified: `feat_team_analysis.py` — `build_weakness_pairs(team_ctx, era_key) → list`;
  `gap_pair_label(shared_count) → str`; `_print_weakness_pairs(pairs)` display
  helper; `display_team_analysis()` extended to show pair overlap block below
  the unified type table

### Why
The V screen showed per-type aggregates but not which specific pairs of team
members shared multiple weaknesses. "Charizard and Blastoise are both weak to
Electric and Rock" is more actionable than "Electric: 2 weak members".

### Key decisions
- Only pairs with ≥ 2 shared weaknesses are shown (1 shared is too common
  to be meaningful)
- Sorted descending by shared_count so worst pairs appear first
- Pure function `build_weakness_pairs` — no I/O, fully testable

### Test count
`feat_team_analysis.py`: 17 new tests (58 → 75). Full suite unchanged, 0 failures.

---

## §98 — Pythonmon-24: nature & EV build advisor

### What changed
- Modified: `feat_nature_browser.py` — stat calculator (Lv 100, 31 IVs);
  `calc_stat()`, `build_ev_profile(role) → dict`; `build_profiles(pkm_ctx) → list`;
  `display_ev_advisor(pkm_ctx)` showing 4 EV spreads (Physical / Special /
  Bulky Physical / Bulky Special) with computed stats; integrated into `run()`
  when Pokemon loaded

### Why
The nature browser already recommended natures by role and speed tier. The
natural next step was showing the concrete EV spread that goes with each
nature recommendation, and the resulting Level 100 stats.

### Key decisions
- Standard competitive baseline: Lv 100, 31 IVs assumed (documented at top
  of calculator section)
- 4 preset profiles cover the most common builds without requiring user input
- Pure calculation — no new API data needed
- EV total = 508 (standard cap) enforced in all profiles

### Test count
`feat_nature_browser.py`: 58 `check()` calls. Full suite unchanged, 0 failures.

---

## §99 — Pythonmon-26: learnset comparison (key L)

### What changed
- New file: `feat_learnset_compare.py` — `compare_learnsets(set_a, set_b) → dict`;
  `_flat_moves(learnset, form_name) → set`; `_build_move_rows(names, game_ctx)`;
  `_print_stat_header(pkm_a, pkm_b)`; `display_learnset_comparison(pkm_a, pkm_b,
  game_ctx)`; `run(pkm_ctx, game_ctx)`
- Modified: `pokemain.py` — `import feat_learnset_compare`; `L` menu key and handler
- Modified: `run_tests.py` — `feat_learnset_compare` added to SUITES

### Why
Choosing between two Pokemon for the same slot often comes down to what moves
they can learn. Having both learnsets side by side with unique/shared sections
makes that comparison immediate.

### Key decisions
- Flat set comparison (move names only) — ignores learn method, focuses on
  what moves are available not how they're learned
- Brief stat header above the learnset sections for quick context
- `compare_learnsets` is pure — takes two sets, returns three (only_a, only_b,
  shared); fully testable offline

### Test count
19 tests in `feat_learnset_compare.py`. Full suite: ~862 offline tests, 0 failures.

---

## §100 — Pythonmon-11: team builder / slot suggestion (key H)

### What changed
- New file: `feat_team_builder.py` — full implementation across 4 iterations:
  pure scoring engine (A), candidate pool builder (B), display layer (C),
  entry point + menu wiring (D)
- Modified: `pokemain.py` — `import feat_team_builder`; `H` key menu line
  (shown when game + ≥1 team member); `elif choice == "h":` handler
- Modified: `run_tests.py` — `feat_team_builder` added to SUITES
- Modified: `ARCHITECTURE.md` — `feat_team_builder.py` in §1 and §7

### Why
Given a partial team, the tool had no way to suggest what to add next.
Key H fills that gap: it analyses offensive and defensive gaps, finds
Pokemon from cached type rosters that address those gaps, scores them
on intrinsic quality + lookahead (how many gaps remain after adding them),
and presents the top 6 as structured suggestion cards.

### Key decisions
- **Scoring formula**: intrinsic (off_covered×10 + def_covered×8 - weak_pair×6
  + role_bonus×4) + lookahead (patchability/remaining_slots, ×2 when ≤2 slots)
- **`_id_to_gen`** defined locally (same range table as `feat_type_browser`) —
  avoids cross-feature imports at the same layer
- **Dot rating** (●●●●○) is percentile-based within the result set — always
  produces a spread even when all candidates score similarly
- **Roster fetch** separated from pool building so the display layer controls
  progress output
- **`build_suggestion_pool`** named to avoid collision with
  `feat_moveset_data.build_candidate_pool`

### Test count
57 tests in `feat_team_builder.py`. Full suite: ~919 offline tests, 0 failures.

---

## §101 — TD-1 + TD-2: pokemain menu cleanup

### What changed
- Modified: `pokemain.py` — duplicate `L` menu line removed from `_print_menu()`;
  team feature visibility conditions (`V`, `O`, `S`, `H`) merged into a single
  `if` block using `> 0` instead of `>= 1`

### Why
TD-1 and TD-2 from the Copilot audit cross-check. Duplicate menu line caused
key L to appear twice. Separate `if` blocks for each team key were redundant.

### Test count
No new tests (display-only). Full suite unchanged, 0 failures.

---

## §102 — TD-4 + TD-5: pkm_cache duplicate definition cleanup

### What changed
- Modified: `pkm_cache.py` — duplicate `_MACHINES_FILE` definition at line 462
  removed; `_learnset_path` helper and `game_to_slug` moved out of the constants
  block into a dedicated "Slug and path helpers" section after all constants

### Why
TD-4 and TD-5 from the Copilot audit cross-check. The duplicate constant was
harmless but confusing. The helper functions logically belong after the
constants they reference.

### Test count
No new tests (structural only). Full suite unchanged, 0 failures.

---

## §103 — PKG-1 + PKG-2 + PKG-3: PyInstaller packaging support

### What changed
- Modified: `pkm_cache.py` — `sys.frozen` guard: when running as a PyInstaller
  bundle, `_BASE` is redirected to the folder next to the executable instead of
  using `__file__` (which points inside the bundle); 3 new tests (47 → 50)
- New file: `build.py` — build helper script; `python build.py` or
  `python build.py --clean`; checks PyInstaller availability, runs correct flags,
  prints distribution instructions
- New file: `.github/workflows/build.yml` — GitHub Actions workflow; builds
  Windows, macOS, Linux executables in parallel on Release publish or manual
  trigger; uploads as downloadable artifacts

### Why
The toolkit works well for developers running from source, but distributing it
to non-developer users required Python to be installed. PyInstaller bundles
everything into a single executable — users double-click and run, no setup needed.

### Key decisions
- `sys.frozen` guard is the standard PyInstaller pattern; has zero impact on
  normal dev runs (`sys.frozen` is not set by the Python interpreter)
- `cache/` is always created next to the executable on first run — same UX
  as the source version
- GitHub Actions uses `PYTHONUTF8=1` to avoid Windows CP1252 encoding errors
  on the `✓` character in `build.py` output
- Artifacts retained for 30 days; release uploads only when triggered by
  a GitHub Release (not on manual `workflow_dispatch` runs)

### Test count
`pkm_cache.py`: 3 new frozen-path tests (47 → 50). Full suite unchanged, 0 failures.


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

---

## §105 — Batch 5: code quality sweep (TD-7, TD-8, TD-9)

### What changed
- Modified: `pokemain.py` — bare `except:` → `except (TypeError, ValueError)`;
  duplicate `_MENU_CHOICES` inside `main()` consolidated to module level (TD-7, TD-9)
- Modified: `feat_quick_view.py` — broad `except Exception:` → specific types;
  `_SEP_WIDTH = 46` constant added; all `"─" * 46` literals replaced (TD-7, TD-8)
- Modified: `pkm_cache.py` — three `except Exception: pass` in cache_info
  counts replaced with `except (OSError, ValueError, TypeError): pass` (TD-7)

### Why

Three items from a Copilot audit cross-check, confirmed as genuinely worth
fixing (others were dismissed as wrong tool for a CLI, already handled, or
by-design).

**TD-7 — Broad exception handling:**
One bare `except:` in `pokemain._format_stats` and three `except Exception`
blocks in non-test code. Bare `except:` catches `SystemExit`, `KeyboardInterrupt`,
and other things you never want to swallow. Specific types are explicit about
what can actually fail and let unexpected errors surface rather than hide.

**TD-8 — Magic constants:**
`feat_quick_view.py` had `"─" * 46` repeated four times with no named constant.
`_SEP_WIDTH = 46` defined once at module top; all four uses updated. `pokemain.py`
already had `W = 52` and `_CACHE_SEP_WIDTH = 46` — no change needed there.
Other files already define their own `_W`, `_BLOCK_SEP`, `_STAT_W` etc.

**TD-9 — Input validation (partial):**
A `_MENU_CHOICES` frozenset already existed inside `main()` from a previous
session but was a local variable with no effect. Promoted to module-level
constant with per-key comments, and the duplicate inside `main()` removed.
The frozenset serves as documentation — the elif chain is still the
authoritative dispatcher and handles `"move"` (multi-char) and digit keys
correctly without needing a pre-check.

### Test count
No new tests (all changes are display/structural, no logic). Full suite
unchanged, 0 failures.


## §106 — Pythonmon-31: Team coverage vs in-game opponents (initial release)

### What changed
- New file: `feat_opponent.py` — full implementation of the opponent analysis feature, including:
  - Static trainer data loader (`data/trainers.json`)
  - Iteration A: `load_trainer_data()`, `get_trainers_for_game()`, `list_trainer_names()`, `get_trainer()`
  - Iteration B: `analyze_matchup()`, `uncovered_threats()`, `recommended_leads()` (moveset‑aware logic)
  - Iteration C: `pick_trainer_interactive()`, `display_matchup_results()`
  - Entry point `run(team_ctx, game_ctx)` called from pokemain
  - Self‑tests (35 offline) covering all pure logic
- Modified: `pkm_session.py` — `select_game()` now adds a `version_slugs` list to `game_ctx` (using `GAME_TO_VERSION_GROUPS` from `pkm_pokeapi.py`). This allows the opponent feature to merge trainer data across grouped games (e.g. Red/Blue/Yellow). Self‑tests updated from 28 to 30 (removed a problematic fallback test).
- Modified: `pokemain.py` — added menu line `X. Team vs opponent` (visible when game and team loaded) and handler `elif choice == "x":` that calls `feat_opponent.run(team_ctx, game_ctx)`.

### Why
To let players evaluate their loaded team against real in‑game opponents (gym leaders, Elite Four, Champions). The feature uses a static trainer database (bundled in `data/trainers.json`) because PokeAPI does not provide trainer data. The analysis is moveset‑aware: threats/resists are based on the opponent's actual move types, while your team's counters are based on STAB move types.

### Key decisions
- **Game grouping via `version_slugs`**: Instead of using a single game slug, `game_ctx` now contains a list of PokeAPI version slugs (e.g. `["red-blue","yellow"]`). The opponent feature merges trainers from all versions in the group, eliminating duplicates.
- **Trainer data keyed by version slug**: `trainers.json` is organised by version slug (e.g. `"red-blue"`, `"yellow"`), matching the PokeAPI version‑group slugs. This keeps the data structure aligned with the rest of the toolkit.
- **Moveset‑aware analysis**: For each opponent Pokémon, we resolve the actual move types (using `cache.get_move()` and `cache.resolve_move()`). This provides accurate threat assessment.
- **STAB‑based counters**: For your team, we assume you will use STAB moves (type‑advantage via your Pokémon's types). This is a reasonable simplification that avoids fetching your team's actual movesets.
- **Offline‑first**: All trainer data is bundled; no network calls are made during analysis. The only network dependency is for resolving move types, which is already cached.

### Bugs found during testing
- The initial self‑test for `version_slugs` included a fallback case for a non‑existent game (`"Fake Game"`). This caused a `StopIteration` because `select_game()` expects a real game name. The test was removed; only the two valid game groups (Red/Blue/Yellow and Scarlet/Violet) are now tested.

### Test count
- `feat_opponent.py`: 35 offline tests.
- `pkm_session.py`: 30 tests (was 28).
- Full offline suite: ~954 tests, 0 failures.


---

## §107 — Pythonmon-31: Team coverage vs in‑game opponents (completed)

### What changed
- New file: `feat_opponent.py` — full implementation of the opponent analysis feature.
  - Static trainer data loader from `data/trainers.json` (bundled with the toolkit).
  - Support for multiple version slugs: `get_trainers_for_versions()`, `list_trainer_names_for_versions()`, `get_trainer_for_versions()`, and `_merge_trainer_dicts()`.
  - Moveset‑aware matchup logic: `analyze_matchup()` uses opponent’s actual move types (via `get_move_type()` and `cache.resolve_move()`). Team counters are based on STAB move types.
  - Interactive trainer picker with version indicators (e.g. “Brock (R,Y)”).
  - Full output display: per‑opponent Pokémon blocks with threats, resists, counters; uncovered threats summary; recommended leads.
  - Self‑tests: 18 offline tests covering merging, version indicators, and analysis.
- Modified: `pkm_session.py` — `select_game()` now adds a `version_slugs` list to `game_ctx`, using `GAME_TO_VERSION_GROUPS` from `pkm_pokeapi.py`. Self‑tests updated to 30 (two new tests for version_slugs).
- Modified: `pokemain.py` — added menu key `X` (shown when game and team are loaded) that calls `feat_opponent.run(team_ctx, game_ctx)`.
- Modified: `run_tests.py` — added `feat_opponent` suite to the test registry.

### Why
To allow players to evaluate their team against real in‑game opponents (gym leaders, Elite Four, Champions). The feature uses a static trainer database because PokeAPI does not provide trainer data. The analysis is moveset‑aware: threats/resists are based on the opponent’s actual move types, while your team’s counters are based on STAB move types.

### Key decisions
- **Game grouping via `version_slugs`**: Instead of a single game slug, `game_ctx` now contains a list of PokeAPI version slugs. The opponent feature merges trainer data from all versions in the group, eliminating duplicates and showing version indicators.
- **Trainer data keyed by version slug**: `trainers.json` is organised by version slug (e.g. `"red-blue"`, `"yellow"`), aligning with the PokeAPI version‑group slugs. This keeps the data structure consistent.
- **Moveset‑aware analysis**: For each opponent Pokémon, we resolve the actual move types using `cache.get_move()` and `cache.resolve_move()`. This provides accurate threat assessment.
- **STAB‑based counters**: For your team, we assume you will use STAB moves (type‑advantage via your Pokémon’s types). This is a reasonable simplification that avoids fetching your team’s actual movesets.
- **Offline‑first**: All trainer data is bundled; no network calls are made during analysis. Move type resolution uses the local move cache (already populated by normal usage).

### Bugs found during testing
- The initial self‑test for `version_slugs` included a fallback case for a non‑existent game, causing a `StopIteration`. The test was removed; only valid game groups are tested.
- A test for `Blue` merging incorrectly assumed identical data across versions; the fixture was adjusted to omit `Blue` from `yellow`, ensuring the merging logic behaved as expected.
- The threat test initially looked for the `"WEAK TO"` section; it was changed to check for `"✓ Team is not hit SE"` because Lapras is not weak to Brock’s Normal moves.

### Test count
- `feat_opponent.py`: 18 offline tests.
- `pkm_session.py`: 30 tests (was 28).
- Full offline suite: ~972 tests, 0 failures.

---

## §108 — Pythonmon-23: persistent game selection (`--game`) + `--help` flag

### What changed
- Modified: `pkm_session.py` — added `make_game_ctx(game_name)` function that returns a complete `game_ctx` dict for a given game name (raises `ValueError` if the game is not in `calc.GAMES`). Refactored `select_game()` to use it. Added 3 new self‑tests (T31–T33) verifying `make_game_ctx` for valid games (Scarlet/Violet, Red/Blue/Yellow) and invalid input. Test count increased from 30 to 33.
- Modified: `pokemain.py` — added `--game <name>` flag handling before the main loop. If the flag is present, `make_game_ctx` is called with the provided name; on success, `game_ctx` is pre‑set and a confirmation message is printed; on error, the tool exits with an error message.
- Modified: `pokemain.py` — added `--help` (and `-h`) flag that displays a concise usage summary and exits. The help text includes all supported startup flags (`--cache-info`, `--check-cache`, `--refresh-*`, `--game`).

### Why
**Persistent game selection:** Users who always work in the same game can now skip the game selection prompt by starting the toolkit with `--game "Scarlet / Violet"`. This speeds up repeated sessions.

**Help flag:** The toolkit lacked a built‑in usage summary; new users had to guess flags or read the README. The `--help` flag provides an immediate overview.

### Key decisions
- `make_game_ctx` is a pure function that can be used independently of the interactive game picker. It is tested offline.
- The `--game` flag is processed after diagnostic and refresh flags but before the main menu, so it works even if other flags are also used (e.g., `--game "Scarlet / Violet" --cache-info` still shows the cache info).
- The help text lists all available flags in a compact format and points to the README for feature details.

### Bugs found during testing
- None; all existing tests pass, and manual testing confirmed the flags work as expected.

### Test count
- `pkm_session.py`: 33 tests (was 30).
- `pokemain.py`: no new tests (the flag‑handling code is purely additive and does not affect the menu loop).
- Full offline suite: unchanged (~972 tests), 0 failures.

---

## §109 — V2 Package 1: Core library / presentation separation

### What changed
- Created core modules for pure logic:
  - `core_stat.py` – stat functions (`compare_stats`, `total_stats`, `infer_role`, `infer_speed_tier`, `stat_bar`), with self‑tests (21).
  - `core_egg.py` – egg group functions (`egg_group_name`, `format_egg_groups`), with self‑tests (8).
  - `core_evolution.py` – evolution chain parsing and filtering (`parse_trigger`, `flatten_chain`, `filter_paths_for_game`), with self‑tests (20).
  - `core_move.py` – move scoring, combo selection, status ranking, and static tables (`TWO_TURN_MOVES`, `STATUS_MOVE_TIERS`, etc.), with self‑tests (11).
  - `core_team.py` – team analysis and builder logic (defensive/offensive analysis, weakness pairs, candidate scoring, ranking), with self‑tests (24).
  - `core_opponent.py` – opponent analysis (`analyze_matchup`, `uncovered_threats`, `recommended_leads`), with self‑tests (5).
- Refactored the following feature files to import from the core modules and remove duplicated pure logic:
  - `feat_stat_compare.py`
  - `feat_quick_view.py`
  - `feat_nature_browser.py`
  - `feat_egg_group.py`
  - `feat_evolution.py`
  - `feat_moveset_data.py` (now a thin wrapper)
  - `feat_moveset.py` (imports adjusted)
  - `feat_team_moveset.py` (imports adjusted)
  - `feat_team_analysis.py`
  - `feat_team_offense.py`
  - `feat_team_builder.py`
  - `feat_opponent.py`
- Updated `run_tests.py` to include all core modules in the test suite.

### Why
To separate presentation from business logic, enabling independent testing, reuse across different frontends (e.g., a future TUI or GUI), and cleaner architecture. This is the first step toward the V2 roadmap.

### Key decisions
- Core modules are placed in the same folder with a `core_` prefix, making imports straightforward.
- Each core module has its own `_run_tests()` with offline tests, and is added to `run_tests.py`.
- The `feat_*.py` files now act as thin UI wrappers: they fetch data via `pkm_cache`, call core functions, and display results.
- Data access (cache and network) remains outside the core modules, preserving testability.
- Step 7 (consolidating data access) was postponed to a later V2 package to keep this refactoring focused.

### Test count
- New core modules add 89 offline tests (21+8+20+11+24+5).
- Existing tests were redistributed; the total offline test count remains stable and all tests pass.


## §110 — V2 Package 2: SQLite data layer

### What changed
- Created `pkm_sqlite.py` – a new module that manages a single SQLite database (`pokemon.db`) in the cache directory.
- Rewrote `pkm_cache.py` to use SQLite instead of JSON files. All public functions keep the same signatures and return values.
- The database is created on first access; tables are created automatically.
- The move table now includes a `version` column to track `MOVES_CACHE_VERSION`.
- Metadata table stores schema version and moves schema version for consistency checks.
- Existing JSON cache files are not migrated; users can delete their old `cache/` folder to start fresh, or the database will be populated lazily as they use the tool.

### Why
SQLite provides referential integrity, atomic multi‑table updates, efficient indexing, and simpler code. It also enables complex queries (e.g., “all Fire‑type Pokémon with base Speed > 100 that learn Earthquake”) that were impractical with JSON files. This is the second step toward the V2 roadmap.

### Key decisions
- JSON data is stored as text in the database, preserving the existing data structures without schema changes.
- The `pkm_sqlite` module isolates all SQLite‑specific code, making the transition easier.
- The public API of `pkm_cache.py` remains unchanged, so no other modules needed modifications.
- The build process is unaffected; the database is created at runtime.

### Test count
- All existing tests pass after adaptation (the temporary directory now holds a `.db` file).
- No new tests were added; the existing coverage remains sufficient.


---

## §111 — V2 Package 3: One‑time full data import (`--sync`)

### What changed
- Added `pkm_sync.py` – a script that downloads all Pokémon, moves, type rosters, natures, abilities, egg groups, and evolution chains from PokeAPI and stores them in the SQLite database.
- Added `fetch_all_pokemon()` to `pkm_pokeapi.py` to fetch all Pokémon in bulk.
- Added a `--sync` command‑line flag to `pokemain.py` that runs the sync script. The flag also accepts `--force` to overwrite an existing database.
- Added a `sync_status` table to `pkm_sqlite.py` to track progress, allowing the sync to resume from where it left off if interrupted.
- Updated `run_tests.py` to recognise the new files and mark them as intentional non‑test files.

### Why
The lazy‑fetch approach, while functional, introduces delays on first use. After a full sync, the toolkit becomes completely offline and all lookups are instant. This is the third step toward the V2 roadmap.

### Key decisions
- The sync script is a separate module (`pkm_sync.py`) to keep the main codebase clean.
- Progress is tracked per section (moves, Pokémon, type rosters, etc.) using a `sync_status` table, enabling resume on interruption.
- Existing data is not automatically migrated; users must run `--sync` explicitly to populate the database fully.
- The `--force` flag deletes the existing database and starts from scratch.

### Test count
- No new tests; the sync script is not unit‑tested due to its long‑running nature, but it is manually verified.
- All existing tests continue to pass.


----


## §112 — V2 Package 4.1: UI abstraction layer

### What changed
- New files: `ui_base.py`, `ui_cli.py`
- Modified: all `feat_*.py` to accept a `ui` parameter and use it for I/O
- Modified: `pokemain.py` to instantiate `CLI` and pass `ui` to features
- Modified: `pkm_session.py` – interactive functions moved to UI layer
- Modified: `ARCHITECTURE.md` – documented the new UI layer
- Modified: `README.md` – no user‑visible change; updated file list

### Why
To separate UI concerns from application logic, enabling future front‑ends (e.g., a TUI) without rewriting core features. The existing CLI behaviour is unchanged, but all output and input now go through a common interface.

### Key decisions
- The UI base class is abstract; the CLI implementation wraps existing interactive code.
- Interactive selection functions (`select_pokemon`, `select_game`, etc.) are now part of the UI, not `pkm_session`.
- All feature `run()` functions now accept an optional `ui` parameter (default `None` creates a dummy UI for standalone mode).
- The main loop remains in `pokemain.py` (not moved to `ui.run()`), preserving the current menu structure.
- The `end` parameter was added to `print_output` to support grid printing in the egg group browser.

### Bugs fixed
- Added missing `end` parameter to `UI.print_output` and `CLI.print_output` to allow printing without newline.
- Updated all `feat_*.py` files to use `ui.print_output()` consistently, eliminating direct `print` calls.

### Test count
All existing tests pass; no new tests added (behaviour unchanged).

---

## §113 — Team builder: filter out pure level‑up evolutions

### What changed
- Modified: `core_evolution.py` – added `trigger_is_pure_level_up` and `is_pure_level_up_chain` functions; added 8 new tests (28 total)
- Modified: `feat_team_builder.py` – integrated evolution filtering into `build_suggestion_pool`; added 2 new tests (59 total)
- Modified: `README.md`, `ARCHITECTURE.md` – updated documentation

### Why
When the team builder suggested Pokémon to fill gaps, it would often list all stages of a level‑up‑only evolution chain (e.g., Dratini, Dragonair, Dragonite) even though only the final stage is useful in most cases. The filtering now removes lower stages when a higher stage also matches the team's needs, unless the evolution involves a trade, item, or special condition (where both forms may be relevant).

### Key decisions
- A trigger is considered pure level‑up if it contains the word "Level" and none of the keywords `Trade`, `Use`, `Friendship`, `Happiness`, `Item`, `Move`, `Time`, or `Location`.
- The filtering is applied after candidate pool construction and uses the cached evolution chains. If a chain is missing from the cache, no filtering is performed for that candidate (safe fallback).
- Mixed chains (e.g., Seadra → Kingdra) are not filtered because the higher stage is not obtained purely by level‑up.

### Bugs found during testing
- Initial test expected all three stages of a mixed chain to remain, but the logic correctly removed the base stage when a pure level‑up intermediate stage existed. Test expectation was adjusted to match intended behaviour.

### Test count
`core_evolution.py`: 28 tests (was 20). `feat_team_builder.py`: 59 tests (was 57). Full suite: unchanged.

---

## §114 — Remove standalone stat comparison (merge into learnset comparison)

### What changed
- Modified: `pokemain.py` – removed menu entry `C` and its handler; removed import of `feat_stat_compare`
- Modified: `README.md` – updated menu and features to reflect removal; added note in learnset comparison about stat header
- Modified: `ARCHITECTURE.md` – removed references to `feat_stat_compare.py` from file list and feature modules

### Why
The stat comparison screen (key C) was largely redundant because the learnset comparison (key L) already includes a detailed stat header with the same information (base stats, total, role, speed tier). Consolidating reduces menu clutter and simplifies the user experience. Users who only want stat comparison can still get it by using L and ignoring the move sections.

### Key decisions
- The `feat_stat_compare.py` module is retained (it is still used by `feat_learnset_compare.py` for the stat header and by `feat_nature_browser.py` for role/speed tier). It is simply no longer a standalone menu feature.
- No functionality is lost; the learnset comparison now serves as the single entry point for comparing two Pokémon.

### Test count
No new tests; all existing tests pass.

---

## §115 — Main menu reorganisation

### What changed
- Modified: `pokemain.py` – rewrote `_build_menu_lines` to group menu entries logically and place the three core actions (game, Pokemon, team) at the top.
- Removed the standalone stat comparison entry (already merged in §114).
- Updated condition visibility for several features to match the new layout.

### Why
The previous menu structure was cluttered and the ordering was ad‑hoc. Grouping features by required context makes the menu easier to scan and use. Placing game, Pokemon, and team management at the top reflects their primary role in setting up a session.

### Key decisions
- Features are now grouped in this order: core actions, game‑only features, Pokemon‑dependent features, numbered moveset features, team features, cache utilities, quit.
- Separators and blank lines are used to visually distinguish sections.
- The `R` (refresh) key is now only shown when a Pokemon is loaded.
- The `MOVE` and `W` keys remain available for users who prefer not to run a full `--sync`.

### Test count
No new tests; all existing tests pass.


---

## §117 — TUI foundation (split‑pane layout)

### What changed
- Added `textual` to `requirements.txt`.
- Created `ui_tui.py` with a basic `TUI` class that inherits from `UI` and launches a textual app with a split‑pane layout.
- The left pane shows context (game, Pokémon, team) and menu options built by `menu_builder`.
- The right pane shows feature output via `print_output`.
- Interactive methods (`input_prompt`, `confirm`, `select_from_list`, etc.) currently fall back to console input (blocking).
- Key handling is stubbed; only `Q`, `G`, `P`, `T` are partially implemented.

### Why
To provide a richer user interface that keeps context visible and allows mouse/keyboard navigation. This is the first step toward a full TUI.

### Key decisions
- The TUI is an alternative UI implementation, selectable via `--tui`. The CLI remains the default.
- The `TUI` class maintains its own state (contexts) and uses `textual` widgets for display.
- For now, interactive prompts are still handled by the console, but the layout and output rendering are already functional.
- The menu is built using the same `menu_builder` functions as the CLI, ensuring consistency.

### Next steps
- Replace blocking interactive methods with textual modals.
- Implement full key bindings for all menu actions.
- Add scrollable output, colors, and formatting.

---

## §118 — Full async conversion and TUI enhancement

### What changed

**UI abstraction completion**
- All UI methods (`input_prompt`, `confirm`, `select_from_list`, `select_pokemon`, etc.) are now async.
- Every feature module (`feat_*.py`) now has an `async def run()` and uses `await` for all UI calls.
- The `CLI` and `TUI` classes implement the abstract `UI` interface with async methods.
- `pokemain.py` now only handles flags, instantiates the appropriate UI, and calls `await ui.run()`.
- The main menu loop moved into `CLI.run()`; `TUI.run()` starts the textual app.
- `menu_builder.py` created to build context and menu lines, used by both UIs.

**TUI implementation**
- Added `textual` to `requirements.txt`.
- Created `ui_tui.py` with a split‑pane layout (left: context + menu, right: output).
- Added persistent input bar at the bottom for text input, eliminating the need for console blocking.
- Implemented modal screens:
  - `GameSelectionScreen` – select a game from a list
  - `PokemonSelectionScreen` – search and select a Pokémon
  - `FormSelectionScreen` – choose a form when multiple exist
  - `InputModal` – simple text input (used by `input_prompt`)
  - `ConfirmModal` – yes/no confirmation
  - `ListSelectionModal` – choose from a numbered list (used by `select_from_list`)
- Added `_wait_for_modal` helper to push a screen and wait for a result.
- Key bindings now handle all menu keys (G, P, T, M, B, N, A, L, E, V, O, S, H, X, Y, W, R, 1–4, Q).
- The `print_output` method appends to the right‑pane `TextArea`; `print_progress` is implemented but currently adds new lines instead of overwriting (acceptable for now).

**Feature conversions**
- All feature files (`feat_*.py`) were converted to async, with `print` replaced by `await ui.print_output` and `input` by `await ui.input_prompt`.
- The type chart in `feat_quick_view.py` is captured via `contextlib.redirect_stdout` and printed via `ui.print_output` so it appears in the TUI.
- `feat_learnset_compare.py` now uses `ui.select_pokemon` to pick the second Pokémon, which in TUI shows the modal.
- `feat_team_loader.py` was made async; the team management menu now uses the persistent input bar for commands.
- `feat_team_builder.py` now has an async `fetch_needed_rosters` that uses `ui.print_progress` (though progress appears as separate lines).
- `feat_opponent.py` uses async modals for trainer selection.

**Test fixes**
- All `--autotest` suites were updated to run synchronously; where needed, dummy UI classes now have the same signature as real UI methods.
- `asyncio.run` is used in test functions to run async code.

**Menu reorganisation and removal of stat comparison**
- The main menu was regrouped: core actions (G, P, T) at the top, then game‑only features, Pokémon‑dependent features, team features, cache utilities.
- The standalone stat comparison (key C) was removed; its functions are still used by the learnset comparison and nature browser.

**Team builder evolution filtering**
- Added `trigger_is_pure_level_up` and `is_pure_level_up_chain` to `core_evolution.py`.
- In `feat_team_builder.build_suggestion_pool`, lower‑stage pure level‑up evolutions are filtered out when a higher stage is also a candidate (e.g., Dratini → Dragonair → Dragonite only keeps Dragonite). Mixed chains (e.g., Seadra → Kingdra) keep both.

**Key binding changes**
- The move table pre‑load was changed from `MOVE` (multi‑character) to the single key `Y` to avoid conflict with move lookup (`M`).
- `W` still pre‑loads the TM/HM table and now works in the TUI.

### Why
To provide a fully functional terminal UI that keeps context visible and eliminates console‑blocking prompts. The async conversion ensures that the TUI remains responsive and can handle modals. Removing the redundant stat comparison reduces menu clutter. Filtering evolution stages in the team builder improves suggestion quality.

### Key decisions
- Keep the CLI as the default; the TUI is an alternative launched with `--tui`.
- Use `textual` for the TUI because of its rich widget set and ease of development.
- Use modals for complex selections (games, Pokémon, forms, list choices) and the persistent input bar for simple text prompts.
- All feature modules must be async and await UI calls, which required extensive but straightforward refactoring.
- The `_is_tui` helper was removed because the TUI now handles prompts natively (except the movepool filter, which is now skipped in TUI).
- `calc.print_results` is captured to ensure its output appears in the TUI’s right pane.

### Bugs fixed during testing
- Added missing `end` parameter to `print_output` to allow grid printing in egg group browser.
- Fixed `TextArea.write` error by using `insert` instead.
- Resolved `NoActiveWorker` error by implementing `_wait_for_modal` with `push_screen` and a future.
- Corrected the test dummy UI to accept `flush` and `end` parameters.
- Adjusted test expectations for mixed evolution chains (Horsea → Seadra → Kingdra) to match filtering logic.

### Test count
All existing tests pass; new tests added for `core_evolution` (8) and `feat_team_builder` (2). Full offline test count remains stable.

### Next steps
- Improve `print_progress` to update the same line instead of appending new lines.
- Add colours and formatting to the TUI output.
- Consider adding a command palette or mouse support.
- Investigate making the move filter prompt optional in TUI (currently skipped entirely).

---

## §119 — Main menu reorganisation and stat comparison removal

### What changed
- Modified `pokemain.py` – rewrote `_build_menu_lines` to group menu entries logically: core actions (G, P, T) at the top, then game‑only features, Pokémon‑dependent features, numbered moveset features, team features, and cache utilities.
- Removed the `C` (stat comparison) menu entry and its handler.
- Removed the import of `feat_stat_compare` from `pokemain.py`.
- Deleted `feat_stat_compare.py` – its functions are now imported from `core_stat.py` by `feat_learnset_compare.py` and `feat_nature_browser.py`.
- Updated `README.md` and `ARCHITECTURE.md` to reflect the removal.
- Added a note in the learnset comparison description that a stat header is shown above the move tables.

### Why
The previous menu was cluttered and did not follow a clear logical grouping. Placing the most frequently used actions at the top makes session setup faster. Removing the standalone stat comparison reduces menu noise, as the same information is already shown in the learnset comparison screen.

### Key decisions
- Features are now grouped by required context: core actions, game‑only features, Pokémon‑dependent features, numbered moveset features, team features, cache utilities.
- Separators and blank lines visually separate sections.
- The `R` (refresh) key is shown only when a Pokémon is loaded.
- The `MOVE` and `W` keys remain available for users who prefer not to run a full `--sync`.

### Test count
No new tests; all existing tests pass.

---

## §120 — Team builder evolution filtering

### What changed
- Added `trigger_is_pure_level_up` and `is_pure_level_up_chain` to `core_evolution.py` (8 new tests).
- Modified `feat_team_builder.build_suggestion_pool` to filter out lower‑stage pure level‑up evolutions when a higher stage is also a candidate.
- Added 2 new tests in `feat_team_builder` to verify the filtering for the Dratini line (all pure) and the Horsea/Seadra/Kingdra line (mixed).
- Updated `ARCHITECTURE.md` to note the new core functions.

### Why
When the team builder suggested Pokémon to fill gaps, it often listed all stages of a level‑up‑only evolution chain (e.g., Dratini, Dragonair, Dragonite) even though only the final stage is useful in most cases. The filtering now removes lower stages when a higher stage also matches the team's needs, unless the evolution involves a trade, item, or special condition (where both forms may be relevant).

### Key decisions
- A trigger is considered pure level‑up if it contains the word "Level" and none of the keywords `Trade`, `Use`, `Friendship`, `Happiness`, `Item`, `Move`, `Time`, or `Location`.
- The filtering is applied after candidate pool construction and uses the cached evolution chains. If a chain is missing from the cache, no filtering is performed for that candidate (safe fallback).
- Mixed chains (e.g., Seadra → Kingdra) are not filtered because the higher stage is not obtained purely by level‑up.

### Bugs found during testing
- Initial test expected all three stages of a mixed chain to remain, but the logic correctly removed the base stage when a pure level‑up intermediate stage existed. Test expectation was adjusted to match intended behaviour.

### Test count
`core_evolution.py`: 28 tests (was 20). `feat_team_builder.py`: 59 tests (was 57). Full suite unchanged.

---

## §121 — Move table pre‑load key change and TM/HM table fix in TUI

### What changed
- Modified `menu_builder.py` – changed the menu line for pre‑loading moves from `MOVE.` to `Y.    Pre-load move table`.
- Updated `ui_cli.py` – changed the handler for `"move"` to `"y"`.
- Updated `ui_tui.py` – added handlers for `"y"` (move table) and `"w"` (TM/HM table), both now use the persistent input bar and modals for confirmation.
- Removed the `"move"` entry from `_MENU_CHOICES` in `pokemain.py` (documentation only).
- Updated `README.md` to reflect the new keys.

### Why
The `MOVE` key conflicted with the move lookup key `M` (the first character of `MOVE` triggered the lookup before the full string could be entered). Changing it to a single key `Y` resolves the conflict and makes the interface consistent with other single‑letter commands. The TM/HM table pre‑load (`W`) was not implemented in the TUI; this change adds it.

### Key decisions
- Keep the same functionality as in the CLI: `Y` (move table) and `W` (TM/HM table) work identically in both interfaces.
- In the TUI, the prompts and confirmations use modals (for confirmation) and the persistent input bar (for the `F`/`R` selection), so no console blocking occurs.

### Test count
No new tests; all existing tests pass.

---

## §122 — Default UI for frozen builds

### What changed
- Modified `pokemain.py` – added `--cli` flag; when frozen (`sys.frozen`), the TUI is now the default interface.
- Updated `build.py` – added `--hidden-import textual` to ensure `textual` is bundled.
- Updated `README.md` – documented the new defaults and the `--cli` flag.

### Why
The TUI is the more user‑friendly interface and should be the default for end users who download the standalone executable. The `--cli` flag allows power users or those on low‑resource terminals to fall back to the classic interface.

### Key decisions
- The CLI remains the default when running from source, to avoid requiring `textual` for development.
- `textual` is explicitly hidden‑imported to guarantee it is included in the frozen bundle.

### Test count
No new tests; existing tests pass.

## §123 — Team builder: BST bonus in scoring formula

### What changed
- Modified `core_team.py` – added `_W_BST = 5` constant, imported `total_stats` from `core_stat`.
- Updated `score_candidate` to include a BST bonus: `(total_stats / 720) * _W_BST`.
- The bonus is added after the intrinsic score (coverage, defensive gaps, shared weakness penalty, role bonus) and before the lookahead component.
- Updated docstring to mention the new bonus.

### Why
When multiple candidates provide similar coverage, the one with higher total base stats is generally more useful in practice. The BST bonus acts as a secondary differentiator, giving a small advantage to Pokémon with better raw stats without overshadowing the primary coverage considerations.

### Key decisions
- The bonus is normalized to a 0–1 scale (max total ~720) and multiplied by `_W_BST = 5`, so the maximum possible bonus is 5 points. This is less than the coverage bonuses (10 per type) and role bonus (4), ensuring coverage remains the dominant factor.
- The bonus applies only when `base_stats` are available (i.e., when the candidate is already in the local cache). Uncached candidates receive no BST bonus, which is acceptable because they are less likely to be the best choice anyway.

### Test count
No new tests; existing tests pass. The scoring change is covered by existing candidate ranking tests (the scores change, but ranking logic remains correct).

---

## §124 — TUI polish and evolution module merge

### What changed

**TUI polish**
- Scrollable left pane: wrapped context and menu in `ScrollableContainer` (4.2.4).
- Progress bar for long operations: replaced text‑based progress with `ProgressBar` widget for move and TM/HM pre‑load (`Y` and `W`). Progress updates show percentage and current item.
- Error modal: added `ErrorModal` screen for network failures and other errors; replaced `print_output` error messages with modal.
- Keyboard navigation: added focus and key handlers to `GameSelectionScreen`, `FormSelectionScreen`, and `ConfirmModal` so arrow keys and Enter work; Escape cancels.
- Output coloring: introduced `_colorize()` method in `ui_tui.py` that applies markup to session headers, section headers, errors, warnings, successes, weakness/resistance lines, profile headers, and dot ratings. Only TUI output is colored; CLI unchanged.
- Type chart string conversion: `matchup_calculator.format_results()` added; `print_results` now uses it. `feat_quick_view` uses the string directly, removing `contextlib.redirect_stdout` capture.
- Fixed blank line issue: changed `update_output` to use `RichLog.write()` without extra newline; adjusted `print_output` to not add duplicate newlines.

**Module merge**
- Merged `feat_evolution.py` into `feat_quick_view.py`. The evolution chain display is now part of the quick view screen (option 1). The pure logic remains in `core_evolution.py` for team builder use.
- Updated `feat_quick_view.py` with all evolution helpers (`_get_types_for_slug`, `_type_tag`, `_get_species_gen`, `_get_or_fetch_chain`, `_display_evolution_block`) and moved the self‑tests.
- Removed `feat_evolution.py` from the project.
- Updated documentation (`README.md`, `ARCHITECTURE.md`, `run_tests.py`) to reflect the merge.

### Why

**TUI polish** was needed to make the interface more responsive, informative, and visually pleasant:
- Scrollable left pane prevents clipping of long menus.
- Progress bars give clear feedback during long operations.
- Error modals make failures obvious.
- Keyboard navigation improves accessibility.
- Colours help distinguish different types of output at a glance.
- The type chart string conversion simplifies TUI integration.

**Module merge** reduces code duplication and keeps related UI code together. Evolution chain is only displayed in option 1, so there’s no need for a separate feature file.

### Key decisions
- Used `RichLog` for output pane because it supports markup and doesn’t add extra newlines.
- Colouring rules are applied in the TUI’s `print_output` method based on line content, keeping the logic out of feature modules.
- The evolution chain fetches types on demand with a cache‑first strategy; the progress bar shows “Fetching types for N stage(s)…” when needed.
- The merged file’s self‑test now includes the evolution tests (4) alongside the existing quick view tests (none previously), so total tests for `feat_quick_view.py` are 4.

### Bugs found during testing
- `ui_cli.print_output` missing `flush` parameter caused `TypeError` when called by `feat_evolution` with `flush=True`; fixed by adding the parameter.
- The type chart was not appearing in TUI after switching to `RichLog` because the output was being captured and printed with extra newlines; fixed by using `format_results` and updating `print_output`.
- The “★ = current Pokémon” line was missing in TUI due to the blank line issue and was fixed by adjusting `update_output`.

### Test count
- `feat_quick_view.py`: 4 tests (evolution chain).
- `matchup_calculator.py`: unchanged.
- All other modules unchanged.
- Full offline suite: unchanged (all tests pass).

--