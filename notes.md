# Pokemon Toolkit — Development Notes

> This is the complete decision and history log for the AI assistant in future sessions.
> For a clean feature/architecture overview, see README.md.
> Last updated: March 2026.

---

## CURRENT STATUS SNAPSHOT

**Project state:** Feature-complete for single-Pokemon analysis. All core features working.

### Active files

| File | Status | Self-tests |
|---|---|---|
| `pokemain.py` | ✅ Production | launch + integration only |
| `pkm_session.py` | ✅ Production | `--autotest` (14 offline) |
| `pkm_cache.py` | ✅ Production | `python pkm_cache.py` (33 offline) |
| `pkm_pokeapi.py` | ✅ Production | `--autotest` (~10 offline; `--verify` live) |
| `matchup_calculator.py` | ✅ Production | `--autotest` (79 offline) |
| `feat_type_matchup.py` | ✅ Production | no pure logic to test (all IO) |
| `feat_move_lookup.py` | ✅ Production | `--autotest` (12 offline + 2 cache) |
| `feat_movepool.py` | ✅ Production | `--autotest` (9 offline + 2 cache) |
| `feat_moveset.py` | ✅ Production | `--autotest` (23 offline + 1 cache) |
| `feat_moveset_data.py` | ✅ Production | `--autotest` (152 offline) |
| `feat_type_browser.py` | ✅ Production | `--autotest` (41 offline) |
| `feat_nature_browser.py` | ✅ Production | `--autotest` (27 offline) |
| `feat_ability_browser.py` | ✅ Production | `--autotest` (14 offline) |
| `run_tests.py` | ✅ Production | runs all suites; `--offline`, `--quiet` flags |

### Feature checklist

| Feature | Status |
|---|---|
| Type vulnerabilities & resistances | ✅ |
| Move lookup (stats + version history + coverage) | ✅ |
| Learnable move list (conditions) | ✅ |
| Learnable move list (scored) | ✅ |
| Moveset recommendation (Coverage / Counter / STAB) | ✅ |
| Type coverage summary in moveset output | ✅ |
| Locked slots (pin specific moves) | ✅ |
| Per-variety learnset (regional/alternate forms) | ✅ |
| Old cache auto-upgrade (variety_slug backfill) | ✅ |
| Era-aware type charts (ERA1/2/3) | ✅ |
| Gen/era compatibility enforcement | ✅ |

### Known limitations / open items

- `STATUS_MOVE_TIERS` is hand-curated (~130 entries). New moves need manual additions.
- Simple forms with identical types (Rotom variants) share the base form's learnset — by design.
- Legends: Z-A cooldown mechanic not modelled by PokeAPI — standard values shown.

### Files to delete

`test_status_categories.py`, `probe_status_categories.py` — superseded by `feat_moveset_data.py --autotest`.
`pkm_scraper.py`, `pkm_move_scraper.py`, `debug2.py`, `debug3.py`, `probe_forms.py`, `test_move_parser.py` — old dev artifacts.

`test_score_move.py` — interactive scored-pool viewer; not part of the test suite but harmless to keep.

### Context dicts (current schema)

```python
game_ctx = {
    "game"    : str,    # e.g. "Scarlet / Violet"
    "era_key" : str,    # "era1" | "era2" | "era3"
    "game_gen": int,    # 1–9
}

pkm_ctx = {
    "pokemon"     : str,        # species slug / search key (e.g. "sandslash")
    "variety_slug": str,        # PokeAPI variety slug (e.g. "sandslash-alola")
    "form_name"   : str,        # display name (e.g. "Alolan Sandslash")
    "types"       : list[str],  # e.g. ["Ice", "Steel"]
    "type1"       : str,
    "type2"       : str,        # "None" (string) if single-type
    "species_gen" : int,
    "form_gen"    : int,
    "base_stats"  : dict,       # hp, attack, defense, special-attack, special-defense, speed
}
```

---

## DECISION LOG


---
## 2. Architecture Decisions

### 2.1 Two-state menu system
**Decision:** Main menu has two states — no-Pokemon-loaded and Pokemon-loaded.
**Reason:** Avoids re-entering Pokemon name every time. Session persists until explicitly changed.
**Implementation:** `session` dict passed around; `None` = no Pokemon loaded.

### 2.2 Modular file structure (8 files)
**Decision:** Split into separate modules rather than one large file.
**Reason:** Easier to maintain, test individually, and evolve each concern independently.
Each file has a single responsibility (scraping, caching, UI, calculation).

### 2.3 Data source split
**Decision:** Two websites, each used for what they do best:
- **pokemondb.net** — Pokemon forms, types, base stats, learnsets
- **Bulbapedia** — Move table (current values) + modification history (versioned changes)

**Reason:** Bulbapedia has a dedicated `/wiki/List_of_modified_moves` page with structured tables
for all historical changes. pokemondb.net has no equivalent — changes are buried in prose.
Switching Pokemon data to Bulbapedia was rejected because pokemondb.net parses more cleanly.

### 2.4 Per-Pokemon JSON files (not a single pokemon.json)
**Decision:** One file per Pokemon: `cache/pokemon/<name>.json`
**Rejected alternative:** Single `pokemon.json` with all ~1025 entries.
**Reason:** Per-file means load only what you need, write only what changed, corruption is
isolated to one Pokemon. The single-file approach would require loading and rewriting the
entire file on every save — slow and risky at scale.
**Exception:** `moves.json` stays as a single file because moves are always loaded as a
complete lookup table.

### 2.5 Pokemon index file
**Decision:** `cache/pokemon_index.json` — compact summary (name + types per form only).
**Reason:** Enables future cross-Pokemon queries (team builder) without loading all individual
files. Updated automatically on every `save_pokemon()` call.
**Index repair:** `get_pokemon()` silently repairs the index if a Pokemon's file exists but
is missing from the index (handles pre-index cached files from older versions).

### 2.6 SQLite as future migration path
**Decision:** Documented as a future option, not implemented now.
**Trigger:** Only needed if team builder requires filtered cross-Pokemon queries
(e.g. "all Fire types with base Speed > 100") that the index file can't serve efficiently.
**Migration path is clean:** only `pkm_cache.py` internals change; all callers use the same
`cache.get_pokemon(name)` → dict API regardless of storage backend.

### 2.7 Move versioning schema: from_gen / to_gen ranges
**Decision:** Each versioned move entry uses `from_gen` / `to_gen` integer range:
```json
{"from_gen": 1, "to_gen": 5, "type": "Fire", "category": "Special", "power": 95, ...}
{"from_gen": 6, "to_gen": null, ...}
```
`to_gen: null` means still current (open-ended).

**Rejected alternative:** `applies_to_gens: [1, 2, 3, 4, 5]` — explicit list of gen numbers.
**Reason:** Range is more explicit, easier to reason about, simpler lookup logic, and
future-proof (new gen = only update records with `to_gen: null`).

**`applies_to_games` override:** Highest-priority field for game-specific exceptions
(e.g. Legends: Z-A uses a cooldown system instead of PP). Takes precedence over gen range.

### 2.8 Move scraper: three-pass pipeline
**Decision:** `build_moves()` runs three passes:
- **Pass 1** — `/wiki/List_of_moves`: scrapes all ~902 moves with current gen values
- **Pass 2** — `/wiki/List_of_modified_moves`: applies historical changes (power, accuracy, PP, type, category)
- **Pass 3** — `apply_gen1_3_category_rule()`: corrects Gen 1-3 categories based on type-based rule

**Reason for Pass 3:** The Gen 1-3 Physical/Special split was type-based (Dragon/Fire/Water/
Grass/Electric/Ice/Psychic = Special; everything else = Physical). Bulbapedia does NOT list
this as individual move changes because it affected all moves wholesale. Pass 1 gives current
(Gen 4+) individual categories. Without Pass 3, all Gen 1-3 entries have wrong categories.

**Pass 3 logic:**
- Any entry overlapping Gen 1-3 with a non-Status category gets corrected to type-based rule
- If the entry spans both eras (from_gen ≤ 3 AND to_gen ≥ 4 or None), it gets split at Gen 4:
  closed half (Gen 1-3) gets type-based category, opened half (Gen 4+) keeps current category

---


---

## 3. Design Constraints

### 3.1 Thonny IDE on Windows
- Scripts run via `%run scriptname.py` in the Thonny shell
- Arguments passed as `%run scriptname.py --flag`
- No virtual environment — system Python
- No network access from Claude's sandbox — all scraping must happen on user's machine

### 3.2 No external dependencies
All scraping uses `urllib.request` (stdlib). No `requests`, `BeautifulSoup`, or `lxml`.
This was a deliberate constraint to avoid pip install complications for the user.

### 3.3 Single flat folder
All .py files and the `cache/` subdirectory live in the same folder.
No package structure, no `__init__.py`.

### 3.4 Atomic writes mandatory
All cache writes go to `<file>.tmp` first, then `shutil.move()` to final path.
Reason: crash mid-write leaves original untouched. `shutil.move()` is atomic on same filesystem.
Orphaned `.tmp` files are cleaned up on write failure.

### 3.5 Defensive reads mandatory
Every `get_*` function in `pkm_cache.py` is wrapped in try/except.
On `FileNotFoundError`, `JSONDecodeError`, or `OSError` → return None (cache miss).
On schema validation failure → print warning, return None (triggers re-scrape).
Corrupt files are self-healing: next access re-scrapes and overwrites.

---


---

## 4. Resolved Edge Cases

### 4.1 Numeric Pokemon name input ("1")
**Problem:** User typed "1" (Pokedex number), pokemondb.net resolved it to a Pokemon page.
**Fix:** `lookup_pokemon()` in `pkm_session.py` rejects any input where `name.isdigit()` is True
before hitting the network. Prints "Please enter a name, not a Pokedex number."

### 4.2 Unexpected name resolution confirmation
**Fix:** After a successful fetch, if the found Pokemon name differs from the input, print
"Found: <name> (for input '<input>')". This catches partial-match redirects.
Only prints when names differ — exact matches stay silent (no noise).

### 4.3 Pre-index cache files missing from index
**Problem:** Users who had `cache/pokemon/<n>.json` files from before the index feature
was added would never have those entries in `pokemon_index.json`.
**Fix:** `get_pokemon()` checks if the Pokemon is in the index after a successful read.
If not, calls `_update_index()` silently. Self-heals through normal usage, no migration needed.

### 4.4 Outrage Gen 1-3 category wrong
**Problem:** Pass 1 gives Outrage current category (Physical). Pass 2 finds the Gen 4
power+category change but doesn't correct the Gen 2-3 entry because the type-based split
is not listed as individual move changes on Bulbapedia.
**Fix:** Pass 3 (`apply_gen1_3_category_rule`) sweeps all entries and corrects Gen 1-3
categories based on type. Outrage is Dragon type → Special in Gen 1-3 → correctly split.

### 4.5 Moves with multiple changes (e.g. Outrage: category at Gen 4, PP at Gen 5)
**Fix:** `_apply_change()` is designed to be called multiple times in ascending gen order.
Each call finds the current open-ended entry and splits it. The result after two calls on
Outrage is 3 entries: Gen 2-3 (Special, 90 power, 15 PP), Gen 4 (Physical, 120, 15),
Gen 5+ (Physical, 120, 10).

---


---

## 5. Failed Approaches and Debugging

### 5.1 Move list scraper — Pass 1 producing 0 moves (3 iterations)

**Attempt 1 — Wrong column order assumed**
Assumed columns were: Name, Type, Category, Power, Accuracy, PP, Effect, Prob.
Actual columns are: #, Name, Type, Category, PP, Power, Accuracy, Gen.
No Effect column on this page. Result: 0 moves.

**Attempt 2 — Wrong gen extraction method**
Used `link_re = re.compile(r'>([^<]+)</a>')` to extract Roman numeral from gen cell.
Actual gen cell HTML: `<b><a href="..."><span style="color:#fff;">I</span></a></b>`
The `>I</a>` pattern never matches because `</span>` comes before `</a>`.
Also: `td_re` was capturing content only (not the tag+content tuple), so
`data-sort-value="1"` on the `<td>` tag was inaccessible.
Result: 0 moves.

**Root cause identified via debug scripts:**
- `debug_scraper.py` — dumped raw HTML of first few rows, revealed actual column order
- `debug2.py` — counted `<tr>` blocks, confirmed 8-cell rows exist but none parsed
- `debug3.py` — step-by-step minimal parser that worked correctly

**Fix:**
- `td_re = re.compile(r'(<td[^>]*>)(.*?)</td>', re.DOTALL)` — captures (tag, content) tuple
- Gen extracted from `cells[7][0]` (the `<td>` tag) via `data-sort-value="(\d+)"`
- Name/type/category extracted via `title="Name (move)"`, `title="Type (type)"`,
  `title="(Physical|Special|Status)..."` attributes — robust against nested `<span>` tags

**Lesson:** Always write a minimal debug script first. Don't assume HTML structure.
The `title="..."` attribute approach is more robust than link text extraction.

**Important workflow note:** When Claude provides updated files, the user must re-download
them — Thonny keeps the old version in memory/on disk. Always confirm with a version marker
or small visible change that the new file is actually running.

### 5.2 Move modifications scraper — Pass 2 producing 0 changes

**Problem:** Regex `r'id="Generation_([IVX]+)_to_Generation_([IVX]+)"'` missed all sections.
**Actual IDs:** `Generation_I_to_Generation_II`, `Generation_I_to_Generation_II_2`, etc.
Bulbapedia appends `_2`, `_3`, `_4`... suffixes for each change type within the same
generation transition (one suffix per category of change: power, accuracy, PP, type, category).
**Fix:** Added `(?:_\d+)?` to the regex.

**Problem 2:** Nested table structure.
Outer wrapper table contains inner data table. Simple `re.finditer(r'<table...')` finds the
outer table first; the inner table (with the actual data) is nested inside. The fix was to
iterate all tables in each section and take the LAST one that has a "Move" header.

**Problem 3:** Logic inversion in `_apply_change`.
Original design had `_apply_change(versions, change_gen, old_fields)` where old_fields was
applied to the historical (pre-change) entry. But the opened entry was left with current
values from Pass 1 (correct for post-change). This was architecturally sound but required
careful understanding. Final design uses explicit `old_fields` + `new_fields` parameters.

