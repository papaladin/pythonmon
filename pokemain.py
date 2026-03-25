#!/usr/bin/env python3
"""
pokemain.py  Pokemon Toolkit main entry point

State: pkm_ctx and game_ctx are independent, either can be None.

  State 0 (nothing):  Load Pokemon / Select game / Look up move / Refresh moves
  State 1 (game only): same + Look up move uses game context
  State 2 (pkm only):  Load different / Refresh Pokemon / Select game
  State 3 (both):      Full feature set

Feature gates:
  1–4. Pokemon features       → needs Pokemon + game
  M.   Move lookup            → needs game only
  B.   Type browser           → no context needed
  N.   Nature & EV advisor    → no context needed (enriched when Pokemon loaded)
  A.   Ability browser        → no context needed (enriched when Pokemon loaded)
  L.   Learnset comparison    → needs Pokemon + game
  E.   Egg group browser      → needs Pokemon
  T.   Team management        → needs game
  V/O/S/H/X. Team features    → needs team + game
"""

import sys

try:
    import matchup_calculator as calc
    from pkm_session import (select_game, select_pokemon, refresh_pokemon,
                             print_session_header)
    import feat_quick_view
    import feat_moveset
    import feat_movepool
    import feat_move_lookup
    import feat_type_browser
    import feat_nature_browser
    import feat_ability_browser
    import feat_team_loader
    import feat_team_analysis
    import feat_team_offense
    import feat_team_moveset
    import feat_learnset_compare
    import feat_egg_group
    import feat_evolution
    import feat_team_builder
    import feat_opponent
    import pkm_cache as cache
    import pkm_pokeapi
    from ui_cli import CLI
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Feature registry ──────────────────────────────────────────────────────────
# (label, module, entry_point, needs_pkm, needs_game, available)

PKM_FEATURES = [
    ("Quick view  (stats / abilities / types)", feat_quick_view, "run",         True,  True,  True),
    ("Learnable move list (conditions)",   feat_movepool,     "run",              True,  True,  True),
    ("Learnable move list (scored)",       feat_moveset,      "run_scored_pool",  True,  True,  True),
    ("Moveset recommendation",             feat_moveset,      "run",              True,  True,  True),
]


# ── Stats line formatter ──────────────────────────────────────────────────────

def _format_stats(base_stats):
    if not base_stats:
        return ""
    hp   = base_stats.get("hp", "?")
    atk  = base_stats.get("attack", "?")
    def_ = base_stats.get("defense", "?")
    spa  = base_stats.get("special-attack", "?")
    spd  = base_stats.get("special-defense", "?")
    spe  = base_stats.get("speed", "?")
    try:    total = str(hp + atk + def_ + spa + spd + spe)
    except (TypeError, ValueError): total = "?"
    return f"HP{hp} Atk{atk} Def{def_} SpA{spa} SpD{spd} Spe{spe}  Total {total}"


# ── Menu renderers ────────────────────────────────────────────────────────────

W = 52              # inner width of the menu box
_CACHE_SEP_WIDTH = 46   # separator width in the --cache-info display

# All valid menu choices.  Used as documentation and to keep the dispatcher
# in sync; the elif chain in main() is the authoritative handler.
_MENU_CHOICES = frozenset({
    "q",    # quit
    "p",    # load pokemon
    "g",    # select game
    "r",    # refresh pokemon
    "t",    # team management
    "v",    # team defensive analysis
    "o",    # team offensive coverage
    "s",    # team moveset synergy
    "h",    # team builder suggestions
    "x",    # opponent analysis
    "m",    # move lookup
    "b",    # type browser
    "n",    # nature browser
    "a",    # ability browser
    "l",    # learnset compare
    "e",    # egg group browser
    "move", # pre-load move table (multi-char key)
    "w",    # pre-load TM/HM table
})

