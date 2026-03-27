# Pokemon Toolkit

A Python CLI for in-game Pokemon analysis. Load any Pokemon and game, then explore
type matchups, learnable moves, moveset recommendations, egg group browsing, and team composition analysis.

All data is fetched from [PokeAPI](https://pokeapi.co) on first use and cached locally
in a SQLite database. Subsequent runs are fully offline — no network needed.

**Runs on Python 3.10+ with no installation.** Uses only the standard library + `requests` + `textual`.

---

## Quick start

```
python pokemain.py
```

Optional startup flags:
```
python pokemain.py --cache-info               # show count of cached Pokémon, moves, learnsets, etc.
python pokemain.py --check-cache              # scan the cache database and report issues
python pokemain.py --refresh-moves            # force-refresh the full move table
python pokemain.py --refresh-pokemon <n>      # force-refresh one Pokemon's cached data
python pokemain.py --refresh-learnset <n> <game>  # force-refresh one learnset
python pokemain.py --refresh-all <n>          # force-refresh all data for a Pokemon
python pokemain.py --refresh-evolution <n>    # force-refresh one Pokemon's evolution chain
python pokemain.py --help                     # show usage summary and exit
python pokemain.py --game "Scarlet / Violet"  # pre-select a game, skipping the selection prompt
python pokemain.py --cli                      # use CLI UI
python pokemain.py --tui                      # use TUI (built with Textual) UI
```

To pre-load all data upfront (recommended for offline use):
```
python pkm_sync.py          # download all Pokémon, moves, type rosters, etc. into the database
python pkm_sync.py --force  # wipe and re-download from scratch
```

First run requires a network connection to populate the cache. After that, all
features work offline. If PokeAPI is unreachable on a sparse cache, a warning is
printed at startup. The **Y** and **W** keys in the menu pre-warm the move and
machine tables in bulk — recommended before first moveset run.

**Database location:** The SQLite database (`pokemon.db`) lives in the `cache/` folder
next to the source files (or next to the executable when running a bundled build).

**Bundled executable:** The pre‑built executable launches the Terminal UI (TUI) by default.  
If you prefer the classic CLI, run it with `--cli` (e.g., `./pokemain --cli`).

---

## Menu overview

```
  G   Select game          P   Load Pokemon
  ─────────────────────────────────────────────
  1   Quick View           (needs Pokemon + game)
  2   Learnable moves      (needs Pokemon + game)
  3   Scored move pool     (needs Pokemon + game)
  4   Moveset recommend    (needs Pokemon + game)
  M   Move lookup          (needs game)
  ─────────────────────────────────────────────
  B   Type browser
  N   Nature browser
  A   Ability browser
  E   Egg group browser     (needs Pokemon)
  L   Compare learnsets     (needs Pokemon + game)
  ─────────────────────────────────────────────
  T   Manage team
  V   Team analysis        (needs team + game)
  O   Offensive coverage   (needs team + game)
  S   Team moveset synergy (needs team + game)
  H   Team builder         (needs team + game)
  X   Team vs opponent     (needs team + game)
  ─────────────────────────────────────────────
  Y   Pre-load move table
  W   Pre-load TM/HM table
  Q   Quit
```

Features only appear in the menu when their required context is available.
Keys that need a Pokemon show only after `P` is pressed; `V` shows only when a team
has at least one member loaded.

---

## Features

### 1 — Quick view

**Needs:** Pokemon + game

Shows a full single-screen summary for the loaded Pokemon:

- **Base stats** as a bar chart (hp / atk / def / sp.atk / sp.def / speed)
- **Inferred role and speed tier** (Physical / Special / Mixed attacker; Fast / Mid / Slow)
- **Abilities** with effect descriptions (from abilities cache)
- **Egg groups** — inline display of which breeding groups this Pokemon belongs to
- **Defensive type chart** — all attacking types grouped by multiplier:
  immunities (×0), resistances (×0.25, ×0.5), weaknesses (×2, ×4)
- **Evolution chain** — compact inline display at the bottom; filtered by
  game generation (future-gen evolutions not shown for older games)

**Era-aware:** the type chart reflects the era of the selected game.
Fairy type does not appear for Gen 1–5 games.

**Assumptions / limitations:**
- Ability effects are loaded from the abilities index cache; if the ability was
  introduced after the last cache refresh, its description may be missing.
- Base stats shown are the Pokemon's base stats, not EVs/IVs/nature-adjusted values.

---

### 2 — Learnable move list

**Needs:** Pokemon + game

Shows all moves the Pokemon can learn in the selected game, grouped by learn method:
- Level-up moves (with level)
- TM / HM (with machine number)
- Move tutor
- Egg moves

Each row shows: move name, type, category (physical/special/status), power, accuracy, PP.
Move stats are era-correct: if a move changed stats between generations, the version
matching the selected game is shown.

**Limitations:**
- Learnset is fetched from PokeAPI. If PokeAPI has incomplete data for a specific
  game / Pokemon combination, some moves may be missing.
- Tutor location data is not shown (PokeAPI does not provide it reliably).

---

### 3 — Scored move pool

**Needs:** Pokemon + game

Same move pool as option 2, but sorted by individual move score (highest first).
Each row includes a score breakdown showing which factors contributed.

Score formula:
```
score = base_power
      × stat_weight      (attack vs sp.attack ratio, Gen 4+ only)
      × stab_bonus       (×1.5 if STAB)
      × accuracy_factor
      × two_turn_penalty (Solar Beam, Fly, etc.)
      × recoil_factor
      × effect_factor    (secondary effect chance)
      × priority_factor
```

**Use this to:** see which moves are objectively strongest for this Pokemon in this game,
before deciding on a final moveset.

---

### 4 — Moveset recommendation

**Needs:** Pokemon + game

Recommends a 4-move set in three modes simultaneously:

| Mode | Optimises for |
|---|---|
| Coverage | Types hit super-effectively across the 4 moves |
| Counter | Covers as many of this Pokemon's own weaknesses as possible |
| STAB | Maximises STAB move count and power |

**Locked slots:** before running, you can pin specific moves (e.g. a signature move
or a HM you need). Locked moves are included in all three recommendations.

**Output includes:**
- The 4 recommended moves with individual scores
- Type coverage summary: which types the set hits SE
- Weakness coverage: which of the Pokemon's weaknesses are covered by the moveset
- A note if fewer than 4 move types are available (e.g. pure Normal-type in Gen 1)

**Assumptions:**
- Status moves are ranked separately from attacking moves and included based on
  a hand-curated tier list (`STATUS_MOVE_TIERS` in `core_move.py`).
  Moves not in the tier list fall to lowest priority.
- The scoring formula does not account for in-game team composition or opponent AI.
  It optimises a single Pokemon's moveset in isolation.
- 16 moves are excluded from auto-recommendation (self-KO, setup-dependent, etc.)
  but can still be used as locked slots. See ARCHITECTURE.md § COMBO_EXCLUDED.

---

### M — Move lookup

**Needs:** game

Look up any move by name. Accepts partial names (e.g. "thunder" shows Thunderbolt,
Thunder, Thundershock, Thunderpunch, etc.).

Shows: type, category, power, accuracy, PP, **effect description** (one-sentence summary
of what the move does), and a version history table showing how stats changed across generations.

Also shows **offensive coverage**: which types this move hits SE, neutrally, and
not-very-effectively (era-aware).

---

### B — Type browser

Browse all Pokemon of a given type (or type combination).
Enter one or two types; the browser shows all matching Pokemon with their full type
and the generation they were introduced.

Useful for: finding a Pokemon of a specific type to fill a team slot.

**Limitations:** the type roster is fetched from PokeAPI's `/type/{name}` endpoint
and cached. If a Pokemon was added after the last cache refresh, it may not appear.

---

### N — Nature & EV build advisor

Shows two complete build profiles for the loaded Pokémon (when available), followed
by the full 25-nature reference table.

**Build profiles** (shown when a Pokémon is loaded):

Each profile combines a recommended nature with a standard EV spread and shows
the resulting stat values for all 6 stats at Level 100:

| Profile | Optimises for |
|---|---|
| Speed-safe | Maximises Speed tier — never lose a speed tie |
| Power-max  | Maximises primary attacking stat at the cost of speed |

Example for Charizard (Special / Fast):
- Profile 1: Timid (+Spe/−Atk), 252 SpA / 252 Spe / 4 HP
- Profile 2: Modest (+SpA/−Atk), 252 SpA / 252 Spe / 4 HP

Each profile shows base stat, final stat, and change per stat, with notes
indicating which stats the nature boosts/cuts and how many EVs are allocated.

**Assumption:** All stat calculations assume Level 100, 31 IVs in all stats
(standard competitive baseline). Actual values will differ at lower levels
or with non-31 IVs.

**Nature table** (always shown): all 25 natures with +10%/−10% effects,
and a top-5 role-aware nature ranking when a Pokémon is loaded.

---

### A — Ability browser

Browse all abilities with their effect descriptions. Enter a name (or partial name)
to search. From any ability, drill in to see which Pokemon have it.

Also available from the quick view screen (option 1): the current Pokemon's abilities
are shown with drill-in available.

---

### T — Team management

Load up to 6 Pokemon into a team for the current session.

Commands in the team sub-menu:
- Type a Pokemon name to add it to the next free slot
- `-2` to remove slot 2 (or any slot number)
- `C` to clear the entire team
- `Q` to return to the main menu

Team is **session-only** — it is not saved to disk. Load your team at the start of
each session using T.

---

### V — Team defensive vulnerability analysis

**Needs:** team (at least 1 member) + game

Shows a single unified table with one row per attacking type in the era:

```
  Type       | Weakness                     | Resistance                | Immunity               | Comments
  -----------+------------------------------+---------------------------+------------------------+---------
  Rock       |  3  Char(×4) Lapr Butt(×4)  |  0  -                     |  0  -                  | !! CRITICAL
  Ice        |  2  Char  Blas               |  1  Venu(×0.25)           |  0  -                  | .  MINOR
  Water      |  1  Char                     |  2  Venu  Blas            |  0  -                  |
  Ground     |  0  -                        |  1  Blas                  |  1  Char               |
  Dragon     |  0  -                        |  0  -                     |  0  -                  |
```

**Column meanings:**
- **Weakness** — members weak to this type (×2 or ×4). `(×4)` suffix for double-weak members.
- **Resistance** — members that resist this type. `(×0.25)` suffix for double-resist members.
- **Immunity** — members fully immune (×0).
- **Comments** — gap classification when applicable.

**Gap classification:**
- `!! CRITICAL` — 3 or more members weak, zero coverage (no resist + no immune)
- `!  MAJOR` — 3 or more members weak, at most 1 coverage
- `.  MINOR` — exactly 2 members weak, zero coverage

**All types in the era are always shown**, including types where the team has no
particular interaction (shown as `0  -` in all columns). This lets you immediately
see which types pose no threat and which your team is neutral to.

**Pokemon names are abbreviated to 4 characters** in the table (e.g. Charizard → Char,
Blastoise → Blas). Names shorter than 4 characters are shown as-is.

A summary block below the table lists any gap types grouped by severity.

---

### O — Team offensive coverage

**Needs:** team (at least 1 member) + game

For each attacking type in the era, shows which team members can hit it
super-effectively — both by type and by best learnable move.

Each member is shown with a type-letter tag and their best scored move of
that type: `Char:Flamethrower(F)` = Charizard can hit SE with Fire via
Flamethrower. When no scoreable move is available the type letter alone is
shown as a fallback.

All types in the era are always shown. Types with no SE coverage are labelled
`GAP`. A summary line at the bottom shows overall coverage count and lists
gap types.

---

### S — Team moveset synergy

**Needs:** team (at least 1 member) + game

Generates recommended 4-move movesets for every Pokémon in the team simultaneously,
then evaluates the team's combined offensive coverage.

Before running, you choose one optimisation mode applied to all members:

| Mode | Optimises for |
|---|---|
| Coverage | Maximum type diversity — hits the most types SE across the team |
| Counter | Each member covers as many of its own weaknesses as possible |
| STAB | Maximises same-type moves for each member |

**Per-member block:**

```
  Charizard  [Fire / Flying]
  Weak:  Rock  Water  Electric  Ice
  Flamethrower          Air Slash
  Earthquake            Dragon Claw
  SE: 6 / 18 types
```

Each block shows: name and types, defensive weaknesses, the 4 recommended moves
(2 per line), and how many types that moveset hits SE. `—` fills any empty slot
when fewer than 4 scoreable moves exist in the pool.

**Team coverage summary** (below all member blocks):

```
  ── Team coverage ────────────────────────────────────────────
  Covered:  14 / 18 types hit SE
  Gaps:     Dragon  Ghost  Normal
  Overlap:  Water (5)  Ground (3)
```

- **Covered** — types hit SE by at least one team member
- **Gaps** — types with no SE coverage across the whole team
- **Overlap** — types covered by 3 or more members (potential redundancy)

**Assumptions / limitations:**
- Uses recommended movesets, not the Pokémon's actual in-game moves.
- Status moves may appear based on the `STATUS_MOVE_TIERS` ranking used by the engine.
- Coverage is computed from the recommended combo, not from the Pokémon's types.
- The engine optimises each member independently — it does not jointly optimise
  the team as a unit.

---

### H — Team builder

**Needs:** team (at least 1 member) + game

Suggests the best Pokémon to fill the next open team slot based on the current
team's offensive and defensive gaps.

**Gap analysis:**
- **Offensive gaps** — era types that no current team member can hit SE using their own types
- **Defensive gaps** — types where ≥2 members are weak AND 0 members resist or are immune (critical)

**Each suggestion card shows:**

```
  1. Garchomp      [Dragon / Ground]   ●●●●●
     ✓ Covers:  Normal  Rock  Electric
     ✓ Resists: Electric
     ✗ Adds pair: Charizard shares: Rock  Ice
     → After: Dragon gap  (3 types cover it)
```

- **●●●●●** — dot rating (1–5) based on percentile rank within the suggestion set
- **Covers** — offensive gap types this Pokémon can hit SE
- **Resists** — critical defensive gap types this Pokémon resists or is immune to
- **Adds pair** — warning when this Pokémon would share ≥2 weaknesses with an existing member
- **After** — lookahead showing which gaps would remain and how patchable they are

Up to 6 candidates are shown, ranked by a composite score:

```
  intrinsic  =  offensive contribution × 10
              + defensive contribution × 8
              - shared weakness pairs  × 6
              + role diversity bonus   × 4
              + BST bonus              (up to × 5, normalised to base-stat total)
  lookahead  =  patchability of remaining gaps / slots_remaining
                (weighted ×2 when ≤2 slots remain)
  total      =  intrinsic + lookahead
```

**Evolution filtering:**  
When multiple stages of a pure level‑up evolution chain (e.g., Dratini → Dragonair → Dragonite) are all valid candidates, only the highest stage is shown. This avoids cluttering the suggestions with intermediate forms that would eventually evolve into the same final Pokémon. If the evolution requires a trade, an item, or a special condition (e.g., Seadra → Kingdra), both forms are kept because they represent distinct acquisition paths or type/role changes.

**Notes:**
- A note is shown when the team has fewer than 3 members (suggestions improve with more context).
- Candidates are drawn from cached type rosters. Missing rosters are fetched automatically
  before the pool is built; a per-type progress indicator is shown.
- Base stats are used for role diversity and BST scoring when the Pokémon is already in the
  local cache; type-only scoring is used for uncached entries.

---

### X — Team vs in‑game opponent

**Needs:** team (at least 1 member) + game

Select a named opponent (gym leader, Elite Four member, Champion) from the chosen game.
The toolkit analyses your loaded team against that opponent's party, showing:

- **Per‑opponent Pokémon blocks**:  
  *Name, type, level, and moveset*  
  - ⚠️ **WEAK TO** – team members that are hit super‑effectively by the opponent's moves (moveset‑aware)  
  - ✓ **RESISTS** – team members that resist the opponent's moves  
  - 💥 **HITS SE** – team members that can hit the opponent super‑effectively with their own STAB moves

- **Uncovered threats** – opponents that no team member can hit SE with STAB moves  
- **Recommended leads** – team members sorted by how many opponent Pokémon they can cover with STAB

**Data source:** static `data/trainers.json` bundled with the toolkit. The file is updated manually as new games are added. Move types are resolved from the local move cache (no network needed after first run).

**Era‑aware:** the type chart used for calculating resistances and weaknesses matches the selected game's era (Gen 1, Gen 2–5, Gen 6+). Moves that changed type or category across generations are resolved correctly for the chosen game.


---

## Supported games

17 games across 3 type chart eras:

| Era | Games | # Types |
|---|---|---|
| ERA1 (Gen 1) | Red / Blue / Yellow | 15 |
| ERA2 (Gen 2–5) | Gold/Silver/Crystal, Ruby/Sapphire/Emerald, FireRed/LeafGreen, Diamond/Pearl/Platinum, HeartGold/SoulSilver, Black/White, Black 2/White 2 | 17 |
| ERA3 (Gen 6+) | X/Y, Omega Ruby/Alpha Sapphire, Sun/Moon, Ultra Sun/Ultra Moon, Sword/Shield, Legends: Arceus, Brilliant Diamond/Shining Pearl, Scarlet/Violet, Legends: Z-A | 18 |

---

## Known limitations

1. **Legends: Z-A cooldown system** — PokeAPI does not yet model Z-A's cooldown mechanic.
   Move stats are shown as standard PP values.

2. **STATUS_MOVE_TIERS is hand-curated** (~130 entries). Moves added to the game after
   the last toolkit update will not have a tier and will fall to lowest priority in
   moveset recommendations. You can still use them as locked slots.

3. **Learnset completeness** — PokeAPI learnset data varies in completeness by game.
   Some older games have partial learnset data. The toolkit shows exactly what PokeAPI
   provides; missing moves are not flagged.

4. **Team is session-only** — closing the toolkit loses the team. No save/load yet.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Wrong moves shown for a regional form | Pokemon cached before §42 (no variety_slug field) | Run `python pokemain.py --refresh-pokemon <n>` |
| Wrong or missing learnset for a Pokemon form | Pokemon cached before §80 (old variety_slug value) | Run `python pokemain.py --refresh-pokemon <n>` |
| Cache data corrupt or stale | Old schema or interrupted write | Run `python pokemain.py --check-cache` for a full report |
| Move table shows `?` for all stats | Move cache is empty | Press **Y** then confirm, or press **Y** → **F** (fetch missing only) |
| Missing move in learnable list | PokeAPI incomplete for this game | Check PokeAPI directly; this is a data gap, not a bug |
| Connection error on first load | PokeAPI unreachable | Check network; cached data is used on all subsequent runs |
| `TypeError: too many values to unpack` | Stale `pkm_cache.py` from before §38 | Replace with latest version |
| No egg group data shown in E or option 1 | Pokemon cached before Pythonmon-27 (`egg_groups` field missing) | Press **R** to refresh Pokemon data |
| Evolution chain shows wrong conditions (missing "day/night" or held item) | Chain cached before §91 bug fixes | Run `python pokemain.py --refresh-evolution <n>` |
| No evolution chain shown in option 1 | Pokemon cached before Pythonmon-9 (`evolution_chain_id` field missing) | Press **R** to refresh Pokemon data |

---

## Running the tests

Every module with testable logic has an `--autotest` flag (offline unless noted):

| Command | Tests |
|---------|-------|
| `python matchup_calculator.py --autotest` | 79 — type chart, all 3 eras, all multipliers |
| `python pkm_cache.py --autotest` | 21 — read/write/invalidate/upsert/batch/integrity/egg_groups/evolution/cache_info |
| `python pkm_session.py --autotest` | 33 — cache upgrade, form selection, era/gen blocking, fuzzy search, form_gen fix, version_slugs, make_game_ctx |
| `python feat_moveset_data.py --autotest` | 1 — module import smoke test (scoring logic moved to core_move.py) |
| `python feat_moveset.py --autotest` | 0 — test body is a placeholder; scoring tests are in core_move.py |
| `python feat_type_browser.py --autotest` | 41 (+8 cache) — gen derivation, name resolution |
| `python feat_nature_browser.py --autotest` | 48 (+11 cache) — nature scoring, stat formula, build profiles |
| `python feat_ability_browser.py --autotest` | 14 (+8 cache) — display helpers |
| `python feat_team_loader.py --autotest` | 41 — team ops, summary line, batch load |
| `python feat_team_analysis.py --autotest` | 75 — defense aggregation, gap labels, display, weakness pairs |
| `python feat_team_offense.py --autotest` | 50 — offensive coverage, type‑letter tags, gap detection, pool cache |
| `python feat_team_moveset.py --autotest` | 2 — recommend and display smoke tests (engine logic moved to core_team.py) |
| `python feat_move_lookup.py --autotest` | 14 (+2 cache) — formatting, coverage all eras, effect line |
| `python feat_movepool.py --autotest` | 16 (+2 cache) — row formatting, section headers, filter |
| `python feat_learnset_compare.py --autotest` | 20 — flat_moves, compare, build rows, display |
| `python feat_egg_group.py --autotest` | 18 — name mapping, formatting, display browser, graceful edge cases |
| `python feat_quick_view.py --autotest` | 4 — evolution chain display (merged from feat_evolution) |
| `python feat_team_builder.py --autotest` | 57 — gap analysis, scoring, pool building, display, run() guards |
| `python feat_opponent.py --autotest` | 18 — trainer data loading, merging, matchup logic, display |
| `python core_stat.py --autotest` | 21 — stat bar, total stats, role, speed tier, compare |
| `python core_egg.py --autotest` | 8 — egg group name mapping, formatting |
| `python core_evolution.py --autotest` | 28 — trigger parsing, flattening, filtering, level-up chain detection |
| `python core_move.py --autotest` | 11 — move scoring, combo selection, status ranking |
| `python core_team.py --autotest` | 24 — defensive/offensive analysis, team builder scoring |
| `python core_opponent.py --autotest` | 5 — opponent analysis |
| `python pkm_pokeapi.py --autotest` | 14 — versioned entry builder, mapping tables, fetch_pokemon offline, egg_groups, evolution_chain_id, check_connectivity |
| `python pkm_sqlite.py --autotest` | 0 (no public interface; tested via pkm_cache) |
| `python pkm_sync.py --autotest` | 0 (sync script, not unit‑tested) |
| `ui_base.py --autotest` | 0 — abstract base class; no logic to test |
| `ui_cli.py --autotest`  | 0 — CLI implementation is purely interactive I/O; no pure logic |
| `ui_tui.py --autotest`  | 0 — TUI implementation is interactive; testing would require Textual's test harness, not covered by offline test runner |

Run all suites at once:
```
python run_tests.py           # all suites (cache entries auto-downloaded if missing)
python run_tests.py --offline # skip cache-dependent suites (no network needed)
python run_tests.py --quiet   # summary table only
```

---
## Files

| File | Role |
|---|---|
| `pokemain.py` | Entry point; menu loop; context wiring |
| `pkm_session.py` | Interactive game + Pokemon context selection |
| `pkm_cache.py` | All cache reads and writes (single gateway, uses SQLite) |
| `pkm_sqlite.py` | SQLite database layer (tables, connections, low‑level access) |
| `pkm_sync.py` | One‑time full data import from PokeAPI to SQLite |
| `pkm_pokeapi.py` | PokeAPI adapter; fetch + translate raw data |
| `matchup_calculator.py` | Type chart data (ERA1/2/3) + multiplier logic |
| `core_stat.py` | Pure stat functions (compare_stats, total_stats, infer_role, etc.) |
| `core_egg.py` | Pure egg group functions (egg_group_name, format_egg_groups) |
| `core_evolution.py` | Pure evolution chain logic (parse_trigger, flatten_chain, filter) |
| `core_move.py` | Pure move scoring and combo selection |
| `core_team.py` | Pure team analysis and builder logic |
| `core_opponent.py` | Pure opponent analysis logic |
| `feat_quick_view.py` | Quick view (stats / abilities / egg groups / type chart / evolution chain) |
| `feat_move_lookup.py` | Move lookup by name |
| `feat_movepool.py` | Learnable move list with learn conditions |
| `feat_moveset.py` | Scored pool + moveset recommendation UI |
| `feat_moveset_data.py` | Data fetching for moveset recommendation (I/O) |
| `feat_type_browser.py` | Browse Pokemon by type |
| `feat_nature_browser.py` | Nature & EV build advisor + nature browser (key N) |
| `feat_ability_browser.py` | Ability browser + drill-in |
| `feat_team_loader.py` | Team context management (add/remove/view) |
| `feat_team_analysis.py` | Team defensive vulnerability table |
| `feat_team_offense.py` | Team offensive type coverage (key O) |
| `feat_team_moveset.py` | Team moveset synergy (key S) |
| `feat_egg_group.py` | Egg group browser + breeding partners (key E) |
| `feat_learnset_compare.py` | Learnset comparison between two Pokémon (key L) |
| `feat_team_builder.py` | Team slot suggestion — gap analysis + ranked candidates (key H) |
| `feat_opponent.py` | Team coverage vs in‑game opponents (key X) |
| `run_tests.py` | Test runner for all suites |
| `build.py` | Build script — produces a single-file executable via PyInstaller |
| `ui_base.py` | Abstract base class for UI implementations |
| `ui_cli.py`  | CLI implementation of the UI interface |
| `ui_tui.py`  | TUI implementation (Textual); default for bundled executables |

**Obsolete files** (safe to delete):
`feat_type_matchup.py` (renamed to `feat_quick_view.py` in §85),
`feat_evolution.py` (merged into `feat_quick_view.py` in §124),
`feat_stat_compare.py` (functions moved to `core_stat.py` in §109),
`pkm_scraper.py`, `pkm_move_scraper.py`, `debug2.py`, `debug3.py`, `probe_forms.py`,
`test_move_parser.py`, `test_status_categories.py`, `probe_status_categories.py`