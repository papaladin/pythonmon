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
| Quick wins batch (Pythonmon 1–4, 16) | Loading indicator (S screen), fuzzy name search, batch move upserts, session pool cache, get_form_gen bug fix | §72–§76 |
| Quick wins batch 2 (Pythonmon 5, 12, 13) | Cache integrity check (`--check-cache`), add-to-team prompt after P, partial move refresh (F option in MOVE) | §77–§79 |

---

## Planned improvements


---

### 🖥️ UX improvements

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-2 | Fuzzy name matching | ✅ Done §73 -  Accept partial Pokemon names in `pkm_session`. Search against `pokemon_index.json` keys; show ranked suggestions (same pattern as `match_move`). Only finds previously cached Pokemon — document this clearly. | 🟢 Low |
| Pythonmon-5 | Add-to-team prompt after P | ✅ Done §78 — 10-line addition to the P handler in `pokemain.py`; suppressed when no game loaded or team full. | 🟢 Low || Pythonmon-6 | Move filter in pool | Filter option 2 / 3 output by type, category, or minimum power before display. `feat_movepool.py` already builds a structured row list — add a pre-display filter prompt. | 🟢 Low |
| Pythonmon-7 | History within session | `H` key navigates back through recently viewed Pokemon. A `deque(maxlen=10)` in `pokemain.py` holding past `pkm_ctx` values. No persistence. | 🟢 Low |
| Pythonmon-14 | STATUS_MOVE_TIERS auto-update | Detect status moves that fall back to tier 4 / quality 0 (unknown). Prompt user to classify and persist additions alongside the built-in table. Requires a design decision on where user overrides live. | 🟡 Medium |

---

### 🧬 Pokemon features

| ID | Feature | Description | Complexity |
|---|---|---|---|
| Pythonmon-8 | Stat comparison | New `feat_stat_compare.py` with side-by-side base stat bars for two Pokemon. No new API data — reuses cached `base_stats`. New menu key (e.g. `C`) when Pokemon loaded. | 🟢 Low |
| Pythonmon-9 | Evolution chain | Show evolution conditions and stat changes per stage. Requires new `/evolution-chain` PokeAPI endpoint + cache layer + recursive tree parsing. Complex evolution conditions (trade, item, friendship). | 🔴 High |
| Pythonmon-10 | Per-form learnset | ✅ Done §80 — `fetch_pokemon` stores `form_slug` as `variety_slug`; 12 new offline tests. Investigation found Rotom appliances are already separate varieties in PokeAPI; fix covers the narrower case where form slug ≠ variety slug. | 🟡 Medium |
| Pythonmon-11 | Team builder / slot suggestion | Given a partial team (1–5 members), suggest types / roles that fill defensive and offensive gaps. Highest-complexity team feature; depends on the type roster cache being populated. | 🔴 High |

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

- **Team persistence** — the session is short (1 game + up to 6 Pokemon); re-entering is acceptable. May revisit if usage patterns change.
- **GUI / web interface** — CLI by design; runs from any terminal
- **Online multiplayer meta analysis** — this tool is for in-game teams, not competitive
- **Database migration** — JSON cache is sufficient; SQLite documented as future option only
- **Pip packages beyond requests** — hard constraint

---
