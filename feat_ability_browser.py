#!/usr/bin/env python3
"""
feat_ability_browser.py  Ability browser

Two modes depending on what is loaded:

  No Pokémon loaded:
    List all abilities grouped by generation with their short effect.
    User can search by name to drill into a specific ability (full effect
    + list of Pokémon that have it).

  Pokémon loaded:
    Show the current Pokémon's abilities (with effects) prominently first,
    then offer to browse / search all abilities.

Abilities were introduced in Gen 3. A warning is shown for Gen 1/2 games
but the feature is always accessible.

Ability index is fetched from PokeAPI once and cached in
cache/abilities_index.json. Individual ability details (full effect text +
Pokémon list) are fetched on demand and cached in cache/abilities/<slug>.json.

Menu key: A  (always shown)

Entry points:
  run(game_ctx=None, pkm_ctx=None, ui=None)   called from pokemain
  main()                             standalone
"""

import os
import sys

try:
    import pkm_cache as cache
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)

# Generation in which abilities were introduced
_ABILITY_MIN_GEN = 3

# Column widths for the ability list table
_C_NAME   = 22
_C_GEN    =  6
_C_EFFECT = 52
_GAP      = "  "


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen_label(gen: int) -> str:
    """Return a short generation label, e.g. 3 → 'Gen 3'."""
    return f"Gen {gen}" if gen else "?"


def _wrap(text: str, width: int, indent: str = "") -> list[str]:
    """Wrap text to width, returning lines. First line has no indent."""
    words  = text.split()
    lines  = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    if not lines:
        return [""]
    result = [lines[0]]
    for l in lines[1:]:
        result.append(indent + l)
    return result


def _ability_display_name(slug: str, index: dict) -> str:
    """Return display name from index, falling back to title-cased slug."""
    entry = index.get(slug)
    if entry:
        return entry["name"]
    return slug.replace("-", " ").title()


async def _print_ability_row(ui, name: str, gen: int, short_effect: str) -> None:
    """Print one row of the ability list table."""
    gen_s    = _gen_label(gen)
    wrapped  = _wrap(short_effect, _C_EFFECT)
    first    = wrapped[0]
    await ui.print_output(f"  {name:<{_C_NAME}}{_GAP}{gen_s:<{_C_GEN}}{_GAP}{first}")
    for extra in wrapped[1:]:
        await ui.print_output("  " + " " * _C_NAME + _GAP + " " * _C_GEN + _GAP + extra)


async def _print_ability_table_header(ui) -> None:
    header = (f"  {'Ability':<{_C_NAME}}{_GAP}{'Gen':<{_C_GEN}}"
              f"{_GAP}{'Effect (short)'}")
    sep    = "  " + "─" * (len(header) - 2)
    await ui.print_output(header)
    await ui.print_output(sep)


# ── Ability list (all) ────────────────────────────────────────────────────────

async def _print_all_abilities(ui, index: dict) -> None:
    """Print all abilities grouped by generation."""
    # Group by gen
    groups: dict[int, list] = {}
    for slug, entry in index.items():
        g = entry.get("gen", 0)
        groups.setdefault(g, []).append((entry["name"], g, entry["short_effect"], slug))

    for gen in sorted(groups):
        entries = sorted(groups[gen], key=lambda r: r[0].lower())
        await ui.print_output(f"\n  ── Generation {gen} " + "─" * 48)
        await _print_ability_table_header(ui)
        for name, g, effect, _slug in entries:
            await _print_ability_row(ui, name, g, effect)


# ── Ability detail (drill-in) ─────────────────────────────────────────────────

def _fetch_ability_detail(slug: str) -> dict | None:
    """
    Fetch full ability data from PokeAPI: full effect text + Pokémon list.
    Caches to cache/abilities/<slug>.json.
    Returns None on network failure.
    """
    # Check per-ability cache first
    detail = cache.get_ability_detail(slug)
    if detail is not None:
        return detail

    try:
        import pkm_pokeapi as api
        detail = api.fetch_ability_detail(slug)
        cache.save_ability_detail(slug, detail)
        return detail
    except ConnectionError as e:
        # Use print here because this is a network error, but we can also use ui.print_output if we had ui.
        # For now, keep print; it will appear in console but not in TUI.
        print(f"\n  Connection error: {e}")
        return None


