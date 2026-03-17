# TASKS.md

# Current work — quick wins batch

**Status:** NOT STARTED

Four tickets selected from the roadmap for their low complexity and high
daily-use impact. All are self-contained: no new PokeAPI endpoints, no schema
changes, no new context objects.

Ticket IDs reference ROADMAP.md identifiers. Each step must include:
1. Implementation
2. `_run_tests()` additions (where testable logic exists)
3. Documentation updates (`HISTORY.md`, `ROADMAP.md` if needed)

---

# Pythonmon-1 — S screen loading indicator

**Status:** ✅ COMPLETE (§72)
**File:** `feat_team_moveset.py`

## What
Print a progress line before `recommend_team_movesets` runs so the user
knows the tool is working during a cold-cache run with a full 6-member team.

Proposed output (before the member blocks appear):
```
  Computing movesets for 6 member(s)…
```

## Where
In `run()` in `feat_team_moveset.py`, between the mode prompt and the
`recommend_team_movesets` call.

## Tests
No pure logic to test. Verify manually: press S with a cold cache and confirm
the line appears before the learnset fetch messages.

## Notes
- The O screen already has a similar pattern ("Loading move data for N member(s)...").
  Match that style exactly.
- Do not add the line inside `display_team_movesets` — keep display functions
  side-effect-free with respect to loading state.

---

# Pythonmon-2 — Fuzzy name matching

**Status:** ✅ COMPLETE (§73)
**File:** `pkm_session.py`
**Complexity:** 🟢 Low

## What
When the user types a partial Pokemon name (e.g. "char"), search
`pokemon_index.json` for all keys that start with or contain the input,
and offer ranked suggestions before falling back to a PokeAPI lookup.

Proposed flow:
```
  Enter Pokemon name: char
  Multiple matches — did you mean:
    1. Charizard
    2. Charmander
    3. Charmeleon
    4. Sawk     (contains "har" — ranked lower)
  Enter number (or 0 to type a different name):
```

## Design decisions to make before implementation
- **Prefix-only vs. substring**: prefix matches ranked first, substring
  matches shown below (same as `match_move` in `feat_moveset.py`).
- **Only cached Pokemon**: the index only contains Pokemon the user has
  previously looked up. Display a note: "(showing cached Pokemon only —
  enter full name to search PokeAPI)".
- **Exact slug match still tried first**: if "charizard" is in the index,
  load it directly without showing the picker.
- **Max suggestions shown**: cap at 8 to avoid flooding the screen.

## Where
In `_lookup_pokemon_name()` in `pkm_session.py`. After the name is entered
but before calling `_fetch_or_cache`, run the index search. If one exact
match: proceed as today. If multiple: show picker. If none in index: proceed
to PokeAPI as today.

## Tests
Add to `pkm_session.py _run_tests()`:
- prefix search returns correct candidates from a fake index
- exact match skips the picker
- empty index falls through to PokeAPI path
- result is capped at 8

---

# Pythonmon-3 — Batch move upserts in build_candidate_pool

**Status:** ✅ COMPLETE (§74)
**File:** `feat_moveset_data.py`
**Complexity:** 🟡 Medium

## What
`build_candidate_pool` currently writes `moves.json` once per missing move.
With 20 uncached moves, that is 20 full reads + 20 full writes of a file
that may already contain ~900 entries. Replace with a single write at the
end of the fetch loop.

## Current code (simplified)
```python
for name in missing:
    entries = pokeapi.fetch_move(name)
    cache.upsert_move(name, entries)       # read + write per iteration
```

## Target behaviour
```python
batch = {}
for name in missing:
    entries = pokeapi.fetch_move(name)
    batch[name] = entries
if batch:
    cache.upsert_move_batch(batch)         # single read + write
```

## Where
- `feat_moveset_data.py` — update the fetch loop in `build_candidate_pool`
- `pkm_cache.py` — add `upsert_move_batch(entries_dict)` function

## Implementation notes
- `upsert_move_batch` follows the same pattern as `upsert_move` but merges
  a whole dict in one operation:
  ```python
  def upsert_move_batch(batch: dict) -> None:
      existing = get_moves() or {}
      existing.update(batch)
      existing["_scraped_at"] = _now()
      existing["_version"]    = MOVES_CACHE_VERSION
      _write(_MOVES_FILE, existing)
  ```
- Keep `upsert_move` for single-move callers (it is used in `run_tests.py`
  cache warm-up and elsewhere).
- If any individual fetch fails, skip that move and continue — same
  behaviour as today.

## Tests
- `pkm_cache.py`: add tests for `upsert_move_batch` — multiple keys written
  in one call, existing keys preserved, version set correctly.
- `feat_moveset_data.py`: extend the existing cache-key regression test to
  verify that the batch path also saves under the learnset name (not canonical).

---

# Pythonmon-4 — Session pool caching for O and S screens

**Status:** TO DO
**Files:** `pokemain.py`, `feat_team_offense.py`, `feat_team_moveset.py`
**Complexity:** 🟢 Low

## What
Both the O and S screens rebuild member move pools on every visit. With a
6-member team this is up to 6 × learnset lookups + scoring passes each time.
A session-level cache makes every repeat visit instant.

