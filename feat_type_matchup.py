#!/usr/bin/env python3
"""
feat_type_matchup.py — Quick view: base stats, abilities, type matchup

When a Pokémon is loaded, displays:
  1. Base stats (HP / Atk / Def / SpA / SpD / Spe + total)
  2. Abilities with short effects
  3. Type vulnerabilities and resistances

In manual-type mode (standalone, no Pokémon), only the type chart is shown.

Entry points:
  run(pkm_ctx, game_ctx)  — called from the main menu (key 1)
  main()                  — standalone

Standalone usage:
    python feat_type_matchup.py
"""

import sys

try:
    import matchup_calculator as calc
    from pkm_session import select_game, select_pokemon, select_from_list, print_session_header
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Base stats display ───────────────────────────────────────────────────────

_STAT_LABELS = [
    ("hp",             "HP"),
    ("attack",         "Atk"),
    ("defense",        "Def"),
    ("special-attack", "SpA"),
    ("special-defense","SpD"),
    ("speed",          "Spe"),
]
_BAR_MAX   = 255   # maximum possible base stat
_BAR_WIDTH = 20    # visual bar width in chars


def _stat_bar(value: int) -> str:
    """Return a simple ASCII progress bar for a base stat value."""
    filled = round(value / _BAR_MAX * _BAR_WIDTH)
    return "[" + "█" * filled + "·" * (_BAR_WIDTH - filled) + "]"


def _print_base_stats(base_stats: dict, form_name: str) -> None:
    """Print base stats as a labelled bar chart."""
    if not base_stats:
        return
    print(f"\n  Base stats — {form_name}")
    print("  " + "─" * 46)
    total = 0
    for key, label in _STAT_LABELS:
        val = base_stats.get(key, 0)
        total += val
        bar = _stat_bar(val)
        print(f"  {label:<4}  {val:>3}  {bar}")
    print("  " + "─" * 46)
    print(f"  {'Total':>8}  {total:>3}")


# ── Abilities display ─────────────────────────────────────────────────────────

def _print_abilities_section(abilities: list, form_name: str) -> None:
    """Print abilities with short effects, using the ability index for names/effects."""
    if not abilities:
        return
    try:
        import pkm_cache as _cache
        index = _cache.get_abilities_index()
    except Exception:
        index = None

    print(f"\n  Abilities — {form_name}")
    print("  " + "─" * 46)
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
        print(f"  {name}{tag}")
        if effect:
            print(f"    {effect}")


# ── Core display ──────────────────────────────────────────────────────────────

def run(pkm_ctx: dict, game_ctx: dict, constraints: list = None) -> None:
    """
    Display type vulnerabilities and resistances.
    Called from pokemain with both contexts already loaded.
    """
    print_session_header(pkm_ctx, game_ctx, constraints)

    form_name  = pkm_ctx.get("form_name", pkm_ctx.get("pokemon", ""))
    base_stats = pkm_ctx.get("base_stats", {})
    abilities  = pkm_ctx.get("abilities", [])

    _print_base_stats(base_stats, form_name)
    _print_abilities_section(abilities, form_name)

    calc.print_results(
        pkm_ctx["type1"],
        pkm_ctx["type2"],
        game_ctx["game"],
        game_ctx["era_key"]
    )


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
        run(pkm_ctx, game_ctx)

    else:
        # Manual type entry — mirrors the original matchup_calculator.py flow
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