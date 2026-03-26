#!/usr/bin/env python3
"""
pokemain.py  Pokemon Toolkit main entry point
"""

import sys
import asyncio
import pkm_cache as cache
import pkm_pokeapi

async def main():
    # Quick diagnostic flags that don't require UI
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
Pokemon Toolkit — Command-line interface for in-game Pokemon analysis

Usage: python pokemain.py [OPTIONS]

Options:
  --help, -h            Show this help message and exit
  --cli                 Force classic CLI mode (default when running from source)
  --tui                 Force TUI mode (default for frozen executables)
  --cache-info          Show count of cached Pokémon, moves, learnsets, etc.
  --check-cache         Scan all cache files and report issues
  --refresh-moves       Force-refresh the full move table
  --refresh-pokemon <n> Force-refresh one Pokemon's cached data
  --refresh-learnset <n> <game>  Force-refresh one learnset
  --refresh-all <n>     Force-refresh all data for a Pokemon
  --refresh-evolution <n>  Force-refresh one Pokemon's evolution chain
  --game <name>         Pre-select a game (e.g., "Scarlet / Violet")

Run without arguments to start the interactive menu.
""")
        sys.exit(0)

    if "--cache-info" in sys.argv:
        info = cache.get_cache_info()
        labels = [
            ("pokemon",         "Pokémon"),
            ("learnsets",       "Learnsets"),
            ("moves",           "Moves"),
            ("machines",        "Machines"),
            ("types",           "Types"),
            ("natures",         "Natures"),
            ("abilities_index", "Abilities index"),
            ("abilities",       "Abilities"),
            ("egg_groups",      "Egg groups"),
            ("evolution",       "Evolution chains"),
        ]
        moves_val  = info.get("moves", 0)
        moves_note = f"  (schema v{cache.MOVES_CACHE_VERSION})" if moves_val > 0 else ""
        print("\nCache contents:")
        print("─" * 46)
        for key, label in labels:
            val  = info.get(key, 0)
            note = moves_note if key == "moves" else ""
            print(f"{label:<20}: {val:>5}{note}")
        print("─" * 46)
        total = sum(info.values())
        print(f"{'Total':<20}: {total:>5}")
        sys.exit(0)

    if "--check-cache" in sys.argv:
        issues = cache.check_integrity()
        if issues:
            print(f"\nCache integrity: {len(issues)} issue(s) found:")
            for issue in issues:
                print(f"  • {issue}")
        else:
            print("\nCache integrity: clean — no issues found.")
        sys.exit(0)

    # Handle refresh flags (these may be used together with other flags)
    if "--refresh-moves" in sys.argv:
        cache.invalidate_moves()
    if "--refresh-pokemon" in sys.argv:
        idx = sys.argv.index("--refresh-pokemon")
        if idx + 1 < len(sys.argv):
            cache.invalidate_pokemon(sys.argv[idx + 1])
        else:
            print("Usage: --refresh-pokemon <n>")
    if "--refresh-learnset" in sys.argv:
        idx = sys.argv.index("--refresh-learnset")
        if idx + 2 < len(sys.argv):
            cache.invalidate_learnset(sys.argv[idx+1], sys.argv[idx+2])
        else:
            print("Usage: --refresh-learnset <n> <game>")
    if "--refresh-all" in sys.argv:
        idx = sys.argv.index("--refresh-all")
        if idx + 1 < len(sys.argv):
            cache.invalidate_all(sys.argv[idx + 1])
        else:
            print("Usage: --refresh-all <n>")
    if "--refresh-evolution" in sys.argv:
        idx = sys.argv.index("--refresh-evolution")
        if idx + 1 < len(sys.argv):
            name = sys.argv[idx + 1]
            data = cache.get_pokemon(name)
            if data is None:
                print(f"'{name}' not in cache — nothing to refresh.")
            else:
                chain_id = data.get("evolution_chain_id")
                if chain_id is None:
                    print(f"No evolution chain ID for '{name}'.")
                else:
                    cache.invalidate_evolution_chain(chain_id)
                    print(f"Evolution chain for '{name}' invalidated.")
        else:
            print("Usage: --refresh-evolution <n>")

    # Determine UI mode
    if "--cli" in sys.argv:
        ui_mode = "cli"
    elif "--tui" in sys.argv:
        ui_mode = "tui"
    else:
        # Default: TUI for frozen apps, CLI for source runs
        ui_mode = "tui" if getattr(sys, "frozen", False) else "cli"

    if ui_mode == "tui":
        from ui_tui import TUI
        ui = TUI()
    else:
        from ui_cli import CLI
        ui = CLI()

    # Offline mode detection (only needed if cache is sparse)
    _cache_info = cache.get_cache_info()
    if _cache_info.get("pokemon", 0) < 5:
        if not pkm_pokeapi.check_connectivity():
            await ui.print_output("⚠  PokeAPI unreachable — running from cache only.")
            await ui.print_output("   New Pokémon and moves cannot be fetched this session.")
            await ui.print_output()

    # Pre‑select game if --game flag given
    if "--game" in sys.argv:
        idx = sys.argv.index("--game")
        if idx + 1 < len(sys.argv):
            game_name = sys.argv[idx + 1]
            try:
                from pkm_session import make_game_ctx
                ui.game_ctx = make_game_ctx(game_name)
                await ui.print_output(f"Pre-selected game: {game_name}")
            except ValueError as e:
                await ui.print_output(f"ERROR: {e}")
                sys.exit(1)
        else:
            await ui.print_output("ERROR: --game requires a game name argument.")
            sys.exit(1)

    await ui.run()

if __name__ == "__main__":
    asyncio.run(main())