#!/usr/bin/env python3
"""
run_tests.py  Consolidated test runner for the Pokemon Toolkit.

Runs every file's --autotest suite.  Before the cache-dependent suites,
the required cache entries (moves + learnset) are fetched from PokeAPI if
they are not already present.  The cache suites are skipped only if the
network is unavailable and the data is not in the cache.

Usage:
  python run_tests.py           # run all tests (auto-warms cache as needed)
  python run_tests.py --offline # skip cache-dependent suites entirely
  python run_tests.py --quiet   # suppress per-suite output (summary only)
"""

import subprocess
import sys
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)   # so inline imports of pkm_cache / pkm_pokeapi work

# ── Cache item registry ───────────────────────────────────────────────────────
#
# Each entry describes one item that must be in the local cache before the
# cache-dependent test suites can run.
#
# key        — unique identifier used by SUITES to declare what they need
# label      — human-readable name shown in the warm-up section
# check()    — returns truthy if item already in cache, falsy if missing
# fetch()    — fetches + stores the item; raises on failure

def _cache_items():
    """
    Build and return the cache item definitions.
    Deferred import so the module is importable even if pkm_cache is not on path.
    """
    import pkm_cache   as _cache
    import pkm_pokeapi as _api

    def _check_move(name):
        return lambda: _cache.get_move(name) is not None

    def _fetch_move(slug, display):
        def _do():
            entries = _api.fetch_move(slug)
            _cache.upsert_move(display, entries)
        return _do

    def _check_learnset(variety_slug, game):
        return lambda: _cache.get_learnset(variety_slug, game) is not None

    def _fetch_learnset(variety_slug, form_name, game):
        def _do():
            result = _cache.get_learnset_or_fetch(variety_slug, form_name, game)
            if result is None:
                raise ConnectionError(f"fetch returned None for {variety_slug}/{game}")
        return _do

    return {
        "move:Flamethrower": {
            "label": "move  Flamethrower",
            "check": _check_move("Flamethrower"),
            "fetch": _fetch_move("flamethrower", "Flamethrower"),
        },
        "move:Earthquake": {
            "label": "move  Earthquake",
            "check": _check_move("Earthquake"),
            "fetch": _fetch_move("earthquake", "Earthquake"),
        },
        "learnset:charizard:Scarlet / Violet": {
            "label": "learnset  Charizard / Scarlet & Violet",
            "check": _check_learnset("charizard", "Scarlet / Violet"),
            "fetch": _fetch_learnset("charizard", "Charizard", "Scarlet / Violet"),
        },
        "type_roster:Fire": {
            "label": "type roster  Fire",
            "check": lambda: _cache.get_type_roster("Fire") is not None,
            "fetch": lambda: _cache.get_type_roster_or_fetch("Fire"),
        },
        "natures": {
            "label": "natures",
            "check": lambda: _cache.get_natures() is not None,
            "fetch": lambda: _cache.get_natures_or_fetch(),
        },
        "abilities_index": {
            "label": "abilities index",
            "check": lambda: _cache.get_abilities_index() is not None,
            "fetch": lambda: _cache.get_abilities_index_or_fetch(),
        },
    }


# ── Test suite registry ───────────────────────────────────────────────────────
#
# Each entry: (label, file, args, cache_keys)
#   cache_keys — list of _cache_items() keys that must exist before this suite.
#                Empty list = always run (offline suite).

