# ROADMAP.md
# Long-term feature goals for the Pokemon Toolkit

> Items marked ✅ are complete. Items marked ⬜ are planned.
> Each planned item carries a **Pythonmon-N** identifier used in TASKS.md and HISTORY.md
> to prevent ambiguity during implementation and AI handoffs.
> For granular steps of the item currently in progress, see TASKS.md.
> For completed item details, see HISTORY.md.

---

## Completed features

| Feature | Description | History ref |
|---|---|---|
| Core CLI skeleton | Menu loop, game + Pokemon context, cache layer | §1–§11 |
| Web scraper (move data) | pokemondb.net move table + modifications scraper | §1–§11 |
| PokeAPI migration | Replaced web scraper with PokeAPI; move versioning schema | §12–§13 |
| Type vulnerabilities | Full defensive chart, all 3 type chart eras | §15 |
| Learnable move list | Level-up / TM-HM / tutor / egg with stats per row | §16–§19 |
| Moveset recommendation | Scored pool + 3 modes (Coverage / Counter / STAB), locked slots | §21–§50 |
| Type coverage display | Types hit SE shown in moveset output; uncoverable weakness annotation | §44, §54 |
| Per-variety learnsets | Regional / alternate forms get correct move pool (variety_slug) | §42–§43 |
| Type browser | List all Pokemon of a given type or type combo | §51–§52 |
| Nature browser | 25-nature table + stat recommender by role and speed tier | §53 |
| Ability browser | Browse all abilities + full effect + Pokemon roster drill-in | §57 |
| Quick view (option 1) | Base stats bar chart + abilities + type chart in one screen | §58 |
| Team loader | Session-only team of up to 6 Pokemon; T key; add/remove/clear | §59 |
| Team defensive analysis | Unified type table: weak/resist/immune per type, gap labels | §60–§61 |
| Team offensive coverage | Per-type hitter table with best scored move per hitting type; O key | §62–§64 |
| Team moveset synergy | Per-member recommended movesets + team coverage summary; S key | §66–§71 |
| Quick wins batch (Pythonmon 1–4, 16) | Loading indicator (S screen), fuzzy name search, batch move upserts, session pool cache, get_form_gen bug fix | §72–§76 |
| Quick wins batch 2 (Pythonmon 5, 12, 13) | Cache integrity check (`--check-cache`), add-to-team prompt after P, partial move refresh (F option in MOVE) | §77–§79 |
| Per-form learnset fix (Pythonmon-10) | `fetch_pokemon` stores `form_slug` as `variety_slug`; correct learnset for forms where form slug ≠ variety slug | §80 |

---

## Planned improvements

### 🔧 Backend / robustness

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-1 | S screen loading indicator | ✅ Done §72 — `print()` before engine call in `run()`, matching O screen style. | 🟢 Low |
| Pythonmon-3 | Batch move upserts | ✅ Done §74 — `build_candidate_pool` writes `moves.json` once at end of fetch loop. Meaningful speedup on first-run with large learnsets. | 🟡 Medium |
| Pythonmon-4 | Session pool caching for O and S | ✅ Done §76 — session dict in `pokemain.py`; `pool_cache` parameter added to `run()` and pool-building functions in both O and S screens. | 🟢 Low |
| Pythonmon-12 | Stale moves partial refresh | ✅ Done §79 — `fetch_missing_moves()` in `pkm_pokeapi`; MOVE handler updated with F/R/Enter menu. | 🟡 Medium |
| Pythonmon-13 | Cache integrity check | ✅ Done §77 — `check_integrity()` in `pkm_cache`; `--check-cache` flag in `pokemain`; 4 new tests. | 🟢 Low |
| Pythonmon-17 | Cache size report | ✅ Done §92 — `get_cache_info()` in `pkm_cache`; `--cache-info` flag in `pokemain`; 10-layer table with totals; 6 new tests (52 → 58). | 🟢 Low |
| Pythonmon-18 | Offline mode detection | ✅ Done §93 — `check_connectivity()` in `pkm_pokeapi`; startup warning in `pokemain.main()` when cache sparse (< 5 pokemon) and PokeAPI unreachable; 3 new offline mock tests (11 → 14). | 🟢 Low |
| Pythonmon-19 | Learnset staleness flag | ✅ Done §94 — `LEARNSET_STALE_DAYS=30` + `get_learnset_age_days()` in `pkm_cache`; note printed in options 2/3/4 when age > 30 days; 4 new tests (58 → 62). | 🟢 Low |

---