async def _print_ability_detail(ui, slug: str, index: dict) -> None:
    """Fetch and print full details for one ability."""
    entry = index.get(slug)
    if entry is None:
        await ui.print_output(f"\n  Ability '{slug}' not found in index.")
        return

    name    = entry["name"]
    gen     = entry.get("gen", 0)
    s_eff   = entry.get("short_effect", "")

    await ui.print_output(f"\n  {'─'*68}")
    await ui.print_output(f"  {name}  (Gen {gen})")
    await ui.print_output(f"  {'─'*68}")
    await ui.print_output(f"\n  Short effect:  {s_eff}")

    detail = _fetch_ability_detail(slug)
    if detail:
        full = detail.get("effect", "")
        if full and full != s_eff:
            await ui.print_output(f"\n  Full effect:")
            for line in _wrap(full, 68, indent="    "):
                await ui.print_output(f"    {line}")

        pokemon_list = detail.get("pokemon", [])
        if pokemon_list:
            # Split into normal and hidden ability holders
            normal = [p for p in pokemon_list if not p.get("is_hidden")]
            hidden = [p for p in pokemon_list if p.get("is_hidden")]
            await ui.print_output(f"\n  Pokémon with this ability ({len(normal)} normal"
                  f"{f', {len(hidden)} hidden' if hidden else ''}):")
            names_normal = sorted(p["name"] for p in normal)
            names_hidden = sorted(p["name"] for p in hidden)
            # Print in columns (3 per row)
            for chunk in [names_normal, names_hidden]:
                if not chunk:
                    continue
                is_hidden_chunk = chunk is names_hidden
                if is_hidden_chunk:
                    await ui.print_output("")
                    await ui.print_output("  Hidden:")
                label = "    "
                for i in range(0, len(chunk), 3):
                    row = "  ".join(f"{n:<22}" for n in chunk[i:i+3])
                    await ui.print_output(f"  {label}{row}")
    await ui.print_output("")


# ── Pokémon abilities display ─────────────────────────────────────────────────

async def _print_pkm_abilities(ui, pkm_ctx: dict, index: dict) -> None:
    """Display the abilities of the currently loaded Pokémon."""
    abilities = pkm_ctx.get("abilities", [])
    form_name = pkm_ctx.get("form_name", pkm_ctx.get("pokemon", "?"))

    if not abilities:
        await ui.print_output(f"\n  No ability data for {form_name}.")
        await ui.print_output("  Press R in the main menu to refresh Pokémon data.")
        return

    await ui.print_output(f"\n  Abilities for {form_name}:")
    await ui.print_output("  " + "─" * 60)
    for ab in abilities:
        slug      = ab.get("slug", "")
        is_hidden = ab.get("is_hidden", False)
        name      = _ability_display_name(slug, index)
        tag       = "  [Hidden Ability]" if is_hidden else ""
        short_eff = index.get(slug, {}).get("short_effect", "(effect unknown)")
        await ui.print_output(f"\n  {name}{tag}")
        for line in _wrap(short_eff, 64, indent="    "):
            await ui.print_output(f"    {line}")
    await ui.print_output("")


# ── Search / drill-in (uses persistent input bar) ───────────────────────────

async def _search_and_drill(ui, index: dict) -> None:
    """
    Prompt user for an ability name, find matches, and drill into the detail.
    Loops until user enters nothing.
    """
    while True:
        query = (await ui.input_prompt("\n  Search ability (Enter to skip): ")).strip().lower()
        if not query:
            return

        matches = [
            (slug, entry)
            for slug, entry in index.items()
            if query in entry["name"].lower() or query in slug
        ]

        if not matches:
            await ui.print_output(f"  No ability found matching '{query}'.")
            continue

        if len(matches) == 1:
            await _print_ability_detail(ui, matches[0][0], index)
        else:
            matches.sort(key=lambda r: r[1]["name"].lower())
            await ui.print_output(f"\n  {len(matches)} abilities match '{query}':")
            for i, (slug, entry) in enumerate(matches, 1):
                await ui.print_output(f"  {i:3d}. {entry['name']}")
            try:
                idx = int((await ui.input_prompt("  Enter number to drill in (0 to cancel): ")).strip())
                if 1 <= idx <= len(matches):
                    await _print_ability_detail(ui, matches[idx - 1][0], index)
            except ValueError:
                pass


# ── Main entry point ─────────────────────────────────────────────────────────

async def run(game_ctx=None, pkm_ctx=None, ui=None) -> None:
    """
    Ability browser entry point.  Always accessible; warns for Gen 1/2 games.
    After listing all abilities, the user can search for a specific ability
    and drill into its details. The loop continues until the user enters
    an empty query.
    """
    if ui is None:
        # Fallback dummy UI for standalone
        from ui_dummy import DummyUI
        ui = DummyUI()

    # Gen 1/2 warning
    if game_ctx is not None:
        game_gen  = game_ctx.get("game_gen", 1)
        game_name = game_ctx.get("game", f"Gen {game_gen}")
        if game_gen < _ABILITY_MIN_GEN:
            await ui.print_output(f"\n  ⚠  Abilities did not exist in {game_name}.")
            await ui.print_output(    "     They were introduced in Generation 3 (Ruby / Sapphire).")
            await ui.print_output(    "     The browser below is shown for reference only.\n")

    # Load ability index
    index = cache.get_abilities_index_or_fetch()
    if index is None:
        await ui.print_output("\n  Could not load ability data (network unavailable and no cache).")
        return

    # If Pokémon loaded: show its abilities first
    if pkm_ctx is not None:
        await _print_pkm_abilities(ui, pkm_ctx, index)

    # Full list
    await ui.print_output("  All abilities by generation  (search below to drill in)")
    await _print_all_abilities(ui, index)

    # Search / drill-in (works in both CLI and TUI)
    await _search_and_drill(ui, index)


