#!/usr/bin/env python3
"""
feat_team_analysis.py  Team defensive vulnerability analysis

Given a loaded team (up to 6 Pokemon), shows a unified type table with one
row per attacking type.

Entry points:
  run(team_ctx, game_ctx)   called from pokemain
  main()                    standalone
"""

import sys

try:
    import matchup_calculator as calc
    from feat_team_loader import team_slots, team_size, print_team
    from core_team import build_team_defense, build_unified_rows, gap_label, build_weakness_pairs, gap_pair_label
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Display helpers ───────────────────────────────────────────────────────────

_COL_TYPE   = 10   # type name column
_COL_CNT    =  2   # count sub-column (Wk / Res / Imm / Neu)
_COL_WNAMES = 30   # weak names sub-column
_COL_RNAMES = 28   # resist names sub-column
_COL_INAMES = 20   # immune names sub-column
_GAP_WIDTH  = 12   # gap label column

_NAME_ABBREV = 4   # characters kept from each Pokemon name


def _abbrev(name: str) -> str:
    """Truncate a Pokemon name to _NAME_ABBREV characters."""
    return name[:_NAME_ABBREV]


def _weak_tag(name: str, mult: float) -> str:
    """Abbreviate name; append (xN) suffix for x4 or higher."""
    short = _abbrev(name)
    return f"{short}(\u00d7{int(mult)})" if mult >= 4.0 else short


def _resist_tag(name: str, mult: float) -> str:
    """Abbreviate name; append (x0.25) suffix for double-resist."""
    short = _abbrev(name)
    return f"{short}(\u00d70.25)" if mult <= 0.25 else short


def _names_cell(names: list, width: int) -> str:
    """
    Format a list of name strings into a fixed-width cell.
    Truncates with '...' if the joined string is too long.
    Returns '-' if the list is empty.
    """
    if not names:
        return "-"
    joined = "  ".join(names)
    if len(joined) <= width:
        return joined
    # Truncate: fit as many names as possible then append ...
    result = ""
    for i, n in enumerate(names):
        candidate = (result + ("  " if result else "") + n)
        if len(candidate) + 3 <= width or i == 0:
            result = candidate
        else:
            result += "..."
            break
    return result


def _print_unified_table(rows: list, n_members: int) -> None:
    """Print the full unified type table."""
    # Header
    sep = (f"  {'-'*_COL_TYPE}"
           f"-+-{'-':>{_COL_CNT}}-{'-'*_COL_WNAMES}"
           f"-+-{'-':>{_COL_CNT}}-{'-'*_COL_RNAMES}"
           f"-+-{'-':>{_COL_CNT}}-{'-'*_COL_INAMES}"
           f"-+--{'-'*_COL_CNT}--{'-'*_GAP_WIDTH}")

    # Each merged column header spans: _COL_CNT + 2 + _COL_NAMES
    _W_SPAN = _COL_CNT + 2 + _COL_WNAMES   # 34
    _R_SPAN = _COL_CNT + 2 + _COL_RNAMES   # 32
    _I_SPAN = _COL_CNT + 2 + _COL_INAMES   # 24
    hdr = (f"  {'Type':<{_COL_TYPE}}"
           f" | {'Weakness':<{_W_SPAN}}"
           f" | {'Resistance':<{_R_SPAN}}"
           f" | {'Immunity':<{_I_SPAN}}"
           f" | {'Comments'}")
    print()
    print(hdr)
    print(sep)

    for r in rows:
        weak_names   = [_weak_tag(n, m)   for n, m in r["weak_members"]]
        resist_names = [_resist_tag(n, m) for n, m in r["resist_members"]]
        immune_names = [_abbrev(n) for n in r["immune_members"]]

        wk_cnt  = len(r["weak_members"])
        rs_cnt  = len(r["resist_members"])
        im_cnt  = len(r["immune_members"])
        neu_cnt = r["neutral_count"]
        cover   = rs_cnt + im_cnt

        wk_cell  = _names_cell(weak_names,   _COL_WNAMES)
        rs_cell  = _names_cell(resist_names, _COL_RNAMES)
        im_cell  = _names_cell(immune_names, _COL_INAMES)
        gap      = gap_label(wk_cnt, cover)

        line = (f"  {r['type']:<{_COL_TYPE}}"
                f" | {wk_cnt:>{_COL_CNT}}  {wk_cell:<{_COL_WNAMES}}"
                f" | {rs_cnt:>{_COL_CNT}}  {rs_cell:<{_COL_RNAMES}}"
                f" | {im_cnt:>{_COL_CNT}}  {im_cell:<{_COL_INAMES}}"
                f" | {gap}")
        print(line)


def _print_weakness_pairs(pairs: list) -> None:
    """Print the shared-weakness section for all qualifying pairs."""
    if not pairs:
        return
    # Dynamic name column: "Name A + Name B", capped at 26
    name_col = min(26, max(len(f"{p['name_a']} + {p['name_b']}") for p in pairs))
    sep_w    = name_col + 2 + 40

    print("  Shared weaknesses (pairs with \u2265 2 in common)")
    print("  " + "\u2500" * sep_w)
    for p in pairs:
        label    = f"{p['name_a']} + {p['name_b']}"
        types_str = "  ".join(p["shared_types"])
        count_str = f"({p['shared_count']} shared)"
        severity  = gap_pair_label(p["shared_count"])
        suffix    = f"  {severity}" if severity else ""
        print(f"  {label:<{name_col}}  {types_str:<34}{count_str}{suffix}")


