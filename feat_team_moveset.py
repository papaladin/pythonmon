#!/usr/bin/env python3
"""
feat_team_moveset.py  Team moveset synergy

Orchestrates team-level moveset recommendations by running the single-Pokemon
scoring engine across all team members and aggregating results into a team
offensive coverage summary.

Accessible via menu key S (needs team + game).

Public API:
  recommend_team_movesets(team_ctx, game_ctx, mode, pool_cache, ui) -> list[dict]
  run(team_ctx, game_ctx, pool_cache, ui)   called from pokemain (key S)
  main()                    standalone
"""

import sys

try:
    from feat_team_loader import team_slots, team_size
    from feat_moveset_data import build_candidate_pool
    from core_move import select_combo
    import matchup_calculator as calc
    from core_team import (weakness_types, se_types, build_offensive_coverage,
                           empty_member_result, format_weak_line,
                           format_move_pair, format_se_line)
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Constants ──────────────────────────────────────────────────────────────

_MODES = {
    "c": "coverage",
    "u": "counter",
    "s": "stab",
}

_COL_MOVE   = 22   # left move-name column width (matches feat_moveset.py)
_BLOCK_SEP  = 56   # width of ═ / ─ separators


# ── Core logic ─────────────────────────────────────────────────────────────

async def recommend_team_movesets(team_ctx: list, game_ctx: dict, mode: str,
                                  pool_cache: dict | None = None,
                                  ui=None) -> list:
    """
    Compute a recommended moveset for each filled team slot.

    Calls build_candidate_pool + select_combo from feat_moveset_data for each
    member — no scoring logic is duplicated here.  If a member's pool is empty
    (cache miss / network unavailable), the result is correctly shaped with
    empty lists rather than crashing.

    pool_cache — optional session-level dict keyed by (variety_slug, game_slug).
                 When provided, already-computed damage pools are reused.
                 New pools are stored back into the dict.

    mode — "coverage" | "counter" | "stab"

    Returns list[dict], one entry per filled slot:
      { form_name, moves (list[dict]), weakness_types (list[str]),
        se_types (list[str]) }
    """
    era_key   = game_ctx["era_key"]
    game_slug = game_ctx.get("game_slug", game_ctx["game"])
    results   = []

    for _idx, pkm in team_slots(team_ctx):
        cache_key = (pkm["variety_slug"], game_slug)
        if pool_cache is not None and cache_key in pool_cache:
            damage_pool = pool_cache[cache_key]
        else:
            pool        = await build_candidate_pool(pkm, game_ctx, ui=ui)
            damage_pool = pool["damage"]
            if pool_cache is not None:
                pool_cache[cache_key] = damage_pool

        weak_ty = weakness_types(pkm, era_key)
        combo   = select_combo(damage_pool, mode, weak_ty, era_key)  # no await
        se      = se_types(combo, era_key)

        results.append({
            "form_name":      pkm["form_name"],
            "types":          pkm.get("types", []),
            "moves":          combo,
            "weakness_types": weak_ty,
            "se_types":       se,
        })

    return results


# ── Display functions ──────────────────────────────────────────────────────

async def _display_member_block(ui, result: dict, era_key: str) -> None:
    """Print the 5-line compact block for one team member."""
    form_name = result["form_name"]
    types_str = " / ".join(result["types"]) if result["types"] else "?"

    # Pad move list to exactly 4 slots (None = empty)
    names = [m["name"] for m in result["moves"]]
    names += [None] * (4 - len(names))

    await ui.print_output(f"  {form_name}  [{types_str}]")
    await ui.print_output(f"  {format_weak_line(result['weakness_types'])}")
    await ui.print_output(f"  {format_move_pair(names[0], names[1])}")
    await ui.print_output(f"  {format_move_pair(names[2], names[3])}")
    await ui.print_output(f"  {format_se_line(result['se_types'], era_key)}")


async def _display_coverage_summary(ui, coverage: dict) -> None:
    """
    Print the team offensive coverage summary block.

    Always shown:  Covered line (N / total types hit SE)
    Shown if any:  Gaps line
    Shown if any:  Overlap line (types covered by ≥3 members)
    """
    total   = coverage["total_types"]
    covered = coverage["covered"]
    gaps    = coverage["gaps"]
    overlap = coverage["overlap"]

    await ui.print_output("  ── Team coverage " + "─" * (_BLOCK_SEP - 17))
    await ui.print_output(f"  Covered:  {len(covered)} / {total} types hit SE")

    if gaps:
        await ui.print_output("  Gaps:     " + "  ".join(gaps))
    else:
        await ui.print_output("  Full coverage!")

    if overlap:
        parts = [f"{t} ({n})" for t, n in overlap]
        await ui.print_output("  Overlap:  " + "  ".join(parts))


async def display_team_movesets(ui, results: list, game_ctx: dict, mode: str) -> None:
    """
    Print the full team moveset synergy screen.

    One compact block per filled slot, framed by ═ separators,
    followed by the team offensive coverage summary.
    """
    era_key = game_ctx["era_key"]
    game    = game_ctx["game"]

    await ui.print_output(f"\n  Team moveset synergy  |  {mode}  |  {game}")
    await ui.print_output("  " + "═" * _BLOCK_SEP)

    for i, result in enumerate(results):
        if i > 0:
            await ui.print_output("  " + "─" * _BLOCK_SEP)
        await _display_member_block(ui, result, era_key)

    await ui.print_output("  " + "═" * _BLOCK_SEP)

    coverage = build_offensive_coverage(results, era_key)
    await _display_coverage_summary(ui, coverage)
    await ui.print_output("  " + "═" * _BLOCK_SEP)


