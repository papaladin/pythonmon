# ROADMAP.md
# Long‑term feature goals for the Pokemon Toolkit

> Items marked ✅ are complete.  
> For completed item details, see `HISTORY.md`.  
> For granular steps of the item currently in progress, see `TASKS.md`.

---

## Completed features

| Feature | Description | History ref |
|---|---|---|
| Core CLI skeleton | Menu loop, game + Pokemon context, cache layer | §1–§11 |
| Web scraper (move data) | pokemondb.net move table + modifications scraper | §1–§11 |
| PokeAPI migration | Replaced web scraper with PokeAPI; move versioning schema | §12–§13 |
| Type vulnerabilities | Full defensive chart, all 3 type chart eras | §15 |
| Learnable move list | Level‑up / TM‑HM / tutor / egg with stats per row | §16–§19 |
| Moveset recommendation | Scored pool + 3 modes (Coverage / Counter / STAB), locked slots | §21–§50 |
| Type coverage display | Types hit SE shown in moveset output; uncoverable weakness annotation | §44, §54 |
| Per‑variety learnsets | Regional / alternate forms get correct move pool (variety_slug) | §42–§43 |
| Type browser | List all Pokemon of a given type or type combo | §51–§52 |
| Nature browser | 25‑nature table + stat recommender by role and speed tier | §53 |
| Ability browser | Browse all abilities + full effect + Pokemon roster drill‑in | §57 |
| Quick view (option 1) | Base stats bar chart + abilities + type chart in one screen | §58 |
| Team loader | Session‑only team of up to 6 Pokemon; T key; add/remove/clear | §59 |
| Team defensive analysis | Unified type table: weak/resist/immune per type, gap labels | §60–§61 |
| Team offensive coverage | Per‑type hitter table with best scored move per hitting type; O key | §62–§64 |
| Team moveset synergy | Per‑member recommended movesets + team coverage summary; S key | §66–§71 |
| Quick wins batch (Pythonmon 1–4, 16) | Loading indicator (S screen), fuzzy name search, batch move upserts, session pool cache, get_form_gen bug fix | §72–§76 |
| Quick wins batch 2 (Pythonmon 5, 12, 13) | Cache integrity check (`--check-cache`), add‑to‑team prompt after P, partial move refresh (F option in MOVE) | §77–§79 |
| Per‑form learnset fix (Pythonmon‑10) | `fetch_pokemon` stores `form_slug` as `variety_slug`; correct learnset for forms where form slug ≠ variety slug | §80 |
| Move filter in pool (Pythonmon‑6) | Filter learnable moves by type / category / power; full table shown first, prompt at bottom | §81 |
| Stat comparison (Pythonmon‑8) | Side‑by‑side bar chart comparison of two Pokemon; key C | §82 |
| Role & speed tier display (Pythonmon‑32) | Added to quick view and stat compare; pure inference from base stats | §83 |
| Move effect description (Pythonmon‑28) | Effect text from PokeAPI shown in move lookup (key M) | §84 |
| Egg group browser (Pythonmon‑27) | Full roster drill‑in for all 15 egg groups; key E; per‑variety learnset integration | §86–§88 |
| Evolution chain display (Pythonmon‑9) | Per‑game filtered chain with trigger descriptions; generation‑aware; inline block on quick view | §89–§91 |
| Cache size report (Pythonmon‑17) | `--cache-info` flag showing counts per cache layer | §92 |
| Offline mode detection (Pythonmon‑18) | PokeAPI connectivity probe at startup; clear warning when unreachable | §93 |
| Learnset staleness flag (Pythonmon‑19) | Shows cached age when learnset older than 30 days | §94 |
| Move filter on scored pool (Pythonmon‑20) | Extended filter from option 2 to option 3 (scored moveset) | §95 |
| Batch team load (Pythonmon‑22) | Comma‑separated Pokemon names load multiple team slots at once | §96 |
| Weakness overlap heatmap (Pythonmon‑30) | V screen extended to show pairs of members with 2+ shared weaknesses | §97 |
| Nature & EV build advisor (Pythonmon‑24) | Four standard EV spreads with Lv100 stat calculations per role | §98 |
| Learnset comparison (key L) | Side‑by‑side learnable moves; unique to each Pokemon highlighted | §99 |
| Team builder / slot suggestion (Pythonmon‑11, key H) | Given partial team, suggest 6 Pokemon to fill gaps; scored by coverage + intrinsic quality | §100 |
| Menu cleanup (TD‑1, TD‑2, TD‑5, TD‑9) | Removed duplicates in menu display and constants; promoted _MENU_CHOICES to module level | §101–§102 |
| PyInstaller packaging (PKG‑1, PKG‑2, PKG‑3) | Standalone executables for Windows/macOS/Linux; sys.frozen guard; GitHub Actions build workflow | §103 |
| Display bug fixes (4 fixes) | Move lookup accuracy/PP/version‑history; quick view pause; learnset compare fallback | §104 |
| Code quality sweep (TD‑7, TD‑8, TD‑9) | Specific exception types; magic constants extracted; input validation improved | §105 |
| Pythonmon‑31 (part 1) | Team coverage vs in‑game opponents – static trainer database, version‑slug merging, key X | §106–§107 |
| Pythonmon‑23 | Persistent game selection + help flag | `--game` flag skips game selection; `--help` shows usage summary | §108 |


