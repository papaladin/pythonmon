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
| Team offensive coverage | Per-type hitter table with best scored move; O key | §62–§64 |
| Team moveset synergy | Per-member recommended movesets + team coverage summary; S key | §66–§71 |

---

## Planned improvements

### 🔧 Backend / robustness

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-1 | S screen loading indicator | ✅ Done §72 — `print()` before engine call in `run()`, matching O screen style. | 🟢 Low |
| Pythonmon-3 | Batch move upserts | ✅ Done §74 - `build_candidate_pool` currently writes `moves.json` once per missing move. Collect all missing entries then write once at the end. Meaningful speedup on first-run with large learnsets. | 🟡 Medium |
| Pythonmon-4 | Session pool caching for O and S | Both screens rebuild member move pools on every visit. A session-level dict keyed by `(variety_slug, game_slug)` makes repeat visits instant. No persistence — cleared on exit. | 🟢 Low |
| Pythonmon-12 | Stale moves partial refresh | `--refresh-moves` wipes the whole `moves.json`. Surface a "fetch only missing moves" option in the menu (`MOVE` key) so new-game moves can be added without discarding everything. | 🟡 Medium |
| Pythonmon-13 | Cache integrity check | A `--check-cache` startup flag that iterates all JSON files, runs the existing `_valid_*` checks, and prints a report. No menu integration needed — standalone diagnostic. | 🟢 Low |

---

### 🖥️ UX improvements

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-2 | Fuzzy name matching | ✅ Done §73 -  Accept partial Pokemon names in `pkm_session`. Search against `pokemon_index.json` keys; show ranked suggestions (same pattern as `match_move`). Only finds previously cached Pokemon — document this clearly. | 🟢 Low |
| Pythonmon-5 | Add-to-team prompt after P | After a successful `P` load, offer "Add to team? (y/n)". Single `input()` + `feat_team_loader.add_to_team()`. Natural flow improvement; no new context needed. | 🟢 Low |
| Pythonmon-6 | Move filter in pool | Filter option 2 / 3 output by type, category, or minimum power before display. `feat_movepool.py` already builds a structured row list — add a pre-display filter prompt. | 🟢 Low |
| Pythonmon-7 | History within session | `H` key navigates back through recently viewed Pokemon. A `deque(maxlen=10)` in `pokemain.py` holding past `pkm_ctx` values. No persistence. | 🟢 Low |
| Pythonmon-14 | STATUS_MOVE_TIERS auto-update | Detect status moves that fall back to tier 4 / quality 0 (unknown). Prompt user to classify and persist additions alongside the built-in table. Requires a design decision on where user overrides live. | 🟡 Medium |

---

### 🧬 Pokemon features

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-8 | Stat comparison | New `feat_stat_compare.py` with side-by-side base stat bars for two Pokemon. No new API data — reuses cached `base_stats`. New menu key (e.g. `C`) when Pokemon loaded. | 🟢 Low |
| Pythonmon-9 | Evolution chain | Show evolution conditions and stat changes per stage. Requires new `/evolution-chain` PokeAPI endpoint + cache layer + recursive tree parsing. Complex evolution conditions (trade, item, friendship). | 🔴 High |
| Pythonmon-10 | Per-form learnset | Cosmetic forms sharing a `variety_slug` (Rotom appliances, Wormadam cloaks, most Megas) get the base-form learnset. Fixing requires per-family slug mapping research and careful cache extension. | 🟡 Medium |
| Pythonmon-11 | Team builder / slot suggestion | Given a partial team (1–5 members), suggest types / roles that fill defensive and offensive gaps. Highest-complexity team feature; depends on the type roster cache being populated. | 🔴 High |

---

### ⛔ Blocked

| ID | Feature | Blocker |
|---|---|---|
| Pythonmon-15 | Legends: Z-A cooldown system | PokeAPI does not yet model the Z-A cooldown mechanic. Revisit once PokeAPI adds support. |

---

## Bugs / hotfixes

| ID | Bug | Root cause | Complexity |
|---|---|---|---|
| Pythonmon-16 | `get_form_gen` false-positive on "mega" substring | ✅ Done §75 — word-split check replaces substring check; Meganium and any similar name now handled correctly. | 🟢 Low |

---

## Out of scope (deliberate)

- **Team persistence** — the session is short (1 game + up to 6 Pokemon); re-entering is acceptable. May revisit if usage patterns change.
- **GUI / web interface** — CLI by design; runs from any terminal
- **Online multiplayer meta analysis** — this tool is for in-game teams, not competitive
- **Database migration** — JSON cache is sufficient; SQLite documented as future option only
- **Pip packages beyond requests** — hard constraint

---
