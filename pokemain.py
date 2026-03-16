#!/usr/bin/env python3
"""
pokemain.py  Pokemon Toolkit main entry point

State: pkm_ctx and game_ctx are independent, either can be None.

  State 0 (nothing):  Load Pokemon / Select game / Look up move / Refresh moves
  State 1 (game only): same + Look up move uses game context
  State 2 (pkm only):  Load different / Refresh Pokemon / Select game
  State 3 (both):      Full feature set

Feature gates:
  1. Quick view (stats / abilities / types)  → needs both
  2. Learnable move list (conditions)    → needs both
  3. Learnable move list (scored)        → needs both
  4. Moveset recommendation              → needs both
  M. Look up a move                      → needs game only
  B. Type browser                        → no context needed
  N. Nature browser / recommender        → no context needed
  T. Pre-load move table                 → no context needed
  W. Pre-load TM/HM table               → no context needed
"""

import sys

try:
    import matchup_calculator as calc
    from pkm_session import (select_game, select_pokemon, refresh_pokemon,
                             print_session_header)
    import feat_type_matchup
    import feat_moveset
    import feat_movepool
    import feat_move_lookup
    import feat_type_browser
    import feat_nature_browser
    import feat_ability_browser
    import feat_team_loader
    import feat_team_analysis
    import feat_team_offense
    import pkm_cache as cache
    import pkm_pokeapi
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Feature registry ──────────────────────────────────────────────────────────
# (label, module, entry_point, needs_pkm, needs_game, available)