---

## Roadmap to V2

The following steps represent a phased approach to evolving the toolkit into version 2.0. Each step builds on the previous one, and the order minimises risk while keeping the tool usable throughout.

### 1. Core library / presentation separation

**What:** Split the codebase into two distinct layers: a pure logic library (no I/O, no print statements, no `input()` calls) and a thin presentation layer on top. The logic library will contain all scoring formulas, type calculations, team analysis, and data access.

**Why:** Currently `feat_*.py` files mix business logic with display code. This makes the scoring engine hard to test in isolation, impossible to reuse across different frontends, and difficult to reason about. The separation creates a foundation for everything that follows.

**Effort:** 🟡 Medium  
**Complexity:** 🟡 Medium  
**Added value:** Enables independent testing, reuse across frontends, cleaner architecture.

---

### 2. SQLite data layer

**What:** Replace the JSON file cache with a single SQLite database. Migrate existing cache data into tables. Keep the same public API for `pkm_cache.py` so the rest of the toolkit is unaware of the change.

**Why:** The current JSON cache is a hand‑rolled relational database. SQLite gives referential integrity, real queries, atomic multi‑table writes, and standard migration tooling for free. It also eliminates the per‑file atomic‑write complexity.

**Effort:** 🔴 High  
**Complexity:** 🟡 Medium  
**Added value:** Relational integrity, faster lookups on large datasets, proper schema migrations, ability to query across entities (e.g. “all Pokemon that learn Earthquake and have base Speed > 100”).

---

### 3. One‑time full data import

**What:** Add a command (`python pokemain.py --sync`) that downloads all Pokemon, moves, learnsets, etc., into the SQLite database upfront.

**Why:** The current cache‑miss latency (network call mid‑session when a Pokemon or move hasn't been looked up) is the single most disruptive part of the user experience. With a full import, the tool is either fully ready or it isn’t — no partial states, no mid‑session surprises.

**Effort:** 🟡 Medium  
**Complexity:** 🟡 Medium  
**Added value:** Truly instant responses after initial setup; unconditional offline‑first; simplified code (no cache‑miss logic).

---

### 4. Terminal UI (TUI)

**What:** Replace the sequential prompt‑and‑redraw loop with a persistent split‑pane terminal interface (using `textual` or `curses`). The game, Pokemon, and team context are always visible. Feature output updates in the right pane without clearing the screen. Navigation is keyboard‑driven.

**Why:** The current UX requires the user to mentally hold context because the screen clears on every action. A TUI makes all context visible at once and reduces interactions to keypresses rather than typed commands.

**Effort:** 🔴 High  
**Complexity:** 🔴 High  
**Added value:** Drastically improved user experience; faster workflows; keeps CLI as fallback.

---

### 5. Data‑driven move scoring

**What:** Replace the hand‑tuned scoring formula (base_power × stat_weight × STAB × accuracy × …) with a model trained on real competitive usage data (Smogon usage, tournament sets, battle replay outcomes).

**Why:** The current formula optimises a move in isolation using manually calibrated constants. Real competitive data encodes metagame knowledge (e.g. Stealth Rock’s importance, surprise coverage moves) that the formula cannot capture.

**Effort:** 🟡 Medium  
**Complexity:** 🟡 Medium  
**Added value:** Recommendations grounded in what actually wins games; can be delivered as an optional mode.

---

### 6. Joint team optimisation

**What:** Replace the current per‑member independent scoring with a combinatorial search over full 6‑Pokemon team compositions, optimising a joint objective (coverage, synergy, weakness overlap, etc.).

**Why:** Team synergies emerge from combinations, not from individual quality. A team of six independently “good” Pokemon can have crippling shared weaknesses or complete offensive redundancy. The current builder scores candidates against a partial team, but cannot explore the space of compositions that are only strong together.

**Effort:** 🔴 High  
**Complexity:** 🔴 High  
**Added value:** Finds teams that are greater than the sum of their parts. Beam search or simulated annealing over the composition space will run in seconds locally.