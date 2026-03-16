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