### 🖥️ UX improvements

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-2 | Fuzzy name matching | ✅ Done §73 — Accept partial Pokemon names in `pkm_session`. Search against `pokemon_index.json` keys; show ranked suggestions (same pattern as `match_move`). Only finds previously cached Pokemon. | 🟢 Low |
| Pythonmon-5 | Add-to-team prompt after P | ✅ Done §78 — 10-line addition to the P handler in `pokemain.py`; suppressed when no game loaded or team full. | 🟢 Low |
| Pythonmon-6 | Move filter in pool | ✅ Done §81 — `_apply_filter` + `_passes_filter` (pure); `_prompt_filter` (interactive); `_display_learnset` gains `filter_spec=None`; full table shown first, `f` to filter at bottom. 7 new tests (9 → 16). | 🟢 Low |
| Pythonmon-20 | Move filter on scored pool | ✅ Done §95 — `_adapt_pool_for_filter` + `_display_filtered_scored_pool` in `feat_moveset`; filter prompt at bottom of `run_scored_pool()`; 5 new tests (28 → 33). | 🟢 Low |
| Pythonmon-21 | Team text export | ~~Parked~~ — `team_summary_line()` already shown in the menu header on every screen; a dedicated export adds minimal value. | 🟢 Low |
| Pythonmon-22 | Batch team load | ✅ Done §96 — `_resolve_batch_name` + `_build_pkm_ctx_from_cache` + `_load_batch`; comma detection in `_team_menu`; cache-only, ambiguous→first-alpha; 11 new tests (28 → 39). | 🟡 Medium |
| Pythonmon-23 | Persistent game selection | ~~Parked~~ — game context survives the session already; re-selecting on restart is quick especially with the short GAMES list (17 entries). | 🟢 Low |

---

### 🧬 Pokemon features

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-8 | Stat comparison | ✅ Done §82 — new `feat_stat_compare.py`; `compare_stats` + `total_stats` (pure); side-by-side bar display; key `C` in pokemain; 13 tests. | 🟢 Low |
| Pythonmon-9 | Evolution chain | ✅ Done §89–§91 — pure parsing (§89A, 16 tests); schema/API/cache + `--refresh-evolution` + R key (§90B, 52 pkm_cache tests); display with gen-filter + `filter_paths_for_game` (§91C, 35 feat_evolution tests). Bug fix: `held_item` field for trade evolutions, `time_of_day` for friendship evolutions. | 🔴 High |
| Pythonmon-10 | Per-form learnset | ✅ Done §80 — `fetch_pokemon` stores `form_slug` as `variety_slug`; 12 new offline tests. Investigation found Rotom appliances are already separate varieties in PokeAPI; fix covers the narrower case where form slug ≠ variety slug. | 🟡 Medium |
| Pythonmon-11 | Team builder / slot suggestion | ✅ Done §100 — new `feat_team_builder.py`; pure scoring engine (A), pool builder (B), display (C), `run()` + key `H` (D); 57 tests. Gap analysis, patchability lookahead, dot rating, per-type roster fetch with progress. | 🔴 High |
| Pythonmon-24 | EV training recommendation | ✅ Done §98 — integrated into `feat_nature_browser` as combined Nature & EV build advisor; two profiles (speed-safe vs power-max); `_calc_stat` + `build_profiles` + `_print_build_profiles`; assumes Lv 100 / 31 IVs; 21 new tests (27 → 48). | 🟡 Medium |
| Pythonmon-25 | Speed tier display | ~~Parked~~ — fully covered by §83: option 1 already shows "Speed: Fast (base N)" with exact value, and option C shows tier side-by-side. Benchmark table adds no material information. | 🟢 Low |
| Pythonmon-26 | Learnset comparison | ✅ Done §99 — new `feat_learnset_compare.py`; `_flat_moves` + `compare_learnsets` (pure); compact stat header above three move sections; key `L`; 20 tests. | 🟡 Medium |
| Pythonmon-27 | Egg group browser | ✅ Done §86–§88 — `egg_groups` field in pokemon cache (§86A); `fetch_egg_group` + `get/save_egg_group` + `check_integrity` (§87B); full roster browser key E + quick view inline (§88C). Bug fix: `egg_groups` missing from `pkm_ctx` in `select_pokemon`. 47 pkm_cache + 18 feat_egg_group tests. | 🟡 Medium |
| Pythonmon-28 | Move effect description | ✅ Done §84 — `"effect"` field added to `fetch_move` and `fetch_all_moves`; `MOVES_CACHE_VERSION` bumped to 3; Effect line in `_display_move`; 2 new tests in feat_move_lookup (12 → 14), 1 in pkm_cache (37 → 38). | 🟢 Low |
| Pythonmon-32 | Role & speed tier in quick view and stat compare | ✅ Done §83 — `infer_role` + `infer_speed_tier` added as public API to `feat_stat_compare.py`; removed from `feat_nature_browser` (now imports them); Role/Speed line added to option 1 and option C; 13 new tests (13 → 26). | 🟢 Low |

---

