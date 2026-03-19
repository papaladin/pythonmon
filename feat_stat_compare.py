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
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Constants ─────────────────────────────────────────────────────────────────

_STAT_KEYS = [
    ("hp",              "HP"),
    ("attack",          "Atk"),
    ("defense",         "Def"),
    ("special-attack",  "SpA"),
    ("special-defense", "SpD"),
    ("speed",           "Spe"),
]
_BAR_MAX    = 255   # maximum possible base stat
_BAR_WIDTH  = 18    # visual bar width in chars (shorter than quick-view to fit two)
_COL_LABEL  =  4    # "HP  " / "Spe "
_COL_VAL    =  3    # "255" right-aligned
_SEP        = "  "  # separator between left and right halves


# ── Pure logic ────────────────────────────────────────────────────────────────

def _stat_bar(value: int) -> str:
    """Return an ASCII progress bar for a base stat value."""
    filled = round(value / _BAR_MAX * _BAR_WIDTH)
    return "[" + "█" * filled + "·" * (_BAR_WIDTH - filled) + "]"


def total_stats(base_stats: dict) -> int:
    """Return the sum of all 6 base stats.  Missing keys default to 0."""
    return sum(base_stats.get(k, 0) for k, _ in _STAT_KEYS)


def infer_role(base_stats: dict) -> str:
    """
    Return the inferred attacking role based on Atk vs SpA.
      'physical' — Atk >= SpA * 1.2
      'special'  — SpA >= Atk * 1.2
      'mixed'    — neither dominates
    """
    atk = base_stats.get("attack", 1) or 1
    spa = base_stats.get("special-attack", 1) or 1
    if atk >= spa * 1.2:
        return "physical"
    if spa >= atk * 1.2:
        return "special"
    return "mixed"


def infer_speed_tier(base_stats: dict) -> str:
    """
    Return the speed tier based on base Speed.
      'fast' — Speed >= 90
      'mid'  — Speed in [70, 89]
      'slow' — Speed < 70
    """
    spe = base_stats.get("speed", 0)
    if spe >= 90: return "fast"
    if spe >= 70: return "mid"
    return "slow"


def compare_stats(stats_a: dict, stats_b: dict) -> list:
    """
    Compare two base_stats dicts stat by stat.

    Returns a list of 6 dicts, one per stat, in _STAT_KEYS order:
      {
        "key"   : str,          # "hp", "attack", etc.
        "label" : str,          # "HP", "Atk", etc.
        "val_a" : int,
        "val_b" : int,
        "winner": "a" | "b" | "tie",
      }
    """
    rows = []
    for key, label in _STAT_KEYS:
        va = stats_a.get(key, 0)
        vb = stats_b.get(key, 0)
        if va > vb:
            winner = "a"
        elif vb > va:
            winner = "b"
        else:
            winner = "tie"
        rows.append({"key": key, "label": label,
                     "val_a": va, "val_b": vb, "winner": winner})
    return rows


# ── Display ───────────────────────────────────────────────────────────────────