# ── Standalone entry point ────────────────────────────────────────────────────

def main() -> None:
    import asyncio
    asyncio.run(run())


# ── Unit tests (unchanged) ────────────────────────────────────────────────────

def _run_tests(with_cache: bool = False) -> None:
    passed = 0
    failed = 0

    def check(label, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")

    # ── _gen_label ────────────────────────────────────────────────────────────
    check("_gen_label 3 → 'Gen 3'",   _gen_label(3) == "Gen 3")
    check("_gen_label 1 → 'Gen 1'",   _gen_label(1) == "Gen 1")
    check("_gen_label 0 → '?'",       _gen_label(0) == "?")

    # ── _wrap ─────────────────────────────────────────────────────────────────
    short  = _wrap("hello world", 80)
    check("_wrap short text → single line", short == ["hello world"])

    long_text = "Powers up Fire-type moves when the Pokémon is in a pinch."
    wrapped = _wrap(long_text, 30)
    check("_wrap produces multiple lines for long text", len(wrapped) > 1)
    check("_wrap lines all fit in width", all(len(l) <= 30 for l in wrapped))
    check("_wrap empty string → single empty line", _wrap("", 40) == [""])

    # ── _ability_display_name ─────────────────────────────────────────────────
    fake_index = {
        "blaze":      {"name": "Blaze",       "gen": 3, "short_effect": "Powers up Fire moves."},
        "levitate":   {"name": "Levitate",     "gen": 3, "short_effect": "Immune to Ground."},
        "solar-power":{"name": "Solar Power",  "gen": 4, "short_effect": "Boosts SpA in sun."},
    }
    check("_ability_display_name from index",
          _ability_display_name("blaze", fake_index) == "Blaze")
    check("_ability_display_name fallback slug → title",
          _ability_display_name("some-unknown-ability", fake_index) == "Some Unknown Ability")

    # ── _print_pkm_abilities output ───────────────────────────────────────────
    import io as _io, sys as _sys

    fake_pkm = {
        "form_name": "Charizard",
        "abilities": [
            {"slug": "blaze",       "is_hidden": False},
            {"slug": "solar-power", "is_hidden": True},
        ]
    }
    buf = _io.StringIO()
    _sys.stdout = buf
    # Create a dummy UI that writes to buf
    from ui_dummy import DummyUI
    ui = DummyUI()
    import asyncio
    asyncio.run(_print_pkm_abilities(ui, fake_pkm, fake_index))
    _sys.stdout = _sys.__stdout__
    out = buf.getvalue()

    check("_print_pkm_abilities: Pokémon name in output",
          "Charizard" in out)
    check("_print_pkm_abilities: Blaze listed",
          "Blaze" in out)
    check("_print_pkm_abilities: Solar Power listed as hidden",
          "Solar Power" in out and "Hidden Ability" in out)
    check("_print_pkm_abilities: short effects shown",
          "Powers up Fire moves" in out and "Boosts SpA in sun" in out)

    # Empty abilities list
    buf2 = _io.StringIO()
    _sys.stdout = buf2
    asyncio.run(_print_pkm_abilities(ui, {"form_name": "Lapras", "abilities": []}, fake_index))
    _sys.stdout = _sys.__stdout__
    out2 = buf2.getvalue()
    check("_print_pkm_abilities: empty abilities shows fallback message",
          "No ability data" in out2)

    # ── withcache tests ───────────────────────────────────────────────────────
    if with_cache:
        index_live = cache.get_abilities_index_or_fetch()
        check("withcache: index is non-empty dict",
              isinstance(index_live, dict) and len(index_live) > 0)
        check("withcache: index has 100+ abilities",
              len(index_live) > 100)

        # Spot-check well-known abilities
        check("withcache: 'blaze' present",   "blaze"   in index_live)
        check("withcache: 'levitate' present", "levitate" in index_live)
        check("withcache: 'intimidate' present", "intimidate" in index_live)

        blaze = index_live.get("blaze", {})
        check("withcache: blaze name is 'Blaze'",
              blaze.get("name") == "Blaze")
        check("withcache: blaze gen is 3",
              blaze.get("gen") == 3)
        check("withcache: blaze has short_effect",
              bool(blaze.get("short_effect")))

        levitate = index_live.get("levitate", {})
        check("withcache: levitate has short_effect",
              bool(levitate.get("short_effect")))

        # All entries must have required keys
        all_valid = all(
            "name" in v and "gen" in v and "short_effect" in v
            for v in index_live.values()
        )
        check("withcache: all entries have name/gen/short_effect", all_valid)

    print()
    if failed:
        print(f"  {passed} passed, {failed} failed out of {passed+failed} tests.")
        sys.exit(1)
    else:
        print(f"  {passed} passed, 0 failed out of {passed} tests.")
        print("  All tests passed.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--autotest",  action="store_true")
    parser.add_argument("--withcache", action="store_true")
    args = parser.parse_args()
    if args.autotest:
        _run_tests(with_cache=args.withcache)
    else:
        main()