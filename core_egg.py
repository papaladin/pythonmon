#!/usr/bin/env python3
"""
core_egg.py  Pure egg‑group logic (no I/O, no display)

Functions:
  egg_group_name(slug) → str
  format_egg_groups(egg_groups) → str
"""

# Mapping of PokeAPI egg‑group slugs to in‑game display names
_EGG_GROUP_NAMES = {
    "monster"      : "Monster",
    "water1"       : "Water 1",
    "water2"       : "Water 2",
    "water3"       : "Water 3",
    "bug"          : "Bug",
    "flying"       : "Flying",
    "ground"       : "Field",        # PokeAPI slug "ground" ≠ in‑game "Field"
    "fairy"        : "Fairy",
    "plant"        : "Grass",        # PokeAPI slug "plant" ≠ in‑game "Grass"
    "humanshape"   : "Human-Like",
    "mineral"      : "Mineral",
    "indeterminate": "Amorphous",
    "ditto"        : "Ditto",
    "dragon"       : "Dragon",
    "no-eggs"      : "Undiscovered",
}

import sys

def egg_group_name(slug: str) -> str:
    """
    Return the in‑game display name for a PokeAPI egg group slug.
    Falls back to title‑cased slug for unknown groups.
    """
    return _EGG_GROUP_NAMES.get(slug, slug.replace("-", " ").title())


def format_egg_groups(egg_groups: list) -> str:
    """
    Return a formatted string of egg group display names.
    e.g. ["monster", "dragon"] → "Monster  /  Dragon"
    Returns "" for an empty list.
    """
    return "  /  ".join(egg_group_name(s) for s in egg_groups)


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

    print("\n  core_egg.py — self-test\n")

    # ── egg_group_name ───────────────────────────────────────────────────────
    if egg_group_name("monster") == "Monster":
        ok("egg_group_name: monster → Monster")
    else:
        fail("egg_group_name monster", egg_group_name("monster"))

    if egg_group_name("ground") == "Field":
        ok("egg_group_name: ground → Field (slug ≠ in‑game name)")
    else:
        fail("egg_group_name ground", egg_group_name("ground"))

    if egg_group_name("plant") == "Grass":
        ok("egg_group_name: plant → Grass (slug ≠ in‑game name)")
    else:
        fail("egg_group_name plant", egg_group_name("plant"))

    if egg_group_name("no-eggs") == "Undiscovered":
        ok("egg_group_name: no-eggs → Undiscovered")
    else:
        fail("egg_group_name no-eggs", egg_group_name("no-eggs"))

    if egg_group_name("humanshape") == "Human-Like":
        ok("egg_group_name: humanshape → Human-Like")
    else:
        fail("egg_group_name humanshape", egg_group_name("humanshape"))

    if egg_group_name("indeterminate") == "Amorphous":
        ok("egg_group_name: indeterminate → Amorphous")
    else:
        fail("egg_group_name indeterminate", egg_group_name("indeterminate"))

    # Unknown slug → title‑cased fallback
    if egg_group_name("some-new-group") == "Some New Group":
        ok("egg_group_name: unknown slug → title‑cased fallback")
    else:
        fail("egg_group_name fallback", egg_group_name("some-new-group"))

    # ── format_egg_groups ─────────────────────────────────────────────────────
    if format_egg_groups(["monster", "dragon"]) == "Monster  /  Dragon":
        ok("format_egg_groups: two groups formatted correctly")
    else:
        fail("format_egg_groups two", repr(format_egg_groups(["monster", "dragon"])))

    if format_egg_groups(["ground"]) == "Field":
        ok("format_egg_groups: single group with name mapping")
    else:
        fail("format_egg_groups single", repr(format_egg_groups(["ground"])))

    if format_egg_groups([]) == "":
        ok("format_egg_groups: empty list → empty string")
    else:
        fail("format_egg_groups empty", repr(format_egg_groups([])))

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