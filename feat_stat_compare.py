#!/usr/bin/env python3
"""
feat_stat_compare.py  Side-by-side base stat comparison

Displays the base stats of two Pokemon side by side, with bars and
winner markers.  The first Pokemon is the currently loaded one;
the second is selected interactively via select_pokemon().

No new API data — both base_stats dicts come from the pokemon cache.

Entry points:
  run(pkm_ctx, game_ctx)   called from pokemain (key C)
  main()                   standalone
"""

import sys

try:
    from pkm_session import select_game, select_pokemon, print_session_header
    from core_stat import stat_bar, total_stats, infer_role, infer_speed_tier, compare_stats
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Constants ─────────────────────────────────────────────────────────────────

_COL_LABEL  =  4   # "HP  " / "Spe "
_COL_VAL    =  3   # "255" right-aligned
_SEP        = "  "  # separator between left and right halves
_W = 56            # inner separator width


def _type_str(pkm_ctx: dict) -> str:
    t1 = pkm_ctx.get("type1", "?")
    t2 = pkm_ctx.get("type2", "None")
    return f"{t1} / {t2}" if t2 != "None" else t1


def display_comparison(pkm_a: dict, pkm_b: dict, game_ctx: dict) -> None:
    """
    Print a side-by-side base stat comparison for two Pokemon.

    Each stat row:
      HP    78  [████████··········]  ★    108  [█████████████·····]
    ★ = higher value  •  = tied
    """
    game = game_ctx["game"] if game_ctx else "—"
    name_a = pkm_a["form_name"]
    name_b = pkm_b["form_name"]
    type_a = _type_str(pkm_a)
    type_b = _type_str(pkm_b)

    # Each stat row layout:
    # "  LABEL  VAL  [BAR]  MARK    VAL  [BAR]  MARK"
    # Left half width = _COL_LABEL + 2 + _COL_VAL + 2 + bar_len + 2 + 1 + 4
    _bar_len   = 18 + 2   # "[" + fills + "]"
    _left_w    = _COL_LABEL + 2 + _COL_VAL + 2 + _bar_len + 2 + 1 + 4

    name_a_str = f"{name_a}  [{type_a}]"
    name_b_str = f"{name_b}  [{type_b}]"

    print(f"\n  Stat comparison  |  {game}")
    print("  " + "═" * _W)
    print(f"  {name_a_str:<{_left_w}}{name_b_str}")
    print("  " + "═" * _W)

    rows = compare_stats(pkm_a.get("base_stats", {}),
                         pkm_b.get("base_stats", {}))

    for r in rows:
        marker_a = "★" if r["winner"] == "a" else ("•" if r["winner"] == "tie" else " ")
        marker_b = "★" if r["winner"] == "b" else ("•" if r["winner"] == "tie" else " ")
        bar_a = stat_bar(r["val_a"])
        bar_b = stat_bar(r["val_b"])
        print(
            f"  {r['label']:<{_COL_LABEL}}"
            f"  {r['val_a']:>{_COL_VAL}}  {bar_a}  {marker_a}"
            f"    "
            f"{r['val_b']:>{_COL_VAL}}  {bar_b}  {marker_b}"
        )

    print("  " + "─" * _W)
    tot_a = total_stats(pkm_a.get("base_stats", {}))
    tot_b = total_stats(pkm_b.get("base_stats", {}))
    mark_a = "★" if tot_a > tot_b else ("•" if tot_a == tot_b else " ")
    mark_b = "★" if tot_b > tot_a else ("•" if tot_a == tot_b else " ")
    bar_pad = " " * 20   # align totals under bars
    print(
        f"  {'Total':<{_COL_LABEL}}"
        f"  {tot_a:>{_COL_VAL}}  {bar_pad}  {mark_a}"
        f"    "
        f"{tot_b:>{_COL_VAL}}  {bar_pad}  {mark_b}"
    )
    bs_a = pkm_a.get("base_stats", {})
    bs_b = pkm_b.get("base_stats", {})
    label_a = f"{infer_role(bs_a).capitalize()} / {infer_speed_tier(bs_a).capitalize()}"
    label_b = f"{infer_role(bs_b).capitalize()} / {infer_speed_tier(bs_b).capitalize()}"
    print(f"  {'Role':<{_COL_LABEL}}  {label_a:<{_left_w}}{label_b}")
    print("  " + "═" * _W)
    print("  ★ = higher   • = tied")


# ── Entry points ──────────────────────────────────────────────────────────────

def run(pkm_ctx: dict, game_ctx: dict) -> None:
    """Called from pokemain (key C). Prompts for the second Pokemon."""
    print(f"\n  Comparing {pkm_ctx['form_name']} with...")
    pkm_b = select_pokemon(game_ctx=game_ctx)
    if pkm_b is None:
        print("  No Pokemon selected.")
        return

    display_comparison(pkm_ctx, pkm_b, game_ctx)
    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("╔══════════════════════════════════════════╗")
    print("║         Stat Comparison                  ║")
    print("╚══════════════════════════════════════════╝")

    game_ctx = select_game()
    if game_ctx is None:
        sys.exit(0)

    print("\n  First Pokemon:")
    pkm_a = select_pokemon(game_ctx=game_ctx)
    if pkm_a is None:
        sys.exit(0)

    print("\n  Second Pokemon:")
    pkm_b = select_pokemon(game_ctx=game_ctx)
    if pkm_b is None:
        sys.exit(0)

    display_comparison(pkm_a, pkm_b, game_ctx)
    input("\n  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import io, contextlib
    errors = []
    def ok(label):  print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_stat_compare.py — self-test\n")

    # ── display_comparison (stdout capture) ───────────────────────────────────

    stats_a = {"hp": 108, "attack": 130, "defense": 95,
               "special-attack": 80, "special-defense": 85, "speed": 102}
    stats_b = {"hp": 78, "attack": 84, "defense": 78,
               "special-attack": 109, "special-defense": 85, "speed": 100}
    pkm_a = {"form_name": "Garchomp", "type1": "Dragon", "type2": "Ground",
             "base_stats": stats_a}
    pkm_b = {"form_name": "Charizard", "type1": "Fire", "type2": "Flying",
             "base_stats": stats_b}
    game_ctx = {"game": "Scarlet / Violet", "era_key": "era3",
                "game_gen": 9, "game_slug": "scarlet-violet"}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        display_comparison(pkm_a, pkm_b, game_ctx)
    out = buf.getvalue()

    if "Garchomp" in out and "Charizard" in out:
        ok("display_comparison: names present")
    else:
        fail("display_comparison names", out[:80])

    if "Total" in out and "Role" in out:
        ok("display_comparison: Total and Role lines present")
    else:
        fail("display_comparison lines", out[-200:])

    # Graceful on missing stats
    pkm_empty = {"form_name": "Unknown", "type1": "Normal", "type2": "None",
                 "base_stats": {}}
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        display_comparison(pkm_empty, pkm_empty, game_ctx)
    out2 = buf2.getvalue()
    if "Total" in out2:
        ok("display_comparison: no crash on empty base_stats")
    else:
        fail("display_comparison empty stats", out2[:80])

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