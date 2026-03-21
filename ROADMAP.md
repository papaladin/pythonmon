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
| Pythonmon-17 | Cache size report | `--cache-info` flag (or section within `--check-cache`) showing count of cached Pokemon, learnsets, moves, abilities, types. Diagnostic companion to `--check-cache`. | 🟢 Low |
| Pythonmon-18 | Offline mode detection | Detect network failure at startup and print a clear warning: "PokeAPI unreachable — running from cache only". Currently the error surfaces deep in a fetch call. | 🟢 Low |
| Pythonmon-19 | Learnset staleness flag | Show `(cached X days ago)` note on the session header for learnsets older than N days. Useful after a new game patch. | 🟢 Low |

---

### 🖥️ UX improvements

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-2 | Fuzzy name matching | ✅ Done §73 — Accept partial Pokemon names in `pkm_session`. Search against `pokemon_index.json` keys; show ranked suggestions (same pattern as `match_move`). Only finds previously cached Pokemon. | 🟢 Low |
| Pythonmon-5 | Add-to-team prompt after P | ✅ Done §78 — 10-line addition to the P handler in `pokemain.py`; suppressed when no game loaded or team full. | 🟢 Low |
| Pythonmon-6 | Move filter in pool | ✅ Done §81 — `_apply_filter` + `_passes_filter` (pure); `_prompt_filter` (interactive); `_display_learnset` gains `filter_spec=None`; full table shown first, `f` to filter at bottom. 7 new tests (9 → 16). | 🟢 Low |
| Pythonmon-20 | Move filter on scored pool | Extend the §81 filter to option 3 (scored pool). Same three constraints (type / category / min power). Near-copy of the `feat_movepool` filter work applied to `feat_moveset`. | 🟢 Low |
| Pythonmon-21 | Team text export | After pressing `T`, offer to print the team as a copyable one-liner (e.g. `Charizard / Blastoise / Venusaur`). No file I/O — one `print()`. | 🟢 Low |
| Pythonmon-22 | Batch team load | In the T sub-menu, accept a comma-separated list of names to fill multiple slots at once (e.g. `char, blastoise, gengar`). Each name goes through the existing fuzzy picker. | 🟡 Medium |
| Pythonmon-23 | Persistent game selection | `--game "Scarlet / Violet"` startup flag that skips the game selection prompt. Useful for users who always work in the same game. | 🟢 Low |

---

### 🧬 Pokemon features

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-8 | Stat comparison | ✅ Done §82 — new `feat_stat_compare.py`; `compare_stats` + `total_stats` (pure); side-by-side bar display; key `C` in pokemain; 13 tests. | 🟢 Low |
| Pythonmon-9 | Evolution chain | ✅ Done §89–§91 — pure parsing (§89A, 16 tests); schema/API/cache + `--refresh-evolution` + R key (§90B, 52 pkm_cache tests); display with gen-filter + `filter_paths_for_game` (§91C, 35 feat_evolution tests). Bug fix: `held_item` field for trade evolutions, `time_of_day` for friendship evolutions. | 🔴 High |
| Pythonmon-10 | Per-form learnset | ✅ Done §80 — `fetch_pokemon` stores `form_slug` as `variety_slug`; 12 new offline tests. Investigation found Rotom appliances are already separate varieties in PokeAPI; fix covers the narrower case where form slug ≠ variety slug. | 🟡 Medium |
| Pythonmon-11 | Team builder / slot suggestion | Given a partial team (1–5 members), suggest types / roles that fill defensive and offensive gaps. Highest-complexity team feature; depends on the type roster cache being populated. | 🔴 High |
| Pythonmon-24 | EV training recommendation | Given a Pokemon and a role (Physical / Special / Bulky / Fast), suggest an EV spread with reasoning. Pure calculation — no new data. New `feat_ev_advisor.py`. | 🟡 Medium |
| Pythonmon-25 | Speed tier display | For the loaded Pokemon, show its Speed against key base Speed benchmarks (90 / 100 / 110 / 130) and how it compares to team members. Pure calculation from cached `base_stats`. | 🟢 Low |
| Pythonmon-26 | Learnset comparison | Compare learnsets of two Pokemon in the same game: moves unique to A, unique to B, shared. Builds on cached learnset data. New `feat_learnset_compare.py`. | 🟡 Medium |
| Pythonmon-27 | Egg group browser | ✅ Done §86–§88 — `egg_groups` field in pokemon cache (§86A); `fetch_egg_group` + `get/save_egg_group` + `check_integrity` (§87B); full roster browser key E + quick view inline (§88C). Bug fix: `egg_groups` missing from `pkm_ctx` in `select_pokemon`. 47 pkm_cache + 18 feat_egg_group tests. | 🟡 Medium |
| Pythonmon-28 | Move effect description | ✅ Done §84 — `"effect"` field added to `fetch_move` and `fetch_all_moves`; `MOVES_CACHE_VERSION` bumped to 3; Effect line in `_display_move`; 2 new tests in feat_move_lookup (12 → 14), 1 in pkm_cache (37 → 38). | 🟢 Low |
| Pythonmon-32 | Role & speed tier in quick view and stat compare | ✅ Done §83 — `infer_role` + `infer_speed_tier` added as public API to `feat_stat_compare.py`; removed from `feat_nature_browser` (now imports them); Role/Speed line added to option 1 and option C; 13 new tests (13 → 26). | 🟢 Low |

---

