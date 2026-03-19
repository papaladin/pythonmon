# Pokemon Toolkit

A Python CLI for in-game Pokemon analysis. Load any Pokemon and game, then explore
type matchups, learnable moves, moveset recommendations, egg group browsing, and team composition analysis.

All data is fetched from [PokeAPI](https://pokeapi.co) on first use and cached locally
as JSON. Subsequent runs are fully offline — no network needed.

**Runs on Python 3.10+ with no installation.** Uses only the standard library + `requests`.

---

## Quick start

```
python pokemain.py
```

Optional startup flags:
```
python pokemain.py --check-cache              # scan all cache files and report issues
python pokemain.py --refresh-moves            # force-refresh the full move table
python pokemain.py --refresh-pokemon <name>   # force-refresh one Pokemon's cached data
python pokemain.py --refresh-learnset <name> <game>  # force-refresh one learnset
python pokemain.py --refresh-all <name>       # force-refresh all data for a Pokemon
```

First run requires a network connection to populate the cache. After that, all
features work offline. The **T** and **W** keys in the menu pre-warm the move and
machine tables in bulk — recommended before first moveset run.

---

## Menu overview

```
  G   Select game          P   Load Pokemon
  ─────────────────────────────────────────────
  1   Type matchup         (needs Pokemon + game)
  2   Learnable moves      (needs Pokemon + game)
  3   Scored move pool     (needs Pokemon + game)
  4   Moveset recommend    (needs Pokemon + game)
  M   Move lookup          (needs game)
  ─────────────────────────────────────────────
  B   Type browser
  N   Nature browser
  A   Ability browser
  C   Stat comparison       (needs Pokemon + game)
  E   Egg group browser     (needs Pokemon)
  ─────────────────────────────────────────────
  T   Manage team
  V   Team analysis        (needs team + game)
  O   Offensive coverage   (needs team + game)
  S   Team moveset synergy (needs team + game)
  ─────────────────────────────────────────────
  MOVE  Pre-load move table
  W     Pre-load TM/HM table
  Q     Quit
```

Features only appear in the menu when their required context is available.
Keys that need a Pokemon show only after `P` is pressed; `V` shows only when a team
has at least one member loaded.

---

## Features

### 1 — Type matchup (quick view)

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
  a hand-curated tier list (`STATUS_MOVE_TIERS` in `feat_moveset_data.py`).
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

### N — Nature browser

Shows all 25 natures with their stat effects (+10% / −10%).

Also: enter the Pokemon's role (physical / special / mixed) and speed tier preference,
and the browser recommends the top 3 natures and explains why.

---

### A — Ability browser

Browse all abilities with their effect descriptions. Enter a name (or partial name)
to search. From any ability, drill in to see which Pokemon have it.

Also available from the type matchup screen (option 1): the current Pokemon's abilities
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

## Supported games

17 games across 3 type chart eras:

| Era | Games | # Types |
|---|---|---|
| ERA1 (Gen 1) | Red / Blue / Yellow | 15 |
| ERA2 (Gen 2–5) | Gold/Silver/Crystal, Ruby/Sapphire/Emerald, FireRed/LeafGreen, Diamond/Pearl/Platinum, HeartGold/SoulSilver, Black/White, Black 2/White 2 | 17 |
| ERA3 (Gen 6+) | X/Y, Omega Ruby/Alpha Sapphire, Sun/Moon, Ultra Sun/Ultra Moon, Sword/Shield, Legends: Arceus, Brilliant Diamond/Shining Pearl, Scarlet/Violet, Legends: Z-A | 18 |

---

## Known limitations

1. **Regional / alternate forms** — most forms (Alolan, Galarian, Hisuian,
   Paldean, Shaymin Sky Forme, etc.) are fully supported via their distinct
   `variety_slug`. The `variety_slug` field now stores the form slug where it
   differs from the variety slug (§80), ensuring correct learnsets for those
   forms. Mega Evolutions share the base learnset by design — PokeAPI models
   them as separate varieties but with identical move pools.

2. **Legends: Z-A cooldown system** — PokeAPI does not yet model Z-A's cooldown mechanic.
   Move stats are shown as standard PP values.

3. **STATUS_MOVE_TIERS is hand-curated** (~130 entries). Moves added to the game after
   the last toolkit update will not have a tier and will fall to lowest priority in
   moveset recommendations. You can still use them as locked slots.

4. **Learnset completeness** — PokeAPI learnset data varies in completeness by game.
   Some older games have partial learnset data. The toolkit shows exactly what PokeAPI
   provides; missing moves are not flagged.

5. **Team is session-only** — closing the toolkit loses the team. No save/load yet.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Wrong moves shown for a regional form | Pokemon cached before §42 (no variety_slug field) | Delete `cache/pokemon/<n>.json` and reload |
| Wrong or missing learnset for a Pokemon form | Pokemon cached before §80 (old variety_slug value) | Run `python pokemain.py --refresh-pokemon <n>` |
| Cache files corrupt or stale | JSON write interrupted / old schema | Run `python pokemain.py --check-cache` for a full report |
| Move table shows `?` for all stats | Move cache is empty | Press **MOVE** then **F** (fetch missing) or **R** (fetch all) |
| Missing move in learnable list | PokeAPI incomplete for this game | Check PokeAPI directly; this is a data gap, not a bug |
| Connection error on first load | PokeAPI unreachable | Check network; cached data is used on all subsequent runs |
| `TypeError: too many values to unpack` | Stale `pkm_cache.py` from before §38 | Replace with latest version |
| No egg group data shown in E or option 1 | Pokemon cached before Pythonmon-27 (`egg_groups` field missing) | Press **R** to refresh Pokemon data |
| Evolution chain shows wrong conditions (missing "day/night" or held item) | Chain cached before §91 bug fixes | Run `python pokemain.py --refresh-evolution <n>` or delete `cache/evolution/` |
| No evolution chain shown in option 1 | Pokemon cached before Pythonmon-9 (`evolution_chain_id` field missing) | Press **R** to refresh Pokemon data |
---

## Running the tests

Every module with testable logic has an `--autotest` flag (offline unless noted):

| Command | Tests |
|---|---|
| `python matchup_calculator.py --autotest` | 79 — type chart, all 3 eras, all multipliers |
| `python pkm_cache.py` | 47 — read/write/invalidate/upsert/batch/index/integrity/egg_groups/check_integrity |
| `python pkm_session.py --autotest` | 28 — cache upgrade, form selection, era/gen blocking, fuzzy search, form_gen fix |
| `python feat_moveset_data.py --autotest` | 156 — scoring formula, combo selection, status ranking, batch cache regression |
| `python feat_type_browser.py --autotest` | 41 (+8 cache) — gen derivation, name resolution |
| `python feat_nature_browser.py --autotest` | 27 (+11 cache) — nature scoring (role/speed inference now in feat_stat_compare) |
| `python feat_ability_browser.py --autotest` | 14 (+8 cache) — display helpers |
| `python feat_team_loader.py --autotest` | 28 — team ops, summary line |
| `python feat_team_analysis.py --autotest` | 58 — defense aggregation, gap labels, display |
| `python feat_team_offense.py --autotest`  | 50 — offensive coverage, type-letter tags, gap detection, pool cache |
| `python feat_team_moveset.py --autotest`  | 70 — moveset engine, formatting helpers, coverage aggregation, pool cache |
| `python feat_moveset.py --autotest` | 28 (+1 cache) — breakdown, coverage, locked moves |
| `python feat_move_lookup.py --autotest` | 14 (+2 cache) — formatting, coverage all eras, effect line |
| `python feat_movepool.py --autotest` | 16 (+2 cache) — row formatting, section headers, filter |
| `python feat_stat_compare.py --autotest` | 26 — compare_stats, total_stats, infer_role, infer_speed_tier, display |
| `python feat_egg_group.py --autotest` | 18 — name mapping, formatting, display browser, graceful edge cases |
| `python feat_evolution.py --autotest` | 35 — trigger parsing, chain flattening, gen filter, display (mock) |
| `python pkm_pokeapi.py --autotest` | ~22 — versioned entry builder, mapping tables, fetch_pokemon offline, egg_groups, evolution_chain_id |

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
| `pkm_cache.py` | All cache reads and writes (single gateway) |
| `pkm_pokeapi.py` | PokeAPI adapter; fetch + translate raw data |
| `matchup_calculator.py` | Type chart data (ERA1/2/3) + multiplier logic |
| `feat_quick_view.py` | Option 1: quick view (stats / abilities / egg groups / type chart) |
| `feat_move_lookup.py` | Key M: move lookup with version history |
| `feat_movepool.py` | Option 2: learnable move list with conditions |
| `feat_moveset.py` | Options 3–4: scored pool + moveset recommendation UI |
| `feat_moveset_data.py` | Scoring engine (pure logic, no I/O) |
| `feat_type_browser.py` | Key B: browse Pokemon by type |
| `feat_nature_browser.py` | Key N: nature table + recommender |
| `feat_ability_browser.py` | Key A: ability browser + drill-in |
| `feat_stat_compare.py` | Key C: side-by-side base stat comparison + stat analysis helpers |
| `feat_egg_group.py` | Key E: egg group browser + breeding partners |
| `feat_evolution.py` | Evolution chain display (embedded in option 1) |
| `feat_team_loader.py` | Key T: team context management |
| `feat_team_analysis.py` | Key V: team defensive vulnerability table |
| `feat_team_offense.py`  | Key O: team offensive type coverage |
| `feat_team_moveset.py` | Key S: team-level moveset recommendations + coverage summary |
| `run_tests.py` | Test runner for all suites |

**Obsolete files** (safe to delete):
`feat_type_matchup.py` (renamed to `feat_quick_view.py` in §85),
`pkm_scraper.py`, `pkm_move_scraper.py`, `debug2.py`, `debug3.py`, `probe_forms.py`,
`test_move_parser.py`, `test_status_categories.py`, `probe_status_categories.py`