### 5.3 scrape_modifications `str_replace` failures
Several `str_replace` operations failed because the file had already been partially modified
from a previous attempt — the old string was no longer present. Solution: use `view` to
read exact current content before attempting any replacement.

### 5.4 `_update_index` accidentally wired into `save_learnset`
When using string replacement to add `_update_index(name, data)` after `save_pokemon()`,
the replacement pattern matched both the pokemon save block AND the learnset save block
(both had `data["scraped_at"] = _now()` followed by `_write(path, data)`).
Fix: used line number inspection + targeted single-line removal.

---


---

## 6. Bulbapedia HTML Structure Reference

### 6.1 List_of_moves page
URL: `https://bulbapedia.bulbagarden.net/wiki/List_of_moves`
Table columns (in order): `#`, `Name`, `Type`, `Category`, `PP`, `Power`, `Accuracy`, `Gen`
Row structure:
```html
<tr>
  <td>53</td>                            <!-- col 0: dex number (plain int) -->
  <td><a href="..." title="Flamethrower (move)">Flamethrower</a></td>  <!-- col 1 -->
  <td ...><a href="..." title="Fire (type)"><span>Fire</span></a></td>  <!-- col 2 -->
  <td ...><a href="..." title="Special move"><span>Special</span></a></td> <!-- col 3 -->
  <td>15</td>                            <!-- col 4: PP -->
  <td>90</td>                            <!-- col 5: Power -->
  <td>100%</td>                          <!-- col 6: Accuracy (has % suffix!) -->
  <td data-sort-value="1" ...><b><a href="..."><span>I</span></a></b></td> <!-- col 7: Gen -->
</tr>
```

**Key parsing notes:**
- Gen number: read `data-sort-value` attribute on the `<td>` tag — NOT the link text
  (the Roman numeral is inside `<span>` inside `<a>`, so `>I</a>` never appears directly)
- Name: use `title="Name (move)"` attribute pattern
- Type: use `title="Type (type)"` attribute pattern
- Category: use `title="(Physical|Special|Status)..."` attribute pattern
- Accuracy: strip `%` suffix before parsing as int
- Power/PP: plain integers, `—` = None

### 6.2 List_of_modified_moves page
URL: `https://bulbapedia.bulbagarden.net/wiki/List_of_modified_moves`
Section IDs: `Generation_I_to_Generation_II`, `Generation_I_to_Generation_II_2`, etc.
Suffix `_2`, `_3`... = different change category (power, accuracy, PP, type, category)
within the same gen transition.

Table structure: nested — outer wrapper + inner data table.
Inner table headers identify the changed field (Power / Accuracy / PP / Type / Category).
Sub-headers: `Gen I | Gen II` (old value | new value).
Data rows: move name in col 0 (use `title="Name (move)"`), then old value, then new value.
Values are plain `<td>90\n</td>` — strip whitespace.

**Known incomplete:** Bulbapedia's own banner says "missing Generation VIII changes."
Gen 1-3 type-based split is NOT listed here at all (see Pass 3 rationale above).

---


---

## 7. resolve_move() Logic

```python
def resolve_move(moves_data, move_name, game, game_gen):
    # Priority 1: applies_to_games exact match (for Z-A cooldown system etc.)
    # Priority 2: from_gen <= game_gen <= to_gen (None = open-ended)
    # Returns None if no entry matches (move didn't exist in that gen)
    # NO fallback to first entry — a miss means genuinely not available
```

**Test cases that must pass:**

| Move | Game | Gen | Expected |
|---|---|---|---|
| Outrage | Red/Blue/Yellow | 1 | None (introduced Gen 2) |
| Outrage | Gold/Silver/Crystal | 2 | Special, power=90, pp=15 |
| Outrage | Ruby/Sapphire/Emerald | 3 | Special, power=90, pp=15 |
| Outrage | Diamond/Pearl/Platinum | 4 | Physical, power=120, pp=15 |
| Outrage | Black/White | 5 | Physical, power=120, pp=10 |
| Outrage | Scarlet/Violet | 9 | Physical, power=120, pp=10 |
| Flamethrower | Red/Blue/Yellow | 1 | Special, power=95, pp=15 |
| Flamethrower | Black/White | 5 | Special, power=95, pp=15 |
| Flamethrower | X/Y | 6 | Special, power=90, pp=15 |
| Flamethrower | Scarlet/Violet | 9 | Special, power=90, pp=15 |
| Thunderbolt | Legends: Z-A | 9 | cooldown=2 (game override) |
| Thunderbolt | Scarlet/Violet | 9 | power=90, pp=15 (standard) |

These are coded as assertions in `pkm_cache.py` self-test.

---


---

## 8. Gen 1-3 Type-Based Category Rule

```python
SPECIAL_TYPES_GEN1_3 = {"Dragon", "Fire", "Water", "Grass", "Electric", "Ice", "Psychic"}

def _category_gen1_3(move_type):
    return "Special" if move_type in SPECIAL_TYPES_GEN1_3 else "Physical"
```

**All other types in Gen 1-3 are Physical:** Normal, Fighting, Poison, Ground, Flying,
Bug, Rock, Ghost (Gen 1 Ghost moves hit Normal types — special mechanic), Dark (added Gen 2),
Steel (added Gen 2).

**Note on Ghost in Gen 1:** Ghost-type moves were bugged in Gen 1 (Lick was Normal-type
effective, not Ghost). The category rule still applies (Ghost = Physical in Gen 1-3).

**This rule applies to entries with `from_gen <= 3`.** Any move entry that spans across
the Gen 3/4 boundary (to_gen is None or >= 4) must be split at Gen 4 by Pass 3.

---


---

## 9. Cache Module Key Design Points (pkm_cache.py)

### Upsert rules
- Layer 2 (pokemon): match by `form["name"]`, replace matching forms, append new ones
- Layer 3 (learnsets): `dict.update()` semantics on forms dict
- Layer 1 (moves): entire versioned list replaced per move name

### Index file
- `pokemon_index.json` stores only `{name: {forms: [{name, types}]}}` — no stats
- Auto-updated by `save_pokemon()` via `_update_index()`
- Auto-repaired by `get_pokemon()` if entry missing from index
- `invalidate_pokemon()` removes entry from index via `invalidate_index_entry()`
- Index write failure is non-fatal (per-Pokemon file already saved)

### Refresh flags (CLI)
```
python pokemain.py --refresh-moves
python pokemain.py --refresh-pokemon <name>
python pokemain.py --refresh-learnset <name> <game>
python pokemain.py --refresh-all <name>
```

### Interactive refresh
- Menu option "3. Refresh moves table" → calls `pkm_move_scraper.build_moves()`
- Menu option "R. Refresh current Pokemon" → calls `cache.invalidate_all()` + `refresh_session()`

### Test redirection
Self-tests redirect `_BASE`, `_POKEMON_DIR`, `_LEARNSET_DIR`, `_MOVES_FILE`, `_INDEX_FILE`
to a `tempfile.TemporaryDirectory()`. Tests must redirect ALL five globals or index writes
go to the real cache dir during testing.

---


---

## 10. Roadmap Status

| Step | Description | Status |
|---|---|---|
| 1 | GAME_TO_VERSION_GROUPS mapping | ✅ Done |
| 2 | fetch_pokemon() — types, stats, forms | ✅ Done |
| 3 | fetch_move() / fetch_all_moves() — versioned | ✅ Done |
| 4 | fetch_learnset() + machines cache | ✅ Done |
| 5 | Wire PokeAPI fully into pkm_cache (confirm _LEGACY_SCRAPER=False) | ⬜ Pending |
| 6 | Parallel validation + scraper deletion | ⬜ Pending |
| 7 | Final cleanup of migration constants | ⬜ Pending |
| — | feat_type_matchup | ✅ Done |
| — | feat_move_lookup | ✅ Done |
| — | feat_movepool | ✅ Done |
| — | feat_moveset (recommendation) | ⬜ Not started |

---

## 11. Miscellaneous Findings

### 11.1 pokemondb.net intro-paragraph parser
The original scraper relied on the `<p><em>Name</em> is a ... type</p>` paragraph.
This breaks for Pokémon whose intro paragraph has alternate phrasing.
PokeAPI completely replaces the need for this.

### 11.2 Bulbapedia List_of_modified_moves table format
Historical move changes are stored as: `<row> = [move_name, gen_changed, field, old, new]`.
Gen numbers are Roman numerals. The "old" value is what changed FROM, not TO.
This caused an off-by-one in the first implementation — see §5.

### 11.3 pkm_matchup.py
The original single-file prototype. Superseded by the modular toolkit.
Can be removed from the folder if it still exists.

---
## 12. PokeAPI vs Web Scraping — Analysis and Decision (March 2026)

### Context
Evaluated switching from web scraping (pokemondb.net + Bulbapedia) to the PokeAPI REST API
(pokeapi.co/docs/v2) before building the learnset scraper. Decision made before any learnset
code was written, which made this the right moment to switch.

### What PokeAPI covers for our use cases

**Move data (replaces pkm_move_scraper.py entirely):**
- `/api/v2/move/{name}` returns current power, accuracy, PP, type, damage_class
- `past_values` field: list of `PastMoveStatValue` objects, each with power/accuracy/PP/type
  and the `version_group` in which those values applied
- This directly replaces all three scraper passes:
  - Pass 1 (current values) — covered by top-level fields
  - Pass 2 (Bulbapedia modification history) — covered by `past_values`
  - Pass 3 (Gen 1-3 type-based category correction) — covered by `past_values` entries
    for early version groups, which already have the correct historical categories
- Version-group precision is FINER than our gen-level from_gen/to_gen ranges
  (e.g. can distinguish Red/Blue from Yellow if values ever differed)
- Eliminates the Bulbapedia Gen VIII completeness warning entirely

**Learnset data (replaces the planned scraper we hadn't built yet):**
- `/api/v2/pokemon/{name}` returns `moves` array
- Each entry has `version_group_details`: list of {level_learned_at, move_learn_method,
  version_group} — one entry per game in which the Pokemon can learn the move
- move_learn_method values: "level-up", "egg", "tutor", "machine"
- This gives us level-up moves (with level), TM/HM, egg moves, and tutor moves per game
  in a single API call — the entire learnset layer, for free

**TM/HM numbers per game:**
- `/api/v2/machine/{id}` maps machine number (TM01, HM04...) to a move and version_group
- "TM26 = Earthquake in Red/Blue but TM41 in Gold/Silver" is handled natively
- We weren't planning to scrape this at all — it's a bonus capability

**Pokemon base data:**
- `/api/v2/pokemon/{name}` also returns base stats, types, abilities, sprites
- Types field is an array with slot numbers, handles dual-type natively
- Replaces pokemondb.net scraping for types/stats

**Rate limiting:**
- No rate limits since late 2018 (moved to static hosting)
- Fair use policy asks for local caching — which we already do by design
- No authentication required

### What PokeAPI does NOT handle well

**Alternate forms:**
- Each form is a separate endpoint: charizard, charizard-mega-x, charizard-mega-y
- Our current scraper gets all forms from one pokemondb.net page with one HTTP request
- With PokeAPI, discovering all forms requires either:
  a) Calling `/api/v2/pokemon-species/{name}` first to get `varieties` list, then
     fetching each variety individually
  b) Or: keeping pokemondb.net just for the form discovery step
- This is the main structural difference — more API calls per Pokemon lookup

**Brand-new games:**
- PokeAPI lags behind new game releases by weeks to months
- pokemondb.net and Bulbapedia are updated much faster after launch
- Legends: Z-A is already in our GAMES list — its API coverage may be incomplete
- Mitigation: keep scraping code as fallback, use config flag to switch per-source

### Build cost: move table initialisation
- Current scraper: 2 HTTP requests → entire moves.json in seconds
- PokeAPI: ~900 individual requests (one per move) → several minutes for initial build
- This is a one-time cost (cache-once strategy)
- Must show progress counter to user during initial build (e.g. "Fetching move 342/920...")
- Subsequent runs: fully offline from cache, identical to current behaviour

### Decision
**Primary source: PokeAPI** for moves, learnsets, base stats, and types.
**Fallback/supplement: web scraping** for:
- Alternate form discovery (pokemondb.net species page, one call per lookup)
- Brand-new games not yet in PokeAPI
- Any data gap identified during migration testing

This eliminates the two most fragile components we already debugged extensively
(Bulbapedia HTML parsing, pokemondb.net type extraction), and gives us learnsets,
TM/HM mapping, and tutor moves without writing any new scraping code.

### Architecture: source adapter pattern (Option A — config flag)

New file: `pkm_config.py`
```python
DATA_SOURCE = "pokeapi"  # or "scrape" — controls which backend is called on cache miss
```

New file: `pkm_pokeapi.py` — translates PokeAPI responses into our existing cache schemas.
All callers (pkm_session.py, pokemain.py) remain completely untouched.
Only `pkm_cache.py` changes: on cache miss, it calls either `pkm_scraper` or `pkm_pokeapi`
based on the config flag.

Internal JSON schema does NOT change:
- `cache/pokemon/<n>.json` format stays the same
- `cache/moves.json` from_gen/to_gen versioned format stays the same (PokeAPI's
  version_group entries map cleanly onto gen-level ranges — slightly more precise but
  fully compatible)
- `cache/learnsets/<n>_<game>.json` format stays the same (PokeAPI returns the same
  logical data, just sourced differently)

Option B (abstract adapter class / protocol) deferred until there's a need to use both
sources simultaneously for the same data type (e.g. scrape Z-A data, API for everything
else). Option A's config flag is sufficient for now.

### PokeAPI internal identifier mapping needed
PokeAPI uses hyphenated lowercase slugs, not our display names:
- "Red / Blue / Yellow" → version_group "red-blue" (Yellow is separate: "yellow")
- "Gold / Silver / Crystal" → "gold-silver" / "crystal"
- "Diamond / Pearl / Platinum" → "diamond-pearl" / "platinum"
- "Legends: Arceus" → "legends-arceus"
- "Legends: Z-A" → likely "legends-z-a" (verify when available)
A mapping table in `pkm_pokeapi.py` translates our GAMES list entries to API slugs.
Note: some of our combined entries (e.g. "Red / Blue / Yellow") cover multiple PokeAPI
version groups — learnset queries need to check all of them.

