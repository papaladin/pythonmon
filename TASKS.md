# TASKS.md

# Current work — batch 5: code quality sweep

Three tickets from the Copilot audit cross-check. All are low-risk,
self-contained cleanup items with no behaviour changes for the user.

Recommended implementation order: TD-7 → TD-8 → TD-9.
- TD-7 is smallest scope (single bare except + a handful of broad Exception).
- TD-8 (magic constants) is mechanical but touches more files.
- TD-9 (input validation) is the most user-visible change.

---

# TD-7 — Broad exception handling

**Status:** ✅ COMPLETE (§105)
**Files:** `pokemain.py`, `feat_quick_view.py`, `pkm_cache.py`
**Complexity:** 🟢 Low

## What

Replace bare `except:` and overly broad `except Exception:` clauses with
specific exception types. Three locations:

### pokemain.py line 79
```python
# Before
try:    total = str(hp + atk + def_ + spa + spd + spe)
except: total = "?"

# After
try:    total = str(hp + atk + def_ + spa + spd + spe)
except (TypeError, ValueError): total = "?"
```
The only realistic failures here are `TypeError` (a stat is "?" string from
the `.get("hp", "?")` fallback) or `ValueError`. Nothing else can fail.

### feat_quick_view.py line ~82
```python
# Before
try:
    import pkm_cache as _cache
    index = _cache.get_abilities_index()
except Exception:
    index = None

# After
try:
    import pkm_cache as _cache
    index = _cache.get_abilities_index()
except (ImportError, OSError, ValueError):
    index = None
```
This wraps a cache read. Only import errors or OS/JSON errors are possible.

### pkm_cache.py — cache_info counts (~lines 1130–1150)
Three consecutive `except Exception: pass` blocks inside the cache info
function. These wrap calls to `get_moves()`, `get_natures()`,
`get_abilities_index()` — all of which are already defensive and return None
on any error. The Exception catch is a double-safety net. Replace with:
```python
except (OSError, ValueError, TypeError):
    pass
```

Note: `feat_moveset_data.py` and `feat_team_moveset.py` broad exceptions are
inside `_run_tests()` — test harness code, intentionally catching anything to
report failures gracefully. Leave those unchanged.
Similarly `feat_team_builder.py` broad exception is inside a test assertion.
Leave unchanged.

---

# TD-8 — Magic constants

**Status:** ✅ COMPLETE (§105)
**Files:** `pokemain.py`, `feat_quick_view.py`
**Complexity:** 🟢 Low

## What

Extract repeated magic separator widths into named module-level constants.
Scope is limited to the two files where the same literal number appears
multiple times without a name.

### pokemain.py
```python
# Line 248, 253 — "─" * 46 appears twice in _print_context_lines
# Add near top of display section:
_STAT_SEP_WIDTH = 46
```

### feat_quick_view.py
```python
# "─" * 46 appears 4 times across _print_base_stats,
# _print_abilities_section, and the egg groups block.
# Already has _SEP_WIDTH = 46 defined in feat_evolution.py but not here.
# Add at module level:
_SEP_WIDTH = 46
```

Do NOT chase every separator width in every file — only extract where the
same literal appears 2+ times in the same file with no existing constant.
Other files already define their own `_W`, `_BLOCK_SEP`, `_STAT_W` etc.

---

# TD-9 — Input validation (partial)

**Status:** ✅ COMPLETE (§105)
**Files:** `pokemain.py`
**Complexity:** 🟢 Low

## What

Add an explicit set of valid menu choices at the top of the main loop.
The current `else: print("Invalid choice")` works correctly but silently
accepts and ignores any unrecognised string before falling through to the
else. The improvement is clarity and a slight speed-up (set lookup vs
chained elif for the invalid case).

```python
# Add near top of main(), before the while loop:
_MENU_CHOICES = frozenset({
    "q", "p", "g", "r", "t", "v", "o", "s", "h",
    "m", "b", "n", "a", "c", "l", "e", "move", "w",
})
```

The validation stays implicit — the existing elif chain handles all valid
choices. The constant is used only for documentation and any future guard.
Do NOT add an early-exit guard before the elif chain — that would require
duplicating the digit check logic and the "move" multi-char key. The
current structure already handles all cases correctly via the final `else`.

The real value: the constant makes the full set of valid choices visible in
one place, which is useful when adding new keys.

---

# Completion criteria

Batch 5 is complete when:
* TD-7: no bare `except:` anywhere in non-test code; broad `except Exception`
  replaced with specific types in the 3 target locations
* TD-8: `_SEP_WIDTH = 46` defined in `feat_quick_view.py`; `_STAT_SEP_WIDTH`
  or equivalent in `pokemain.py`; all `"─" * 46` replaced with the constant
  in those two files
* TD-9: `_MENU_CHOICES` frozenset defined and documented in `pokemain.py`
* All offline tests pass (`python run_tests.py --offline`)
* HISTORY.md updated
