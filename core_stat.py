#!/usr/bin/env python3
"""
core_stat.py  Pure stat-related logic (no I/O, no display)

Functions:
  stat_bar(value) → str
  total_stats(base_stats) → int
  infer_role(base_stats) → str
  infer_speed_tier(base_stats) → str
  compare_stats(stats_a, stats_b) → list[dict]
"""

import sys

# Order and labels of the six stats
STAT_KEYS = [
    ("hp", "HP"),
    ("attack", "Atk"),
    ("defense", "Def"),
    ("special-attack", "SpA"),
    ("special-defense", "SpD"),
    ("speed", "Spe"),
]

_BAR_MAX = 255
_BAR_WIDTH = 18


def stat_bar(value: int) -> str:
    """Return an ASCII progress bar for a base stat value."""
    filled = round(value / _BAR_MAX * _BAR_WIDTH)
    return "[" + "█" * filled + "·" * (_BAR_WIDTH - filled) + "]"


def total_stats(base_stats: dict) -> int:
    """Return the sum of all 6 base stats. Missing keys default to 0."""
    return sum(base_stats.get(k, 0) for k, _ in STAT_KEYS)


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
    if spe >= 90:
        return "fast"
    if spe >= 70:
        return "mid"
    return "slow"


def compare_stats(stats_a: dict, stats_b: dict) -> list:
    """
    Compare two base_stats dicts stat by stat.

    Returns a list of 6 dicts, one per stat in STAT_KEYS order:
      {
        "key"   : str,          # "hp", "attack", etc.
        "label" : str,          # "HP", "Atk", etc.
        "val_a" : int,
        "val_b" : int,
        "winner": "a" | "b" | "tie",
      }
    """
    rows = []
    for key, label in STAT_KEYS:
        va = stats_a.get(key, 0)
        vb = stats_b.get(key, 0)
        if va > vb:
            winner = "a"
        elif vb > va:
            winner = "b"
        else:
            winner = "tie"
        rows.append({
            "key": key,
            "label": label,
            "val_a": va,
            "val_b": vb,
            "winner": winner,
        })
    return rows


# ── Self‑tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import sys
    errors = []
    total = 0
    def ok(label):
        nonlocal total
        total += 1
        print(f"  [OK]   {label}")
    def fail(label, msg=""):
        nonlocal total
        total += 1
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  core_stat.py — self-test\n")

    # ── stat_bar ─────────────────────────────────────────────────────────────
    b = stat_bar(255)
    if b == "[" + "█" * 18 + "]":
        ok("stat_bar: max value → full bar")
    else:
        fail("stat_bar max", repr(b))

    b = stat_bar(0)
    if b == "[" + "·" * 18 + "]":
        ok("stat_bar: zero → empty bar")
    else:
        fail("stat_bar zero", repr(b))

    # ── total_stats ─────────────────────────────────────────────────────────
    t = total_stats({"hp": 78, "attack": 84, "defense": 78,
                     "special-attack": 109, "special-defense": 85, "speed": 100})
    if t == 534:
        ok("total_stats: Charizard = 534")
    else:
        fail("total_stats Charizard", str(t))

    t_missing = total_stats({"hp": 50})
    if t_missing == 50:
        ok("total_stats: missing keys default to 0")
    else:
        fail("total_stats missing keys", str(t_missing))

    # ── infer_role ──────────────────────────────────────────────────────────
    if infer_role({"attack": 130, "special-attack": 65}) == "physical":
        ok("infer_role: physical")
    else:
        fail("infer_role physical")

    if infer_role({"attack": 45, "special-attack": 135}) == "special":
        ok("infer_role: special")
    else:
        fail("infer_role special")

    if infer_role({"attack": 85, "special-attack": 90}) == "mixed":
        ok("infer_role: mixed")
    else:
        fail("infer_role mixed")

    if infer_role({"attack": 120, "special-attack": 100}) == "physical":
        ok("infer_role: threshold physical (1.2)")
    else:
        fail("infer_role threshold physical")

    if infer_role({"attack": 119, "special-attack": 100}) == "mixed":
        ok("infer_role: just below threshold → mixed")
    else:
        fail("infer_role below threshold")

    # ── infer_speed_tier ─────────────────────────────────────────────────────
    if infer_speed_tier({"speed": 90}) == "fast":
        ok("infer_speed_tier: 90 → fast")
    else:
        fail("infer_speed_tier 90")

    if infer_speed_tier({"speed": 89}) == "mid":
        ok("infer_speed_tier: 89 → mid")
    else:
        fail("infer_speed_tier 89")

    if infer_speed_tier({"speed": 70}) == "mid":
        ok("infer_speed_tier: 70 → mid")
    else:
        fail("infer_speed_tier 70")

    if infer_speed_tier({"speed": 69}) == "slow":
        ok("infer_speed_tier: 69 → slow")
    else:
        fail("infer_speed_tier 69")

    if infer_speed_tier({"speed": 0}) == "slow":
        ok("infer_speed_tier: 0 → slow")
    else:
        fail("infer_speed_tier 0")

    # ── compare_stats ───────────────────────────────────────────────────────
    a = {"hp": 80, "attack": 130, "defense": 95,
         "special-attack": 80, "special-defense": 85, "speed": 102}
    b = {"hp": 78, "attack": 84, "defense": 78,
         "special-attack": 109, "special-defense": 85, "speed": 100}
    rows = compare_stats(a, b)
    if rows[0]["winner"] == "a" and rows[4]["winner"] == "tie" and rows[3]["winner"] == "b":
        ok("compare_stats: correct winners")
    else:
        fail("compare_stats", str(rows))

    # All equal → all ties
    all_equal = {k: 100 for k, _ in STAT_KEYS}
    rows_eq = compare_stats(all_equal, all_equal)
    if all(r["winner"] == "tie" for r in rows_eq):
        ok("compare_stats: all equal → all ties")
    else:
        fail("compare_stats all equal")

    print()
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
    else:
        print("This module is a library; run with --autotest to test.")