Known version_group slug → our GAMES display name mapping (verify slugs against API before coding):
```
"red-blue"                  → "Red / Blue / Yellow" (yellow is a separate slug but same era)
"yellow"                    → also maps to "Red / Blue / Yellow"
"gold-silver"               → "Gold / Silver / Crystal"
"crystal"                   → also maps to "Gold / Silver / Crystal"
"ruby-sapphire"             → "Ruby / Sapphire / Emerald"
"emerald"                   → also maps to "Ruby / Sapphire / Emerald"
"firered-leafgreen"         → "FireRed / LeafGreen"
"diamond-pearl"             → "Diamond / Pearl / Platinum"
"platinum"                  → also maps to "Diamond / Pearl / Platinum"
"heartgold-soulsilver"      → "HeartGold / SoulSilver"
"black-white"               → "Black / White"
"black-2-white-2"           → "Black 2 / White 2"
"x-y"                       → "X / Y"
"omega-ruby-alpha-sapphire" → "Omega Ruby / Alpha Sapphire"
"sun-moon"                  → "Sun / Moon"
"ultra-sun-ultra-moon"      → "Ultra Sun / Ultra Moon"
"sword-shield"              → "Sword / Shield"
"brilliant-diamond-shining-pearl" → "Brilliant Diamond / Shining Pearl"
"scarlet-violet"            → "Scarlet / Violet"
"legends-arceus"            → "Legends: Arceus"
"legends-z-a"               → "Legends: Z-A"  ← verify, may not exist in API yet
```
For learnset lookups, need to union all version_group slugs belonging to a given GAMES entry
(e.g. querying "Gold / Silver / Crystal" means merging results from "gold-silver" + "crystal").

### PokeAPI response schema details — key fields

**`/api/v2/move/{name}` — relevant fields:**
```json
{
  "name": "flamethrower",
  "power": 90,
  "pp": 15,
  "accuracy": 100,
  "damage_class": {"name": "special"},
  "type": {"name": "fire"},
  "generation": {"name": "generation-i"},
  "past_values": [
    {
      "accuracy": null,
      "effect_chance": null,
      "power": 95,
      "pp": null,
      "type": null,
      "version_group": {"name": "gold-silver"}
    }
  ]
}
```
`past_values` entries only list the fields that CHANGED — nulls mean "same as the next newer
entry". To reconstruct full stats for a version_group, start from current values and apply
past_values in reverse chronological order (most recent past_value first).
`version_group` in past_values is the LAST version_group where those old values were in effect
(i.e. "these values applied UP TO AND INCLUDING this version_group").

**`/api/v2/pokemon/{name}` — learnset relevant fields:**
```json
{
  "moves": [
    {
      "move": {"name": "flamethrower"},
      "version_group_details": [
        {
          "level_learned_at": 0,
          "move_learn_method": {"name": "machine"},
          "version_group": {"name": "red-blue"}
        },
        {
          "level_learned_at": 47,
          "move_learn_method": {"name": "level-up"},
          "version_group": {"name": "scarlet-violet"}
        }
      ]
    }
  ]
}
```
`level_learned_at: 0` = not level-up (TM/HM/tutor/egg). Filter by `move_learn_method.name`
to separate categories.

**`/api/v2/pokemon-species/{name}` — forms relevant fields:**
```json
{
  "varieties": [
    {"is_default": true,  "pokemon": {"name": "charizard",        "url": "..."}},
    {"is_default": false, "pokemon": {"name": "charizard-mega-x", "url": "..."}},
    {"is_default": false, "pokemon": {"name": "charizard-mega-y", "url": "..."}}
  ]
}
```
Use this to discover all forms before fetching each one individually.

### What does NOT change in the internal schema

The `cache/moves.json` from_gen/to_gen versioned format stays fully intact.
The translation from PokeAPI's version_group-level `past_values` to our gen-level ranges
is done inside `pkm_pokeapi.py`, invisible to all callers.
The `cache/pokemon/<n>.json` and `cache/learnsets/<n>_<game>.json` schemas stay the same.
`pkm_cache.py` callers (pkm_session.py, pokemain.py, feat_*.py) are completely untouched.

### Files impacted by migration

| File | Change |
|---|---|
| `pkm_config.py` | NEW — `DATA_SOURCE` flag |
| `pkm_pokeapi.py` | NEW — API adapter, all translation logic lives here |
| `pkm_cache.py` | Small change — on cache miss, branch on `DATA_SOURCE` |
| `pkm_scraper.py` | Unchanged — kept as fallback |
| `pkm_move_scraper.py` | Superseded but kept for fallback / new-game gap filling |
| All other files | Completely untouched |

### Testing the migration

Golden-file comparison strategy: run both backends for the same inputs and diff the outputs.
Specifically:
- Build `moves.json` via scraper → save as `moves_scrape.json`
- Build `moves.json` via PokeAPI → save as `moves_api.json`
- Compare Outrage, Flamethrower, Thunderbolt versioned entries — these are the known-good
  spot-check cases already in the test suite
- Run `pkm_cache.py` self-tests (22 assertions) against PokeAPI-sourced data — all must pass
- Fetch Charizard from both sources, compare types/forms output
- Fetch Garchomp learnset (well-known Gen 4 Pokemon) from PokeAPI, verify level-up, TM,
  tutor moves look complete for Diamond/Pearl

---


---

## 13. PokeAPI `past_values` Findings and Gen1-3 Category Rule (Step 3)

### past_values timestamp semantics (discovered via --dry-run testing)

PokeAPI's `past_value.version_group` is the **last version_group that still had the OLD value**,
not the first version_group with the new value. This is off by one generation compared to
Bulbapedia, which records the gen in which the change was introduced.

Practical effect:
- Flamethrower past_value under `x-y` (Gen6) means: Gen6 still had power=95.
  PokeAPI current value (power=90) first applies in Gen7 (Sun/Moon).
  Bulbapedia says the nerf was in X/Y (Gen6). **PokeAPI boundary = Gen6/Gen7, not Gen5/Gen6.**
- Thunderbolt: same pattern (same nerf as Flamethrower, same boundary).
- Outrage: power=90 in Gen2-4 (not Gen2-3 as Bulbapedia says; PokeAPI says power changed
  at Gen5 not Gen4). PP changed at Gen5→Gen6. Category tracked as Physical throughout
  (see Gen1-3 rule below).

Updated test assertions now use PokeAPI values, not Bulbapedia values. Both sources have
minor discrepancies; since we're fully migrated to PokeAPI, we accept PokeAPI as truth.

### PokeAPI does NOT model the Gen1-3 type→category rule

PokeAPI stores only the individual category that was assigned at the Gen4 Phys/Spe split.
For moves like Outrage (Dragon type), PokeAPI says "Physical" all the way back to Gen2.
This is incorrect for gameplay purposes: in Gen1-3, Dragon-type moves were Special.

**Fix implemented in `_apply_gen1_3_category_rule()` (called inside `_build_versioned_entries`):**

Special types in Gen1-3: Fire, Water, Grass, Electric, Ice, Psychic, Dragon, Dark.
All others (Normal, Fighting, Poison, Ground, Flying, Bug, Rock, Ghost, Steel) are Physical.

The function:
1. For any entry covering Gen1-3 (from_gen <= 3), determines the correct category from the type.
2. If the Gen1-3 category differs from the stored category AND the entry spans Gen4+, splits
   the entry at the Gen3/Gen4 boundary: [Gen1-3: corrected category] + [Gen4+: unchanged].
3. If no category change needed (e.g. Fire move already stored as Special), no split.

Result for Outrage (Dragon, intro Gen2, stored as Physical throughout):
- Entry from_gen=2 to_gen=4 gets split → [Gen2-3: Special, power=90] + [Gen4: Physical, power=90]

### Legends: Z-A cooldown system not in PokeAPI

PokeAPI has no data for the Z-A cooldown mechanics. The Thunderbolt Z-A override test was
removed from the live assertion suite. If Z-A mechanics are ever needed, they must be
hardcoded manually or sourced from Bulbapedia/custom scraping.

### Corrected test expectations (PokeAPI + Gen1-3 rule applied)

| Move | Game / Gen | Expected result |
|---|---|---|
| Outrage | Gen1 | None (introduced Gen2) |
| Outrage | Gen2 | **Special**, power=90, pp=10 |
| Outrage | Gen3 | **Special**, power=90, pp=10 |
| Outrage | Gen4 | Physical, power=90, pp=10 ← PokeAPI says power=90 through Gen4 |
| Outrage | Gen5 | Physical, power=120, pp=15 ← power/pp change at Gen5 per PokeAPI |
| Outrage | Gen9 | Physical, power=120, pp=10 |
| Flamethrower | Gen1 | Special, power=95, pp=15 |
| Flamethrower | Gen6 | Special, power=**95**, pp=15 ← PokeAPI boundary is Gen6/Gen7 |
| Flamethrower | Gen7 | Special, power=**90**, pp=15 |
| Flamethrower | Gen9 | Special, power=90, pp=15 |
| Thunderbolt | Gen9 | power=90, pp=15 |

---


---

## 14. Four-state menu UX redesign — design decisions

### Why split game and Pokémon into independent contexts

Previously `build_session()` always asked for both Pokémon AND game in sequence, so you
couldn't look up a move or change game without re-entering a Pokémon. Real usage pattern:
- You pick a game for a session (e.g. Scarlet/Violet) and keep it for many lookups
- You swap Pokémon frequently
- You look up moves with no specific Pokémon in mind

### Session state in pokemain.py (top-level locals, not a dict)

```python
pkm_ctx     = None   # or {pokemon, form_name, types, type1, type2,
                     #      species_gen, form_gen, base_stats}
game_ctx    = None   # or {game, era_key, game_gen}
constraints = []     # list of confirmed move name strings
```

These are separate locals in `main()`, not nested inside each other.
`constraints` is Pokémon-scoped: cleared when a new Pokémon is loaded, kept when game changes.

### Feature gate rules (source of truth)

| Feature | Needs pkm_ctx | Needs game_ctx | Needs moves.json |
|---|---|---|---|
| Type vulnerabilities | ✓ | ✓ | ✗ |
| Full learnable move list | ✓ | ✓ | ✓ |
| Moveset recommendation | ✓ | ✓ | ✓ |
| Look up a move | ✗ | ✓ (for gen context) | ✓ |
| Refresh moves table | ✗ | ✗ | writes it |

Move lookup works without game_ctx but the result would lack "in this game" context — so we
require game_ctx and chain into game selection if missing, rather than showing a degraded result.

### Chaining behavior when context is missing

When user picks a feature and one or both contexts are missing:
- Tell user what's needed: "Type vulnerabilities needs a Pokémon and a game."
- Immediately chain: "Let's select a game first." → game selection prompt
- Then: "Now select a Pokémon." → pokemon selection prompt
- Then run the feature
- Do NOT return to the main menu between steps — stay in the feature flow

Only exception: if user types blank or aborts during a chained selection, return to menu.

### Form type validation against era

When game_ctx is available during pokemon selection:
- Validate type1 exists in era; if not → inform + abort selection
- If type2 doesn't exist in era → warn + treat as single-type (same behavior as before)
- If form was introduced after game_gen → warn but continue (same as before)

When game_ctx is NOT available (Pokémon loaded without game):
- Skip era validation entirely
- Show warning deferred to when game is selected

### feat_*.run() signature change

Old: `feat_type_matchup.run(session)` where session has all keys flat.
New: `feat_type_matchup.run(pkm_ctx, game_ctx)` — two separate dicts.

The feature modules access keys the same way, just from the right dict:
- `pkm_ctx["type1"]` instead of `session["type1"]`
- `game_ctx["era_key"]` instead of `session["era_key"]`

### Constraint moves — design

Stored as `constraints = []` in `pokemain.py` main loop state.
Populated via a dedicated "Add/edit locked moves" sub-flow inside the moveset feature (not
yet active — placeholder is enough for now).

Lookup logic when user types a move name:
1. Exact match (case-insensitive) against moves.json keys → preferred
2. If no exact match: show "Move not found. Did you mean: X, Y, Z?" (startswith filter)
3. If nothing: "Move not found in database."

Confirmed constraints shown in the 4-line header as:
`Locked: Flamethrower, Air Slash`
(line is omitted entirely if constraints list is empty)

---


---

## 15. Dynamic menu rules and matchup_calculator.py decision

### Menu visibility rules (final)

| Element | Condition to show |
|---|---|
| Numbered features (type matchup, movelist, moveset) | Both pkm_ctx AND game_ctx loaded |
| M. Look up a move | game_ctx loaded |
| R. Refresh data for current Pokemon | pkm_ctx loaded |
| P. Load a **different** Pokemon (vs just "Load") | pkm_ctx loaded |
| G. **Change** game (vs "Select game") | game_ctx loaded |
| T. Refresh moves table | always |
| Q. Quit | always |

Pressing M with no game loaded: print "Select a game first (press G)" and loop — do NOT chain into game selection (M is not a feature that needs chaining, the user just forgot).

### matchup_calculator.py — keep as standalone library

Three importers: pkm_session.py, pokemain.py, feat_type_matchup.py.
Merging into feat_type_matchup.py would create a layering violation (session layer importing from a display-feature file). Data and logic layers must not depend on display layers.

The standalone main() is retained — lets you do a quick type lookup without loading the full toolkit.

No code moves. File stays as-is forever unless the type chart data itself needs updating.

---


---

## 16. Step 4 — Learnset fetch design decisions

### Base form only (known limitation)

`fetch_learnset()` fetches `/api/v2/pokemon/{slug}` where slug is the base
form (e.g. `charizard`, not `charizard-mega-x`). All alternate forms of the
same Pokémon share the base-form learnset in the cache.

Why: PokeAPI does have per-form move lists for a handful of Pokémon (Rotom
appliances, Wormadam cloaks, Megas), but in practice the differences are
cosmetic or irrelevant to the move optimizer. The 5% edge cases are not worth
the added complexity (3-5 extra API calls per Pokémon, form name resolution).

If this becomes a problem in the moveset optimizer, the fix is to add a
`form_slug` param to `fetch_learnset()` and call it with the correct slug for
that form. Cache key stays `<name>_<game>.json` per form key.

### machines.json — one fetch, shared across all games

`cache/machines.json` maps machine resource URLs to display labels:
  `"https://pokeapi.co/api/v2/move/53/" : "TM38"`

