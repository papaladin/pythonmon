# TASKS.md

# Current work — batch 3: UX + Pokemon features

**Status:** NOT STARTED

Two tickets. Pythonmon-6 is additive to an existing feature with no new files.
Pythonmon-8 is a new standalone feature file with a new menu key.

Ticket IDs reference ROADMAP.md identifiers. Each step must include:
1. Implementation
2. `_run_tests()` additions (where testable logic exists)
3. Documentation updates (`HISTORY.md`, `ROADMAP.md`, `TASKS.md`)

---

# Pythonmon-6 — Move filter in pool

**Status:** TO DO
**File:** `feat_movepool.py`
**Complexity:** 🟢 Low

## What

When the user presses `2` (learnable move list), offer an optional filter
before the list is displayed. The user can narrow the output by type,
category, or minimum power — or skip filtering entirely to see everything.

Proposed flow:
```
  Enter Pokemon name: charizard
  (loaded from cache)

  Filter move list? (Enter to skip)
    Type     (e.g. Fire, Water — blank = all)
    Category (P)hysical / (S)pecial / (T) Status / (Enter = all)
    Min power (e.g. 80 — blank = all)

  Type: fire
  Category: s
  Min power: 80

  [ Charizard  •  Fire / Flying  •  Scarlet / Violet ]

  ── LEVEL-UP ─────────────────────────
  Lv  1    Flamethrower   Fire   Special   90  100%   15pp
  Lv 76    Fire Blast     Fire   Special  110   85%    5pp
  ...
```

## Design

### New pure logic function: `_apply_filter(entries, game_ctx, f) → list`

```python
f = {
    "type"    : str | None,   # e.g. "Fire" — case-insensitive match
    "category": str | None,   # "Physical" | "Special" | "Status"
    "min_power": int | None,  # inclusive lower bound on power
}
```

Takes a flat list of `(label, move_name, details_or_None)` tuples (one per
move across all sections) and returns the filtered subset. Pure — no I/O.

### New interactive function: `_prompt_filter() → dict`

Asks the three questions. Returns a filter dict. All fields optional — pressing
Enter on any question sets that field to `None` (no constraint).

Category input normalised: `"p"` → `"Physical"`, `"s"` → `"Special"`,
`"t"` or `"sta"` → `"Status"`. Anything else → `None` (no filter).

### Integration point in `_display_learnset`

After `_prefetch_missing` and before rendering:

```python
filter_spec = _prompt_filter()
```

Pass `filter_spec` through to the section renderers. Each section skips moves
that don't match. If all moves in a section are filtered out, the section
header is also suppressed.

Show a count at the top: `Showing 12 of 54 moves (filtered)` when a filter
is active. Show nothing extra when no filter is applied.

### Filter is per-visit

Not persisted. Each press of `2` starts fresh.

## Files

Only `feat_movepool.py` changes. No new files, no pokemain changes.

## Tests

Add to `feat_movepool.py _run_tests()`:

- `_apply_filter` with type filter: only matching type returned
- `_apply_filter` with category filter: only matching category returned
- `_apply_filter` with min_power filter: only moves at or above threshold
- `_apply_filter` with combined filters: intersection applied correctly
- `_apply_filter` with no filter (all None): all moves returned unchanged
- `_apply_filter` with filter that matches nothing: returns `[]`
- Move with `power=None` (status move): excluded by min_power filter,
  included when min_power is None

## Notes

- The filter is applied to the `details` dict returned by `_get_move_details`.
  If `details` is None (move not in cache), the move is included regardless
  of filter — same graceful behaviour as today.
- The `_display_learnset` function receives the filter spec and passes it
  down; `_prompt_filter` is called once before rendering begins.
- Summary line at the bottom should reflect filtered counts:
  `Showing 12 of 54 moves  (8 level-up  4 TM/HM  0 tutor  0 egg)`
- `run()` does not change signature.

---

# Pythonmon-8 — Stat comparison

**Status:** TO DO
**Files:** `feat_stat_compare.py` (new), `pokemain.py`, `run_tests.py`
**Complexity:** 🟢 Low

## What