# ── Main display ──────────────────────────────────────────────────────────────

def display_team_analysis(team_ctx: list, game_ctx: dict) -> None:
    era_key  = game_ctx["era_key"]
    game     = game_ctx["game"]
    filled   = team_size(team_ctx)

    if filled == 0:
        print("\n  Team is empty -- load some Pokemon first (press T).")
        return

    # ── Roster header ─────────────────────────────────────────────────────────
    print(f"\n  Team defensive analysis  |  {game}")
    print("  " + "=" * 56)
    for _idx, pkm in team_slots(team_ctx):
        dual = (f"{pkm['type1']} / {pkm['type2']}"
                if pkm["type2"] != "None" else pkm["type1"])
        print(f"  {pkm['form_name']:<24}  {dual}")
    print("  " + "=" * 56)

    # ── Unified table ─────────────────────────────────────────────────────────
    team_def = build_team_defense(team_ctx, era_key)
    rows     = build_unified_rows(team_def, era_key)

    print("\n  Weakness / Resistance / Immunity: count + member names")
    print("  (x4) suffix on weak member  |  (x0.25) suffix on double-resist  |  Comments = gap classification")
    _print_unified_table(rows, filled)

    # ── Gap summary ───────────────────────────────────────────────────────────
    criticals = [r["type"] for r in rows
                 if gap_label(len(r["weak_members"]),
                              len(r["resist_members"]) + len(r["immune_members"])) == "!! CRITICAL"]
    majors    = [r["type"] for r in rows
                 if gap_label(len(r["weak_members"]),
                              len(r["resist_members"]) + len(r["immune_members"])) == "!  MAJOR"]
    minors    = [r["type"] for r in rows
                 if gap_label(len(r["weak_members"]),
                              len(r["resist_members"]) + len(r["immune_members"])) == ".  MINOR"]

    if criticals or majors or minors:
        print()
        if criticals:
            print(f"  !! CRITICAL gaps : {' / '.join(criticals)}")
        if majors:
            print(f"  !  MAJOR gaps    : {' / '.join(majors)}")
        if minors:
            print(f"  .  MINOR gaps    : {' / '.join(minors)}")
    else:
        print("\n  No significant gaps detected.")

    # ── Weakness overlap heatmap ──────────────────────────────────────────────
    pairs = build_weakness_pairs(team_ctx, era_key)
    if pairs:
        print()
        _print_weakness_pairs(pairs)


# ── Entry points ──────────────────────────────────────────────────────────────

def run(team_ctx: list, game_ctx: dict) -> None:
    """Called from pokemain."""
    display_team_analysis(team_ctx, game_ctx)
    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("+===========================================+")
    print("|     Team Defensive Analysis               |")
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

    display_team_analysis(team_ctx, game_ctx)
    input("\n  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import io, contextlib
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_analysis.py — self-test\n")

    # Keep only the tests that are purely display or I/O.
    # Most logic tests are now in core_team.py.

    # ── Smoke test for display functions ─────────────────────────────────────
    def _pkm(name, t1, t2="None"):
        return {"form_name": name, "type1": t1, "type2": t2}

    charizard = _pkm("Charizard", "Fire", "Flying")
    team1 = [charizard, None, None, None, None, None]
    game_ctx = {"era_key": "era3", "game": "Test"}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        display_team_analysis(team1, game_ctx)
    out = buf.getvalue()
    if "Rock" in out and "Charizard" in out:
        ok("display_team_analysis: output contains expected info")
    else:
        fail("display_team_analysis smoke", out[:200])

    # ── _abbrev, _weak_tag, _resist_tag, _names_cell ─────────────────────────
    if _abbrev("Charizard") == "Char":
        ok("_abbrev: works")
    else:
        fail("_abbrev")

    if _weak_tag("Charizard", 4.0) == "Char(\u00d74)":
        ok("_weak_tag: x4 tag")
    else:
        fail("_weak_tag")

    if _resist_tag("Venusaur", 0.25) == "Venu(\u00d70.25)":
        ok("_resist_tag: x0.25 tag")
    else:
        fail("_resist_tag")

    if _names_cell(["Charizard", "Blastoise"], 20) == "Charizard  Blastoise":
        ok("_names_cell: short list")
    else:
        fail("_names_cell short")

    long_names = ["Charizard", "Blastoise", "Venusaur", "Pikachu"]
    truncated = _names_cell(long_names, 20)
    if len(truncated) <= 20 and "..." in truncated:
        ok("_names_cell: truncation")
    else:
        fail("_names_cell truncation", truncated)

    # ── _print_weakness_pairs (stdout capture) ───────────────────────────────
    pairs = [
        {"name_a": "Charizard", "name_b": "Lapras",
         "shared_types": ["Electric", "Rock"], "shared_count": 2},
        {"name_a": "Charizard", "name_b": "Butterfree",
         "shared_types": ["Electric", "Flying", "Rock"], "shared_count": 3},
    ]
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        _print_weakness_pairs(pairs)
    out2 = buf2.getvalue()
    if "Charizard + Lapras" in out2 and "!! CRITICAL" in out2:
        ok("_print_weakness_pairs: works")
    else:
        fail("_print_weakness_pairs", out2[:200])

    print()
    total = 5  # number of tests in this file after move
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