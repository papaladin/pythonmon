# TASKS.md

# Current work — Technical debt + Packaging

**Status:** ✅ ALL COMPLETE — §101–§103

All technical debt (TD-1 through TD-6) and packaging (PKG-1 through PKG-3) complete.
To build a distributable binary: `pip install pyinstaller` then `python build.py`.


---

# TD-1 — Duplicate `L` menu line

**Status:** ⬜ NOT STARTED
**File:** `pokemain.py`
**Complexity:** 🟢 Low

## What

`_print_menu()` appends the `L` learnset line twice:

```python
lines.append("L. Compare learnsets  (pick a second Pokémon)")
lines.append("L. Compare learnsets  (pick a second Pokémon)")   # ← dead
```

The `seen` deduplication guard at the bottom silently discards the second
occurrence at runtime, so the menu looks correct — but the dead line is a
maintenance hazard and makes the intent unclear.

## Fix

Remove the second append. One line deletion.

## Verification

`python -c "import pokemain; print('OK')"` must pass.
Visually confirm `L` appears once in the menu when both Pokemon and game are loaded.

---

# TD-2 — Inconsistent team handler style

**Status:** ⬜ NOT STARTED
**File:** `pokemain.py`
**Complexity:** 🟢 Low

## What

Two inconsistencies in `_print_menu()` and the main loop:

**1. Guard style mismatch**

| Key | Menu visibility condition | Handler guard |
|---|---|---|
| V, O, S | `team_size(team_ctx) > 0` | `team_size(team_ctx) == 0` |
| H | `team_size(team_ctx) >= 1` | `team_size(team_ctx) == 0` |

`> 0` and `>= 1` are identical for integers. Pick one form and use it
consistently. Convention in the rest of the codebase is `> 0` / `== 0`.

**2. Split visibility blocks**

V/O/S visibility and H visibility are two separate `if` blocks:

```python
if team_ctx is not None and feat_team_loader.team_size(team_ctx) > 0:
    lines.append("V. ...")
    lines.append("O. ...")
    lines.append("S. ...")
if team_ctx is not None and has_game and feat_team_loader.team_size(team_ctx) >= 1:
    lines.append("H. ...")
```

H additionally requires `has_game`. The two blocks can be merged:

```python
if team_ctx is not None and feat_team_loader.team_size(team_ctx) > 0:
    lines.append("V. Team defensive vulnerability analysis")
    lines.append("O. Team offensive coverage")
    lines.append("S. Team moveset synergy")
    if has_game:
        lines.append("H. Team builder  (suggest next slot)")
```

## Fix

1. Change `>= 1` to `> 0` in the H menu condition.
2. Merge the two blocks as shown above.

No handler logic changes needed — the handlers already use `== 0`.

## Verification

Menu shows V/O/S/H together when team + game loaded.
H absent when no game selected (even with team loaded).

---

# TD-3 — `_handle_refresh_flags` mixed concerns

**Status:** ⬜ NOT STARTED
**File:** `pokemain.py`
**Complexity:** 🟢 Low

## What

`_handle_refresh_flags` currently does two different things in the same
function body:

- **Diagnostic flags** (`--cache-info`, `--check-cache`): print output and
  call `sys.exit(0)`. Control never returns to the caller.
- **Mutation flags** (`--refresh-*`): invalidate cache entries and return
  normally so the tool continues into the menu.

Mixing these makes the function's contract unclear: does it return, or does
it exit? The answer is "sometimes both", which is confusing.

## Fix

Split into two functions with clear names:

```python
def _handle_diagnostic_flags(args: list) -> None:
    """
    Handle flags that print information and exit immediately.
    Calls sys.exit(0) if a diagnostic flag is found; returns normally otherwise.
    """
    if "--cache-info" in args:
        ...
        sys.exit(0)
    if "--check-cache" in args:
        ...
        sys.exit(0)


def _handle_refresh_flags(args: list) -> None:
    """
    Handle cache mutation flags. Always returns normally.
    """
    if "--refresh-moves" in args:
        ...
    if "--refresh-pokemon" in args:
        ...
    # etc.
```

