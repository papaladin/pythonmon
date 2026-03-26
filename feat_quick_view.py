#!/usr/bin/env python3
"""
feat_quick_view.py — Quick view: base stats, abilities, type matchup

When a Pokémon is loaded, displays:
  1. Base stats (HP / Atk / Def / SpA / SpD / Spe + total)
  2. Abilities with short effects
  3. Type vulnerabilities and resistances

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
    import io
    import contextlib
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        calc.print_results(type1, type2, game, era_key)
    return f.getvalue()


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
    from feat_evolution import get_or_fetch_chain, display_evolution_block
    paths = await get_or_fetch_chain(pkm_ctx, ui=ui)  # <-- ADDED AWAIT
    if paths is not None:
        await display_evolution_block(pkm_ctx, paths,
                                      game_gen=game_ctx.get("game_gen"),
                                      ui=ui)

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


if __name__ == "__main__":
    main()