def _build_context_lines(pkm_ctx, game_ctx, team_ctx=None):
    """Build the list of context lines to display in the menu."""
    lines = []
    if pkm_ctx:
        dual = (f"{pkm_ctx['type1']} / {pkm_ctx['type2']}"
                if pkm_ctx["type2"] != "None" else pkm_ctx["type1"])
        lines.append(f"{pkm_ctx['form_name']}  •  {dual}")
        stats_line = _format_stats(pkm_ctx.get("base_stats", {}))
        if stats_line:
            lines.append(stats_line)
    if not pkm_ctx:
        lines.append("No Pokemon loaded")
    if game_ctx:
        lines.append(game_ctx["game"])
    elif not pkm_ctx:
        lines.append("No game selected")
    if team_ctx is not None:
        filled  = feat_team_loader.team_size(team_ctx)
        summary = feat_team_loader.team_summary_line(team_ctx)
        lines.append(f"Team ({filled}/6): {summary}")
    return lines


def _build_menu_lines(pkm_ctx, game_ctx, team_ctx=None):
    """Build the list of menu lines (including context and options)."""
    has_pkm  = pkm_ctx is not None
    has_game = game_ctx is not None
    both     = has_pkm and has_game
    has_team = team_ctx is not None and feat_team_loader.team_size(team_ctx) > 0

    lines = []

    # ── Always‑visible core actions ─────────────────────────────────────────
    # Select game / change game
    lines.append("G. Select game" if not has_game else "G. Change game")
    # Load Pokemon
    lines.append("P. Load a Pokemon" if not has_pkm else "P. Load a different Pokemon")
    # Manage team (always shown, but team loader requires game)
    lines.append("T. Manage team")
    # Separator
    lines.append("─" * (W+2))

    # ── Features that need game only (or no context) ────────────────────────
    if has_game:
        lines.append("M. Look up a move")
    lines.append("B. Browse Pokémon by type")
    lines.append("N. Nature & EV build advisor")
    lines.append("A. Ability browser")
    lines.append("")  # blank line for grouping

    # ── Features that need a Pokemon (and maybe game) ───────────────────────
    if has_pkm:
        lines.append("E. Egg group browser")
    if both:
        lines.append("L. Compare learnsets  (pick a second Pokémon)")
    # Add a blank line if we have any of these
    if has_pkm or both:
        lines.append("")

    # ── Numbered features (need both Pokemon and game) ──────────────────────
    if both:
        for i, (label, _mod, _fn, np, ng, avail) in enumerate(PKM_FEATURES, start=1):
            if avail:
                lines.append(f"{i}. {label}")
            else:
                short = label[:W-18]
                lines.append(f"   {short:<{W-18}}  [coming soon]")
        lines.append("")

    # ── Team features (need team and game) ──────────────────────────────────
    if has_team and has_game:
        lines.append("V. Team defensive vulnerability analysis")
        lines.append("O. Team offensive coverage")
        lines.append("S. Team moveset synergy")
        lines.append("H. Team builder  (suggest next slot)")
        lines.append("X. Team vs in-game opponent")
        lines.append("")

    # ── Cache utilities (always visible) ────────────────────────────────────
    lines.append("MOVE. Pre-load move table  (stats for all ~920 moves)")
    lines.append("W.    Pre-load TM/HM table (TM numbers in move lists)")
    if has_pkm:
        lines.append("R. Refresh data for current Pokemon")
    lines.append("")
    lines.append("Q. Quit")

    # Remove duplicate empty lines while preserving order
    seen = set()
    result = []
    for ln in lines:
        if ln == "":
            # Keep only one consecutive empty line
            if result and result[-1] == "":
                continue
            result.append(ln)
            continue
        if ln in seen:
            continue
        result.append(ln)
        seen.add(ln)
    return result


# ── Chained context acquisition ───────────────────────────────────────────────

def _ensure_game(ui, game_ctx, pkm_ctx=None):
    """If game_ctx is None, prompt for a game. Returns game_ctx (possibly new)."""
    if game_ctx is not None:
        return game_ctx
    ui.print_output("This feature needs a game selected first.")
    return ui.select_game(pkm_ctx=pkm_ctx)

def _ensure_pokemon(ui, pkm_ctx, game_ctx):
    """If pkm_ctx is None, prompt for a Pokemon. Returns pkm_ctx (possibly new)."""
    if pkm_ctx is not None:
        return pkm_ctx
    ui.print_output("This feature needs a Pokemon loaded first.")
    return ui.select_pokemon(game_ctx=game_ctx)


