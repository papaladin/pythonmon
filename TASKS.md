# TASKS.md
# Current and planned tasks – refactoring & polish

---

## Completed TUI polish items

- [x] 4.2.1 Progress bar for long operations (`y` and `w`)
- [x] 4.2.2 Keyboard navigation hints (built into menu)
- [x] 4.2.3 Mouse support (Textual native)
- [x] 4.2.4 Left pane scrollable
- [x] 4.2.5 Colours in output
- [x] 4.2.6 `select_form` modal
- [x] 4.2.8 Error modal for network failures
- [x] 4.2.9 Loading spinner (progress bar)

---

## Remaining TUI polish

### 4.2.7 Rewrite type chart to return string

**Goal:** Replace `calc.print_results()` (which prints directly) with a function that returns a string, so the TUI can display it without `contextlib.redirect_stdout`.

**Steps:**
- Create `matchup_calculator.format_results(type1, type2, game, era_key) -> str`
- Keep `print_results` for CLI backward compatibility (calls format and prints)
- Update `feat_quick_view.py` to use the new format function and pass string to `ui.print_output`

**Added value:** Cleaner TUI integration, eliminates output capture hack.  
**Complexity:** 🟢 Low  
**Status:** ✅ Done (§124 in History)

---

## Code quality / refactoring tasks

### 1. Remove debug print statements from TUI

**Goal:** Remove all `DEBUG:` lines from `ui_tui.py` to avoid cluttering user output.

**Added value:** Cleaner terminal output, better user experience.  
**Complexity:** 🟢 Low  
**Status:** ⬜ To do

---

### 2. Centralise dummy UI creation

**Goal:** Extract the `DummyUI` class (currently repeated in every feature file) into a single module (e.g., `ui_dummy.py`). Feature files then import and instantiate it when `ui is None`.

**Added value:** Eliminates code duplication, reduces maintenance overhead.  
**Complexity:** 🟢 Low  
**Status:** ⬜ To do

---

### 3. Guard `get_moves()` returning `None`

**Goal:** In `feat_move_lookup._fetch_move_cached` and other places where `get_moves()` is used, handle the `None` case gracefully (treat as empty dict) to avoid crashes when cache is corrupted or version mismatch.

**Added value:** Prevents crashes in edge cases.  
**Complexity:** 🟢 Low  
**Status:** ⬜ To do

---

### 4. Unify `PKM_FEATURES` registry

**Goal:** Move the feature registry from `ui_cli.py` and `ui_tui.py` to a central location (e.g., `feature_registry.py` or `pokemain.py`). Both UI implementations import it.

**Added value:** Single source of truth for available features, easier to add or modify.  
**Complexity:** 🟡 Medium (requires updating both UI files and ensuring imports work)  
**Status:** ⬜ To do

---

### 5. Move common display helpers to `core_ui.py`

**Goal:** Extract duplicated helpers like `_abbrev`, `_stat_bar`, `_format_dots`, etc., into a shared module. This cleans up feature files and avoids inconsistency.

**Added value:** Reduces duplication, improves maintainability, centralises display logic.  
**Complexity:** 🟡 Medium (identify all duplicates, update imports, test)  
**Status:** ⬜ To do

---

### 6. Add type hints to public functions (gradual)

**Goal:** Start adding return and parameter type hints to core modules (`core_*.py`) and entry points (`feat_*.run`). Helps with documentation and IDE support.

**Added value:** Better maintainability, easier for new contributors.  
**Complexity:** 🟡 Medium (spread across many files)  
**Status:** ⬜ To do

---

### 7. Improve error handling in network functions

**Goal:** In `pkm_pokeapi.fetch_machines` and similar, avoid silent skipping of entries when an error occurs. At a minimum, log the problematic machine ID or move name so issues can be debugged.

**Added value:** Helps diagnose data gaps or API inconsistencies.  
**Complexity:** 🟢 Low  
**Status:** ⬜ To do

---

### 8. Centralise `build_pkm_ctx_from_cache` logic

**Goal:** The function `_build_pkm_ctx_from_cache` in `feat_team_loader.py` duplicates logic from `pkm_session.select_pokemon`. Move it to a utility (e.g., `core_pokemon` or `pkm_session`) and reuse.

**Added value:** Reduces duplication, ensures consistency in building `pkm_ctx` from cached data.  
**Complexity:** 🟡 Medium (requires refactoring `select_pokemon` and updating callers)  
**Status:** ⬜ To do

---

### 9. Compile regex patterns for performance

**Goal:** Precompile `_PROGRESS_PATTERN` in `ui_tui.py` and any other regex used inside loops to avoid recompilation.

**Added value:** Minor performance improvement, good practice.  
**Complexity:** 🟢 Low  
**Status:** ⬜ To do

---

### 10. Remove unused imports

**Goal:** Scan the codebase for unused imports (e.g., `Footer` in `ui_tui.py`) and remove them.

**Added value:** Cleaner code, reduces confusion.  
**Complexity:** 🟢 Low  
**Status:** ⬜ To do

---