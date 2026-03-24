#!/usr/bin/env python3
"""
feat_team_offense.py  Team offensive coverage analysis

For each attacking type in the era, shows how many team members can hit that
type super-effectively (x2 or x4) using their own types.

Each member is shown with the best scored move for each hitting type:
  Char:Fire Blast, Wing Attack   (both Fire and Flying hit SE, one move each)
  Geng:Sludge Bomb               (only Poison hits SE)
When no move data is available the type-letter fallback is used: Char(F,F).

Entry points:
  run(team_ctx, game_ctx)   called from pokemain (key O)
  main()                    standalone
"""

import sys

try:
    import matchup_calculator as calc
    from feat_team_loader import team_slots, team_size
    from core_team import build_team_offense, build_offense_rows, coverage_gaps
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Core logic (now in core_team) ─────────────────────────────────────────────

# Functions build_team_offense, build_offense_rows, coverage_gaps imported.
# The old hitting_types is now in core_team as well, but not needed directly here.

# ── Move lookup helpers ───────────────────────────────────────────────────────

def _best_move_for_type(damage_pool: list, target_type: str):
    """
    Scan the scored damage_pool (sorted desc by score) for the highest-scored
    move whose type matches target_type.

    Pure logic — pool must be pre-built by the caller.
    Returns (move_name, score) or None if no move of that type is found.
    """
    for row in damage_pool:
        if row["type"] == target_type:
            return (row["name"], row["score"])
    return None


def _build_member_pools(team_ctx: list, game_ctx: dict,
                        hitter_names: set,
                        pool_cache: dict | None = None) -> dict:
    """
    For each team member whose form_name is in hitter_names, build the scored
    damage pool via feat_moveset_data.build_candidate_pool().

    pool_cache — optional session-level dict keyed by (variety_slug, game_slug).
                 When provided, pools already in the cache are reused without
                 re-scoring.  New pools are stored back into the dict.
                 Pass None (default) for the original single-call behaviour.

    May trigger learnset and move-detail fetches from PokeAPI (shows progress).
    Returns {form_name: damage_pool_list}.
    """
    import feat_moveset_data as msd

    game_slug = game_ctx.get("game_slug", game_ctx["game"])
    pools = {}
    for _idx, pkm in team_slots(team_ctx):
        if pkm["form_name"] not in hitter_names:
            continue
        cache_key = (pkm["variety_slug"], game_slug)
        if pool_cache is not None and cache_key in pool_cache:
            pools[pkm["form_name"]] = pool_cache[cache_key]
        else:
            pool = msd.build_candidate_pool(pkm, game_ctx)
            damage = pool["damage"]
            if pool_cache is not None:
                pool_cache[cache_key] = damage
            pools[pkm["form_name"]] = damage
    return pools


def _enrich_rows_with_moves(rows: list, member_pools: dict) -> None:
    """
    For each hitter entry in each row, attach 'best_moves': a list of the
    best scored move name per hitting type (aligned with hitting_types order).
    Elements are move name strings or None when no move of that type is found.

    Modifies rows in place.
    """
    for r in rows:
        for h in r["hitters"]:
            fname    = h["form_name"]
            dmg_pool = member_pools.get(fname, [])
            best_moves = []
            for htype in h.get("hitting_types", []):
                entry = _best_move_for_type(dmg_pool, htype)
                best_moves.append(entry[0] if entry else None)
            h["best_moves"] = best_moves


# ── Display helpers ───────────────────────────────────────────────────────────

_COL_TYPE    = 10
_COL_HITTERS = 70   # wide enough for ~3 hitters with move names
_NAME_LEN    = 4    # same as feat_team_analysis._abbrev
_MOVE_NAME_LEN = 12  # max characters of move name shown in hitter cell


def _abbrev(name: str) -> str:
    return name[:_NAME_LEN]


def _hitter_tag(form_name: str, hitting_types: list,
                best_moves: list = None) -> str:
    """
    Format a hitter entry.

    With move data available:
      Abbrev:Move1[, Move2]
      e.g.  Char:Flamethrower, Fly   (Fire → Flamethrower, Flying → Fly)
            Geng:Sludge Bomb         (Poison only)
      If a move is missing for one type, the type's first letter is used instead:
      e.g.  Char:Flamethrower, F     (no Flying-type move found)

    Fallback (no move data):
      Abbrev(L,L)
      e.g.  Char(F,F)   Geng(P)
    """
    short = _abbrev(form_name)

    has_moves = best_moves and any(m is not None for m in best_moves)
    if not has_moves:
        letters = [t[0] for t in hitting_types]
        return f"{short}({','.join(letters)})"

    parts = []
    for i, htype in enumerate(hitting_types):
        move = best_moves[i] if i < len(best_moves) else None
        parts.append(move[:_MOVE_NAME_LEN] if move else htype[0])
    return f"{short}:{', '.join(parts)}"


