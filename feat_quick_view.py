#!/usr/bin/env python3
"""
feat_quick_view.py — Quick view: base stats, abilities, type matchup, evolution chain

When a Pokémon is loaded, displays:
  1. Base stats (HP / Atk / Def / SpA / SpD / Spe + total)
  2. Abilities with short effects
  3. Egg groups
  4. Type vulnerabilities and resistances
  5. Evolution chain (filtered by game generation)

In manual-type mode (standalone, no Pokémon), only the type chart is shown.

Entry points:
  run(pkm_ctx, game_ctx, ui=None)  — called from the main menu (key 1)
  main()                           — standalone

Standalone usage:
    python feat_quick_view.py
"""

import sys

try:
    import matchup_calculator as calc
    from pkm_session import select_game, select_pokemon, select_from_list, print_session_header
    from core_stat import stat_bar, infer_role, infer_speed_tier
    from core_egg import format_egg_groups
    import pkm_cache as cache
    from core_evolution import parse_trigger, flatten_chain, filter_paths_for_game
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Base stats display ───────────────────────────────────────────────────────

_SEP_WIDTH = 46   # width of section separator lines throughout this module

_STAT_LABELS = [
    ("hp",             "HP"),
    ("attack",         "Atk"),
    ("defense",        "Def"),
    ("special-attack", "SpA"),
    ("special-defense","SpD"),
    ("speed",          "Spe"),
]


async def _print_base_stats(ui, base_stats: dict, form_name: str) -> None:
    """Print base stats as a labelled bar chart, followed by role and speed tier."""
    if not base_stats:
        return
    await ui.print_output(f"\n  Base stats — {form_name}")
    await ui.print_output("  " + "─" * _SEP_WIDTH)
    total = 0
    for key, label in _STAT_LABELS:
        val = base_stats.get(key, 0)
        total += val
        bar = stat_bar(val)
        await ui.print_output(f"  {label:<4}  {val:>3}  {bar}")
    await ui.print_output("  " + "─" * _SEP_WIDTH)
    await ui.print_output(f"  {'Total':>8}  {total:>3}")
    role = infer_role(base_stats)
    tier = infer_speed_tier(base_stats)
    spe  = base_stats.get("speed", 0)
    role_str = f"{role.capitalize()} attacker"
    tier_str = f"{tier.capitalize()} (base {spe})"
    await ui.print_output(f"  {'Role':>8}  {role_str}  |  Speed: {tier_str}")


# ── Abilities display ─────────────────────────────────────────────────────────

async def _print_abilities_section(ui, abilities: list, form_name: str) -> None:
    """Print abilities with short effects, using the ability index for names/effects."""
    if not abilities:
        return
    try:
        import pkm_cache as _cache
        index = _cache.get_abilities_index()
    except (ImportError, OSError, ValueError):
        index = None

    await ui.print_output(f"\n  Abilities — {form_name}")
    await ui.print_output("  " + "─" * _SEP_WIDTH)
    for ab in abilities:
        slug      = ab.get("slug", "")
        is_hidden = ab.get("is_hidden", False)
        if index and slug in index:
            name   = index[slug]["name"]
            effect = index[slug].get("short_effect", "")
        else:
            name   = slug.replace("-", " ").title()
            effect = "(press A to load ability data)"
        tag = "  [Hidden]" if is_hidden else ""
        await ui.print_output(f"  {name}{tag}")
        if effect:
            await ui.print_output(f"    {effect}")


# ── Type chart (formatted as string) ─────────────────────────────────────────

def _format_type_chart(type1: str, type2: str, game: str, era_key: str) -> str:
    """Return the type chart as a string, suitable for printing via UI."""
    return calc.format_results(type1, type2, game, era_key)


# ── Evolution chain helpers (cache-aware) ─────────────────────────────────────