## Design
A plain dict in `pokemain.py`, passed into the relevant `run()` calls:
```python
_pool_cache = {}   # key: (variety_slug, game_slug) → damage_pool list
```

Lifetime: session only — cleared on exit, never written to disk.

## Interface change
`feat_team_offense.run(team_ctx, game_ctx)` and
`feat_team_moveset.run(team_ctx, game_ctx)` gain an optional parameter:
```python
def run(team_ctx, game_ctx, pool_cache=None):
```
When `pool_cache` is provided, `build_candidate_pool` is called only for
members whose `(variety_slug, game_slug)` key is absent. Results are stored
back into the dict before returning.

`pokemain.py` passes `_pool_cache` on every S and O call. The dict persists
across menu selections for the duration of the session.

## Invalidation
The cache must be cleared when:
- The game changes (`G` key) — `game_slug` in the key handles this
  naturally (different key), so no explicit invalidation needed.
- A team member is replaced (`T` key) — old slots' pools remain in the
  dict but will never be looked up again (different `variety_slug`). No
  harm in keeping them; they are small.

## Tests
Add to `feat_team_offense.py` and `feat_team_moveset.py`:
- When `pool_cache` is provided and key is present, `build_candidate_pool`
  is NOT called (mock it to assert call count = 0).
- When key is absent, pool is computed and stored in the dict.
- `pool_cache=None` falls back to current behaviour (no regression).


---

# Pythonmon-16 — `get_form_gen` false-positive on "mega" substring

**Status:** ✅ COMPLETE (§75)
**File:** `pkm_session.py`

## Root cause

`get_form_gen` uses `if keyword in name_lower` — a plain substring check.

```python
"mega" in "meganium".lower()   # → True  ← BUG
"mega" in "mega charizard x".lower()   # → True  ← correct
```

`"mega"` appears at positions 0–3 inside `"meganium"`, so any Pokémon
whose name contains those four letters in sequence will be incorrectly
assigned `form_gen = 6` regardless of its actual generation.

Only `"mega"` is affected — the other keywords (`alolan`, `galarian`,
`hisuian`, `paldean`) are long enough that no real Pokémon name contains
them as embedded substrings.

## Observed symptom

```
Loaded: Meganium — Grass type
Meganium was introduced in Generation 6 and did not exist in Gold / Silver / Crystal.
```

Meganium is a Gen 2 Pokémon. `get_form_gen("Meganium", species_gen=2)`
incorrectly returns 6 because `"mega" in "meganium"` is True.

## Secondary symptom

The picker also showed a fabricated "Mega Meganium (Grass / Fairy)" form.
Meganium has no Mega Evolution. This is stale/corrupted data in the local
`cache/pokemon/meganium.json`. After the code fix, deleting that cache file
and re-fetching Meganium will return only the base form from PokeAPI, which
the deduplication logic will collapse to a single entry.

## Fix

Replace the substring check with a word-split check in `get_form_gen`:

```python
# Before
if keyword in name_lower:

# After
if keyword in name_lower.split():
```

The special-case check for `"Mega ... Z"` forms at the top of the function
also uses `"mega" in name_lower` — update it consistently to
`"mega" in name_lower.split()`.

```python
# Before
if "mega" in name_lower and name_lower.rstrip().endswith(" z"):

# After
if "mega" in name_lower.split() and name_lower.rstrip().endswith(" z"):
```

Word-split examples:
- `"Mega Charizard X".lower().split()` → `["mega", "charizard", "x"]` → hit ✓
- `"Meganium".lower().split()`         → `["meganium"]`                → miss ✓
- `"Mega Meganium".lower().split()`    → `["mega", "meganium"]`        → hit ✓ (correct)

## Tests to add

In `pkm_session.py _run_tests()`:
- `get_form_gen("Meganium", 2)` returns `2` (not `6`)
- `get_form_gen("Mega Charizard X", 1)` returns `6`
- `get_form_gen("Mega Garchomp Z", 1)` returns `9` (special case still works)
- `get_form_gen("Alolan Sandslash", 8)` returns `7`
- `get_form_gen("Sandslash", 1)` returns `1` (base form, no keyword)

## Cache cleanup note

After applying the fix, users with a corrupted `cache/pokemon/meganium.json`
(or any Pokémon with a fabricated Mega form) should delete the file and let
it re-fetch. The fix itself does not repair existing cache files.

Consider documenting in README troubleshooting: "Wrong or extra forms shown
for a Pokémon → delete `cache/pokemon/<name>.json` and reload."


---

# Completion criteria

This batch is complete when:

* Pythonmon-1: loading line appears before engine runs on S screen
* Pythonmon-2: partial name input offers ranked suggestions from index
* Pythonmon-3: `upsert_move_batch` added; `build_candidate_pool` uses it
* Pythonmon-4: repeat O and S visits do not re-fetch already-built pools
* Pythonmon-16: `get_form_gen` false-positive on "mega" substring

* All offline tests pass (`python run_tests.py --offline`)
* `HISTORY.md` updated for each ticket