SUITES = [
    ("matchup_calculator",       "matchup_calculator.py",  ["--autotest"],               []),
    ("pkm_cache",                "pkm_cache.py",            [],                            []),
    ("pkm_pokeapi",              "pkm_pokeapi.py",          ["--autotest"],               []),
    ("pkm_session",              "pkm_session.py",          ["--autotest"],               []),
    ("feat_moveset_data",        "feat_moveset_data.py",    ["--autotest"],               []),
    ("feat_moveset",             "feat_moveset.py",         ["--autotest"],               []),
    ("feat_move_lookup",         "feat_move_lookup.py",     ["--autotest"],               []),
    ("feat_movepool",            "feat_movepool.py",        ["--autotest"],               []),
    ("feat_type_browser",        "feat_type_browser.py",    ["--autotest"],               []),
    ("feat_nature_browser",      "feat_nature_browser.py",  ["--autotest"],               []),
    ("feat_ability_browser",     "feat_ability_browser.py", ["--autotest"],               []),
    ("feat_team_loader",         "feat_team_loader.py",     ["--autotest"],               []),
    ("feat_team_analysis",        "feat_team_analysis.py",   ["--autotest"],               []),
    ("feat_team_offense",         "feat_team_offense.py",    ["--autotest"],               []),
    ("feat_team_moveset",         "feat_team_moveset.py",    ["--autotest"],               []),
    # ── cache-dependent suites ────────────────────────────────────────────────
    ("feat_moveset (cache)",
        "feat_moveset.py",     ["--autotest", "--withcache"],
        ["learnset:charizard:Scarlet / Violet"]),
    ("feat_move_lookup (cache)",
        "feat_move_lookup.py", ["--autotest", "--withcache"],
        ["move:Flamethrower", "move:Earthquake"]),
    ("feat_movepool (cache)",
        "feat_movepool.py",    ["--autotest", "--withcache"],
        ["move:Flamethrower", "move:Earthquake"]),
    ("feat_type_browser (cache)",
        "feat_type_browser.py",["--autotest", "--withcache"],
        ["type_roster:Fire"]),
    ("feat_nature_browser (cache)",
        "feat_nature_browser.py", ["--autotest", "--withcache"],
        ["natures"]),
    ("feat_ability_browser (cache)",
        "feat_ability_browser.py", ["--autotest", "--withcache"],
        ["abilities_index"]),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

W = 60   # console width

def _banner(label):
    pad = max(0, W - len(label) - 4)
    print(f"\n{'─'*2}  {label}  {'─'*pad}")


def _extract_counts(output: str):
    """
    Parse pass/fail counts from a suite's stdout.
    Returns (passed, failed) ints, or (None, None) if unparseable.
    """
    lines = output.strip().splitlines()

    # Pass 1: lines that give both passed AND failed explicitly
    for line in reversed(lines):
        m = re.search(r"(\d+) tests:\s*(\d+) passed,\s*(\d+) failed", line)
        if m:
            return int(m.group(2)), int(m.group(3))
        m = re.search(r"(\d+) passed,\s*(\d+) failed", line)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"FAILED \((\d+)\)", line)
        if m:
            return None, int(m.group(1))

    # Pass 2: "All N tests passed" — assume 0 failures
    for line in reversed(lines):
        m = re.search(r"All(?: (\d+))? tests? passed", line)
        if m:
            return int(m.group(1)) if m.group(1) else None, 0

    # Pass 3: count tagged tokens as best-effort fallback
    n_pass = (len(re.findall(r"\[PASS\]",   output))
            + len(re.findall(r"\[OK\]",     output))
            + len(re.findall(r"^\s+PASS\s", output, re.MULTILINE))
            + len(re.findall(r"\s+OK\s*$",  output, re.MULTILINE)))
    n_fail = len(re.findall(r"\[FAIL\]|FAIL\s*\(", output))
    if n_pass or n_fail:
        return n_pass if n_pass else None, n_fail

    return None, None


