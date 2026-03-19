#!/usr/bin/env python3
"""
feat_egg_group.py  Egg group browser and breeding partner finder

Surfaces egg group data in two places:
  - Option 1 (quick view): compact inline display of group names
  - Key E (browser): full roster of breeding partners per group

Egg group slugs from PokeAPI differ from in-game display names in two
important cases: "ground" → Field, "plant" → Grass.  All 15 known groups
are mapped in _EGG_GROUP_NAMES.

Entry points:
  egg_group_name(slug)          → str   (used by feat_type_matchup)
  format_egg_groups(egg_groups) → str   (used by feat_type_matchup)
  run(pkm_ctx)                  → None  called from pokemain; key E
  main()                        → None  standalone
"""

import sys

try:
    from pkm_session import select_game, select_pokemon
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Egg group name mapping ────────────────────────────────────────────────────

_EGG_GROUP_NAMES: dict[str, str] = {
    "monster"      : "Monster",
    "water1"       : "Water 1",
    "water2"       : "Water 2",
    "water3"       : "Water 3",
    "bug"          : "Bug",
    "flying"       : "Flying",
    "ground"       : "Field",        # PokeAPI slug "ground" ≠ in-game "Field"
    "fairy"        : "Fairy",
    "plant"        : "Grass",        # PokeAPI slug "plant" ≠ in-game "Grass"
    "humanshape"   : "Human-Like",
    "mineral"      : "Mineral",
    "indeterminate": "Amorphous",
    "ditto"        : "Ditto",
    "dragon"       : "Dragon",
    "no-eggs"      : "Undiscovered",
}


# ── Pure helpers (used by feat_type_matchup and browser) ─────────────────────

def egg_group_name(slug: str) -> str:
    """
    Return the in-game display name for a PokeAPI egg group slug.
    Falls back to title-cased slug for unknown groups.
    """
    return _EGG_GROUP_NAMES.get(slug, slug.replace("-", " ").title())


def format_egg_groups(egg_groups: list) -> str:
    """
    Return a formatted string of egg group display names.
    e.g. ["monster", "dragon"] → "Monster  /  Dragon"
    Returns "" for an empty list.
    """
    return "  /  ".join(egg_group_name(s) for s in egg_groups)


# ── Roster fetch (cache-aware) ────────────────────────────────────────────────

def get_or_fetch_roster(slug: str) -> list | None:
    """
    Return the egg group roster from cache, fetching from PokeAPI on miss.
    Returns None if the group is unknown or the network is unavailable.
    """
    import pkm_cache as cache
    roster = cache.get_egg_group(slug)
    if roster is not None:
        return roster
    try:
        import pkm_pokeapi as pokeapi
        group_name = egg_group_name(slug)
        print(f"  Fetching {group_name} egg group roster...", end=" ", flush=True)
        roster = pokeapi.fetch_egg_group(slug)
        cache.save_egg_group(slug, roster)
        print(f"{len(roster)} Pokémon.")
        return roster
    except ValueError:
        print("not found.")
        return None
    except ConnectionError as e:
        print(f"connection error: {e}")
        return None


# ── Display ───────────────────────────────────────────────────────────────────

_W         = 54    # separator width
_COLS      =  5    # names per row in the roster grid
_COL_WIDTH = 16    # characters per name cell


def _print_roster_grid(roster: list, current_slug: str) -> None:
    """Print a roster as a compact name grid, marking the current Pokemon."""
    for i, entry in enumerate(roster):
        name = entry["name"]
        # Truncate long names to fit column
        cell = name[:_COL_WIDTH - 1] if len(name) >= _COL_WIDTH else name
        # Mark current Pokemon with ★
        if entry["slug"] == current_slug:
            cell = f"{cell} ★"
        print(f"  {cell:<{_COL_WIDTH}}", end="")
        if (i + 1) % _COLS == 0:
            print()
    if len(roster) % _COLS != 0:
        print()   # final newline if last row wasn't complete


def display_egg_group_browser(pkm_ctx: dict) -> None:
    """Full browser display for key E."""
    groups    = pkm_ctx.get("egg_groups", [])
    form_name = pkm_ctx.get("form_name", pkm_ctx.get("pokemon", ""))
    slug      = pkm_ctx.get("variety_slug") or pkm_ctx.get("pokemon", "")

    print(f"\n  Egg groups  |  {form_name}")
    print("  " + "═" * _W)

    if not groups:
        print("\n  No egg group data for this Pokémon.")
        print("  Try pressing R to refresh the Pokémon data.")
        return

    print(f"  Groups: {format_egg_groups(groups)}")

    for group_slug in groups:
        group_label = egg_group_name(group_slug)
        roster = get_or_fetch_roster(group_slug)

        print()
        if roster is None:
            print(f"  {group_label} group  (could not load roster)")
            continue

        undiscovered = (group_slug == "no-eggs")
        header = f"  {group_label} group  ({len(roster)} Pokémon)"
        if undiscovered:
            header += "  — cannot breed"
        print(header)
        print("  " + "─" * _W)
        _print_roster_grid(roster, slug)

    print()
    print("  ★ = current Pokémon")
    print("  " + "═" * _W)