The full machine table is built on the first learnset fetch that needs it.
It covers ALL version groups in one pass (limit=2000). On subsequent learnset
fetches (same or different game), the cached table is reused — no re-fetch.

### Return signature: (learnset, machines) tuple

`fetch_learnset()` returns a tuple so `get_learnset_or_fetch()` can persist
both the learnset and the machines table in a single API round-trip. This
avoids an extra ~900-call machine fetch on the very next learnset request.

### Lazy loading + cache invalidation

`get_learnset_or_fetch(name, game)` is the single public entry point for
learnset data. Callers never call `fetch_learnset` directly.

Cache invalidation:
- `invalidate_learnset(name, game)` -- one game at a time
- `invalidate_all(name)` -- all games for one Pokémon
- `machines.json` is never auto-invalidated (machine numbers don't change)

### TM label format

PokeAPI item names: `tm038` → `TM38`, `hm04` → `HM4`.
Stripping leading zeros: `tm001` → `TM1` (matches in-game display for older
gens; Gen9 uses 3-digit numbers which PokeAPI stores as `tm001`→`tm171`).
Sort order: all TMs first (numeric), then HMs (numeric).

---


---

## 17. Code Audit and Cleanup (March 2026)

### Bugs found and fixed

**1. Duplicate `fetch_learnset` definition in `pkm_pokeapi.py`**
- Root cause: the session that inserted `fetch_learnset` via string injection added a
  new version at the insertion point, but the file already contained a second (better)
  version written in a prior session. Python silently uses the last definition.
- The inserted version had `machines_cache=` as the parameter name.
- The surviving (active) version used `machines=`.
- `pkm_cache.py` was calling with `machines_cache=` → `TypeError`.
- Fix: deleted the first (stale) definition. One `fetch_learnset` remains.

**2. `pkm_cache.get_learnset_or_fetch` unpacking a dict as a tuple**
- Root cause: the surviving `fetch_learnset` returns a plain `dict`, but
  `get_learnset_or_fetch` was written expecting a `(learnset, machines)` tuple.
- Error: `TypeError: too many values to unpack (expected 2)`
- Fix: changed to `result = _api.fetch_learnset(...)` — no unpacking.
- The surviving version handles machines internally (passes them to `fetch_learnset`,
  which embeds TM labels directly into the learnset dict).

**3. Duplicate `get_machines` / `save_machines` in `pkm_cache.py`**
- Root cause: two separate sessions each inserted a machines cache block.
- The first (stale) version used a merge-on-save pattern keyed by version-group slug.
- The second (active) version uses a flat URL→label dict.
- Python used the last definition — but the first version's `save_machines` was being
  called earlier in the file, writing in the wrong schema.
- Fix: removed the first block entirely (lines 319–391).

### Dead code removed

| Symbol | File | Reason |
|---|---|---|
| `fetch_learnset_cached()` | `pkm_session.py` | Superseded by `cache.get_learnset_or_fetch()`. Never called. |
| `import pkm_move_scraper` | `pokemain.py` | Tagged MIGRATION ONLY, never called. |
| `from pkm_scraper import get_form_gen` | `pkm_session.py` | Function is pure logic (no scraping). Inlined directly into `pkm_session.py` as `get_form_gen()`. |

### What was inlined

`get_form_gen(form_name, species_gen)` — 10-line keyword-lookup function.
Lives in `pkm_session.py` now. No network access, no scraper needed.
`pkm_scraper` is still imported in `pkm_session.py` because the `_LEGACY_SCRAPER = True`
path uses `pkm_scraper.fetch_pokemon_forms()`. This import will be removed in Step 6.

**4. `get_learnset` / `save_learnset` accidentally deleted during audit cleanup**
- Root cause: the line-range deletion used to remove the duplicate machines block
  (lines 319–391) was one block too wide. `get_learnset()`, `save_learnset()`, and
  a duplicate `_LEARNSET_DIR` assignment were collateral damage.
- Symptom: `NameError: name 'get_learnset' is not defined` on first movepool lookup.
- Fix: re-inserted `get_learnset()` and `save_learnset()` in their correct position
  (between the moves layer and the machines layer). Also removed a leftover
  `_valid_machines()` validator whose schema was stale (checked for dict-of-dicts,
  but the live machines format is a flat `{url: label}` dict).
- Lesson: always use `str_replace` for targeted edits; line-range deletions are
  fragile when block boundaries aren't verified precisely first.

### Files still present but entirely superseded

`pkm_scraper.py` and `pkm_move_scraper.py` are fully dead code at runtime
(`_LEGACY_SCRAPER = False`). They are kept only to support the Step 6 parallel
validation (running old and new paths side-by-side to confirm parity before deletion).

### Dev artifact files to delete

The following files are debugging/diagnostic tools from the development process.
They are not part of the toolkit and can be deleted from the folder:
`debug2.py`, `debug3.py`, `debug_scraper.py`, `probe_forms.py`, `test_move_parser.py`

---

## 18. feat_movepool Implementation Notes

### Column layout (fixed-width CLI)
```
  Label    Move                    Type        Category    Pwr    Acc     PP
  Lv 46    Flamethrower            Fire        Special      90   100%   15pp
  TM38     Fire Blast              Fire        Special     110    85%    5pp
           Heat Wave               Fire        Special      95    90%   10pp
           Dragon Dance            Dragon      Status       --    --%   20pp
```

### Move detail pre-fetch
On first call for a Pokémon+game, all moves in the learnset that are not yet in
`moves.json` are batch-fetched (with a progress counter). On subsequent calls, all
details come from cache — zero API calls.

### Form fallback
If `pkm_ctx["form_name"]` is not a key in `learnset["forms"]`, the display falls back
to the first form in the dict. Relevant for alternate forms (Mega, Alolan, etc.) until
per-form learnsets are implemented.

### Constraint integration
If `constraints` is non-empty (locked moves set by user):
- Moves in the pool that are locked: shown as "Locked moves learnable here: X, Y"
- Locked moves NOT in the pool: shown as "WARNING — locked moves NOT in pool: Z"
This is groundwork for the moveset optimizer (feat_moveset.py).

### Known limitation
Base form only. Alternate forms share the base Pokémon's learnset.
Fix path: pass `form_slug` to `fetch_learnset()`, cache per form, update form_label resolution.
Not worth the complexity until the moveset optimizer actually needs it.

---

## 19. PokeAPI Migration Complete (Steps 5–7)

### What was removed from pkm_session.py

- `_LEGACY_SCRAPER = False` constant
- `import pkm_scraper`
- The `if _LEGACY_SCRAPER: ... else:` branch in `_fetch_or_cache()` — kept only the PokeAPI body
- `_forms_to_cache()` helper — only existed to convert scraper output into cache schema;
  `fetch_pokemon()` already returns the correct schema directly

### Why parallel validation was skipped

`_LEGACY_SCRAPER` was set to `False` from the moment it was introduced and never changed.
The PokeAPI path has been the only live path throughout. Data quality was validated
in actual use (Charizard, Onix, etc.) rather than by diff comparison.

### Files to delete from your folder

```
pkm_scraper.py
pkm_move_scraper.py
```

These have zero references in any active file. Deleting them has no effect on the toolkit.

### Current active file list (post-migration)

```
pokemain.py
pkm_session.py
pkm_cache.py
pkm_pokeapi.py
matchup_calculator.py
feat_type_matchup.py
feat_move_lookup.py
feat_movepool.py
feat_moveset.py        ← stub, not yet implemented
README.md
notes.md
cache/                 ← generated at runtime
```

---

## 20. Decisions and Cleanups (post-migration)

### Tutor context — abandoned

PokeAPI has no data on move tutor NPCs, locations, or costs. Bulbapedia has it
but only as unstructured prose inside per-game articles — not scrapeable in any
reliable way. A static lookup table per game was considered but the maintenance
burden vs. value wasn't worth it. The tutor section in the move list shows move
stats only. Documented here so this isn't re-investigated in future.

### Locked moves / constraints UI

The `constraints` list is wired into `pokemain.py` and displayed in the session
header, but there is currently no UI to add or remove moves from it. This is
intentionally deferred to the moveset recommendation feature (feat_moveset.py),
where it will be designed as part of the optimizer flow rather than standalone.

### Menu state 0 — "No Pokemon loaded" added

Previously state 0 (nothing loaded) only showed "No game selected".
Now shows both "No Pokemon loaded" and "No game selected" for clarity.

### T / W split in main menu

Pre-load options split into two separate menu items:
- T — pre-loads move table (~920 moves: type/power/acc/PP)
- W — pre-loads TM/HM machine table (~900 entries across all games)

Both are still lazy by default (fetched on first use). T and W are opt-in
pre-warming options for users who want zero latency from the start.

Both handlers show current cache status before asking for confirmation,
and display progress during the fetch.

### PokeAPI migration steps 5–7

Marked complete without a formal parallel validation run. `_LEGACY_SCRAPER`
was always `False` in production — the PokeAPI path was the only live path.
Data quality validated through live use. Scraper files deleted.

---

## 21. Moveset Recommendation — Design Decisions and Formula

### Scope

`feat_moveset.py` (display + UI) + `feat_moveset_data.py` (static tables + scoring logic).
4-move set recommendation for a loaded Pokémon + game context.

### Optimisation modes

Three modes, selectable via sub-menu (or all three shown at once):

| Mode | Weights heavily | Best for |
|---|---|---|
| Coverage | Types hit super-effectively | Offensive sweepers |
| Counter-weakness | Moves that address the Pokémon's own type weaknesses | Balanced / defensive |
| STAB focus | Moves matching the Pokémon's own type(s) | High-stat attackers |

All three use the same scoring engine with different weight parameters.
Decided to show all three rather than a single opaque recommendation — the
comparison teaches strategy.

### Status moves

Handled as a separate 4th section, not forced into the 4-move set.
Displays top 1–3 status options with category label.
Ranking tier: offensive ailment (paralysis, burn) > setup (stat boost) > recovery > field effect.
Data source: `meta.category` from PokeAPI — clean and reliable.

### Locked slots (constraints)

Designed in from Step 1 — same code path whether 0, 1, 2, or 3 moves are locked.
`constraints` list already exists in pokemain state.
UI to add/remove locked moves implemented in Step 8 (after scoring engine is proven).

### Physical/Special stat weighting

Applied for Gen 4+ only (where each move has its own category).
For Gen 1–3, type determines category — already handled in move data.

```
stat_weight = relevant_stat / weaker_stat, capped at 2.0
```

Where `relevant_stat` = Attack for Physical moves, Sp.Atk for Special.
A Pokémon with Atk 130 / SpAtk 65 → stat_weight = 2.0 for Physical moves.
A Pokémon with balanced stats → stat_weight ≈ 1.0 (no distortion).

### Two-turn move penalties

The API's `min_turns`/`max_turns` fields cannot distinguish:
- Charge moves (turn 1: nothing, turn 2: attack) vs recharge moves (turn 1: attack, turn 2: nothing)
- Invulnerable during off-turn (Fly, Dig, Dive) vs exposed (Solar Beam, Hyper Beam)

Source: static table `TWO_TURN_MOVES` in `feat_moveset_data.py`. List is ~18 moves,
essentially frozen since Gen 5. One-time manual entry, zero ongoing maintenance.

Penalty factors (applied to effective power):

| Type | Invulnerable | Penalty | Rationale |
|---|---|---|---|
| Charge + exposed | No | × 0.5 | Worst: exposed before dealing any damage |
| Recharge + exposed | No | × 0.6 | Bad but better: damage lands first, then exposed |
| Charge + protected | Yes | × 0.8 | Acceptable: safe while waiting, still loses a turn |

Note: these moves are not excluded — they still appear as alternatives if they
score well enough. The penalty just prevents them dominating the recommendation
when a simpler 1-turn option exists.

### Accuracy floor

Moves below 75% accuracy are included in the candidate pool but:
- Accuracy factor is floored at 0.75 for scoring (not lower, to avoid over-penalising)
- A disclaimer is shown in the display output for any recommended move below 75%

Excluded from hard cutoff because high-power low-accuracy moves (Thunder 110pw/70acc,
Blizzard 110pw/70acc, Focus Blast 120pw/70acc) can still be situationally best,
especially with no better alternative.

### Scoring formula

```
move_score =
    base_power
    × stat_weight          # (relevant_stat / weaker_stat), capped 1.0–2.0, Gen 4+ only
    × stab_bonus           # 1.5 if move type in Pokémon's types, else 1.0
    × two_turn_penalty     # from table above, else 1.0
    × accuracy_factor      # min(accuracy, 100) / 100, min 0.75

combo_score =
    sum(move_scores)
    + coverage_bonus       # +15 per unique type hit SE beyond the first
    + weakness_cover       # +25 if a Pokémon weakness is addressed
    - redundancy_penalty   # -20 per duplicate move type (beyond first of that type)
```

Combo search: brute-force over top 20 scored candidates.
C(20,4) = 4,845 combos — runs in milliseconds in Python.

### Display format (planned)

Per-move row in recommendation output:
```
  Flamethrower   Fire    Special   90pw  100%  STAB  ✓ covers Rock weakness
  Earthquake     Ground  Physical  100pw 100%        ✓ covers Rock/Electric weakness
  Air Slash      Flying  Special   75pw   95%  STAB
  Dragon Claw    Dragon  Physical  80pw  100%  STAB
```

Accuracy disclaimer appended if any move is below 75%.
Status section shown separately below the 4-move set.

### What was considered and rejected / deferred

- **Tutor location context**: abandoned — no structured data available (see §20)
- **Hard exclusion of low-accuracy moves**: replaced with disclaimer approach
- **Forcing status move into 4-move set**: replaced with separate section
- **Single recommendation mode**: replaced with 3 modes + all-three view
---

## 22. Step 1 complete — feat_moveset_data.py + feat_moveset.py bug fix

### feat_moveset_data.py created

Static data tables for moveset recommendation scoring:

- `TWO_TURN_MOVES`: 23 moves across 3 penalty categories
  - Charge + exposed (×0.5): Solar Beam, Solar Blade, Sky Attack, Skull Bash, Razor Wind,
    Ice Burn, Freeze Shock, Electro Shot
  - Recharge + exposed (×0.6): Hyper Beam, Giga Impact, Frenzy Plant, Blast Burn,
    Hydro Cannon, Rock Wrecker, Roar of Time, Meteor Assault, Eternabeam
  - Charge + protected (×0.8): Fly, Dig, Dive, Bounce, Shadow Force, Phantom Force, Sky Drop
  - Source: Bulbapedia knowledge of two-turn move mechanics
  - Note: Solar Beam/Blade skip charge in sun — scored as general case (no sun assumed)

- `STATUS_CATEGORIES`: maps PokeAPI move-meta-category slugs → {label, tier}
  - Tier 1: ailment (paralysis, burn, sleep, poison)
  - Tier 2: net-good-stats (Swords Dance, Dragon Dance, Nasty Plot)
  - Tier 3: heal (Recover, Roost, Synthesis)
  - Tier 4: whole-field-effect, field-effect, force-switch, unique
  - Source: PokeAPI move-meta-category endpoint

- `ACCURACY_FLOOR = 0.75`

Unit test suite: 36 tests, all passing. Run directly: `python feat_moveset_data.py`

### feat_moveset.py bug fix

Line 24 referenced `session` (old context model pre-split). Fixed to call
`print_session_header(pkm_ctx, game_ctx)` matching the actual function signature.
The `run()` function already had the correct parameters — only the body was stale.

### README updated

- File map: feat_moveset_data.py added, feat_moveset.py status updated
- New section: "Two-turn move penalties (moveset scoring)" with full reference table

### What to verify with user

TWO_TURN_MOVES list was built from Bulbapedia knowledge. User should confirm:
- No missing moves (particularly newer Gen 8/9 additions)
- No incorrect penalty categories
- Focus Punch deliberately excluded (same-turn mechanic, not a 2-turn charge)
- Bide / Future Sight / Doom Desire deliberately excluded (different mechanics)

### Correction to TWO_TURN_MOVES (user review)

User confirmed 4 missing moves after reviewing Bulbapedia:

Charge + exposed additions:
- Geomancy (Fairy, status move — no power, penalty moot, included for completeness)
- Meteor Beam (Rock, raises Sp.Atk on charge turn, 120 power)

Recharge + exposed additions:
- Prismatic Laser (Psychic, 160 power, recharge after use)
- Shadow Half (Ghost, halves all HP, no base power, penalty moot)

All other entries confirmed correct. Total: 27 moves in table.
Unit tests updated to 40 (all passing).

probe_status_categories.py created — live PokeAPI probe to verify
STATUS_CATEGORIES slugs. Run on user machine to confirm all slugs match.
---

## 23. Step 2 complete — score_move()

### Added to feat_moveset_data.py

`score_move(move_name, move_entry, pkm_ctx, game_ctx) → float`

Formula:
  score = base_power × stat_weight × stab_bonus × two_turn_penalty × accuracy_factor

- Returns 0.0 for None entry (move unavailable in game) or status moves (power=None).
- stat_weight: Gen 4+ only. relevant_stat / weaker_stat, capped [1.0, 2.0].
  Physical → Atk/SpA. Special → SpA/Atk. Floor at 1.0 (never penalises).
  Gen 1-3 gets stat_weight=1.0 — type determines category, already in move data.
- stab_bonus: 1.5 if move type in pkm_ctx["types"], else 1.0.
- two_turn_penalty: from TWO_TURN_MOVES lookup, else 1.0.
- accuracy_factor: min(accuracy, 100) / 100, floored at ACCURACY_FLOOR (0.75).
  accuracy=None (always-hits moves like Swift) treated as 100%.

### Minor fix: stat_weight cap test

Original test assumed Garchomp (Atk 130 / SpA 80 = 1.625) hits the 2.0 cap.
It doesn't. Fixed test to use a hypothetical 210/90 ratio to verify the cap logic.
The scorer itself was correct — only the test description was wrong.

### Unit tests: 45 total, all passing
---

## 24. Accuracy scoring — changed from floored to linear (Option B)

### Decision

Original design used `ACCURACY_FLOOR = 0.75`: any move below 75% accuracy was scored
as if it were 75%. The flaw: a 50% move (Inferno) scored the same as a 70% move
(Focus Blast), which is misleading.

Two options were considered:
- Option A: hard cutoff — exclude moves below a threshold entirely
- Option B: linear penalty — score accuracy as-is: accuracy / 100

Went with Option B. It's more honest across the full range and handles edge cases
naturally without a magic threshold. Inferno (100pw/50%) now correctly scores below
Flamethrower (90pw/100%) on Charizard.

### Changes

- `ACCURACY_FLOOR` constant removed and replaced with `LOW_ACCURACY_THRESHOLD = 75`
  — display-only flag, no effect on scoring
- `score_move()`: `acc_factor = min(accuracy, 100) / 100.0` (no floor, no cutoff)
- `test_score_move.py`: breakdown label updated — shows `Acc ×0.50 ⚠` for low-acc moves
- Two new unit tests added:
  - Focus Blast (70%): acc_factor = 0.70 (not 0.75)
  - Inferno (50%): acc_factor = 0.50, scores less than Flamethrower despite higher power
- Total unit tests: 46, all passing
---

## 25. Step 3 — Candidate pool builder (build_candidate_pool)

### What was built

Two functions added to `feat_moveset_data.py`:

**`_score_learnset(form_data, moves_lookup, pkm_ctx, game_ctx, weakness_types, era_key)`**
Pure logic layer — no I/O, no cache calls. Takes already-loaded dicts and
returns `(damage_pool, status_pool)`. Fully unit-testable with mocks.

**`build_candidate_pool(pkm_ctx, game_ctx)`**
Public entry point. Loads learnset via `cache.get_learnset_or_fetch()`, builds
`moves_lookup` from the moves cache, computes defensive weaknesses via
`calc.compute_defense()`, then delegates to `_score_learnset()`.

Returns:
```python
{
  "damage" : list of move dicts, sorted by score desc
  "status" : list of move dicts (status moves, alphabetical)
  "skipped": int  # moves in learnset not yet in moves cache
}
```

Each move dict keys:
  name, type, category, power, accuracy, pp,
  score, is_stab, counters_weaknesses, is_two_turn, low_accuracy

### Design decisions

- `_score_learnset` is separate from `build_candidate_pool` so unit tests
  can inject mock data without touching the cache or network.
- `counters_weaknesses` is a list of the pokemon's own weak types that this
  move hits super-effectively (×2+). Used by Step 5 counter-weakness mode.
- Moves not in the moves cache are silently skipped (counted in `skipped`).
- Status moves are collected into their own pool (not scored, passed to Step 6
  status ranker).

### Tests added: 17 new tests (total: 63, all passing)
---

## 26. Steps 4+5 — Combo selector (select_combo / _combo_score)

### What was built

**`_combo_score(combo, weakness_types, era_key, mode) → float`**
Scores a 4-move combination. Four terms:
- `sum(move_scores)` — base
- `coverage_bonus`: +25 × unique defending types hit SE by any move in the combo (all modes)
- `counter_bonus`: +25 × own weaknesses countered by the combo (counter mode only)
- `stab_bonus`: +30 × STAB moves in the combo (stab mode only)
- `redundancy_penalty`: -20 × duplicate move types beyond first; **Normal-type exempt**

**`select_combo(damage_pool, mode, weakness_types, era_key, locked=None) → list`**
Brute-forces C(min(pool,20), 4) = up to 4845 combos.
Locked moves are forced in; selector fills remaining slots.
Returns up to 4 move dicts (fewer if pool is too small).
Returns locked moves only if free pool is empty.

### Design decisions

- Steps 4 and 5 merged: all three modes share one function, different term activations.
- Normal-type exemption: Normal hits nothing SE, so duplicate Normal moves add no
  coverage overlap. Without exemption, Normal-type Pokemon would be unfairly penalised
  for running multiple Normal STAB options (Snorlax, Blissey, Tauros etc.).
- Coverage bonus of +25 per SE type confirmed (same as counter_bonus for symmetry).
- Pool cap: top 20 moves → C(20,4) = 4845 combos, runs in <10ms in Python.
- Unit tests: mechanism-based (test _combo_score directly) rather than outcome-based
  (outcome depends on exact pool scores and is fragile to minor weight changes).

### Tests added: 14 new tests (total: 77, all passing)
- STAB bonus fires only in stab mode (exact delta = n_stab × 30)
- Counter bonus fires only in counter mode (exact delta = n_countered × 25)
- Redundancy penalty fires for duplicate non-Normal types (exact expected value)
- Normal exemption: two-Normal combo matches manual calculation (no penalty)
- Locked slot always present, not duplicated
- Edge cases: small pool, empty pool
---

## 27. Roadmap update + auto-fetch + scoring observations

### Status update
Steps 1–5 complete. Steps 6–8 remaining (status ranker, display layer, locked slots UI).

### Auto-fetch added to build_candidate_pool
Previously the user had to manually load the full move list in pokemain.py before
requesting a moveset recommendation. Now build_candidate_pool() auto-fetches:
1. Learnset (was already automatic via get_learnset_or_fetch)
2. Missing move details (new: replicates _prefetch_missing from feat_movepool.py)
3. Pokemon species data (handled in test_score_move.py _get_pkm_ctx, auto-fetches
   from PokeAPI if not in cache, warns if multiple distinct-type forms exist)

### Scoring observation — modes too similar
After testing with Charizard and other Pokemon, the three recommendation modes
(Coverage / Counter / STAB) produce very similar results for Pokemon with a dominant
move type (e.g. Charizard's Fire moves). Root cause: the per-move base scores are
large relative to the mode-specific bonuses, so the selector always anchors on the
top individual moves regardless of mode.

Calibration deferred to post-Step-8 refinement (R2 in README).
The 5 reference Pokemon for calibration testing: Gardevoir, Garchomp, Ampharos,
Gyarados, Magmar.
→ R2 resolved in §37 (marginal coverage model + raised redundancy penalty).

### Future refinements added to roadmap (README)
- R1: Move priority penalty — ✅ Done (§34)
- R2: Combo scoring weight calibration — ✅ Done (§37, marginal coverage + redundancy penalty)
- R3: Recoil penalty + secondary effect bonus — ✅ Done (§38)

---

## 28. Step 6 — Status move ranker (rank_status_moves)

### What was built

**`STATUS_MOVE_TIERS`** — curated static dict (~130 entries).
Maps status move display names → (tier, quality).
Same design pattern as `TWO_TURN_MOVES`.
Unknown moves fall back to tier 4, quality 0.

**`rank_status_moves(status_pool, top_n=3) → list`**
Sorts by (tier ASC, quality DESC, name ASC).
Enriches each returned dict with `tier`, `quality`, `tier_label`.

### Design decision: curated table vs live API fetch
Chose curated table (Option A) over fetching meta_category from PokeAPI.
Reasons: faster (no network), works offline, allows nuanced quality scores
(e.g. Spore quality=10 vs Sleep Powder quality=7 despite same tier).
Unknown moves gracefully fall back rather than crashing.

### Tests added: 19 new tests (total: 96, all passing)
Tier ordering (1>2>3>4), quality sort within tier, alphabetical tiebreak,
unknown move fallback, top_n enforcement, empty pool, enriched field presence,
Charizard integration (Dragon Dance > Swords Dance).

---

## 29. Step 7 — Display layer (feat_moveset.py)

### What was built

`feat_moveset.py` fully implemented. Replaces the stub.

**`run(pkm_ctx, game_ctx, constraints)`** — called from pokemain.py.
Builds the pool, resolves locked constraints, enters the mode sub-menu.

**Sub-menu choices:**
  1. Coverage, 2. Counter, 3. STAB, A. All three, Q. Back to main menu

**`_resolve_locked(constraints, damage_pool)`** — maps constraint strings
to pool rows. Exact match first, then unambiguous prefix match.
Unmatched names reported to the user but do not crash.

**`_print_combo` / `_print_status`** — display helpers (same logic as
test_score_move.py, kept local to feat_moveset.py).

`pokemain.py`: flipped `available=False` → `True` for "Moveset recommendation".
Feature is now live from the main menu as option 3.

### Design decisions
- Pool is built once per invocation of run(), then reused across all mode
  selections within the session. No re-fetching when switching modes.
- `main()` standalone entry point provided for running feat_moveset.py directly.
- Status recommendations always shown below the damage combo (top 3).

---

## 30. Steps 8a+8b — Learnset name set + move matcher

**`get_learnable_names(pkm_ctx, game_ctx) → set[str]`** in `feat_moveset.py`.
Calls `cache.get_learnset_or_fetch()`, flattens all four sections
(level-up, machine, tutor, egg) into a name set. Returns empty set on error.

**`match_move(user_input, valid_names) → (name|None, status)`** in `feat_moveset.py`.
Priority: exact (case-insensitive) → unambiguous prefix → ambiguous → not_found.
Whitespace-only input treated as empty (not_found).

**Tests**: 13 pure-logic tests in `test_score_move.py --test-8ab`.
`get_learnable_names` tests are cache-conditional (skip with message if Charizard
not cached — the user runs them after loading Charizard in pokemain.py).

---

## 31. Step 8c — Constraint collector (collect_constraints)

**`collect_constraints(pkm_ctx, game_ctx, existing=[]) → list[str]`**
Interactive loop, up to MAX_CONSTRAINTS=4 locked moves.

Flow per iteration:
1. Show current locked list + remaining slots
2. Prompt for move name (or empty/skip/done/q to exit, 'clear' to reset)
3. Validate via match_move() against get_learnable_names()
4. On prefix match: ask confirmation
5. On ambiguous: show up to 6 candidates, ask to be more specific
6. On not-found: explain and retry
7. Reject duplicates silently

Tests in test_score_move.py --test-8c (13 tests, all cache-conditional):
empty/done exit, exact add, prefix+confirm, prefix+reject, not-found retry,
ambiguous retry, duplicate rejection, 4-move cap, auto-exit at max,
clear, existing carryover, q exit.

---

## 32. Step 8d — Wire locked slots into pokemain.py

**Changes to pokemain.py:**
- `from feat_moveset import collect_constraints` added to imports
- `L. Lock moves for recommendation` — visible in menu when both contexts loaded
- `C. Clear locked moves` — visible only when constraints is non-empty
- `l` handler: calls `collect_constraints(pkm_ctx, game_ctx, existing=constraints)`,
  stores result back into `constraints`
- `c` handler: resets `constraints = []`
- Constraints already cleared on Pokemon change (existing behaviour, unchanged)
- Locked moves already displayed in header (existing behaviour, unchanged)

Step 8 fully complete. Moveset recommendation feature is end-to-end live.

---

## 33. Step 8d revised — locked moves moved inside moveset feature

Changed flow after user feedback: L/C should not be main menu items.

**New flow:**
1. Main menu: load Pokemon + game
2. Select option 3 (Moveset recommendation)
3. Pool builds, then collect_constraints runs immediately
4. User enters locked moves (or presses Enter to skip)
5. Mode menu appears

**pokemain.py cleanup:**
- Removed `constraints` list from main loop entirely
- Removed `constraints` param from `_print_menu`, `_print_context_lines`, `module.run()`
- Removed locked move display from session header (managed inside feat_moveset now)

**feat_moveset.run() updated:**
- Calls `collect_constraints(pkm_ctx, game_ctx, existing=[])` after pool build
- Passes result into `_resolve_locked` then `_mode_menu`

---

## 34. R1 — Move priority penalty/bonus (API-driven)

### Approach
`priority` is a top-level integer field on every PokeAPI move endpoint response.
It is constant across generations (not in `past_values`), so stored once in
`current` and propagates to all versioned entries via `**current`.

Preferred over a static table: data-driven, automatically correct for any move,
no manual curation needed.

### Changes

**`pkm_pokeapi.py` — `fetch_move()`**
Added `"priority": data.get("priority", 0)` to `current` dict.

**`feat_moveset_data.py` — `score_move()`**
New `priority_factor` multiplier:
  priority < 0 → max(1.0 + priority × 0.15, 0.1)   e.g. −3 → ×0.55
  priority > 0 → 1.0 + priority × 0.08              e.g. +2 → ×1.16
  priority = 0 → 1.0 (no change)
Floored at 0.1 to prevent zero/negative scores on extreme values.
Missing `priority` key (moves cached before this change) defaults to 0.

**`feat_moveset_data.py` — pool row**
Added `"priority"` field to every damage pool row.

**`feat_moveset.py` — `_breakdown()`**
Displays `Prio -3  x0.55` / `Prio +2  x1.16` in Notes column when priority ≠ 0.

### Cache compatibility
Existing cached moves without `priority` key default to 0 — no forced re-fetch.
New fetches (lazy or via T menu) will include `priority` automatically.

### Tests
7 new unit tests in feat_moveset_data.py. Total: 103 passing.

---

## 35. Compatibility enforcement — Pokemon / game cross-validation

Previously, loading a Pokemon that didn't exist in the selected game
produced a warning but allowed it anyway. Now both directions are hard blocks.

**`select_pokemon(game_ctx)` — Pokemon too new for the game**
  - `form_gen > game_gen` → error message + "Try another Pokemon? (y/n)"
  - "y" → loops back to name prompt (stays within select_pokemon)
  - "n" → returns None (caller returns to main menu)
  - Type-doesn't-exist-in-era errors unchanged (still hard block / single-type fallback)

**`select_game(pkm_ctx)` — game too old for the loaded Pokemon**
  - New optional `pkm_ctx` parameter (default None — no change when absent)
  - `form_gen > game_gen` → error message + "Try another game? (y/n)"
  - "y" → loops back to game list
  - "n" → returns None (caller keeps existing game_ctx)

**`pokemain.py`**
  - `choice == "g"` → `select_game(pkm_ctx=pkm_ctx)` (passes loaded Pokemon)
  - `_ensure_game(game_ctx, pkm_ctx=None)` → forwards pkm_ctx to select_game
  - Feature handler `_ensure_game(game_ctx, pkm_ctx=pkm_ctx)` updated

**Tests**: T9–T14 added to pkm_session.py self-test. Total: 14 tests passing.

---

## 35. Era compatibility — hard blocks instead of warnings

**Behaviour change:**

Previously: loading a Pokémon that didn't exist in the selected game showed a
warning but allowed the user to continue. Switching games with a loaded Pokémon
that didn't exist in the new game had no validation at all.

Now: both directions are hard-blocked with a clear error and a retry prompt.

**`pkm_session.py` — `select_pokemon()`**
- Added `while True:` loop around the entire selection flow.
- `form_gen > game_gen`: error message + "Try a different Pokemon? (y/n)".
  - y → loops back to name prompt
  - n → returns None (back to main menu)
- Primary type not in era: same hard block + retry loop.
- Secondary type not in era: unchanged soft drop (still just a note).

**`pokemain.py` — `g` handler**
- Already passes `pkm_ctx` to `select_game()`. No change needed.

**`pkm_session.py` — `select_game(pkm_ctx=...)`**
- Already loops when pkm_ctx provided and form_gen > game_gen. No change needed.

---

## 36. COMBO_EXCLUDED — auto-combo exclusion list

### Decision
Some moves should never appear in an auto-generated moveset recommendation
even if they score well, because their practical usefulness is conditional
on circumstances the recommender cannot model. They remain available as
*locked* moves (user-forced slots) so the tool doesn't hide them entirely.

### Three groups (all moves vetted by user)

**Group 1 — User faints on use**
Self-Destruct, Explosion, Misty Explosion, Final Gambit, Memento,
Healing Wish, Lunar Dance.
Sacrificing the active Pokemon is never correct as a default suggestion.

**Group 2 — Requires specific other moves to be viable**
Focus Punch: fails if hit before executing — only usable behind Substitute.
Perish Song: KOs both sides in 3 turns — only viable with a trapping move.
Destiny Bond: KOs both sides only if user faints next turn — purely reactive.

**Group 3 — Near-zero practical value as a regular moveslot**
Curse (Ghost): halves HP to badly poison opponent — niche stall only.
Grudge: drains opponent PP on KO.
Spite: reduces target's last move PP by 4.

### Implementation
`COMBO_EXCLUDED` frozenset in `feat_moveset_data.py`.
`select_combo()` filters it from `free_pool` before brute-force search.
Locked moves bypass this filter (user override always wins).
Status-pool moves in this list (Memento, Destiny Bond, etc.) still appear
in the status recommendations — only the damage-combo selector is gated.

### Tests
5 new unit tests. Total: 108 passing.

---

## 37. Coverage bonus: marginal contribution model + redundancy penalty raise

### Problem (observed on Machamp)
Coverage mode was selecting 2 Fighting moves (Cross Chop + Brick Break) over a
4-type set (Cross Chop + Fire Blast + Earthquake + Rock Slide). The old flat
coverage bonus counted all unique SE types across the combo regardless of overlap,
so two Fighting moves contributed the same 5 SE types as one — the second move got
full coverage credit for types the first move already covered.

### Fix 1 — Marginal coverage bonus (feat_moveset_data.py)
`_combo_score()` now evaluates moves in score-descending order and counts only
*new* SE types each move adds. A duplicate-type move contributing 0 new types
earns 0 coverage bonus. This makes type redundancy naturally self-penalising.

### Fix 2 — Raise _REDUNDANCY_PENALTY from 20 to 30
The marginal bonus alone reduced the gap but left a tie (the base score advantage
of Brick Break exactly cancelled the coverage gain of Rock Slide + old penalty).
Raising to 30 breaks the tie: 4-type set wins coverage mode by 10 points.

### Behaviour verified
Coverage mode: 4-type set wins (correct).
STAB mode: 2-Fighting set wins (correct — that's the point of STAB mode).
select_combo() picks the right winner for each mode from the same pool.
All 108 unit tests pass.

---

## 38. R3 — Recoil penalty + secondary effect bonus

### New fields added to move cache (pkm_pokeapi.py)
Three new fields extracted from PokeAPI and stored in every versioned move entry.
All are constant across generations (not in `past_values`) → go in `current`,
propagate automatically to all versioned entries.

- `drain` (int): from `meta.drain`. Negative = recoil (e.g. -33 for Flare Blitz),
  positive = HP drain recovery (e.g. +50 for Giga Drain, Drain Punch).
  Defaults to 0 on old cache entries (neutral).
- `effect_chance` (int): from top-level `effect_chance`. % chance of secondary
  status (burn, paralysis, flinch, etc.). 0 if no secondary effect.
- `ailment` (str): from `meta.ailment.name` (e.g. "burn", "paralysis", "flinch").
  Used in display layer only. "none" if no ailment.

### score_move() — two new factors (feat_moveset_data.py)

**recoil_factor** (from `drain`):
  drain < 0 (recoil):  max(1.0 + drain/100 × 0.5, 0.4) — half the actual recoil
    Flare Blitz -33% → ×0.835,  Double-Edge -25% → ×0.875,  Head Smash -50% → ×0.75
  drain > 0 (healing): 1.0 + drain/100 × 0.3 — small sustain bonus
    Giga Drain / Drain Punch +50% → ×1.15
  drain = 0: 1.0 (no change)

**effect_factor** (from `effect_chance`):
  1.0 + effect_chance/100 × 0.2 — uniform bonus, does not distinguish effect type
    Scald 30% burn → ×1.06,  Fire Blast 10% burn → ×1.02,  Surf 0% → ×1.0

### Display layer (feat_moveset.py _breakdown)
- Shows "Recoil 33%  x0.84" / "Drain 50%  x1.15" when drain ≠ 0
- Shows "30% burn" / "10% paralysis" when effect_chance > 0 and ailment is known

### Cache backward compatibility
Old cached moves without these fields default to 0 / "none" → neutral factors.
No forced re-fetch needed. New data populates on next T menu fetch.

### Tests
11 new unit tests (6 recoil, 5 effect). Total: 119 passing.

### Cache versioning (pkm_cache.py)
Added `MOVES_CACHE_VERSION = 2` constant. `get_moves()` compares `_version` key in moves.json against the constant; mismatch → deletes stale file → returns None → all moves lazily re-fetched with new schema. `save_moves()` and `upsert_move()` both write `_version` on every write. Old cache with no `_version` key is treated as version 0 (mismatch) and invalidated automatically. Bump `MOVES_CACHE_VERSION` for any future move schema change.

---

## 39. Bugfix — save_learnset upsert

### Bug
`save_learnset()` was doing a blind `_write(path, data)` — no merge.
If called with a dict containing only a subset of forms, any other forms
previously stored in the file were silently discarded.

### Impact
Low in practice today — `fetch_learnset()` fetches all forms together in one
call and saves them all at once, so the overwrite never triggers. However the
behaviour was wrong by design and would become a real bug if any future code
path saved a partial form set.

### Fix
Same pattern as `save_pokemon()`: read existing file first, merge `forms`
dicts via `_upsert_forms_dict()` (already existed for this purpose), then
write. New data wins on conflict; existing forms not in new data are preserved.
No change to the JSON file format or schema.

### Tests
Pre-existing self-test "learnset upsert" was already asserting the correct
behaviour and was failing. Now passes. All other tests unaffected.

---

## 40. matchup_calculator.py — standalone self-test added

### Gap identified
`matchup_calculator.py` was the most fundamental shared module (used by almost
all other files) but had no automated tests — running it standalone just launched
the interactive UI.

### Tests added (_run_tests, 79 tests)
- Type pool sizes and composition per era (12 tests)
- `get_multiplier` spot-checks: era3 known values, era2 vs era3 differences,
  era1 quirks (Ghost→Psychic=0×, Bug→Poison=2×, Ice→Fire=1×), unknown type fallback
- `compute_defense` single-type and dual-type: Charizard, Gengar, Magnezone
- Era boundary: Steel def Ghost/Dark resistance in era2 vs era3, Fairy absence
- GAMES/GENERATIONS integrity: valid era_keys, no orphaned gen numbers,
  all chart rows have correct column count

### __main__ behaviour change
`python matchup_calculator.py`              → launches interactive UI (default)
`python matchup_calculator.py --autotest`   → runs self-tests
`python matchup_calculator.py --dry-run`    → alias for --autotest

---

## 41. Main menu restructure — option 3 "Learnable move list (scored)"

### Change
Split the old single moveset menu entry into two distinct options, and renamed
the movepool entry for clarity:

  1. Type vulnerabilities & resistances  (unchanged)
  2. Learnable move list (conditions)    (was "Full learnable move list")
  3. Learnable move list (scored)        (NEW)
  4. Moveset recommendation              (unchanged)

### New: run_scored_pool() in feat_moveset.py
Shows the full scored candidate pool without combo selection:
  - ATTACK MOVES: all damage moves ranked by individual score (descending),
    with rank number, score value, and full breakdown (STAB, stat weight,
    recoil, effect chance, 2-turn penalty, accuracy, priority, type coverage)
  - STATUS MOVES: all status moves ranked by tier + quality (full list, not
    just top 3 as in the recommendation view)

### PKM_FEATURES schema change (pokemain.py)
Tuple extended with an `entry_fn` string field:
  (label, module, entry_fn, needs_pkm, needs_game, available)
Dispatch changed from `module.run()` to `getattr(module, entry_fn)()`,
allowing multiple entry points on the same module.

---

## 42. Per-variety learnset cache (fix Galarian/Hisuian/regional form learnsets)

### Problem
`fetch_learnset()` was always fetching from `pokemon/{species_slug}` (e.g. `pokemon/moltres`).
On PokeAPI, each form variety has its own endpoint with its own move list:
- `pokemon/moltres`       → base Moltres learnset
- `pokemon/moltres-galar` → Galarian Moltres learnset (completely different moves)
The wrong learnset was being fetched and cached for any non-default form.

### Solution: Option A — one cache file per variety_slug + game
File naming changed from `{species_slug}_{game_slug}.json`
to `{variety_slug}_{game_slug}.json`.

Examples:
  cache/learnsets/moltres_scarlet-violet.json        ← base Moltres
  cache/learnsets/moltres-galar_scarlet-violet.json  ← Galarian Moltres

### Changes

**pkm_pokeapi.py**
- `fetch_pokemon()`: each form dict now includes `"variety_slug"` field
  (the PokeAPI variety slug, e.g. `"moltres-galar"`)
- `fetch_learnset(variety_slug, form_name, game, machines)`: signature changed.
  Uses `variety_slug` to fetch the correct PokeAPI endpoint. `form_name` is
  used as the key in the returned `forms` dict.

**pkm_cache.py**
- Added `_learnset_path(variety_slug, game)` helper (also fixed latent bug:
  `invalidate_learnset` was calling this function before it existed)
- `get_learnset(variety_slug, game)`, `save_learnset(variety_slug, game, data)`,
  `invalidate_learnset(variety_slug, game)`: all keyed by variety_slug
- `get_learnset_or_fetch(variety_slug, form_name, game)`: new signature,
  passes both to fetch_learnset
- `invalidate_all(name)`: reads variety_slugs from pokemon cache before
  deleting it, so alternate-form learnset files are also removed on refresh

**pkm_session.py**
- Form tuples are now `(name, types, variety_slug)` 3-tuples throughout
- `pkm_ctx` gains `"variety_slug"` key
- Fallback: old cached pokemon files without `variety_slug` fall back to
  the species slug — base forms are unaffected; alternate forms should be
  refreshed with R

**feat_movepool.py**, **feat_moveset.py**, **feat_moveset_data.py**
- All `get_learnset_or_fetch` calls updated to use
  `pkm_ctx.get("variety_slug") or pkm_ctx["pokemon"]`

### Backward compatibility
- Old learnset cache files (`moltres_scarlet-violet.json`) are simply unused
  after this change (the new key is `moltres-galar_...`). They can be deleted
  manually or left — they won't interfere.
- Old cached pokemon files without `variety_slug` work correctly for base forms.
  Users with cached non-default forms should use R (refresh) once to repopulate.

### Test notes
- All 14 pkm_session tests pass (T1 assertion updated to 3-tuple)
- All 119 feat_moveset_data tests pass
- All pkm_cache tests pass

---

## 43. Auto-upgrade old pokemon cache on variety_slug miss

### Problem
After §42, any pokemon cached *before* the change had no `variety_slug` in its
form dicts. The fallback in `_cache_to_forms` correctly used the species slug,
which works for base forms but silently fetches the wrong PokeAPI endpoint for
alternate forms (e.g. `pokemon/sandslash` instead of `pokemon/sandslash-alola`).

Telling the user to "press R" was unreliable — they'd have to know to do it,
and the learnset would silently return base-form moves.

### Fix: transparent auto-upgrade in `_fetch_or_cache`
Added `_needs_variety_slug_upgrade(cached)` which returns True if any form
in the cached data is missing `variety_slug`. When detected, `_fetch_or_cache`
silently re-fetches from PokeAPI once, saves the updated data, and continues.
The user sees "(cache outdated — re-fetching to get form data...)".

This is a one-time upgrade per Pokemon — subsequent loads hit the cache normally.

### Tests
- T2b added: old-format cache (no variety_slug) → auto-upgrade → re-fetch once,
  resulting tuples contain variety_slug
- All 15 pkm_session tests pass

---

## §44. Menu box fix + moveset coverage display

### E — Menu box overflow fix (pokemain.py)
`W` increased from 48 → 52. The two offending lines:
- `T. Pre-load move table  (type/power/acc/PP for all moves)` was 57 chars
- `W. Pre-load TM/HM table (required for TM numbers in move lists)` was 63 chars

Replaced with shorter but equivalent labels (51 chars each, fit cleanly in W=52):
- `T. Pre-load move table   (stats for all ~920 moves)`
- `W. Pre-load TM/HM table  (TM numbers in move lists)`

`feat_moveset.py` W also updated to 52 (keeps the sub-menu box aligned).

### Coverage summary in moveset recommendation (feat_moveset.py)
Added two new functions:

**`_compute_coverage(combo, era_key) → (se_types, gap_types)`**
- Iterates over all valid types in the era (17 for era2, 18 for era3)
- For each defending type, finds the best multiplier across all moves in the combo
- `se_types`: defending types hit ≥2× by at least one move
- `gap_types`: defending types where ALL moves hit ≤0.5× (resisted or immune)

**`_print_coverage(combo, era_key, weak_types=None)`**
- `Hits SE [N/18]:  Type1  Type2  ...`
- `Gaps    [N/18]:  ...`  (only printed if any exist)
- `Own weak [N/M]:  ✓ Ice  ✓ Dragon  ✗ Fairy`  (only printed if weak_types given)

Called after `_print_combo` in both `_show_mode` and `_show_all`.
`weak_types` is computed from `compute_defense` — already available at call site.

### Design notes
- Single-type targets only (18 types). ×4 is not possible against single-type
  defenders in era3 — no separate ×4 bucket needed.
- Era-aware: era2 shows N/17, era3 shows N/18.
- Gaps line hidden when there are no gaps (keeps output clean for broad movers).

## §45. Self-test coverage audit

Audited every file for untested pure functions. Added `_run_tests()` + `--autotest` to:

- **`feat_moveset.py`** (23 tests): `_breakdown` (7 cases), `_compute_coverage` (4), `_resolve_locked` (5), `match_move` (6). `get_learnable_names` added as `--withcache` test.
- **`feat_move_lookup.py`** (12 tests): `_fmt` (4 cases), `_attacking_coverage` across all 3 eras including era1 quirks (Bug→Poison, Ghost→Psychic).
- **`feat_movepool.py`** (9 tests): `_fmt_move_row` (all column cases + None fallback + status moves), `_section_header` smoke test.
- **`pkm_cache.py`** (+3 tests): `save_machines`/`get_machines`, `invalidate_moves`, `invalidate_learnset`. Added passed counter → now emits `N passed, 0 failed` summary line.

`feat_type_matchup.py` has no testable pure functions (all IO). Not changed.

## §46. `run_tests.py` — consolidated test runner

New file `run_tests.py` runs all suites sequentially and prints a summary table.

**Usage:**
```
python run_tests.py              # offline suites only
python run_tests.py --withcache  # also run cache-dependent variants
```

**Design:**
- Uses `subprocess` to run each file as a child process — fully isolated
- Captures stdout+stderr, prints verbatim output per suite
- `_extract_counts()` parses pass/fail from each file's output using 3 strategies:
  1. `N tests: N passed, N failed` (matchup_calculator, feat_moveset_data)
  2. `N passed, N failed out of N` (pkm_cache, feat_moveset, feat_move_lookup, feat_movepool)
  3. Token fallback: counts `[PASS]`, `[OK]`, trailing `OK` (pkm_pokeapi)
- Cache-dependent suites are registered with `needs_cache=True` and skipped unless `--withcache` is passed
- Non-zero returncode with zero parsed failures → counts as 1 failure (catches crashes)
- Summary table shows per-suite: passed, failed, elapsed time. Totals at bottom.
- Exits with code 1 if any suite failed.

**Total offline test count: 294 tests across 8 suites.**

## §47 — Counter mode: coverage-first selection

**Problem:** `select_combo` in counter mode used a single blended `_combo_score`, so a high-scoring combo covering 2/3 weaknesses would often beat a lower-scoring combo covering all 3. The `_COUNTER_BONUS_PER_WEAK` incentive was too weak to guarantee full coverage.

**Fix:** Two-key sort `(gap, -score)` in `select_combo` for counter mode only. `gap = _uncovered_weaknesses(combo, weakness_types)` — the number of the Pokemon's weakness types not countered by any move in the combo. Primary key = fewest uncovered weaknesses; secondary key = highest `_combo_score` (tiebreaker). Coverage and STAB modes unchanged.

**New helper:** `_uncovered_weaknesses(combo, weakness_types) -> int` — unions all `counters_weaknesses` lists in the combo, returns `len(weaknesses) - len(covered)`.

**`_combo_score` unchanged:** `counter_bonus` remains in the formula as a secondary contributor; it now acts as an intra-tier tiebreaker weight (combos with same gap but different quality are differentiated by score, which includes the counter bonus).

**Tests added (8 new in `feat_moveset_data.py`):**
- `_uncovered_weaknesses` correctness: full cover, partial cover, no cover, empty weakness list
- Test setup verification: gap=1 combo scores higher than gap=0 combo (proving old code had a bug)
- Counter mode selects gap=0 combo over higher-scoring gap=1 combo
- Counter mode tiebreaker: equal-gap combos → highest score wins
- Coverage mode unchanged: still selects by score regardless of gap

**Total offline tests: 316** (feat_moveset_data: 141).

## 49. §48 + §49 — Pool strategy overhaul (mode-specific pools)

See §48 block above. §49 = this cleanup entry (R1/R2/R3 marked done in notes).

## 50. §50 — Conditional move handling + unscoreable move exclusions

**Problem:** Dream Eater (power 100, drain +50%, 100% acc) scored extremely high despite being useless without sleep setup. PokeAPI has no structured field for "requires condition to deal damage" — only free-text effect entries.

**Solution:** three curated static tables (same pattern as TWO_TURN_MOVES):

- **`CONDITIONAL_PENALTY`** — moves that deal zero damage when condition is not met. Applied as a final multiplier in `score_move()`. Entries: Dream Eater (×0.3), Belch (×0.3).
- **`POWER_OVERRIDE`** — moves whose API power is the theoretical maximum but realistic opening-turn power is lower. Wring Out → 120, Eruption → 150, Water Spout → 150. Applied before all other score_move factors.
- **`COMBO_EXCLUDED` additions** — moves that cannot be scored at all: Fling and Natural Gift (power depends on held item/berry), Last Resort (requires all other moves used first). COMBO_EXCLUDED now has 16 entries.

Moves that can get a conditional power bonus but still work without it (Hex, Facade, Venoshock, Wake-Up Slap, Brine, Smelling Salts, Acrobatics, Stored Power) are left as-is — scored at their base power, ignoring the conditional bonus.

Total offline tests: **327** (feat_moveset_data: 152).

**§50 correction:** Eruption and Water Spout removed from `POWER_OVERRIDE` — the API already stores power=150 for both. Only Wring Out (API power=None) needs the override. `POWER_OVERRIDE` application moved before the status-move guard in `score_move()` so Wring Out's None power is replaced before the early return.

## 51. §51 — Type browser (feat_type_browser.py)

New feature: list all Pokémon of a given type or type combination.

**Data source:** PokeAPI `/api/v2/type/{name}`. One call per type, cached forever in `cache/types/<typename>.json` (18 files max). Types never change so no version or invalidation needed.

**New functions:**
- `pkm_pokeapi.fetch_type_roster(type_name)` → `[{slug, slot, id}, ...]`
- `pkm_cache.get_type_roster(type_name)`, `save_type_roster()`, `get_type_roster_or_fetch()`

**Generation derivation:** extracted from the variety ID in the PokeAPI URL. IDs 1–1025 map to Gen 1–9 via static range table. Alternate forms (Mega, Gigantamax, regional — all ID > 10000) display `?` for gen.

**Name display:** slug → title-case (`charizard-mega-x` → `Charizard-Mega-X`).

**Menu key:** `B` — always shown, no context needed.

**Single type:** shows all Pokémon with that type (either slot), with their secondary type in the second column.
**Type combo:** intersects both rosters, shows only Pokémon carrying both types.

Total offline tests: **360** (feat_type_browser: 33 new).

## 52. §52 — Type browser: proper form display names

**Problem:** slug-to-title produced incorrect names for several categories:
- Alternate forms: `magearna-original` → `Magearna-Original` instead of `Original Color Magearna`
- Special chars: `nidoran-f` → `Nidoran-F` instead of `Nidoran♀`
- Punctuation: `mr-mime` → `Mr-Mime` instead of `Mr. Mime`
- Spacing: `tapu-koko` → `Tapu-Koko` instead of `Tapu Koko`

**Approach:** use `pokemon-form/{slug}` English name for all hyphenated slugs. No-hyphen slugs (`charizard`, `pikachu`) are always correct with slug-to-title — skipped.

**New functions:**
- `pkm_pokeapi.fetch_form_display_name(slug)` → English name string or None
- `pkm_cache.resolve_type_roster_names(type_name)` — enriches hyphenated entries with `name` field, saves updated roster. No-op on second call (all resolved). Monkey-patchable for offline tests.

**Cache format change:** roster entries now optionally have `{..., "name": "Mr. Mime"}`. Old cached rosters are enriched transparently on next use.

Total offline tests: **368** (feat_type_browser: 41, +8 new).

## 53. §53 — Nature browser + recommender (feat_nature_browser.py)

**Scope:** display all 25 natures, show per-stat impact on a loaded Pokémon, recommend top-3 natures using role-aware scoring.

**Game dependency:** natures are identical in all Gen 3+ games. Feature always available; shows a warning for Gen 1/2 games.

**Data source:** PokeAPI `/nature?limit=25` + `/nature/{name}` × 25. Cached in `cache/natures.json`. Fetched once, never invalidated.

**New cache functions:** `get_natures()`, `save_natures()`, `get_natures_or_fetch()` in `pkm_cache.py`.

**New API function:** `fetch_natures()` in `pkm_pokeapi.py`.

**Role-aware scorer (`_role_score`):**
- Attacking role: Atk vs SpA (threshold 1.2×) → physical / special / mixed
- Speed tier: Spe ≥ 90 = fast (1.0), 70–89 = mid (0.6), < 70 = slow (0.2)
- Bulk weight: Def/SpD cut hurts less when the stat is already low (weight = min(stat/80, 1.0))
- Key attacking stat boost → weight 1.5; dump stat boost → weight 0.3

**Menu key:** `N` — always shown, no context required. Passes `game_ctx` (for Gen warning) and `pkm_ctx` (for stat impact + top-3).

Total offline tests: **395** (feat_nature_browser: 27 new).

## 54. §54–§56 — Moveset UX improvements

### §54 — Weakness coverage annotation: "no move in pool"

**Problem:** `✗ Electric` for Lapras (LeafGreen) implies the weakness *can't* be covered, when the real reason is that no Ground move exists in Lapras's learnset at all.

**Fix:** `_print_coverage` (feat_moveset.py) takes a new optional `damage_pool` parameter. When provided, it builds `pool_coverable` — the set of weakness types that at least one pool move can counter. Truly uncoverable weaknesses (nothing in pool can hit that type SE) are now shown as `✗ Electric (no move in pool)`. Weaknesses merely not chosen by the combo keep plain `✗`. Legacy callers passing `damage_pool=None` unchanged.

**Tests added:** 3 new tests in `feat_moveset._run_tests`.

### §55 — Short combo note (< 4 move types available)

**Problem:** Zapdos in Red/Blue/Yellow has only Electric/Flying/Normal moves → selector returns 3 moves with no 4th slot. No explanation was shown.

**Fix:** `_print_combo` (feat_moveset.py) checks `len(combo) < 4` after printing rows. If true, draws a separator line and prints: `Only N move type(s) available — M slot(s) left unfilled`. Applies to all three modes.

**Tests added:** 2 new tests in `feat_moveset._run_tests`.

### §56 — Moveset mode sub-menu removed

**Decision:** moveset recommendation was fast enough that the Coverage/Counter/STAB/All sub-menu was unnecessary friction. After constraints are entered, all three modes are now shown immediately (equivalent to old "A. All three modes"). `_mode_menu` deleted; its setup logic inlined into `run()`.

Total offline tests: **400** (feat_moveset: 28 new tests after §54+§55).

## 57. §57–§58 — Ability browser + quick view

### §57 — Ability browser (feat_ability_browser.py)

**Scope:** browse all abilities with short effects; drill into any ability for full effect + Pokémon roster; show current Pokémon's abilities when loaded.

**Game dependency:** abilities introduced in Gen 3. Feature always accessible; warning shown for Gen 1/2 games.

**Data sources:**
- `cache/abilities_index.json` — all abilities: slug → {name, gen, short_effect}. Fetched via `GET /ability?limit=400` + individual calls. One-time fetch, never invalidated.
- `cache/abilities/<slug>.json` — per-ability detail (full effect + Pokémon list). Fetched on demand when user drills in.

**New pkm_pokeapi functions:** `fetch_abilities_index()`, `fetch_ability_detail(slug)`.

**New pkm_cache functions:** `get_abilities_index()`, `save_abilities_index()`, `get_abilities_index_or_fetch()`, `get_ability_detail()`, `save_ability_detail()`, `needs_ability_upgrade()`.

**pkm_cache.py:** now a **5-layer cache**: moves, pokemon, learnsets, type rosters, natures, abilities index, per-ability details.

**pkm_pokeapi.py:** `fetch_pokemon()` now also extracts abilities per variety: `[{slug, is_hidden}, ...]`.

**pkm_session.py:** `_fetch_or_cache()` triggers re-fetch if `cache.needs_ability_upgrade(cached)`. `pkm_ctx` gains `"abilities"` key (populated by `_get_form_abilities()`). Both `select_pokemon` and `refresh_pokemon` updated.

**Auto-upgrade:** existing cached Pokémon files missing the `abilities` field are transparently re-fetched on next load (same mechanism as §43 `variety_slug` upgrade).

**Menu key:** `A` — always shown, no context needed.

### §58 — Quick view: base stats + abilities + type chart (feat_type_matchup.py)

**Renamed** option 1 from "Type vulnerabilities & resistances" to "Quick view (stats / abilities / types)".

**Extended `run()`** to show before the type chart:
1. **Base stats** — bar chart (HP/Atk/Def/SpA/SpD/Spe + total), bar scaled to 255 max.
2. **Abilities** — name + short effect from ability index; falls back to `(press A to load ability data)` if index not yet fetched.

**New helpers in feat_type_matchup.py:** `_print_base_stats()`, `_print_abilities_section()`, `_stat_bar()`.

Total offline tests: **414** (feat_ability_browser: 14 new, pkm_session: fixed mock +0 net).

**§47 addendum — pool cap supplement (superseded by §48):** See §48.

### §48 — Mode-specific pool strategies (no arbitrary cap for counter/coverage)

Root cause: `_POOL_CAP=20` (later supplement heuristic) could never guarantee optimal results for counter or coverage modes on large learnsets.

**Decision:** replace with mode-specific pool builders:

- **Counter** (`_build_counter_pool`): all moves that counter ≥1 weakness (no cap) + top `_COUNTER_FILLER_K=8` non-covering moves as filler. Pool size scales with learnset but typically 10–25 moves. Provably correct: no covering move is ever excluded.
- **Coverage** (`_build_coverage_pool`): best-scoring move per type, max 18 moves. Provably optimal: swapping a lower-scoring same-type move never improves coverage or score.
- **STAB** (`_STAB_POOL_CAP=25`): top-25 by score, pure score selection — unchanged logic.

Both counter and coverage use a **two-pass** approach: pass 1 (fast, no `_combo_score`) finds the best achievable primary metric (min gap / max SE count); pass 2 scores only combos that match that metric.

Pool supplement logic removed entirely. Old `_POOL_CAP` constant removed.

Total offline tests: **316** (feat_moveset_data: 141).

**Revised §46 (auto-warm):** `--withcache` flag removed. Runner always attempts to warm cache before cache suites. Uses `_ensure_test_cache()` which imports pkm_cache/pkm_pokeapi inline, checks each item with `check()`, fetches with `fetch()` (stdout suppressed via redirect). Learnset fetch now raises if `get_learnset_or_fetch` returns None. Cache suites skip with reason string only if fetch failed. `--offline` flag skips warm-up + cache suites entirely.

## 50. Roadmap additions (type browser, party builder, natures)

Three features added to the roadmap:

- **Type browser**: list all Pokémon of a given type or type combo using PokeAPI
  `/api/v2/type/{name}`. Index cacheable per type. Filter by generation optional.
- **Party builder**: given up to 6 Pokémon already in context, aggregate
  defensive type chart across the team, highlight weaknesses and suggest partners.
- **Nature browser**: fetch all 25 natures from PokeAPI `/api/v2/nature/{id}`,
  cache them, and recommend the best nature(s) for a given Pokémon based on its
  highest/lowest base stats.
---

## §59 — Team context + menu overhaul (Step 1)

### Decision: session-only team, no persistence
Team is a list of up to 6 `pkm_ctx` dicts (`None` = empty slot). Not saved to disk — session only.
Rationale: keep it simple, avoid save/load complexity for now. Named multi-team support is on the roadmap if needed.

### Data structure
```python
team_ctx = [pkm_ctx | None, ...]   # always exactly MAX_SLOTS (6) entries
```
Pure list — no wrapping dict. Kept simple and composable with existing `pkm_ctx` shape.

### New file: feat_team_loader.py
Public API:
- `new_team()` → fresh team (6 None slots)
- `team_size(team_ctx)` → count of filled slots
- `team_slots(team_ctx)` → list of (idx, pkm_ctx) for filled slots
- `add_to_team(team_ctx, pkm_ctx)` → (new_team, slot_idx) or raises `TeamFullError`
- `remove_from_team(team_ctx, idx)` → new_team; raises `ValueError` (empty) or `IndexError` (OOB)
- `clear_team(team_ctx)` → empty team
- `team_summary_line(team_ctx)` → "Charizard / Blastoise / ..." or "No team loaded"
- `run(game_ctx, team_ctx)` → team management sub-menu, returns updated team_ctx
- `main()` → standalone entry point

**20 offline self-tests.** All pass.

### pokemain.py changes
- `team_ctx` added as third context; initialised to `new_team()` in `main()`
- `T` key → team management (`feat_team_loader.run(game_ctx, team_ctx)`)
- Old `T` (pre-load move table) → `MOVE` (type `move` at the prompt)
- Menu header shows `Team (N/6): Slot1 / Slot2 / ...`
- `_print_context_lines` and `_print_menu` updated to accept `team_ctx` kwarg

### run_tests.py
- `feat_team_loader` suite added (offline, 20 tests)

### Roadmap — next steps
- **Step 2:** `feat_team_analysis.py` — defensive type aggregation across the team
- **Step 3a:** Team offensive coverage by type
- **Step 3b:** Team offensive coverage by learnable moves
- **Step 4:** Team moveset synergy (individual recommendations + team coverage summary)

### §59 addendum — pkm_cache.py test fix

**Bug found during full-environment validation:** `pkm_cache.py` self-test was missing several path redirects in its temp-directory setup block. `_MACHINES_FILE`, `_TYPES_DIR`, `_NATURES_FILE`, `_ABILITIES_FILE`, and `_ABILITIES_DIR` were still pointing at the real `cache/` directory rather than the temp dir. This caused a `FileNotFoundError` on `save_machines()` in a fresh environment with no `cache/` directory.

**Fix:** added the missing assignments alongside the existing `_BASE`/`_POKEMON_DIR`/`_LEARNSET_DIR`/`_MOVES_FILE`/`_INDEX_FILE` redirects.

**Impact:** pre-existing latent bug — only surfaced in a clean environment. No functional change to runtime behaviour. All 33 `pkm_cache` tests now pass. Full offline suite: **434 tests, 0 failures**.

---

## §60 — Team defensive vulnerability analysis (Step 2)

### New file: feat_team_analysis.py

**Core logic:**
- `aggregate_defense(team_ctx, era_key)` — for each attacking type in the era, buckets every team member into ×4 / ×2 / ×1 / ×0.5 / ×0. Uses `calc.compute_defense()` per member.
- `weakness_score(entry)` — weighted exposure: ×4 members count double (weight 2) + ×2 members (weight 1). Surfaces ×4 threats prominently in sort order.
- `critical_gaps(aggregated, threshold=3)` — types where `len(x4) + len(x2) >= threshold`. Sorted by weakness_score descending.

**Display:**
- Team roster header with types
- Weakness table: one row per attacking type that hits ≥1 member, bar chart + member list split by ×4 / ×2
- Critical gaps warning line (⚠) when ≥3 members share a weakness
- Resistance/immunity summary

**pokemain.py:** `V` key — shown only when team has ≥1 member AND game is selected.

**27 offline self-tests.** Covers: single-type, dual-type, immune, resist, ×4, empty team, era1/era2/era3 quirks (Bug→Poison era1, Psychic→Ghost directional), gap threshold variants, sort order.

**Test fix discovered:** era1 Ghost→Psychic quirk is directional. Ghost ATTACKING Psychic = ×0 (era1 bug). But Psychic ATTACKING Ghost = ×2 in all eras. Corrected test uses pure Poison type (Ekans) to verify Bug→Poison era1 quirk (Ghost/Poison dual-type nets to ×1 because Ghost resists Bug ×0.5).

**Full offline suite: 469 tests, 0 failures.**

### Roadmap — next
- **Step 3a:** Team offensive coverage by type (STAB-based, no cache needed)
- **Step 3b:** Team offensive coverage by learnable moves
- **Step 4:** Team moveset synergy

---

## §60 — Team defensive vulnerability analysis (Step 2)

### New file: feat_team_analysis.py

**Core logic (`build_team_defense`):** for each attacking type valid in the current era, iterates every filled team slot, calls `calc.compute_defense()`, and bins each member into one of five buckets: `weak4x`, `weak2x`, `neutral`, `resist`, `immune`.

**Scoring:**
- `weakness_score`: ×4 counts double (weight 2), ×2 counts once (weight 1). Reflects in-game severity.
- `coverage_score`: resists + immunities, equal weight.

**Display sections:**
1. Team roster (name + types)
2. Weaknesses table sorted by exposure score, bar chart, member names per bucket
3. Critical gaps line: types where 3+ members are weak (threshold constant `_CRITICAL_THRESHOLD = 3`)
4. Resistances / immunities table sorted by immune count

**Era-aware:** uses `game_ctx["era_key"]` — only types valid in the selected era appear. Era1 correctly omits Dark/Steel/Fairy.

**Menu key:** `V` — shown only when game is selected AND team has ≥1 member.

**38 offline self-tests.** All pass.

**Key test finding:** the classic 6-Pokémon fixture (Charizard/Blastoise/Venusaur/Pikachu/Gengar/Snorlax) is balanced enough to never hit the critical-gaps threshold — max 2 members weak to any single type. Critical-gaps test uses a 3× Fire team instead.

---

## §60 — Team defensive vulnerability analysis (Step 2)

### New file: feat_team_analysis.py

**Core functions:**
- `build_team_defense(team_ctx, era_key)` → `{atk_type: [{form_name, multiplier}, ...]}`  
  Calls `calc.compute_defense()` per member; keys match the era's valid type set exactly.
- `weakness_summary(team_defense)` → sorted list of weakness rows  
  Only types where ≥1 member is weak (×2+). Sorted: x4_count desc, weak_count desc, name asc.
- `resistance_summary(team_defense)` → sorted list of resist/immune rows  
  Sorted: immune_count desc, resist_count desc, name asc.
- `critical_gaps(weakness_rows, threshold=3)` → list of type names with weak_count ≥ threshold

**Display:** `display_team_analysis()` shows roster header, weakness table with bar chart (█ for ×4, ▒ for ×2), critical gap warning line, and resistance/immunity table.

**pokemain.py:** `V` key added — shown only when team has ≥1 member and game is selected.

**36 offline self-tests.** Bug found and fixed during testing: test fixtures used Pikachu/Snorlax as Rock-weak Pokémon — neither is actually weak to Rock. Fixed by using Lapras (Water/Ice) and Butterfree (Bug/Flying) as the other two Rock-weak team members.

**Test runner:** full offline suite now **478 tests, 0 failures.**

---

## §61 — Team analysis display overhaul (unified type table)

### Motivation
The two separate weakness and resistance tables made it hard to see at a glance
which types posed no threat and which the team was fully neutral to.

### New layout
Single unified table: one row per attacking type in the era, always showing all types.
Columns: Type | Wk + who (×4 suffix) | Rs + who (×0.25 suffix for double-resist) | Im + who | Neu count | Gap label inline.

Gap rules (inline on row, also summarised below table):
  - `!! CRITICAL`  3+ weak, 0 resist+immune
  - `!  MAJOR`     3+ weak, ≤1 resist+immune
  - `.  MINOR`     2 weak, 0 resist+immune

### New functions
- `build_unified_rows(team_defense, era_key)` → one row per era type, all counts and names, sorted weak-first
- `gap_label(weak_count, cover_count)` → string label or ""
- `_weak_tag(name, mult)` → appends (×N) for ×4+
- `_resist_tag(name, mult)` → appends (×0.25) for double-resist
- `_names_cell(names, width)` → fixed-width cell with truncation and "-" for empty
- `_print_unified_table(rows, n_members)` → full table render

### Removed
`_print_weakness_section` and `_print_resistance_section` (replaced by unified table).
Old `weakness_summary`, `resistance_summary`, `critical_gaps` kept for backward compat and tests.

### Tests
56 total (up from 43). New tests cover `build_unified_rows`, `gap_label`, `_weak_tag`,
`_resist_tag`, `_names_cell`, `_print_unified_table`.
Bug found during testing: assumed Rock would sort first for single-Charizard team,
but Electric/Rock/Water all have weak=1 and sort alphabetically → Electric first.
Test fixed to check structural invariant (weak rows before non-weak rows) rather than specific type.

Full offline suite: **498 tests, 0 failures.**