# ── Interactive helpers ────────────────────────────────────────────────────

async def _mode_prompt(ui) -> str:
    """Interactive mode selector. Returns one of the _MODES values."""
    while True:
        await ui.print_output("\n  Select mode:")
        await ui.print_output("    (C)overage")
        await ui.print_output("    co(U)nter")
        await ui.print_output("    (S)TAB")
        choice = (await ui.input_prompt("  Mode: ")).strip().lower()
        if choice in _MODES:
            return _MODES[choice]
        await ui.print_output("  Invalid choice — press C, U or S.")


# ── Entry points ───────────────────────────────────────────────────────────

async def run(team_ctx: list, game_ctx: dict,
              pool_cache: dict | None = None,
              ui=None) -> None:
    """Menu entry point for key S — Team Moveset Synergy."""
    if ui is None:
        # Fallback dummy UI for standalone
        from ui_dummy import DummyUI
        ui = DummyUI()
        
    if team_size(team_ctx) == 0:
        await ui.print_output("\n  Team is empty — load some Pokémon first (press T).")
        return

    mode = await _mode_prompt(ui)
    n    = team_size(team_ctx)
    await ui.print_output(f"\n  Computing movesets for {n} member(s)...")
    results = await recommend_team_movesets(team_ctx, game_ctx, mode,
                                            pool_cache=pool_cache, ui=ui)
    await display_team_movesets(ui, results, game_ctx, mode)

    await ui.input_prompt("\n  Press Enter to return to the main menu...")


def main() -> None:
    # Dummy UI for standalone
    import builtins
    import asyncio

    class DummyUI:
        async def print_output(self, text, end="\n"): builtins.print(text, end=end)
        async def input_prompt(self, prompt): return builtins.input(prompt)
        async def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
    ui = DummyUI()

    asyncio.run(ui.print_output(""))
    asyncio.run(ui.print_output("  This module is not usable standalone."))
    asyncio.run(ui.print_output("  Launch from pokemain.py instead."))
    asyncio.run(ui.print_output(""))
    asyncio.run(ui.input_prompt("  Press Enter to exit..."))


# ── Self-tests (updated to async) ─────────────────────────────────────────────

def _run_tests():
    errors = []

    def ok(label):
        print(f"  [OK]   {label}")

    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_moveset.py — self-test\n")

    # Most logic is now in core_team; we only test the wrapper and display.

    # ── recommend_team_movesets (mock pool) ─────────────────────────────────
    async def _mock_pool(pkm_ctx, game_ctx, ui=None):
        return {"damage": [], "status": [], "skipped": 0}

    # Synchronous mock for select_combo (real function is sync)
    def _mock_combo(damage_pool, mode, weak_types, era_key, locked=None):
        return []

    import sys as _sys
    _this = _sys.modules[__name__]
    _orig_build = _this.build_candidate_pool
    _orig_combo = _this.select_combo
    _this.build_candidate_pool = _mock_pool
    _this.select_combo = _mock_combo

    team_ctx = [{"form_name": "Charizard", "type1": "Fire", "type2": "Flying",
                 "variety_slug": "charizard", "types": ["Fire","Flying"]},
                None, None, None, None, None]
    game_ctx = {"era_key": "era3", "game": "Test", "game_slug": "test"}

    try:
        # Use a dummy UI for the test to avoid printing
        class DummyUI:
            async def print_output(self, text): pass
            async def input_prompt(self, prompt): return ""
            async def confirm(self, prompt): return False
        dummy = DummyUI()
        import asyncio
        results = asyncio.run(recommend_team_movesets(team_ctx, game_ctx, "coverage", ui=dummy))
        if len(results) == 1 and "form_name" in results[0]:
            ok("recommend_team_movesets: returns list of results")
        else:
            fail("recommend_team_movesets basic", str(results))
    finally:
        _this.build_candidate_pool = _orig_build
        _this.select_combo = _orig_combo

    # ── display_team_movesets (stdout capture) ─────────────────────────────
    import io, contextlib
    fake_result = {
        "form_name": "Charizard",
        "types": ["Fire","Flying"],
        "moves": [],
        "weakness_types": ["Rock","Water","Electric"],
        "se_types": ["Grass","Bug","Steel"],
    }
    class DummyUI2:
        def __init__(self):
            self.buf = io.StringIO()
        async def print_output(self, text):
            self.buf.write(text + "\n")
        async def input_prompt(self, prompt):
            return ""
        async def confirm(self, prompt):
            return False
    dummy2 = DummyUI2()
    asyncio.run(display_team_movesets(dummy2, [fake_result], game_ctx, "coverage"))
    out = dummy2.buf.getvalue()
    if "Charizard" in out and "Weak" in out and "SE" in out:
        ok("display_team_movesets: output contains expected elements")
    else:
        fail("display_team_movesets smoke", out[:200])

    print()
    total = 2
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