Call both from `main()`:

```python
def main():
    _handle_diagnostic_flags(sys.argv[1:])
    _handle_refresh_flags(sys.argv[1:])
    _banner()
    ...
```

## Verification

`python pokemain.py --cache-info` prints and exits (does not open menu).
`python pokemain.py --check-cache` prints and exits.
`python pokemain.py --refresh-moves` invalidates moves and opens menu normally.
`python -c "import pokemain; print('OK')"` passes.

---

# TD-4 — `_MACHINES_FILE` defined twice in `pkm_cache.py`

**Status:** ⬜ NOT STARTED
**File:** `pkm_cache.py`
**Complexity:** 🟢 Low

## What

`_MACHINES_FILE` is defined at line 108 with all the other path constants,
then silently re-defined at line 462 just above `get_machines()`:

```python
# Line 108 — correct location, with all other constants
_MACHINES_FILE= os.path.join(_BASE, "machines.json")

# ... ~350 lines later ...

# Line 462 — redundant duplicate
_MACHINES_FILE = os.path.join(_BASE, "machines.json")
```

Both produce the same value, so behaviour is unaffected. But the duplicate
makes it look like the constant is being *changed* at line 462, which it
isn't.

## Fix

Delete line 462 (`_MACHINES_FILE = os.path.join(_BASE, "machines.json")`
just above the machines cache section comment).

## Verification

`python pkm_cache.py` passes all tests.
`python -c "from pkm_cache import _MACHINES_FILE; print(_MACHINES_FILE)"` prints
the correct path once.

---

# TD-5 — `_learnset_path` and `game_to_slug` layout in `pkm_cache.py`

**Status:** ⬜ NOT STARTED
**File:** `pkm_cache.py`
**Complexity:** 🟢 Low

## What

Two layout problems in the constant/helper block:

**Problem 1:** `_learnset_path()` is wedged between `_LEARNSET_DIR` and
`_MOVES_FILE`, breaking the constant block in two:

```python
_LEARNSET_DIR = os.path.join(_BASE, "learnsets")

def _learnset_path(...):      # ← function interrupts constants
    ...
_MOVES_FILE   = os.path.join(_BASE, "moves.json")
_MACHINES_FILE= ...
```

**Problem 2:** `_learnset_path` calls `game_to_slug`, which is defined
~30 lines *after* `_learnset_path`. Python resolves this at call time
so it works, but reading the file top-to-bottom it looks like a forward
reference bug.

## Fix

Move both `game_to_slug` and `_learnset_path` to a dedicated
`# ── Slug and path helpers ──` section that sits *after* all constants
and *before* the low-level read/write functions. The constant block
becomes uninterrupted:

```python
# ── Directory layout ──
_BASE         = ...
_POKEMON_DIR  = ...
_LEARNSET_DIR = ...
_MOVES_FILE   = ...
_MACHINES_FILE= ...    # (single definition, TD-4 already removed duplicate)
_INDEX_FILE   = ...
_TYPES_DIR    = ...
_NATURES_FILE = ...
_ABILITIES_FILE = ...
_ABILITIES_DIR  = ...
_EGG_GROUP_DIR  = ...
_EVOLUTION_DIR  = ...

MOVES_CACHE_VERSION = 3
LEARNSET_STALE_DAYS = 30

# ── Slug and path helpers ──
def game_to_slug(game: str) -> str: ...
def _learnset_path(variety_slug: str, game: str) -> str: ...

# ── Low-level read / write ──
def _ensure_dirs(): ...
def _read(path): ...
def _write(path, data): ...
```

## Verification

`python pkm_cache.py` passes all tests (especially learnset round-trip tests).
`python -c "from pkm_cache import game_to_slug; print(game_to_slug('Scarlet / Violet'))"` 
prints `scarlet-violet`.

---

# TD-6 — `build_candidate_pool` name collision

**Status:** ⬜ NOT STARTED
**File:** `feat_team_builder.py`, `pokemain.py` (docstring only)
**Complexity:** 🟢 Low

