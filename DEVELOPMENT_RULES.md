# DEVELOPMENT_RULES.md
# Coding standards and conventions for this project

> These rules reflect how the project has been built from the start.
> They exist so that a new contributor (human or AI) produces code that is
> consistent with the rest of the codebase.
> "Rule" means: follow this unless you have a compelling reason not to,
> and if you deviate, document why in HISTORY.md.

---

## 1. Project language and dependencies

- **Python 3.10+**, standard library only for core logic.
- The only allowed external dependency is `requests` (for PokeAPI calls).
- Do NOT add new pip packages without explicit user approval.
- All files run as standalone scripts (`python <file>.py`) with no installation step.

---

## 2. File organisation

- One feature = one file. `feat_<name>.py` for user-facing features.
  Supporting data/logic that is too large for one feature: `feat_<name>_data.py`.
- Pure logic (no I/O, no display) must go in `core_<name>.py` files.
- Shared infrastructure: `pkm_cache.py`, `pkm_sqlite.py`, `pkm_pokeapi.py`, `pkm_session.py`, `matchup_calculator.py`. Do not bloat these with feature-specific logic.
- Entry point: `pokemain.py`. This file wires features together; it contains almost no logic of its own.
- Tests: embedded in each module as `_run_tests()`, NOT in a separate test file.
  `run_tests.py` is only a runner that calls each module's `--autotest` flag.

---

## 3. Module structure (every feat_ and core_ file must follow this order)

    1. Module docstring (purpose, public API, entry points)
    2. Imports (stdlib, then project modules)
    3. Constants
    4. Pure logic functions (only in core modules; feature modules may call them)
    5. Display / formatting helpers (only in feature modules)
    6. Entry points: run(ctx...) called from pokemain, then main() for standalone use
    7. _run_tests() function
    8. if __name__ == "__main__": block with --autotest dispatch

---

## 4. Function design

- Keep functions focused on one thing.
- Prefer functions under ~50 lines. If longer, consider splitting.
  Exception: display functions that build a single visual output may be longer,
  as splitting them often makes them harder to read.
- Pure logic functions must have no print statements and no input() calls.
  They take data in, return data out. They reside in core modules.
- Display functions print to stdout. They do not return values.
- Entry points (`run()`, `main()`) may call both.

---

## 5. Context objects

The project uses plain dicts as context objects. Do not introduce classes.

    game_ctx = {
        "game": str,         # display name e.g. "Scarlet / Violet"
        "gen": int,          # generation number 1-9
        "era_key": str,      # "era1", "era2", "era3"
        "game_slug": str,    # PokeAPI slug e.g. "scarlet-violet"
        ...
    }

    pkm_ctx = {
        "form_name": str,    # display name e.g. "Charizard"
        "type1": str,        # e.g. "Fire"
        "type2": str,        # "None" if single-typed (string, not Python None)
        "variety_slug": str, # PokeAPI variety slug
        ...
    }

    team_ctx = list          # list of 6 elements, each is pkm_ctx or None

Never store mutable state in module-level globals. Pass context through arguments.

---

## 6. Testing rules

### What to test
- All pure logic functions: transformations, calculations, sorting, classification.
- String formatting helpers (tag functions, cell formatters, bar builders).
- Edge cases: empty input, single-item input, maximum-size input, boundary values.
- Era compatibility: when logic depends on era_key, test at least era1 and era3.

### What NOT to test
- Functions that only print (display functions). Exception: use stdout capture
  to verify that specific strings appear in output (e.g. all type names present).
- Functions that call input() interactively.
- Live network calls. Use --withcache flag for cache-dependent tests.

### Test function structure

Every module ends with:

    def _run_tests():
        errors = []
        def ok(label):    print(f"  [OK]   {label}")
        def fail(label, msg=""):
            print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
            errors.append(label)

        # ... test blocks grouped by function under ## comments ...

        print()
        total = N   # must match actual number of ok()/fail() calls
        if errors:
            print(f"  FAILED ({len(errors)}): {errors}")
            sys.exit(1)
        else:
            print(f"  All {total} tests passed")

    if __name__ == "__main__":
        if "--autotest" in sys.argv:
            _run_tests()
        else:
            main()