_W = 56   # inner separator width

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
    _bar_len   = _BAR_WIDTH + 2   # "[" + fills + "]"
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
        bar_a = _stat_bar(r["val_a"])
        bar_b = _stat_bar(r["val_b"])
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
    bar_pad = " " * (_BAR_WIDTH + 2)   # align totals under bars
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

    # ── compare_stats ─────────────────────────────────────────────────────────

    all_equal = {"hp": 100, "attack": 100, "defense": 100,
                 "special-attack": 100, "special-defense": 100, "speed": 100}
    rows = compare_stats(all_equal, all_equal)
    if all(r["winner"] == "tie" for r in rows):
        ok("compare_stats: all equal → all ties")
    else:
        fail("compare_stats all equal", str([r["winner"] for r in rows]))

    stats_a = {"hp": 80, "attack": 130, "defense": 95,
               "special-attack": 80, "special-defense": 85, "speed": 102}
    stats_b = {"hp": 78, "attack":  84, "defense": 78,
               "special-attack": 109, "special-defense": 85, "speed": 100}
    rows = compare_stats(stats_a, stats_b)
    winners = {r["key"]: r["winner"] for r in rows}
    if winners["hp"] == "a":
        ok("compare_stats: HP 80 vs 78 → a wins")
    else:
        fail("compare_stats HP", winners["hp"])
    if winners["attack"] == "a":
        ok("compare_stats: Atk 130 vs 84 → a wins")
    else:
        fail("compare_stats Atk", winners["attack"])
    if winners["special-attack"] == "b":
        ok("compare_stats: SpA 80 vs 109 → b wins")
    else:
        fail("compare_stats SpA", winners["special-attack"])
    if winners["special-defense"] == "tie":
        ok("compare_stats: SpD 85 vs 85 → tie")
    else:
        fail("compare_stats SpD", winners["special-defense"])

    # ── total_stats ───────────────────────────────────────────────────────────

    t = total_stats({"hp": 78, "attack": 84, "defense": 78,
                     "special-attack": 109, "special-defense": 85, "speed": 100})
    if t == 534:
        ok("total_stats: 78+84+78+109+85+100 = 534")
    else:
        fail("total_stats", str(t))

    t_missing = total_stats({"hp": 50})
    if t_missing == 50:
        ok("total_stats: missing keys default to 0")
    else:
        fail("total_stats missing keys", str(t_missing))

    # ── display_comparison (stdout capture) ───────────────────────────────────

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

    if "Garchomp" in out:
        ok("display_comparison: Pokemon A name present")
    else:
        fail("display_comparison name_a", out[:80])

    if "Charizard" in out:
        ok("display_comparison: Pokemon B name present")
    else:
        fail("display_comparison name_b", out[:80])

    stat_labels_present = all(lbl in out for _, lbl in _STAT_KEYS)
    if stat_labels_present:
        ok("display_comparison: all 6 stat labels present")
    else:
        missing = [lbl for _, lbl in _STAT_KEYS if lbl not in out]
        fail("display_comparison stat labels", str(missing))

    if "Total" in out:
        ok("display_comparison: Total line present")
    else:
        fail("display_comparison Total", out[-100:])

    if "Role" in out:
        ok("display_comparison: Role line present")
    else:
        fail("display_comparison Role line", out[-100:])

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

    # ── infer_role ────────────────────────────────────────────────────────────

    if infer_role({"attack": 130, "special-attack": 65}) == "physical":
        ok("infer_role: Atk 130 / SpA 65 → physical")
    else:
        fail("infer_role physical", infer_role({"attack": 130, "special-attack": 65}))

    if infer_role({"attack": 45, "special-attack": 135}) == "special":
        ok("infer_role: Atk 45 / SpA 135 → special")
    else:
        fail("infer_role special", infer_role({"attack": 45, "special-attack": 135}))

    if infer_role({"attack": 85, "special-attack": 90}) == "mixed":
        ok("infer_role: Atk 85 / SpA 90 → mixed")
    else:
        fail("infer_role mixed", infer_role({"attack": 85, "special-attack": 90}))

    if infer_role({"attack": 100, "special-attack": 100}) == "mixed":
        ok("infer_role: equal stats → mixed")
    else:
        fail("infer_role equal", infer_role({"attack": 100, "special-attack": 100}))

    # Exactly at threshold: 120 >= 100 * 1.2 → physical
    if infer_role({"attack": 120, "special-attack": 100}) == "physical":
        ok("infer_role: Atk 120 / SpA 100 → physical (exact threshold)")
    else:
        fail("infer_role threshold", infer_role({"attack": 120, "special-attack": 100}))

    # Just below threshold: 119 < 100 * 1.2 → mixed
    if infer_role({"attack": 119, "special-attack": 100}) == "mixed":
        ok("infer_role: Atk 119 / SpA 100 → mixed (below threshold)")
    else:
        fail("infer_role below threshold", infer_role({"attack": 119, "special-attack": 100}))

    # ── infer_speed_tier ──────────────────────────────────────────────────────

    if infer_speed_tier({"speed": 90}) == "fast":
        ok("infer_speed_tier: 90 → fast")
    else:
        fail("infer_speed_tier 90", infer_speed_tier({"speed": 90}))

    if infer_speed_tier({"speed": 89}) == "mid":
        ok("infer_speed_tier: 89 → mid")
    else:
        fail("infer_speed_tier 89", infer_speed_tier({"speed": 89}))

    if infer_speed_tier({"speed": 70}) == "mid":
        ok("infer_speed_tier: 70 → mid (boundary)")
    else:
        fail("infer_speed_tier 70", infer_speed_tier({"speed": 70}))

    if infer_speed_tier({"speed": 69}) == "slow":
        ok("infer_speed_tier: 69 → slow")
    else:
        fail("infer_speed_tier 69", infer_speed_tier({"speed": 69}))

    if infer_speed_tier({"speed": 0}) == "slow":
        ok("infer_speed_tier: 0 → slow")
    else:
        fail("infer_speed_tier 0", infer_speed_tier({"speed": 0}))

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 26
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