### 👥 Team features (new)

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-29 | Team speed tier table | New team sub-screen showing all 6 members ranked by Speed with key base Speed benchmarks (90 / 100 / 110 / 120 / 130) as reference lines. Pure calculation from cached `base_stats`. | 🟢 Low |
| Pythonmon-30 | Weakness overlap heatmap | Extend the V screen to highlight pairs of members sharing 3+ weaknesses (e.g. "Charizard and Blastoise are both weak to Rock and Electric"). Currently V aggregates by type but does not cross-reference pairs. | 🟡 Medium |
| Pythonmon-31 | Team coverage vs specific opponent | Given a single opponent type combo (e.g. "Water / Ground"), show which team members resist it, which are weak, and which have SE moves against it. Targeted combination of V + O logic. | 🟡 Medium |

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

---

## Out of scope (deliberate)

- **Online multiplayer meta analysis** — this tool is for in-game teams, not competitive

---

## Long-term architectural vision

> These items represent a potential future version of the project — a ground-up
> rethink of the foundation rather than incremental feature additions.
> They are not assigned Pythonmon IDs and are not planned for the near term.
> They are documented here so the direction is explicit and the reasoning is preserved.
> The current architecture remains the active target for all ongoing work.

---

### 🗄️  SQLite data layer

**What:** Replace the JSON file cache with a local SQLite database. All Pokemon,
learnset, move, evolution, and roster data live in a single structured file with
proper relational tables and indexes.

**Why:** The current JSON cache is a hand-rolled relational database. Pokemon files
reference learnset files which reference move entries — these are foreign key
relationships that JSON cannot enforce. Schema changes require version-bump hacks
and transparent re-fetch logic. SQLite gives all of this for free: referential
integrity, real querying, atomic multi-table writes, and standard migration tooling.

**What it brings:** Faster lookups on large datasets, elimination of the per-file
atomic-write complexity, proper schema migrations, and the ability to query across
entities (e.g. "all Pokemon that learn Earthquake and have base Speed > 100")
without loading every individual file.

---

### 📦  One-time full data import

**What:** Replace lazy per-entity PokeAPI fetching with a single bulk import that
downloads the complete PokeAPI dataset into the local database on first run.

**Why:** The current cache-miss latency (network call mid-session when a Pokemon or
move hasn't been looked up before) is the single most disruptive part of the user
experience. Every first lookup for a new Pokemon stalls. With a full upfront import,
the tool is either fully ready or it isn't — no partial states, no mid-session
surprises.

**What it brings:** Truly instant responses for all lookups after the initial setup.
No more "Fetching learnset..." interruptions. The offline-first principle becomes
unconditional rather than cache-dependent. Setup becomes a single explicit step
("sync data") rather than an invisible background process.

---

### 🏗️  Core library / presentation separation

**What:** Split the codebase into two distinct layers: a pure logic library (no I/O,
no print statements, no `input()` calls) and a thin presentation layer on top.
The logic library would be independently importable and testable with no side effects.

**Why:** Currently `feat_*.py` files mix business logic, scoring formulas, and
display code. This makes the scoring engine hard to test in isolation, impossible to
reuse across different frontends, and difficult to reason about when debugging. The
pure functions already exist scattered across files (`score_move`, `compute_defense`,
`compare_learnsets`, `build_offensive_coverage`) — this is about completing that
separation structurally.

**What it brings:** The core logic becomes a testable, reusable library. A TUI, a
web interface, or a Discord bot could be built on top without touching the scoring
engine. Tests become faster and more reliable because they never touch I/O. The
boundary between "what the tool knows" and "how it displays it" becomes explicit.

---

### 🖥️  Terminal UI (TUI)

**What:** Replace the sequential prompt-and-redraw loop with a persistent split-pane
terminal interface. The game and Pokemon context would always be visible. Feature
output would update in the right pane without clearing the screen. Navigation would
be keyboard-driven without re-entering choices.

**Why:** The current UX requires the user to mentally hold context (which game is
loaded, which Pokemon, what team) because the screen clears on every action.
The menu loop pattern also means every interaction is a round-trip: print menu,
read input, print output, return to menu. A TUI makes all context visible at once
and reduces interactions to keypresses rather than typed commands.

**What it brings:** A materially better user experience for the core use case —
sitting down to plan a team. The moveset recommendation screen in particular would
benefit from seeing all three modes side by side and being able to toggle locked
moves without re-running the full flow. The V and O team screens would benefit from
persistent context as you scroll.

---

### 🧠  Data-driven move scoring

**What:** Replace the hand-tuned scoring formula (base_power × stat_weight × STAB ×
accuracy × ...) with a model trained on real competitive usage data — Smogon usage
statistics, tournament sets, or battle replay outcomes.

**Why:** The current formula optimises a move in isolation using a set of manually
calibrated constants. It does not know that Stealth Rock is used on nearly every
team regardless of its "score", that Leftovers recovery matters more than raw power
in many matchups, or that certain coverage moves are valuable precisely because they
surprise opponents. Real competitive data encodes all of this implicitly.

**What it brings:** Recommendations grounded in what actually wins games rather than
a theoretical damage calculation. The model would stay small and local (decision tree
or gradient boosting, not a neural network) — no external API, no privacy concerns,
fully offline. The scoring engine interface stays the same; only the weights change.

---

### ♟️  Joint team optimisation

**What:** Replace the current per-member independent scoring in the team builder with
a combinatorial search over full 6-Pokemon team compositions, optimising a joint
objective function.

**Why:** Team synergies emerge from combinations, not from individual quality.
A team of six independently "good" Pokemon can have crippling shared weaknesses or
complete offensive redundancy. The current builder scores each candidate against the
partial team already loaded, which is better than nothing but cannot explore the
space of compositions that are only strong together.

**What it brings:** Team suggestions that account for role distribution, type
coverage completeness, speed tier spread, and weakness overlap simultaneously. The
difference between a team that looks good on paper and one that actually holds
together under pressure. Beam search or simulated annealing over the composition
space would be fast enough to run locally in seconds.

---