A new screen (key `C`) that shows two Pokemon side by side with their base
stats, so the user can directly compare them. No new API data — both
`base_stats` dicts are already in the cache from prior `P` loads.

Proposed output:

```
  Stat comparison  |  Scarlet / Violet
  ════════════════════════════════════════════════════════
  Charizard  [Fire / Flying]      vs   Garchomp  [Dragon / Ground]
  ════════════════════════════════════════════════════════
  HP     78  [████████·············]      108  [█████████████········]
  Atk    84  [██████████·············]    130  [████████████████·····]
  Def    78  [████████·············]       95  [████████████·········]
  SpA   109  [█████████████········]       80  [█████████············]
  SpD    85  [██████████·············]     85  [██████████·············]
  Spe   100  [████████████·········]      102  [████████████·········]
  ────────────────────────────────────────────────────────
  Total 534                               600
  ════════════════════════════════════════════════════════
  ★ = higher   • = tied
```

## Design

### New file: `feat_stat_compare.py`

Module structure follows project conventions (docstring → imports → constants
→ pure logic → display → entry points → tests → `__main__`).

### Pure logic functions

**`compare_stats(stats_a, stats_b) → list[dict]`**

For each of the 6 stats, returns:
```python
{
    "key":    str,          # "hp", "attack", etc.
    "label":  str,          # "HP", "Atk", etc.
    "val_a":  int,
    "val_b":  int,
    "winner": "a" | "b" | "tie",
}
```
Pure — takes two `base_stats` dicts, returns comparison rows.

**`total_stats(base_stats) → int`**

Sum of all 6 base stats. Pure helper.

### Display function

**`display_comparison(pkm_a, pkm_b, game_ctx)`**

Reuses `_stat_bar` logic from `feat_type_matchup.py` — but does NOT import
it (private function in another module). Define `_stat_bar` locally in
`feat_stat_compare.py`. Same formula, same constants.

Side-by-side layout: left Pokemon name + bar + value, right Pokemon name +
bar + value. Fixed column widths defined as module-level constants.

### Entry point

**`run(pkm_ctx, game_ctx)`** — called from pokemain key `C`.

Since `C` requires two Pokemon, `run()` prompts for the second one
interactively:

```
  Comparing with: Garchomp
  (loaded from cache or prompts for second Pokemon)
```

The first Pokemon (`pkm_ctx`) is the currently loaded one. The second is
selected via `pkm_session.select_pokemon(game_ctx=game_ctx)`.

### pokemain.py changes

- Import `feat_stat_compare` in the try/except block
- Add `C. Compare stats  (needs Pokemon + game)` to the menu, visible when
  `both` (pkm + game loaded)
- Handler: `elif choice == "c": feat_stat_compare.run(pkm_ctx, game_ctx)`

### run_tests.py

Add `feat_stat_compare` to SUITES (offline, no cache keys).

## Tests

Add to `feat_stat_compare.py _run_tests()`:

**`compare_stats`:**
- All stats equal → all winners are "tie"
- A strictly better → all winners are "a"
- Mixed results → correct winner per stat
- `total_stats` is sum of all 6 values

**`display_comparison` (stdout capture):**
- Both Pokemon names appear in output
- All 6 stat labels appear
- "Total" line appears
- Output does not crash on missing stat keys (graceful fallback to 0)

## Notes

- `_stat_bar` is duplicated from `feat_type_matchup.py` by design — private
  helpers are not shared across feature modules (project convention).
- The second Pokemon selection uses the existing fuzzy picker from
  `pkm_session.select_pokemon` — no new input handling needed.
- If the second Pokemon load is aborted (returns None), `run()` prints a
  message and returns without crashing.
- Key `C` is safe — not currently used by any handler in pokemain.

---

# Completion criteria

Batch 3 is complete when:

* Pythonmon-6: filter prompt shown before option 2 output; all filter
  combinations work; tests pass
* Pythonmon-8: `C` key shows side-by-side stat comparison; `feat_stat_compare`
  in `run_tests.py`; all tests pass
* All offline tests pass (`python run_tests.py --offline`)
* `HISTORY.md`, `ROADMAP.md`, `TASKS.md` updated for each ticket