PKM_FEATURES = [
    ("Quick view  (stats / abilities / types)", feat_type_matchup, "run",         True,  True,  True),
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
    except: total = "?"
    return f"HP{hp} Atk{atk} Def{def_} SpA{spa} SpD{spd} Spe{spe}  Total {total}"


# ── Menu renderers ────────────────────────────────────────────────────────────

W = 52   # inner width of the menu box

def _box_line(text=""):
    return f"│  {text:<{W}}│"

def _banner():
    print()
    print("╔" + "═"*(W+2) + "╗")
    print(_box_line("Pokemon Toolkit"))
    print("╚" + "═"*(W+2) + "╝")

def _sep():
    print("├" + "─"*(W+2) + "┤")

def _top():
    print("┌" + "─"*(W+2) + "┐")

def _bot():
    print("└" + "─"*(W+2) + "┘")

def _print_context_lines(pkm_ctx, game_ctx, team_ctx=None):
    """Print the top info lines inside the menu box."""
    if pkm_ctx:
        dual = (f"{pkm_ctx['type1']} / {pkm_ctx['type2']}"
                if pkm_ctx["type2"] != "None" else pkm_ctx["type1"])
        print(_box_line(f"{pkm_ctx['form_name']}  •  {dual}"))
        stats_line = _format_stats(pkm_ctx.get("base_stats", {}))
        if stats_line:
            print(_box_line(stats_line))
    if not pkm_ctx:
        print(_box_line("No Pokemon loaded"))
    if game_ctx:
        print(_box_line(game_ctx["game"]))
    elif not pkm_ctx:
        print(_box_line("No game selected"))
    # Team summary
    if team_ctx is not None:
        filled  = feat_team_loader.team_size(team_ctx)
        summary = feat_team_loader.team_summary_line(team_ctx)
        print(_box_line(f"Team ({filled}/6): {summary}"))

def _print_menu(pkm_ctx, game_ctx, team_ctx=None):
    has_pkm  = pkm_ctx is not None
    has_game = game_ctx is not None
    both     = has_pkm and has_game
    print()
    _top()
    _print_context_lines(pkm_ctx, game_ctx, team_ctx)
    _sep()

    # Pokemon-dependent features — only shown when both contexts are loaded
    if both:
        for i, (label, _mod, _fn, np, ng, avail) in enumerate(PKM_FEATURES, start=1):
            if avail:
                print(_box_line(f"{i}. {label}"))
            else:
                short = label[:W-18]
                print(_box_line(f"   {short:<{W-18}}  [coming soon]"))
        print(_box_line())

    # Move lookup — only shown when game is loaded
    if has_game:
        print(_box_line("M. Look up a move"))
    print(_box_line("B. Browse Pokémon by type"))
    print(_box_line("N. Browse natures / recommend for current Pokémon"))
    print(_box_line("A. Ability browser"))

    # Context management
    if has_pkm:
        print(_box_line("P. Load a different Pokemon"))
        print(_box_line("R. Refresh data for current Pokemon"))
    else:
        print(_box_line("P. Load a Pokemon"))

    if has_game:
        print(_box_line("G. Change game"))
    else:
        print(_box_line("G. Select game"))

    print(_box_line("T. Manage team  (load up to 6 Pokémon)"))
    if team_ctx is not None and feat_team_loader.team_size(team_ctx) > 0:
        print(_box_line("V. Team defensive vulnerability analysis"))
        print(_box_line("O. Team offensive coverage"))
    print(_box_line("MOVE. Pre-load move table  (stats for all ~920 moves)"))
    print(_box_line("W.    Pre-load TM/HM table (TM numbers in move lists)"))
    print(_box_line())
    print(_box_line("Q. Quit"))
    _bot()


# ── Chained context acquisition ───────────────────────────────────────────────

def _ensure_game(game_ctx, pkm_ctx=None):
    """If game_ctx is None, prompt for a game. Returns game_ctx (possibly new)."""
    if game_ctx is not None:
        return game_ctx
    print("\n  This feature needs a game selected first.")
    return select_game(pkm_ctx=pkm_ctx)

def _ensure_pokemon(pkm_ctx, game_ctx):
    """If pkm_ctx is None, prompt for a Pokemon. Returns pkm_ctx (possibly new)."""
    if pkm_ctx is not None:
        return pkm_ctx
    print("\n  This feature needs a Pokemon loaded first.")
    return select_pokemon(game_ctx=game_ctx)


# ── Main loop ─────────────────────────────────────────────────────────────────

def _handle_refresh_flags(args):
    if "--refresh-moves" in args:
        cache.invalidate_moves()
    if "--refresh-pokemon" in args:
        idx = args.index("--refresh-pokemon")
        if idx + 1 < len(args):
            cache.invalidate_pokemon(args[idx + 1])
        else:
            print("  Usage: --refresh-pokemon <name>")
    if "--refresh-learnset" in args:
        idx = args.index("--refresh-learnset")
        if idx + 2 < len(args):
            cache.invalidate_learnset(args[idx+1], args[idx+2])
        else:
            print("  Usage: --refresh-learnset <name> <game>")
    if "--refresh-all" in args:
        idx = args.index("--refresh-all")
        if idx + 1 < len(args):
            cache.invalidate_all(args[idx + 1])
        else:
            print("  Usage: --refresh-all <name>")


def main():
    _handle_refresh_flags(sys.argv[1:])
    _banner()

    pkm_ctx     = None
    game_ctx    = None
    team_ctx    = feat_team_loader.new_team()
    while True:
        _print_menu(pkm_ctx, game_ctx, team_ctx)
        choice = input("\n  Choice: ").strip().lower()

        if choice == "q":
            print("\n  Goodbye!\n")
            sys.exit(0)

        # ── Context management ────────────────────────────────────────────────

        elif choice == "p":
            new = select_pokemon(game_ctx=game_ctx)
            if new is not None:
                pkm_ctx = new

        elif choice == "g":
            new = select_game(pkm_ctx=pkm_ctx)
            if new is not None:
                game_ctx = new

        elif choice == "r":
            if pkm_ctx is None:
                print("\n  No Pokemon loaded to refresh.")
            else:
                pkm_ctx = refresh_pokemon(pkm_ctx, game_ctx=game_ctx)

        elif choice == "t":
            if game_ctx is None:
                print("\n  Please select a game first (press G).")
            else:
                team_ctx = feat_team_loader.run(game_ctx, team_ctx)

        elif choice == "v":
            if game_ctx is None:
                print("\n  Select a game first (press G).")
            elif feat_team_loader.team_size(team_ctx) == 0:
                print("\n  Load a team first (press T).")
            else:
                feat_team_analysis.run(team_ctx, game_ctx)

        elif choice == "o":
            if game_ctx is None:
                print("\n  Select a game first (press G).")
            elif feat_team_loader.team_size(team_ctx) == 0:
                print("\n  Load a team first (press T).")
            else:
                feat_team_offense.run(team_ctx, game_ctx)

        elif choice == "move":
            existing = cache.get_moves()
            n_existing = len(existing) if existing else 0
            if n_existing > 0:
                print(f"\n  Move table already has {n_existing} moves cached.")
                confirm = input("  Re-fetch and overwrite? (y/n): ").strip().lower()
            else:
                print("\n  This fetches type, power, accuracy and PP for all ~920 moves.")
                print("  Moves are also fetched lazily on first lookup — this just")
                print("  avoids any wait when browsing move lists or learnsets.\n")
                confirm = input("  Proceed? (y/n): ").strip().lower()
            if confirm == "y":
                try:
                    moves = pkm_pokeapi.fetch_all_moves()
                    cache.save_moves(moves)
                    print(f"  Done — {len(moves)} moves cached.")
                except ConnectionError as e:
                    print(f"  Connection error: {e}")

        elif choice == "w":
            existing = cache.get_machines()
            if existing:
                n = sum(len(v) for v in existing.values())
                print(f"\n  TM/HM table already cached ({n} entries across {len(existing)} games).")
                confirm = input("  Re-fetch and overwrite? (y/n): ").strip().lower()
            else:
                print("\n  This fetches TM/HM numbers for all games (~900 entries).")
                print("  Required for TM numbers to appear in the learnable move list.")
                print("  After fetching, press R on any Pokemon to reload their learnset")
                print("  with TM numbers included.\n")
                confirm = input("  Proceed? (y/n): ").strip().lower()
            if confirm == "y":
                try:
                    machines = pkm_pokeapi.fetch_machines()
                    cache.save_machines(machines)
                    total = sum(len(v) for v in machines.values())
                    print(f"  Done — {total} TM/HM entries across {len(machines)} games cached.")
                except ConnectionError as e:
                    print(f"  Connection error: {e}")

        # ── Move lookup (needs game) ──────────────────────────────────────────

        elif choice == "m":
            if game_ctx is None:
                print("\n  Select a game first (press G).")
                continue
            feat_move_lookup.run(game_ctx)

        elif choice == "b":
            feat_type_browser.run()

        elif choice == "n":
            feat_nature_browser.run(game_ctx=game_ctx, pkm_ctx=pkm_ctx)

        elif choice == "a":
            feat_ability_browser.run(game_ctx=game_ctx, pkm_ctx=pkm_ctx)

        # ── Pokemon-dependent features ────────────────────────────────────────

        elif choice.isdigit():
            idx = int(choice)
            if idx < 1 or idx > len(PKM_FEATURES):
                print("  Invalid choice, try again.")
                continue

            label, module, entry_fn, needs_pkm, needs_game, avail = PKM_FEATURES[idx - 1]
            if not avail:
                print(f"\n  '{label}' is not yet available.")
                continue

            # Chain: acquire missing context before running
            if needs_game:
                game_ctx = _ensure_game(game_ctx, pkm_ctx=pkm_ctx)
                if game_ctx is None:
                    continue
            if needs_pkm:
                pkm_ctx = _ensure_pokemon(pkm_ctx, game_ctx)
                if pkm_ctx is None:
                    continue

            getattr(module, entry_fn)(pkm_ctx, game_ctx)

        else:
            print("  Invalid choice, try again.")


if __name__ == "__main__":
    main()