def _hitters_cell(hitters: list) -> str:
    """Space-separated list of tagged hitter names, or '-' if empty."""
    if not hitters:
        return "-"
    return "  ".join(
        _hitter_tag(h["form_name"], h["hitting_types"], h.get("best_moves"))
        for h in hitters
    )


def _print_offense_table(rows: list) -> None:
    hdr = (f"  {'Type':<{_COL_TYPE}}"
           f" | {'Who hits SE  (:moves per hitting type, letter=fallback)':<{_COL_HITTERS}}"
           f" | Comments")
    sep = (f"  {'-'*_COL_TYPE}"
           f"-+-{'-'*_COL_HITTERS}"
           f"-+-{'-'*10}")
    print()
    print(hdr)
    print(sep)
    for r in rows:
        cell    = _hitters_cell(r["hitters"])
        comment = "GAP" if not r["hitters"] else ""
        print(f"  {r['type']:<{_COL_TYPE}}"
              f" | {cell:<{_COL_HITTERS}}"
              f" | {comment}")


def display_team_offense(team_ctx: list, game_ctx: dict,
                         pool_cache: dict | None = None) -> None:
    era_key = game_ctx["era_key"]
    game    = game_ctx["game"]
    filled  = team_size(team_ctx)

    if filled == 0:
        print("\n  Team is empty -- load some Pokemon first (press T).")
        return

    # ── Roster header ─────────────────────────────────────────────────────────
    print(f"\n  Team offensive coverage  |  {game}")
    print("  " + "=" * 56)
    for _idx, pkm in team_slots(team_ctx):
        dual = (f"{pkm['type1']} / {pkm['type2']}"
                if pkm["type2"] != "None" else pkm["type1"])
        print(f"  {pkm['form_name']:<24}  {dual}")
    print("  " + "=" * 56)

    # ── Build type-based offense table (now in core_team) ─────────────────────
    team_off = build_team_offense(team_ctx, era_key)
    rows     = build_offense_rows(team_off, era_key)

    # ── Enrich hitters with best scored move per hitting type ──────────────────
    hitter_names = {
        h["form_name"]
        for hlist in team_off.values()
        for h in hlist
    }
    if hitter_names:
        # Show loading message only when at least one pool will be computed
        game_slug = game_ctx.get("game_slug", game_ctx["game"])
        slug_by_name = {pkm["form_name"]: pkm["variety_slug"]
                        for _, pkm in team_slots(team_ctx)}
        needs_fetch = pool_cache is None or any(
            (slug_by_name.get(h), game_slug) not in pool_cache
            for h in hitter_names
        )
        if needs_fetch:
            print(f"\n  Loading move data for {len(hitter_names)} member(s)...")
        member_pools = _build_member_pools(team_ctx, game_ctx, hitter_names,
                                           pool_cache=pool_cache)
        _enrich_rows_with_moves(rows, member_pools)

    # ── Table ─────────────────────────────────────────────────────────────────
    gaps = coverage_gaps(rows)

    print("\n  Abbrev:Move1[, Move2] = best scored move per hitting type"
          "  |  letter = type fallback")
    _print_offense_table(rows)

    # ── Summary ───────────────────────────────────────────────────────────────
    _, valid_types, _ = calc.CHARTS[era_key]
    total    = len(valid_types)
    covered  = total - len(gaps)
    print(f"\n  Coverage: {covered} / {total} types", end="")
    if gaps:
        print(f"  |  Gaps: {' / '.join(gaps)}")
    else:
        print("  |  Full coverage!")


# ── Entry points ──────────────────────────────────────────────────────────────