### Test labels
Labels must be specific: "weakness_summary: Rock sorted first (x4 priority)"
NOT: "sort works" or "test 3".

The label format is: "<function_name>: <what is being asserted>"

### Fixtures
Use minimal inline fixtures — plain dicts that match the real context shape.
Do not import real Pokemon data from cache in offline tests.

    def _pkm(name, t1, t2="None"):
        return {"form_name": name, "type1": t1, "type2": t2}

### Keeping total = N accurate
After adding or removing tests, update `total = N` at the bottom of `_run_tests()`.
A mismatch between the declared total and actual test count is a bug.

---

## 7. Cache and network

- All PokeAPI calls go through `pkm_cache.py`. Never call requests directly
  from a feature file.
- Features must work fully offline if the cache is populated.
- The cache is stored in a single SQLite database (`cache/pokemon.db`). Tables are created automatically on first use. Data is stored as JSON text in the appropriate columns.
- Tests that require cache data are tagged with `--withcache` and are skipped
  during `--offline` runs.
- Never hard-code Pokemon data (stats, types, move lists) in feature files.
  Always read from cache.

---

## 8. Error handling

- If a required module is missing: print a clear error and sys.exit(1).
  Use a try/except ImportError at the top of each file.
- If cache data is missing: print a user-friendly message ("Run the tool with
  a network connection first to populate the cache."), do not traceback.
- Do not use bare `except:`. Catch specific exceptions.
- Do not silently swallow errors. If something fails unexpectedly, let it surface.

---

## 9. Display conventions

- All output is indented with two spaces ("  ") from the left margin.
- Section headers use dashes: `"  -- Section title " + "-" * N`
- Separators use "=" for major breaks, "-" for minor breaks.
- Column widths are defined as module-level constants (`_COL_TYPE = 10`),
  not as magic numbers inside format strings.
- Pokemon names in tables are abbreviated to 4 characters (`_abbrev(name)`).
  Tags like (x4) or (x0.25) are appended after the abbreviated name.
- Multipliers are written with the times sign character: x4, x0.25 (not "x4.0").
- When a cell has no content, display "-" not an empty string.

---

## 10. pokemain.py integration rules

- Every new feature key must appear in `_print_menu()` with a visibility condition.
  Keys requiring a game: show only when `game_ctx is not None`.
  Keys requiring a team: show only when `team_size(team_ctx) > 0`.
- Handler blocks follow this pattern:

      elif choice == "x":
          if game_ctx is None:
              print("\n  Select a game first (press G).")
          elif <other missing context>:
              print("\n  <clear instruction>.")
          else:
              feat_xyz.run(relevant_ctx...)

- Never let a missing context cause an AttributeError or KeyError.
  Always guard and print a helpful message.

---

## 11. Git / versioning conventions

- We do not use git branches for this project (solo development).
- Every significant change is logged in HISTORY.md as a §N entry.
  The §N number increments from the last entry. Never reuse a number.
- The §N log is the authoritative history. Do not rely on git log alone.

---

## 12. Core modules (pure logic)

All pure logic (no I/O, no print, no `input()`) must reside in `core_*.py` files. These modules contain functions that transform data structures and perform calculations. They are independently testable with `--autotest`. Feature modules (`feat_*.py`) should import from core modules and handle only I/O and display. The core modules should not import `pkm_cache` or any other I/O‑heavy module; they operate only on plain data structures passed as arguments.

---

## 13. What NOT to do

- Do not add argparse or click. The CLI is hand-rolled by design.
- Do not add another database. The cache is a single SQLite file; keep it that way.
- Do not introduce async code. Everything is synchronous by design.
- Do not rename existing context keys (game_ctx, pkm_ctx, team_ctx fields)
  without updating every file that uses them and logging the change in HISTORY.md.
- Do not delete the backward-compatible functions in feat_team_analysis.py
  (`weakness_summary`, `resistance_summary`, `critical_gaps`) — they are used
  by tests in run_tests.py.