def _ensure_test_cache(items_needed: set) -> dict:
    """
    Ensure every required cache item exists, fetching from PokeAPI if needed.

    Args:
        items_needed — set of item keys to prepare

    Returns dict: { key -> "cached" | "fetched" | "failed" }
    """
    try:
        all_items = _cache_items()
    except ImportError as e:
        print(f"  [warn] could not import cache modules: {e}")
        return {k: "failed" for k in items_needed}

    status = {}
    for key in sorted(items_needed):
        item  = all_items[key]
        label = item["label"]

        if item["check"]():
            print(f"  [cache]  {label}")
            status[key] = "cached"
            continue

        print(f"  [fetch]  {label} ...", end="", flush=True)
        try:
            import io, contextlib
            _buf = io.StringIO()
            with contextlib.redirect_stdout(_buf):
                item["fetch"]()
            print("  ok")
            status[key] = "fetched"
        except Exception as exc:
            print(f"  FAILED")
            print(f"           ({exc})")
            status[key] = "failed"

    return status


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    offline = "--offline" in sys.argv
    quiet   = "--quiet"   in sys.argv

    print()
    print("╔" + "═" * (W + 2) + "╗")
    print(f"║  {'Pokemon Toolkit — Test Runner':<{W}}║")
    mode = "offline only (--offline)" if offline else "offline + cache (auto-warm)"
    if quiet: mode += "  [quiet]"
    print(f"║  {'Mode: ' + mode:<{W}}║")
    print("╚" + "═" * (W + 2) + "╝")

    # ── Collect all cache keys needed across cache-dependent suites ───────────
    all_needed = set()
    for _, _, _, cache_keys in SUITES:
        all_needed.update(cache_keys)

    # ── Warm the cache (unless --offline) ─────────────────────────────────────
    cache_status = {}
    if all_needed and not offline:
        _banner("cache warm-up")
        cache_status = _ensure_test_cache(all_needed)

    # ── Run each suite ────────────────────────────────────────────────────────
    results = []   # (label, passed, failed, skip_reason, duration_s)

    for label, filename, args, cache_keys in SUITES:

        # Determine whether this suite can run
        if cache_keys:
            if offline:
                results.append((label, None, None, "skipped (--offline)", 0))
                continue
            failed_keys = [k for k in cache_keys if cache_status.get(k) == "failed"]
            if failed_keys:
                names = ", ".join(k.split(":")[-1] for k in failed_keys)
                results.append((label, None, None, f"skipped (fetch failed: {names})", 0))
                continue

        _banner(label)
        cmd = [sys.executable, os.path.join(HERE, filename)] + args

        t0      = time.monotonic()
        proc    = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        elapsed = time.monotonic() - t0

        output = proc.stdout + (proc.stderr or "")
        passed, failed = _extract_counts(output)
        if proc.returncode != 0 and (failed or 0) == 0:
            failed = 1

        if not quiet:
            print(output.rstrip())
        elif (failed or 0) > 0:   # in quiet mode, always show failure detail
            for ln in output.splitlines():
                if any(kw in ln for kw in ("FAIL", "Error", "Traceback", "assert")):
                    print(f"    {ln.strip()}")
        results.append((label, passed, failed, None, elapsed))

    # ── Summary table ─────────────────────────────────────────────────────────
    print()
    print("╔" + "═" * (W + 2) + "╗")
    print(f"║  {'SUMMARY':<{W}}║")
    print("╠" + "═" * (W + 2) + "╣")

    col_label = 30
    col_pass  =  8
    col_fail  =  8
    col_time  =  8

    hdr = (f"  {'Suite':<{col_label}}"
           f"{'Passed':>{col_pass}}"
           f"{'Failed':>{col_fail}}"
           f"{'Time':>{col_time}}")
    print(f"║{hdr:<{W+1}}║")
    print("╠" + "─" * (W + 2) + "╣")

    total_passed = 0
    total_failed = 0
    any_fail     = False

    for label, passed, failed, skip_reason, elapsed in results:
        if skip_reason:
            max_reason = W - col_label - 6   # "  " + label + "  — " + reason
            reason_str = skip_reason if len(skip_reason) <= max_reason else skip_reason[:max_reason-1] + "…"
            row = f"  {label:<{col_label}}  — {reason_str}"
            print(f"║{row:<{W+1}}║")
            continue

        p_str     = str(passed) if passed is not None else "?"
        f_str     = str(failed) if failed is not None else "?"
        t_str     = f"{elapsed:.1f}s"
        fail_flag = " ✗" if (failed or 0) > 0 else ""

        row = (f"  {label + fail_flag:<{col_label}}"
               f"{p_str:>{col_pass}}"
               f"{f_str:>{col_fail}}"
               f"{t_str:>{col_time}}")
        print(f"║{row:<{W+1}}║")

        if passed is not None: total_passed += passed
        if failed is not None: total_failed += failed
        if (failed or 0) > 0:  any_fail = True

    print("╠" + "─" * (W + 2) + "╣")
    total_row = (f"  {'TOTAL':<{col_label}}"
                 f"{total_passed:>{col_pass}}"
                 f"{total_failed:>{col_fail}}")
    print(f"║{total_row:<{W+1}}║")
    print("╚" + "═" * (W + 2) + "╝")

    print()
    if any_fail:
        print("  ✗  Some tests failed.\n")
        sys.exit(1)
    else:
        print("  ✓  All tests passed.\n")


if __name__ == "__main__":
    main()