async def _get_types_for_slug(slug: str, ui=None) -> list[str]:
    """
    Return the type list for a species slug.
    Tries the pokemon cache first (instant). Falls back to fetching from
    PokeAPI on miss (one API call + cache write per uncached stage).
    Returns [] if unavailable.
    """
    data = cache.get_pokemon(slug)
    if data is not None:
        forms = data.get("forms", [])
        if forms:
            return forms[0].get("types", [])
    # Not cached — fetch and save
    try:
        import pkm_pokeapi as pokeapi
        if ui:
            await ui.print_output(f"  Fetching types for {slug}...", end=" ", flush=True)
        else:
            print(f"  Fetching types for {slug}...", end=" ", flush=True)
        data = pokeapi.fetch_pokemon(slug)
        cache.save_pokemon(slug, data)
        forms = data.get("forms", [])
        if forms:
            types = forms[0].get("types", [])
            if ui:
                await ui.print_output(f"done.")
            else:
                print(f"done.")
            return types
    except (ValueError, ConnectionError):
        if ui:
            await ui.print_output(f"failed.")
        else:
            print(f"failed.")
    return []


def _type_tag(types: list[str]) -> str:
    """Format a type list as a bracketed tag: ['Fire', 'Flying'] → '[Fire / Flying]'."""
    if not types:
        return "[?]"
    return f"[{' / '.join(types)}]"


def _get_species_gen(slug: str) -> int | None:
    """
    Return the generation a species was introduced, from the pokemon cache.
    Returns None if not cached (treated as unknown — not filtered out).
    """
    data = cache.get_pokemon(slug)
    if data is not None:
        return data.get("species_gen")
    return None


async def _get_or_fetch_chain(pkm_ctx: dict, ui=None) -> list | None:
    """
    Return the flattened evolution chain paths for the loaded Pokemon.

    Checks pkm_ctx["evolution_chain_id"], then reads from cache/evolution/.
    Fetches from PokeAPI on miss and saves to cache.

    Returns None if:
      - evolution_chain_id is None (event Pokemon with no chain)
      - network unavailable and cache empty
    """
    chain_id = pkm_ctx.get("evolution_chain_id")
    if chain_id is None:
        return None

    paths = cache.get_evolution_chain(chain_id)
    if paths is not None:
        return paths

    try:
        import pkm_pokeapi as pokeapi
        if ui:
            await ui.print_output("  Loading evolution chain...", end=" ", flush=True)
        else:
            print("  Loading evolution chain...", end=" ", flush=True)
        node = pokeapi.fetch_evolution_chain(chain_id)
        paths = flatten_chain(node)
        cache.save_evolution_chain(chain_id, paths)
        if ui:
            await ui.print_output("done.")
        else:
            print("done.")
        return paths
    except (ValueError, ConnectionError):
        return None


async def _display_evolution_block(pkm_ctx: dict, paths: list,
                                    game_gen: int | None = None,
                                    ui=None) -> None:
    """
    Print the compact evolution chain block for embedding in option 1.

    game_gen: if provided, filters out evolutions introduced after that
    generation. Eevee in FireRed (gen 3) will only show the 3 Gen-1/2
    Eeveelutions, not Espeon, Umbreon, Glaceon, Leafeon, Sylveon.
    """
    if ui is None:
        # Fallback dummy UI for standalone
        import builtins
        class DummyUI:
            async def print_output(self, text, end="\n"): builtins.print(text, end=end)
            async def input_prompt(self, prompt): return builtins.input(prompt)
            async def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
        ui = DummyUI()

    current_slug = pkm_ctx.get("pokemon", "")

    # Build species_gen_map for all slugs in the paths
    all_slugs = {stage["slug"] for path in paths for stage in path}
    species_gen_map = {}
    for slug in all_slugs:
        gen = _get_species_gen(slug)
        if gen is not None:
            species_gen_map[slug] = gen

    # Apply game-gen filter
    display_paths = filter_paths_for_game(paths, game_gen, species_gen_map) if game_gen else paths

    await ui.print_output(f"\n  Evolution chain")
    await ui.print_output("  " + "─" * _SEP_WIDTH)

    # Pre-fetch types for all unique slugs not already in cache
    need_fetch = [s for s in all_slugs if cache.get_pokemon(s) is None]
    if need_fetch:
        await ui.print_output(f"  Fetching types for {len(need_fetch)} stage(s)...",
                        end=" ", flush=True)
        for s in need_fetch:
            await _get_types_for_slug(s, ui=ui)   # side-effect: populates cache
        await ui.print_output("done.")

    if len(display_paths) == 1 and len(display_paths[0]) == 1:
        # Single-stage — does not evolve (or all evolutions filtered for this game)
        stage = display_paths[0][0]
        types = await _get_types_for_slug(stage["slug"], ui=ui)
        marker = " ★" if stage["slug"] == current_slug else ""
        no_evo_note = "no further evolution in this game" \
            if game_gen and len(paths) > 1 else "does not evolve"
        await ui.print_output(f"  {stage['slug'].replace('-', ' ').title()} "
                        f"{_type_tag(types)}{marker}  — {no_evo_note}")
    else:
        for path in display_paths:
            parts = []
            for i, stage in enumerate(path):
                types = await _get_types_for_slug(stage["slug"], ui=ui)
                marker = " ★" if stage["slug"] == current_slug else ""
                name = stage["slug"].replace("-", " ").title()
                entry = f"{name} {_type_tag(types)}{marker}"
                if i > 0 and stage["trigger"]:
                    parts.append(f"→  {stage['trigger']}  →  {entry}")
                else:
                    parts.append(entry)
            await ui.print_output("  " + "  ".join(parts))

    await ui.print_output("")
    await ui.print_output("  ★ = current Pokémon")