def run(team_ctx: list, game_ctx: dict,
        pool_cache: dict | None = None) -> None:
    """Called from pokemain."""
    display_team_offense(team_ctx, game_ctx, pool_cache=pool_cache)
    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("+===========================================+")
    print("|     Team Offensive Coverage               |")
    print("+===========================================+")

    try:
        from pkm_session import select_game, select_pokemon
        from feat_team_loader import new_team, add_to_team, TeamFullError
    except ModuleNotFoundError as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)

    game_ctx = select_game()
    if game_ctx is None:
        sys.exit(0)

    team_ctx = new_team()
    print("\n  Add up to 6 Pokemon (blank name to stop).")
    for _ in range(6):
        pkm = select_pokemon(game_ctx=game_ctx)
        if pkm is None:
            break
        try:
            team_ctx, slot = add_to_team(team_ctx, pkm)
            print(f"  Added to slot {slot + 1}.")
        except TeamFullError:
            break

    display_team_offense(team_ctx, game_ctx)
    input("\n  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_offense.py — self-test\n")

    # Most logic is in core_team; keep only display tests.

    # ── _hitter_tag ───────────────────────────────────────────────────────────
    # Fallback format when no moves available
    tag = _hitter_tag("Charizard", ["Fire", "Flying"])
    if tag == "Char(F,F)":
        ok("_hitter_tag: no moves, dual types -> fallback Char(F,F)")
    else:
        fail("_hitter_tag no-move dual", repr(tag))

    tag = _hitter_tag("Gengar", ["Poison"])
    if tag == "Geng(P)":
        ok("_hitter_tag: no moves, single type -> fallback Geng(P)")
    else:
        fail("_hitter_tag no-move single", repr(tag))

    # Enriched format with moves
    tag = _hitter_tag("Charizard", ["Fire", "Flying"], ["Flamethrower", "Wing Attack"])
    if tag == "Char:Flamethrower, Wing Attack":
        ok("_hitter_tag: dual types, both moves -> Char:Flamethrower, Wing Attack")
    else:
        fail("_hitter_tag dual with moves", repr(tag))

    tag = _hitter_tag("Blastoise", ["Water"], ["Surf"])
    if tag == "Blas:Surf":
        ok("_hitter_tag: single type with move -> Blas:Surf")
    else:
        fail("_hitter_tag single with move", repr(tag))

    tag = _hitter_tag("Charizard", ["Fire", "Flying"], ["Flamethrower", None])
    if tag == "Char:Flamethrower, F":
        ok("_hitter_tag: dual types, one move missing -> type letter fallback")
    else:
        fail("_hitter_tag partial moves", repr(tag))

    # Move name truncation
    long_name = "AVeryLongMoveName"
    tag = _hitter_tag("Charizard", ["Fire"], [long_name])
    if tag == f"Char:{long_name[:_MOVE_NAME_LEN]}":
        ok(f"_hitter_tag: move name truncated to {_MOVE_NAME_LEN} chars")
    else:
        fail("_hitter_tag truncation", repr(tag))

    # ── _hitters_cell ─────────────────────────────────────────────────────────
    if _hitters_cell([]) == "-":
        ok("_hitters_cell: empty list -> dash")
    else:
        fail("_hitters_cell empty")

    hitters_no_move = [
        {"form_name": "Charizard", "hitting_types": ["Fire", "Flying"],
         "hitting_letters": ["F", "F"]},
        {"form_name": "Venusaur",  "hitting_types": ["Poison"],
         "hitting_letters": ["P"]},
    ]
    cell = _hitters_cell(hitters_no_move)
    if "Char(F,F)" in cell and "Venu(P)" in cell:
        ok("_hitters_cell: no moves -> fallback tags in cell")
    else:
        fail("_hitters_cell no-move tags", repr(cell))

    hitters_with_moves = [
        {"form_name": "Charizard", "hitting_types": ["Fire", "Flying"],
         "hitting_letters": ["F", "F"],
         "best_moves": ["Flamethrower", "Wing Attack"]},
        {"form_name": "Gengar",    "hitting_types": ["Poison"],
         "hitting_letters": ["P"],
         "best_moves": ["Sludge Bomb"]},
    ]
    cell = _hitters_cell(hitters_with_moves)
    if "Flamethrower" in cell and "Wing Attack" in cell and "Sludge Bomb" in cell:
        ok("_hitters_cell: with best_moves -> all move names present")
    else:
        fail("_hitters_cell with moves", repr(cell))

    # ── _print_offense_table (smoke test) ────────────────────────────────────
    import io, contextlib
    rows = [{"type": "Fire", "hitters": []}]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_offense_table(rows)
    out = buf.getvalue()
    if "Fire" in out and "GAP" in out:
        ok("_print_offense_table: works")
    else:
        fail("_print_offense_table smoke", out[:100])

    print()
    total = 9  # number of tests in this file after move
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