# ── Entry points ──────────────────────────────────────────────────────────────

def run(pkm_ctx: dict) -> None:
    """Called from pokemain (key E)."""
    display_egg_group_browser(pkm_ctx)
    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("╔══════════════════════════════════════════╗")
    print("║         Egg Group Browser                ║")
    print("╚══════════════════════════════════════════╝")

    pkm_ctx = select_pokemon()
    if pkm_ctx is None:
        sys.exit(0)

    run(pkm_ctx)


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):  print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_egg_group.py — self-test\n")

    # ── _EGG_GROUP_NAMES coverage ─────────────────────────────────────────────

    if len(_EGG_GROUP_NAMES) == 15:
        ok("_EGG_GROUP_NAMES: exactly 15 groups")
    else:
        fail("_EGG_GROUP_NAMES count", str(len(_EGG_GROUP_NAMES)))

    # ── egg_group_name ────────────────────────────────────────────────────────

    if egg_group_name("monster") == "Monster":
        ok("egg_group_name: monster → Monster")
    else:
        fail("egg_group_name monster", egg_group_name("monster"))

    if egg_group_name("ground") == "Field":
        ok("egg_group_name: ground → Field (slug ≠ in-game name)")
    else:
        fail("egg_group_name ground", egg_group_name("ground"))

    if egg_group_name("plant") == "Grass":
        ok("egg_group_name: plant → Grass (slug ≠ in-game name)")
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

    # Unknown slug → title-cased fallback
    result = egg_group_name("some-new-group")
    if result == "Some New Group":
        ok("egg_group_name: unknown slug → title-cased fallback")
    else:
        fail("egg_group_name fallback", result)

    # ── format_egg_groups ─────────────────────────────────────────────────────

    r = format_egg_groups(["monster", "dragon"])
    if r == "Monster  /  Dragon":
        ok("format_egg_groups: two groups formatted correctly")
    else:
        fail("format_egg_groups two", repr(r))

    r = format_egg_groups(["ground"])
    if r == "Field":
        ok("format_egg_groups: single group with name mapping")
    else:
        fail("format_egg_groups single", repr(r))

    r = format_egg_groups([])
    if r == "":
        ok("format_egg_groups: empty list → empty string")
    else:
        fail("format_egg_groups empty", repr(r))

    # ── display_egg_group_browser (stdout capture) ────────────────────────────
    import io, contextlib

    # Mock get_or_fetch_roster to avoid network calls
    _orig_get_or_fetch = globals().get("get_or_fetch_roster")

    def _mock_roster(slug):
        if slug == "monster":
            return [{"slug": "bulbasaur",  "name": "Bulbasaur"},
                    {"slug": "charmander", "name": "Charmander"},
                    {"slug": "fakizard",   "name": "Fakizard"}]
        if slug == "dragon":
            return [{"slug": "dratini",   "name": "Dratini"},
                    {"slug": "fakizard",  "name": "Fakizard"}]
        if slug == "no-eggs":
            return [{"slug": "mewtwo", "name": "Mewtwo"}]
        return None

    import sys as _sys
    _self = _sys.modules[__name__]
    _self.get_or_fetch_roster = _mock_roster

    pkm_ctx = {"form_name": "Fakizard", "pokemon": "fakizard",
               "variety_slug": "fakizard", "egg_groups": ["monster", "dragon"]}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        display_egg_group_browser(pkm_ctx)
    out = buf.getvalue()

    if "Fakizard" in out:
        ok("display_egg_group_browser: pokemon name in header")
    else:
        fail("display_egg_group_browser header", out[:80])

    if "Monster" in out and "Dragon" in out:
        ok("display_egg_group_browser: both group names shown")
    else:
        fail("display_egg_group_browser groups", out[:120])

    if "Bulbasaur" in out and "Dratini" in out:
        ok("display_egg_group_browser: roster members shown")
    else:
        fail("display_egg_group_browser roster", out[:200])

    if "★" in out:
        ok("display_egg_group_browser: current Pokemon marked with ★")
    else:
        fail("display_egg_group_browser ★ marker", out[:200])

    # Empty egg_groups → graceful message
    pkm_no_groups = {"form_name": "Mewtwo", "pokemon": "mewtwo",
                     "variety_slug": "mewtwo", "egg_groups": []}
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        display_egg_group_browser(pkm_no_groups)
    out2 = buf2.getvalue()
    if "No egg group data" in out2:
        ok("display_egg_group_browser: empty groups → graceful message")
    else:
        fail("display_egg_group_browser empty", out2[:80])

    # no-eggs group → cannot breed note
    pkm_legendary = {"form_name": "Mewtwo", "pokemon": "mewtwo",
                     "variety_slug": "mewtwo", "egg_groups": ["no-eggs"]}
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        display_egg_group_browser(pkm_legendary)
    out3 = buf3.getvalue()
    if "cannot breed" in out3:
        ok("display_egg_group_browser: no-eggs → cannot breed note")
    else:
        fail("display_egg_group_browser no-eggs", out3[:120])

    # Restore mock
    if _orig_get_or_fetch is not None:
        _self.get_or_fetch_roster = _orig_get_or_fetch

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 18
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