## What

Both `feat_team_builder` and `feat_moveset_data` export a public function
named `build_candidate_pool`:

| Module | Signature | Purpose |
|---|---|---|
| `feat_moveset_data` | `(pkm_ctx, game_ctx) → dict` | Build a scored move pool for a single Pokemon's moveset recommendation |
| `feat_team_builder` | `(team_ctx, game_ctx, off_gaps, def_gaps) → dict` | Build a candidate Pokemon pool from type rosters for slot suggestion |

No runtime collision (separate modules, never imported together into the same
namespace). But the identical name is confusing when reading ARCHITECTURE.md
or working across both files.

## Fix

Rename `feat_team_builder.build_candidate_pool` → `build_suggestion_pool`.

Update all internal references:
- `feat_team_builder.py`: function definition + docstring + `run()` call
- `feat_team_builder.py`: module docstring public API list
- `feat_team_builder.py`: `_run_tests()` test labels that mention the old name
- `ARCHITECTURE.md §7`: entry for `feat_team_builder.py`

No changes needed in `pokemain.py` (it calls `feat_team_builder.run()`,
not `build_candidate_pool` directly).

## Verification

`python feat_team_builder.py --autotest` passes all 57 tests.
`grep "build_candidate_pool" feat_team_builder.py` returns only test labels
and comments that reference the old name for historical context — the actual
function definition and call sites all use `build_suggestion_pool`.

---

# PKG-1 — `pkm_cache._BASE` relocation for frozen builds

**Status:** ⬜ NOT STARTED
**File:** `pkm_cache.py`
**Complexity:** 🟢 Low

## What

Currently `_BASE` is always set relative to `__file__`:

```python
_BASE = os.path.join(os.path.dirname(__file__), "cache")
```

When running inside a PyInstaller bundle, `__file__` points to a location
inside the read-only `.exe` — cache writes fail silently or crash.

The fix redirects `_BASE` to a writable location (next to the executable)
when running as a frozen bundle.

## Fix

Replace the `_BASE` line with:

```python
import sys as _sys
if getattr(_sys, "frozen", False):
    # Running as a PyInstaller bundle — cache lives next to the executable
    _BASE = os.path.join(os.path.dirname(_sys.executable), "cache")
else:
    # Normal source run — cache lives next to the .py files
    _BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
```

Notes:
- `sys.frozen` is set to `True` by PyInstaller at runtime; it does not exist
  in a normal Python environment, so `getattr(..., False)` is the safe test.
- `os.path.abspath(__file__)` is used in the else branch (instead of bare
  `__file__`) for robustness when the script is invoked from a different
  working directory.
- This change has zero effect on `python pokemain.py` or any test run.
- The `_sys` alias avoids shadowing the module-level `sys` that may be
  imported later.

## Test

Add one test to `pkm_cache.py`'s self-test suite (the temp-dir block):

```
- Simulate frozen=True: temporarily set sys.frozen = True, re-evaluate _BASE
  logic, confirm it resolves to os.path.dirname(sys.executable) + "/cache"
- Simulate frozen=False (normal): confirm _BASE resolves relative to __file__
```

The test must restore `sys.frozen` after each case (cleanup in `finally`).

## Verification

`python pkm_cache.py` passes all tests.
`python pokemain.py` opens normally, cache writes to the same location as before.

---

# PKG-2 — PyInstaller single-file executable

**Status:** ⬜ NOT STARTED (requires PKG-1 complete)
**Files:** `build.py` (new), `pokemain.spec` (generated by PyInstaller)
**Complexity:** 🟡 Medium
**Prerequisite:** PKG-1 merged and working.

## What

A single `pokemain.exe` (Windows) or `pokemain` binary (Mac/Linux) that a
non-Python user can double-click to launch the CLI. Python does not need to
be installed on the user's machine.

End-user file layout after distributing:
```
PokemonToolkit/
  pokemain.exe    ← the only thing the user needs to know about
  cache/          ← created automatically on first run
```

The source `.py` files are bundled inside the binary and are invisible to
the end user. The developer's working directory is completely unaffected.