# ── Main loop ─────────────────────────────────────────────────────────────────

def _handle_diagnostic_flags(ui, args: list) -> None:
    """
    Handle flags that print information and exit immediately.
    Calls sys.exit(0) if a diagnostic flag is present; returns normally otherwise.
    """
    if "--help" in args or "-h" in args:
        ui.print_output("""
Pokemon Toolkit — Command-line interface for in-game Pokemon analysis

Usage: python pokemain.py [OPTIONS]

Options:
  --help, -h            Show this help message and exit
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

    if "--cache-info" in args:
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
        ui.print_output("\nCache contents:")
        ui.print_output("─" * _CACHE_SEP_WIDTH)
        for key, label in labels:
            val  = info.get(key, 0)
            note = moves_note if key == "moves" else ""
            ui.print_output(f"{label:<20}: {val:>5}{note}")
        ui.print_output("─" * _CACHE_SEP_WIDTH)
        total = sum(info.values())
        ui.print_output(f"{'Total':<20}: {total:>5}")
        sys.exit(0)

    if "--check-cache" in args:
        issues = cache.check_integrity()
        if issues:
            ui.print_output(f"\nCache integrity: {len(issues)} issue(s) found:")
            for issue in issues:
                ui.print_output(f"  • {issue}")
        else:
            ui.print_output("\nCache integrity: clean — no issues found.")
        sys.exit(0)


def _handle_refresh_flags(ui, args: list) -> None:
    """
    Handle cache mutation flags. Always returns normally.
    """
    if "--refresh-moves" in args:
        cache.invalidate_moves()
    if "--refresh-pokemon" in args:
        idx = args.index("--refresh-pokemon")
        if idx + 1 < len(args):
            cache.invalidate_pokemon(args[idx + 1])
        else:
            ui.print_output("Usage: --refresh-pokemon <n>")
    if "--refresh-learnset" in args:
        idx = args.index("--refresh-learnset")
        if idx + 2 < len(args):
            cache.invalidate_learnset(args[idx+1], args[idx+2])
        else:
            ui.print_output("Usage: --refresh-learnset <n> <game>")
    if "--refresh-all" in args:
        idx = args.index("--refresh-all")
        if idx + 1 < len(args):
            cache.invalidate_all(args[idx + 1])
        else:
            ui.print_output("Usage: --refresh-all <n>")
    if "--refresh-evolution" in args:
        idx = args.index("--refresh-evolution")
        if idx + 1 < len(args):
            name = args[idx + 1]
            data = cache.get_pokemon(name)
            if data is None:
                ui.print_output(f"'{name}' not in cache — nothing to refresh.")
            else:
                chain_id = data.get("evolution_chain_id")
                if chain_id is None:
                    ui.print_output(f"No evolution chain ID for '{name}'.")
                else:
                    cache.invalidate_evolution_chain(chain_id)
                    ui.print_output(f"Evolution chain for '{name}' invalidated.")
        else:
            ui.print_output("Usage: --refresh-evolution <n>")


def main():
    ui = CLI()

    _handle_diagnostic_flags(ui, sys.argv[1:])
    _handle_refresh_flags(ui, sys.argv[1:])
    ui.print_header()

    # Offline mode detection (Pythonmon-18): probe only when cache is sparse
    # so regular well-cached sessions don't pay a 3-second probe cost each run.
    _cache_info = cache.get_cache_info()
    if _cache_info.get("pokemon", 0) < 5:
        if not pkm_pokeapi.check_connectivity():
            ui.print_output("⚠  PokeAPI unreachable — running from cache only.")
            ui.print_output("   New Pokémon and moves cannot be fetched this session.")
            ui.print_output()

    pkm_ctx    = None
    game_ctx   = None
    team_ctx   = feat_team_loader.new_team()
    pool_cache = {}   # session-level damage pool cache shared by O and S screens

    # ── --game flag: pre-select game ──────────────────────────────────────────
    if "--game" in sys.argv:
        idx = sys.argv.index("--game")
        if idx + 1 >= len(sys.argv):
            ui.print_output("ERROR: --game requires a game name argument.")
            sys.exit(1)
        game_name = sys.argv[idx + 1]
        try:
            from pkm_session import make_game_ctx
            game_ctx = make_game_ctx(game_name)
            ui.print_output(f"Pre-selected game: {game_name}")
        except ValueError as e:
            ui.print_output(f"ERROR: {e}")
            sys.exit(1)

    while True:
        # Build menu lines
        context_lines = _build_context_lines(pkm_ctx, game_ctx, team_ctx)
        menu_lines = _build_menu_lines(pkm_ctx, game_ctx, team_ctx)
        # Combine context and menu with a separator
        full_lines = context_lines + ["─" * (W+2)] + menu_lines
        ui.print_menu(full_lines)

        choice = ui.input_prompt("Choice: ").lower()

        if choice == "q":
            ui.print_output("Goodbye!\n")
            sys.exit(0)

        # ── Context management ────────────────────────────────────────────────

        elif choice == "p":
            new = ui.select_pokemon(game_ctx=game_ctx)
            if new is not None:
                pkm_ctx = new
                # Offer to add to team immediately (Pythonmon-5)
                if game_ctx is not None and feat_team_loader.team_size(team_ctx) < 6:
                    add = ui.confirm(f"\nAdd {pkm_ctx['form_name']} to team?")
                    if add:
                        try:
                            team_ctx, slot = feat_team_loader.add_to_team(team_ctx, pkm_ctx)
                            ui.print_output(f"Added to slot {slot + 1}.")
                        except feat_team_loader.TeamFullError:
                            pass

        elif choice == "g":
            new = ui.select_game(pkm_ctx=pkm_ctx)
            if new is not None:
                game_ctx = new

        elif choice == "r":
            if pkm_ctx is None:
                ui.print_output("No Pokemon loaded to refresh.")
            else:
                chain_id = pkm_ctx.get("evolution_chain_id")
                if chain_id is not None:
                    cache.invalidate_evolution_chain(chain_id)
                pkm_ctx = refresh_pokemon(pkm_ctx, game_ctx=game_ctx)

        elif choice == "t":
            if game_ctx is None:
                ui.print_output("Please select a game first (press G).")
            else:
                team_ctx = feat_team_loader.run(ui, game_ctx, team_ctx)

        elif choice == "v":
            if game_ctx is None:
                ui.print_output("Select a game first (press G).")
            elif feat_team_loader.team_size(team_ctx) == 0:
                ui.print_output("Load a team first (press T).")
            else:
                feat_team_analysis.run(team_ctx, game_ctx, ui=ui)

        elif choice == "o":
            if game_ctx is None:
                ui.print_output("Select a game first (press G).")
            elif feat_team_loader.team_size(team_ctx) == 0:
                ui.print_output("Load a team first (press T).")
            else:
                feat_team_offense.run(team_ctx, game_ctx, pool_cache=pool_cache, ui=ui)

        elif choice == "s":
            if game_ctx is None:
                ui.print_output("Select a game first (press G).")
            elif feat_team_loader.team_size(team_ctx) == 0:
                ui.print_output("Load a team first (press T).")
            else:
                feat_team_moveset.run(team_ctx, game_ctx, pool_cache=pool_cache, ui=ui)

        elif choice == "h":
            if game_ctx is None:
                ui.print_output("Select a game first (press G).")
            elif feat_team_loader.team_size(team_ctx) == 0:
                ui.print_output("Load a team first (press T).")
            else:
                feat_team_builder.run(team_ctx, game_ctx, ui=ui)

        elif choice == "x":
            if game_ctx is None:
                ui.print_output("Select a game first (press G).")
            elif feat_team_loader.team_size(team_ctx) == 0:
                ui.print_output("Load a team first (press T).")
            else:
                feat_opponent.run(team_ctx, game_ctx, ui=ui)

        elif choice == "move":
            existing   = cache.get_moves()
            n_existing = len(existing) if existing else 0
            if n_existing > 0:
                ui.print_output(f"\nMove table has {n_existing} moves cached.")
                ui.print_output("F — fetch missing moves only")
                ui.print_output("R — re-fetch all moves (overwrite)")
                ui.print_output("Enter — cancel")
                sub = ui.input_prompt("Choice: ").lower()
            else:
                ui.print_output("\nThis fetches type, power, accuracy and PP for all ~920 moves.")
                ui.print_output("Moves are also fetched lazily on first lookup — this just")
                ui.print_output("avoids any wait when browsing move lists or learnsets.\n")
                confirm = ui.confirm("Proceed?")
                sub = "r" if confirm else ""

            if sub == "f":
                try:
                    moves = pkm_pokeapi.fetch_missing_moves()
                    if moves:
                        cache.upsert_move_batch(moves)
                        ui.print_output(f"Done — {len(moves)} missing move(s) cached.")
                    else:
                        ui.print_output("All moves already cached — nothing to do.")
                except ConnectionError as e:
                    ui.print_output(f"Connection error: {e}")
            elif sub == "r":
                try:
                    moves = pkm_pokeapi.fetch_all_moves()
                    cache.save_moves(moves)
                    ui.print_output(f"Done — {len(moves)} moves cached.")
                except ConnectionError as e:
                    ui.print_output(f"Connection error: {e}")

        elif choice == "w":
            existing = cache.get_machines()
            if existing:
                n = sum(len(v) for v in existing.values())
                ui.print_output(f"\nTM/HM table already cached ({n} entries across {len(existing)} games).")
                confirm = ui.confirm("Re-fetch and overwrite?")
            else:
                ui.print_output("\nThis fetches TM/HM numbers for all games (~900 entries).")
                ui.print_output("Required for TM numbers to appear in the learnable move list.")
                ui.print_output("After fetching, press R on any Pokemon to reload their learnset")
                ui.print_output("with TM numbers included.\n")
                confirm = ui.confirm("Proceed?")
            if confirm:
                try:
                    machines = pkm_pokeapi.fetch_machines()
                    cache.save_machines(machines)
                    total = sum(len(v) for v in machines.values())
                    ui.print_output(f"Done — {total} TM/HM entries across {len(machines)} games cached.")
                except ConnectionError as e:
                    ui.print_output(f"Connection error: {e}")

        # ── Move lookup (needs game) ──────────────────────────────────────────

        elif choice == "m":
            if game_ctx is None:
                ui.print_output("Select a game first (press G).")
                continue
            feat_move_lookup.run(game_ctx, ui=ui)

        elif choice == "b":
            feat_type_browser.run(game_ctx=game_ctx, ui=ui)

        elif choice == "n":
            feat_nature_browser.run(game_ctx=game_ctx, pkm_ctx=pkm_ctx, ui=ui)

        elif choice == "a":
            feat_ability_browser.run(game_ctx=game_ctx, pkm_ctx=pkm_ctx, ui=ui)

        elif choice == "l":
            if pkm_ctx is None:
                ui.print_output("Load a Pokemon first (press P).")
            elif game_ctx is None:
                ui.print_output("Select a game first (press G).")
            else:
                feat_learnset_compare.run(pkm_ctx, game_ctx, ui=ui)

        elif choice == "e":
            if pkm_ctx is None:
                ui.print_output("Load a Pokemon first (press P).")
            else:
                feat_egg_group.run(pkm_ctx, ui=ui)

        # ── Pokemon-dependent features ────────────────────────────────────────

        elif choice.isdigit():
            idx = int(choice)
            if idx < 1 or idx > len(PKM_FEATURES):
                ui.print_output("Invalid choice, try again.")
                continue

            label, module, entry_fn, needs_pkm, needs_game, avail = PKM_FEATURES[idx - 1]
            if not avail:
                ui.print_output(f"'{label}' is not yet available.")
                continue

            # Chain: acquire missing context before running
            if needs_game:
                game_ctx = _ensure_game(ui, game_ctx, pkm_ctx=pkm_ctx)
                if game_ctx is None:
                    continue
            if needs_pkm:
                pkm_ctx = _ensure_pokemon(ui, pkm_ctx, game_ctx)
                if pkm_ctx is None:
                    continue

            getattr(module, entry_fn)(pkm_ctx, game_ctx, ui=ui)

        else:
            ui.print_output("Invalid choice, try again.")


if __name__ == "__main__":
    main()