### 👥 Team features (new)

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-29 | Team speed tier table | ~~Parked~~ — superseded by Pythonmon-25 parking rationale; per-member Speed is visible in the stats bar (option 1) and the tier is shown inline. Low marginal value as a dedicated team screen. | 🟢 Low |
| Pythonmon-30 | Weakness overlap heatmap | ✅ Done §97 — `build_weakness_pairs` + `gap_pair_label` + `_print_weakness_pairs`; pairs ≥2 shared shown below gap summary; `!! CRITICAL` at ≥3; 17 new tests (58 → 75). | 🟡 Medium |
| Pythonmon-31 | Team coverage vs specific opponent | Deferred pending trainer data. Ideal UX requires a built-in gym leader / Elite Four table (name → type combo) per game, but PokeAPI has no trainer endpoint (open issues since 2019). Type-combo input alone lacks the key use case ("beat Cynthia"). Revisit if PokeAPI adds trainer data, or if we build a static table separately. | 🟡 Medium |

---

### 🔧 Technical debt

| ID | Item | Description | Complexity |
|---|---|---|---|
| TD-1 | Duplicate `L` menu line | ✅ Done §101 — single-line deletion in `_print_menu()`. | 🟢 Low |
| TD-2 | Inconsistent team handler style | ✅ Done §101 — merged V/O/S/H into one `if` block; `>= 1` → `> 0`. | 🟢 Low |
| TD-3 | `_handle_refresh_flags` mixed concerns | ✅ Done §101 — split into `_handle_diagnostic_flags` (exits) and `_handle_refresh_flags` (mutates); both called from `main()`. | 🟢 Low |
| TD-4 | `_MACHINES_FILE` defined twice in `pkm_cache.py` | ✅ Done §102 — deleted redundant second definition at line 462. | 🟢 Low |
| TD-5 | `_learnset_path` and `game_to_slug` layout in `pkm_cache.py` | ✅ Done §102 — constant block now uninterrupted; both helpers moved to a dedicated "Slug and path helpers" section. | 🟢 Low |
| TD-6 | `build_candidate_pool` name collision | ✅ Done §102 — `feat_team_builder.build_candidate_pool` renamed to `build_suggestion_pool`. | 🟢 Low |

---

### 📦 Packaging

| ID | Item | Description | Complexity |
|---|---|---|---|
| PKG-1 | `pkm_cache._BASE` relocation for frozen builds | ✅ Done §103 — frozen-path detection added; `sys.frozen` guard redirects `_BASE` to folder next to executable when bundled; 3 new tests (62 → 68 in pkm_cache). | 🟢 Low |
| PKG-2 | PyInstaller single-file executable | ✅ Done §103 — PKG-1 in place; run `python build.py` on target platform to produce `dist/pokemain.exe` / `dist/pokemain`. No further code work required. | 🟡 Medium |
| PKG-3 | `build.py` helper script | ✅ Done §103 — new `build.py`; `--clean` flag; PyInstaller availability check with clear error; platform-aware output path; distribution instructions printed after successful build. | 🟢 Low |

---

### ⛔ Blocked

| ID | Feature | Blocker |
|---|---|---|
| Pythonmon-15 | Legends: Z-A cooldown system | PokeAPI does not yet model the Z-A cooldown mechanic. Revisit once PokeAPI adds support. |

---

## Parked — considered but not planned

Items we have thought through and deliberately set aside. Kept here so the
reasoning is not lost. Revisit if priorities change.

| ID | Feature | Why parked |
|---|---|---|
| Pythonmon-7 | History within session | Low daily impact — pressing P again is fast enough, especially with fuzzy matching (Pythonmon-2) now in place. |
| Pythonmon-14 | STATUS_MOVE_TIERS auto-update | Requires a design decision on where user overrides live, and the current hand-curated list covers all common moves. Revisit if new games introduce many unrecognised status moves. |
| Pythonmon-21 | Team text export | `team_summary_line()` already shown in menu header on every screen; dedicated export adds no material value. |
| Pythonmon-23 | Persistent game selection | Game context survives the session; re-selecting on restart is quick with 17-entry list. |
| Pythonmon-25 | Speed tier display | Fully covered by §83: option 1 shows "Speed: Fast (base N)", option C shows tier side-by-side. Benchmark table adds no material information. |
| Pythonmon-29 | Team speed tier table | Superseded by Pythonmon-25 parking; per-member Speed visible in stats bar (option 1). Low marginal value as a dedicated team screen. |

---

## Out of scope (deliberate)

- **Team persistence** — the session is short (1 game + up to 6 Pokemon); re-entering is acceptable. May revisit if usage patterns change.
- **GUI / web interface** — CLI by design; runs from any terminal
- **Online multiplayer meta analysis** — this tool is for in-game teams, not competitive
- **Database migration** — JSON cache is sufficient; SQLite documented as future option only
- **Pip packages beyond requests** — hard constraint

---
