# DEVELOPMENT_RULES.md
# Coding standards and conventions for this project

> These rules reflect how the project has been built from the start.  
> They exist so that a new contributor (human or AI) produces code consistent with the rest of the codebase.  
> For system design and module roles, see `ARCHITECTURE.md`.
> "Rule" means: follow this unless you have a compelling reason not to,
> and if you deviate, document why in HISTORY.md.

---

## 1. Project language and dependencies

- **Python 3.10+**, standard library only for core logic.
- **Approved external dependencies**:
  - `requests` (PokeAPI calls, only used in `pkm_pokeapi.py`)
  - `textual` (TUI interface, only used in `ui_tui.py`)
- Do **not** add new pip packages without explicit user approval.
- All files run as standalone scripts (`python <file>.py`) with no installation step.

---

## 2. File organisation & Module structure 

Follow the file layout described in `ARCHITECTURE.md` §1.  
Every `feat_*.py` and `core_*.py` file must adhere to this order:

1. Module docstring (purpose, public API, entry points)
2. Imports (stdlib, then project modules)
3. Constants
4. Pure logic functions (only in core modules; feature modules may call them)
5. Display / formatting helpers (only in feature modules)
6. Entry points: `async def run(...)` called from pokemain, then `main()` for standalone use
7. `_run_tests()` function (synchronous)
8. `if __name__ == "__main__":` block with `--autotest` dispatch

---

## 3. Function design

- Keep functions focused on one thing.
- Prefer functions under ~50 lines. If longer, consider splitting.
  Exception: display functions that build a single visual output may be longer,
  as splitting them often makes them harder to read.
- Pure logic functions must have no print statements and no input() calls.
  They take data in, return data out. They reside in core modules.
- Display functions **must** use the `ui` object passed to them (e.g., `await ui.print_output(...)`). They should not print directly.
- Entry points (`run()`) are `async` and receive a `ui` parameter.

---

## 4. Testing rules

### What to test
- All pure logic functions: transformations, calculations, sorting, classification.
- String formatting helpers (tag functions, cell formatters, bar builders).
- Edge cases: empty input, single-item, maximum-size, boundary values.
- Era compatibility: when logic depends on `era_key`, test at least `era1` and `era3`.

### What NOT to test
- Functions that only print (display functions). Exception: use stdout capture to verify that specific strings appear.
- Functions that call `input()` interactively.
- Live network calls. Use `--withcache` flag for cache-dependent tests.

### Test function structure

Every module ends with:

```python
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

### Test labels
Labels must be specific: "weakness_summary: Rock sorted first (x4 priority)"
NOT: "sort works" or "test 3".

The label format is: `<function_name>: <what is being asserted>`

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

- If a required module is missing: print a clear error and `sys.exit(1)`.
  Use a try/except ImportError at the top of each file.
- If cache data is missing: print a user-friendly message ("Run the tool with
  a network connection first to populate the cache."), do not traceback.
- Do not use bare `except:`. Catch specific exceptions.
- Do not silently swallow errors. If something fails unexpectedly, let it surface.
- Use `await ui.show_error(message)` to display errors in a user-friendly way
  (modal in TUI, simple print in CLI).

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

## 10. UI layer (abstract interface)

All user interaction must go through the `UI` abstract class (defined in `ui_base.py`).
Two implementations exist: `CLI` (console) and `TUI` (textual).  
Features receive a `ui` instance (usually named `ui`) as a parameter.

UI methods are **async** and must be awaited:

- `await ui.print_output(text, end="\n")`
- `await ui.input_prompt(prompt) -> str`
- `await ui.confirm(prompt) -> bool`
- `await ui.select_from_list(prompt, options, allow_none) -> str | None`
- `await ui.select_pokemon(game_ctx) -> dict | None`
- `await ui.select_game(pkm_ctx) -> dict | None`
- `await ui.select_form(forms) -> tuple`
- `await ui.print_session_header(pkm_ctx, game_ctx, constraints)`
- `await ui.show_error(message)`

**Do not call `print()` or `input()` directly** in feature code.

---

## 11. Async usage

- Feature entry points (`run()`) are `async`.
- Core logic (`core_*.py`) must remain **synchronous** (no `async`/`await`).
- The UI layer is the only place where asyncio is used.
- Use `asyncio.to_thread()` for blocking I/O (like network calls) inside async handlers.

---

## 12. pokemain.py integration rules

- Every new feature key must appear in `_build_menu_lines()` with a visibility condition.
  Keys requiring a game: show only when `game_ctx is not None`.
  Keys requiring a team: show only when `team_size(team_ctx) > 0`.
- Handler blocks follow this pattern:

      elif choice == "x":
          if game_ctx is None:
              await ui.show_error("Select a game first (press G).")
          elif <other missing context>:
              await ui.show_error("<clear instruction>.")
          else:
              await feat_xyz.run(relevant_ctx..., ui=self)

- Never let a missing context cause an AttributeError or KeyError.
  Always guard and print a helpful message.

---

## 13. Git / versioning conventions

- We do not use git branches for this project (solo development).
- Every significant change is logged in HISTORY.md as a §N entry.
  The §N number increments from the last entry. Never reuse a number.
- The §N log is the authoritative history. Do not rely on git log alone.

---

## 14. What NOT to do

- Do not add argparse or click. The CLI is hand-rolled by design.
- Do not add another database. The cache is a single SQLite file; keep it that way.
- Do not introduce async code in core modules (pure logic).
- Do not rename existing context keys (game_ctx, pkm_ctx, team_ctx fields)
  without updating every file that uses them and logging the change in HISTORY.md.
- Do not delete the backward-compatible functions in `feat_team_analysis.py`
  (`weakness_summary`, `resistance_summary`, `critical_gaps`) — they are used
  by tests in `run_tests.py`.