# ── Core display ──────────────────────────────────────────────────────────────

async def run(pkm_ctx: dict, game_ctx: dict, constraints: list = None, ui=None) -> None:
    """
    Display type vulnerabilities and resistances.
    Called from pokemain with both contexts already loaded.
    """
    if ui is None:
        # Fallback dummy UI for standalone
        import builtins
        class DummyUI:
            async def print_output(self, text, end="\n"): builtins.print(text, end=end)
            async def input_prompt(self, prompt): return builtins.input(prompt)
            async def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
        ui = DummyUI()

    await ui.print_session_header(pkm_ctx, game_ctx, constraints)

    form_name  = pkm_ctx.get("form_name", pkm_ctx.get("pokemon", ""))
    base_stats = pkm_ctx.get("base_stats", {})
    abilities  = pkm_ctx.get("abilities", [])

    await _print_base_stats(ui, base_stats, form_name)
    await _print_abilities_section(ui, abilities, form_name)

    # Egg groups — shown when egg_groups field is present
    egg_groups = pkm_ctx.get("egg_groups", [])
    if egg_groups:
        await ui.print_output(f"\n  Egg groups — {form_name}")
        await ui.print_output("  " + "─" * _SEP_WIDTH)
        await ui.print_output(f"  {format_egg_groups(egg_groups)}")

    # Type chart — capture and print
    chart_output = _format_type_chart(
        pkm_ctx["type1"],
        pkm_ctx["type2"],
        game_ctx["game"],
        game_ctx["era_key"]
    )
    await ui.print_output(chart_output)

    # Evolution chain — shown at the bottom of option 1
    paths = await _get_or_fetch_chain(pkm_ctx, ui=ui)
    if paths is not None:
        await _display_evolution_block(pkm_ctx, paths,
                                       game_gen=game_ctx.get("game_gen"),
                                       ui=ui)

    await ui.print_output("")
    await ui.input_prompt("\n  Press Enter to continue...")


# ── Standalone entry point ────────────────────────────────────────────────────

def main() -> None:
    print()
    print("╔══════════════════════════════════════════╗")
    print("║   Quick View: Stats / Abilities / Types  ║")
    print("╚══════════════════════════════════════════╝")

    mode = select_from_list(
        "  How do you want to specify the type?",
        ["Look up a Pokémon by name", "Enter types manually"]
    )

    if mode == "Look up a Pokemon by name":
        game_ctx = select_game()
        if game_ctx is None:
            sys.exit(0)
        pkm_ctx = select_pokemon(game_ctx=game_ctx)
        if pkm_ctx is None:
            sys.exit(0)
        # In standalone, we don't have a UI instance; we'll use a dummy
        import builtins
        class DummyUI:
            async def print_output(self, text, end="\n"): builtins.print(text, end=end)
            async def input_prompt(self, prompt): return builtins.input(prompt)
            async def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
        ui = DummyUI()
        import asyncio
        asyncio.run(run(pkm_ctx, game_ctx, ui=ui))

    else:
        # Manual type entry
        game_names  = [g[0] for g in calc.GAMES]
        game_choice = select_from_list("  Select GAME:", game_names)
        era_key     = next(g[1] for g in calc.GAMES if g[0] == game_choice)
        _, valid_types, _ = calc.CHARTS[era_key]

        type1 = select_from_list("  Select PRIMARY type:", list(valid_types))
        remaining = [t for t in valid_types if t != type1]
        type2 = select_from_list(
            "  Select SECONDARY type (or 0 for none):", remaining, allow_none=True
        )
        calc.print_results(type1, type2, game_choice, era_key)

    input("\n  Press Enter to continue...")