## Build steps

### Step 1 — Install PyInstaller (build machine only)

```
pip install pyinstaller
```

PyInstaller does not need to be installed on the end user's machine.

### Step 2 — Run the build

```
pyinstaller --onefile --name pokemain pokemain.py
```

Key flags:
- `--onefile`: everything in one binary (as opposed to a folder of DLLs)
- `--name pokemain`: output file name
- No `--windowed` flag — we want the terminal to appear (CLI tool)

Output: `dist/pokemain.exe` (Windows) or `dist/pokemain` (Mac/Linux).

### Step 3 — Test the binary

```
dist/pokemain.exe              # Windows
./dist/pokemain                # Mac/Linux
```

Verify:
- Menu appears correctly
- Selecting a game works
- Loading a Pokemon fetches from PokeAPI and writes to `cache/` next to binary
- `dist/cache/` folder is created automatically

### Notes

- The build must be run on the target OS. A Windows `.exe` built on Mac will
  not work, and vice versa. Each platform requires its own build run.
- PyInstaller bundles the Python interpreter (~8–12 MB overhead). The final
  binary will be ~15–25 MB depending on platform.
- Windows antivirus may flag unsigned PyInstaller binaries as suspicious
  (false positive). This is a known PyInstaller limitation. Signing the binary
  with a code-signing certificate resolves it but requires purchasing one.
- `requests` is a dependency — PyInstaller will detect and bundle it
  automatically since it's imported by `pkm_pokeapi.py`.

## Verification

- Binary launches and shows the main menu.
- Cache writes land in `dist/cache/` (not in the source tree).
- Source `.py` files are untouched.
- `python pokemain.py` still works as before (source run unaffected).

---

# PKG-3 — `build.py` helper script

**Status:** ⬜ NOT STARTED (can be written before PKG-2 is verified)
**File:** `build.py` (new)
**Complexity:** 🟢 Low

## What

A thin wrapper script so any contributor can reproduce the build in one step
without memorising PyInstaller flags.

```
python build.py            # builds for current platform
python build.py --clean    # deletes dist/ and build/ before building
```

## Design

```python
#!/usr/bin/env python3
"""
build.py  Build script for Pokemon Toolkit

Produces a single-file executable using PyInstaller.
Run on each target platform separately:
  Windows → dist/pokemain.exe
  Mac     → dist/pokemain
  Linux   → dist/pokemain

Usage:
  python build.py            # build
  python build.py --clean    # clean build artifacts first

Requires: pip install pyinstaller
"""
import sys, os, shutil, subprocess

DIST_DIR  = os.path.join(os.path.dirname(__file__), "dist")
BUILD_DIR = os.path.join(os.path.dirname(__file__), "build")

def clean():
    for d in (DIST_DIR, BUILD_DIR):
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"  Removed {d}")

def build():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "pokemain",
        "--console",          # keep terminal visible (CLI tool)
        "pokemain.py",
    ]
    print("  Running:", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\n  Build successful.")
        print(f"  Output: {os.path.join(DIST_DIR, 'pokemain')}")
        print("  Distribute the binary + an empty cache/ folder next to it.")
        print("  (cache/ will be created automatically on first run.)")
    else:
        print("\n  Build failed — see PyInstaller output above.")
        sys.exit(1)

if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
    build()
```

## Verification

`python build.py` produces `dist/pokemain.exe` (or platform equivalent).
`python build.py --clean` deletes `dist/` and `build/` before building.
Script prints clear instructions about what to distribute.

---

# Completion criteria

Technical debt done when:
- `python pokemain.py` opens with no duplicate L line visible
- `python pokemain.py --cache-info` exits cleanly
- `python pokemain.py --refresh-moves` returns to menu normally
- `python run_tests.py --offline` → 0 failures

Packaging done when:
- `python pkm_cache.py` passes all tests (including new frozen-path test)
- `python build.py` produces a working binary on at least one platform
- Binary opens the menu, fetches a Pokemon, writes cache next to itself
- `python pokemain.py` (source run) still works unchanged