# ── Self‑tests (includes evolution tests) ─────────────────────────────────────

def _run_tests():
    import io, contextlib, sys as _sys
    errors = []
    def ok(label):  print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_quick_view.py — self-test\n")

    # Test stat bar and role/speed tier (already in core_stat, but we can test wrappers)
    # Not much to test here – we rely on core_stat tests.

    # Evolution tests (moved from feat_evolution.py)
    print("\n  Evolution chain tests")

    # Mock get_or_fetch_chain and type fetching to avoid network
    # Save original functions if needed, but we are replacing them only for the test
    import pkm_cache as _cache
    import core_evolution as _ce

    # Save original chain cache function to restore later
    orig_get_evolution_chain = _cache.get_evolution_chain
    orig_save_evolution_chain = _cache.save_evolution_chain

    # Dummy UI for test (async methods)
    class DummyUI:
        def __init__(self):
            self.buf = io.StringIO()
        async def print_output(self, text, end="\n"):
            self.buf.write(text + end)
        async def input_prompt(self, prompt):
            return ""
        async def confirm(self, prompt):
            return False

    # Mock flatten_chain to avoid network
    def mock_flatten_chain(node):
        return [
            [{"slug": "charmander", "trigger": ""},
             {"slug": "charmeleon", "trigger": "Level 16"},
             {"slug": "charizard", "trigger": "Level 36"}]
        ]

    # Mock _get_types_for_slug
    async def mock_get_types(slug, ui=None):
        return {"charmander": ["Fire"], "charmeleon": ["Fire"],
                "charizard": ["Fire", "Flying"], "eevee": ["Normal"],
                "espeon": ["Psychic"], "umbreon": ["Dark"]}.get(slug, [])

    # Monkey-patch dependencies for the test
    _orig_flatten = _ce.flatten_chain
    _ce.flatten_chain = mock_flatten_chain
    _orig_get_types = globals()["_get_types_for_slug"]
    globals()["_get_types_for_slug"] = mock_get_types

    # Monkey-patch cache to return a fake chain
    def mock_get_evolution_chain(chain_id):
        if chain_id == 1:
            return [
                [{"slug": "charmander", "trigger": ""},
                 {"slug": "charmeleon", "trigger": "Level 16"},
                 {"slug": "charizard", "trigger": "Level 36"}]
            ]
        return None

    _cache.get_evolution_chain = mock_get_evolution_chain

    try:
        pkm_charizard = {"pokemon": "charizard", "evolution_chain_id": 1}
        dummy = DummyUI()
        import asyncio
        async def run_display():
            paths = await _get_or_fetch_chain(pkm_charizard, ui=dummy)
            await _display_evolution_block(pkm_charizard, paths, ui=dummy)
        asyncio.run(run_display())
        out = dummy.buf.getvalue()

        if "Charmander" in out and "Charmeleon" in out and "Charizard" in out:
            ok("evolution: all stage names present")
        else:
            fail("evolution: all stage names present", out[:120])

        if "★" in out:
            ok("evolution: ★ marker present")
        else:
            fail("evolution: ★ marker present", out[:120])

        if "[Fire / Flying]" in out:
            ok("evolution: type tags shown")
        else:
            fail("evolution: type tags shown", out[:120])

        if "Level 16" in out and "Level 36" in out:
            ok("evolution: triggers shown")
        else:
            fail("evolution: triggers shown", out[:120])

    finally:
        # Restore original functions
        _cache.get_evolution_chain = orig_get_evolution_chain
        _cache.save_evolution_chain = orig_save_evolution_chain
        _ce.flatten_chain = _orig_flatten
        globals()["_get_types_for_slug"] = _orig_get_types

    print()
    total = 4  # number of evolution tests
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