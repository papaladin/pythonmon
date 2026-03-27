#!/usr/bin/env python3
"""
ui_cli.py  CLI implementation of the UI abstract base class.
"""

import sys
from ui_base import UI
import pkm_cache as cache
import pkm_pokeapi
from menu_builder import build_context_lines, build_menu_lines
from feat_team_loader import new_team, team_size, add_to_team, TeamFullError
from pkm_session import select_pokemon, select_game, select_form, refresh_pokemon

# Feature registry
PKM_FEATURES = [
    ("Quick view  (stats / abilities / types)", "feat_quick_view", "run", True, True, True),
    ("Learnable move list (conditions)", "feat_movepool", "run", True, True, True),
    ("Learnable move list (scored)", "feat_moveset", "run_scored_pool", True, True, True),
    ("Moveset recommendation", "feat_moveset", "run", True, True, True),
]

class CLI(UI):
    def __init__(self):
        self.pkm_ctx = None
        self.game_ctx = None
        self.team_ctx = new_team()
        self.pool_cache = {}

    async def print_header(self):
        W = 52
        def box_line(text=""):
            return f"│  {text:<{W}}│"
        print()
        print("╔" + "═"*(W+2) + "╗")
        print(box_line("Pokemon Toolkit"))
        print("╚" + "═"*(W+2) + "╝")

    async def print_menu(self, lines: list):
        W = 52
        def box_line(text=""):
            return f"│  {text:<{W}}│"
        print()
        print("┌" + "─"*(W+2) + "┐")
        for line in lines:
            if line == "─" * (W+2):
                print("├" + "─"*(W+2) + "┤")
            else:
                print(box_line(line))
        print("└" + "─"*(W+2) + "┘")

    async def print_output(self, text: str, end: str = "\n", flush: bool = False):
        print(text, end=end, flush=flush)

    async def print_progress(self, text: str, end: str = "\n", flush: bool = False):
        print(text, end=end, flush=flush)

    async def input_prompt(self, prompt: str) -> str:
        return input(prompt).strip()

    async def confirm(self, prompt: str) -> bool:
        return input(prompt + " (y/n): ").strip().lower() == "y"

    async def select_from_list(self, prompt: str, options: list, allow_none: bool = False) -> str | None:
        from pkm_session import select_from_list as _sfl
        return _sfl(prompt, options, allow_none)

    async def select_pokemon(self, game_ctx=None) -> dict | None:
        return select_pokemon(game_ctx)

    async def select_game(self, pkm_ctx=None) -> dict | None:
        return select_game(pkm_ctx)

    async def select_form(self, forms: list) -> tuple:
        return select_form(forms)

    async def print_session_header(self, pkm_ctx: dict, game_ctx: dict, constraints: list = None):
        parts = []
        if pkm_ctx:
            dual = (f"{pkm_ctx['type1']} / {pkm_ctx['type2']}"
                    if pkm_ctx["type2"] != "None" else pkm_ctx["type1"])
            parts.append(f"{pkm_ctx['form_name']}  •  {dual}")
        if game_ctx:
            parts.append(game_ctx["game"])
        if constraints:
            parts.append(f"Locked: {', '.join(constraints)}")
        await self.print_output("\n  [ " + "  •  ".join(parts) + " ]")

    async def show_error(self, message: str) -> None:
        """Display error message in CLI."""
        await self.print_output(f"\n  ERROR: {message}")

    async def run(self):
        while True:
            context_lines = build_context_lines(self.pkm_ctx, self.game_ctx, self.team_ctx)
            menu_lines = build_menu_lines(self.pkm_ctx, self.game_ctx, self.team_ctx, PKM_FEATURES)
            full_lines = context_lines + ["─" * (52+2)] + menu_lines
            await self.print_menu(full_lines)

            choice = (await self.input_prompt("Choice: ")).lower()

            if choice == "q":
                await self.print_output("Goodbye!\n")
                sys.exit(0)

            elif choice == "p":
                new = await self.select_pokemon(game_ctx=self.game_ctx)
                if new is not None:
                    self.pkm_ctx = new
                    if self.game_ctx is not None and team_size(self.team_ctx) < 6:
                        add = await self.confirm(f"\nAdd {self.pkm_ctx['form_name']} to team?")
                        if add:
                            try:
                                self.team_ctx, slot = add_to_team(self.team_ctx, self.pkm_ctx)
                                await self.print_output(f"Added to slot {slot + 1}.")
                            except TeamFullError:
                                pass

            elif choice == "g":
                new = await self.select_game(pkm_ctx=self.pkm_ctx)
                if new is not None:
                    self.game_ctx = new

            elif choice == "r":
                if self.pkm_ctx is None:
                    await self.print_output("No Pokemon loaded to refresh.")
                else:
                    chain_id = self.pkm_ctx.get("evolution_chain_id")
                    if chain_id is not None:
                        cache.invalidate_evolution_chain(chain_id)
                    self.pkm_ctx = refresh_pokemon(self.pkm_ctx, game_ctx=self.game_ctx)

            elif choice == "t":
                if self.game_ctx is None:
                    await self.print_output("Please select a game first (press G).")
                else:
                    from feat_team_loader import run as team_loader_run
                    self.team_ctx = await team_loader_run(self, self.game_ctx, self.team_ctx)

            elif choice in ("v", "o", "s", "h", "x"):
                if self.game_ctx is None:
                    await self.print_output("Select a game first (press G).")
                elif team_size(self.team_ctx) == 0:
                    await self.print_output("Load a team first (press T).")
                else:
                    if choice == "v":
                        import feat_team_analysis
                        await feat_team_analysis.run(self.team_ctx, self.game_ctx, ui=self)
                    elif choice == "o":
                        import feat_team_offense
                        await feat_team_offense.run(self.team_ctx, self.game_ctx, pool_cache=self.pool_cache, ui=self)
                    elif choice == "s":
                        import feat_team_moveset
                        await feat_team_moveset.run(self.team_ctx, self.game_ctx, pool_cache=self.pool_cache, ui=self)
                    elif choice == "h":
                        import feat_team_builder
                        await feat_team_builder.run(self.team_ctx, self.game_ctx, ui=self)
                    elif choice == "x":
                        import feat_opponent
                        await feat_opponent.run(self.team_ctx, self.game_ctx, ui=self)

            elif choice == "m":
                if self.game_ctx is None:
                    await self.print_output("Select a game first (press G).")
                else:
                    import feat_move_lookup
                    await feat_move_lookup.run(self.game_ctx, ui=self)

            elif choice == "b":
                import feat_type_browser
                await feat_type_browser.run(game_ctx=self.game_ctx, ui=self)
            elif choice == "n":
                import feat_nature_browser
                await feat_nature_browser.run(game_ctx=self.game_ctx, pkm_ctx=self.pkm_ctx, ui=self)
            elif choice == "a":
                import feat_ability_browser
                await feat_ability_browser.run(game_ctx=self.game_ctx, pkm_ctx=self.pkm_ctx, ui=self)
            elif choice == "l":
                if self.pkm_ctx is None:
                    await self.print_output("Load a Pokemon first (press P).")
                elif self.game_ctx is None:
                    await self.print_output("Select a game first (press G).")
                else:
                    import feat_learnset_compare
                    await feat_learnset_compare.run(self.pkm_ctx, self.game_ctx, ui=self)
            elif choice == "e":
                if self.pkm_ctx is None:
                    await self.print_output("Load a Pokemon first (press P).")
                else:
                    import feat_egg_group
                    await feat_egg_group.run(self.pkm_ctx, ui=self)

            elif choice == "y":
                existing = cache.get_moves()
                n_existing = len(existing) if existing else 0
                if n_existing > 0:
                    await self.print_output(f"\nMove table has {n_existing} moves cached.")
                    await self.print_output("F — fetch missing moves only")
                    await self.print_output("R — re-fetch all moves (overwrite)")
                    await self.print_output("Enter — cancel")
                    sub = (await self.input_prompt("Choice: ")).lower()
                else:
                    await self.print_output("\nThis fetches type, power, accuracy and PP for all ~920 moves.")
                    await self.print_output("Moves are also fetched lazily on first lookup — this just")
                    await self.print_output("avoids any wait when browsing move lists or learnsets.\n")
                    confirm = await self.confirm("Proceed?")
                    sub = "r" if confirm else ""

                if sub == "f":
                    try:
                        moves = pkm_pokeapi.fetch_missing_moves()
                        if moves:
                            cache.upsert_move_batch(moves)
                            await self.print_output(f"Done — {len(moves)} missing move(s) cached.")
                        else:
                            await self.print_output("All moves already cached — nothing to do.")
                    except ConnectionError as e:
                        await self.print_output(f"Connection error: {e}")
                elif sub == "r":
                    try:
                        moves = pkm_pokeapi.fetch_all_moves()
                        cache.save_moves(moves)
                        await self.print_output(f"Done — {len(moves)} moves cached.")
                    except ConnectionError as e:
                        await self.print_output(f"Connection error: {e}")

            elif choice == "w":
                existing = cache.get_machines()
                if existing:
                    n = sum(len(v) for v in existing.values())
                    await self.print_output(f"\nTM/HM table already cached ({n} entries across {len(existing)} games).")
                    confirm = await self.confirm("Re-fetch and overwrite?")
                else:
                    await self.print_output("\nThis fetches TM/HM numbers for all games (~900 entries).")
                    await self.print_output("Required for TM numbers to appear in the learnable move list.")
                    await self.print_output("After fetching, press R on any Pokemon to reload their learnset")
                    await self.print_output("with TM numbers included.\n")
                    confirm = await self.confirm("Proceed?")
                if confirm:
                    try:
                        machines = pkm_pokeapi.fetch_machines()
                        cache.save_machines(machines)
                        total = sum(len(v) for v in machines.values())
                        await self.print_output(f"Done — {total} TM/HM entries across {len(machines)} games cached.")
                    except ConnectionError as e:
                        await self.print_output(f"Connection error: {e}")

            elif choice.isdigit():
                idx = int(choice)
                if idx < 1 or idx > len(PKM_FEATURES):
                    await self.print_output("Invalid choice, try again.")
                    continue

                label, module_name, entry_fn, needs_pkm, needs_game, avail = PKM_FEATURES[idx - 1]
                if not avail:
                    await self.print_output(f"'{label}' is not yet available.")
                    continue

                if needs_game and self.game_ctx is None:
                    await self.print_output("This feature needs a game selected first.")
                    self.game_ctx = await self.select_game(pkm_ctx=self.pkm_ctx)
                    if self.game_ctx is None:
                        continue
                if needs_pkm and self.pkm_ctx is None:
                    await self.print_output("This feature needs a Pokemon loaded first.")
                    self.pkm_ctx = await self.select_pokemon(game_ctx=self.game_ctx)
                    if self.pkm_ctx is None:
                        continue

                module = __import__(module_name)
                await getattr(module, entry_fn)(self.pkm_ctx, self.game_ctx, ui=self)

            else:
                await self.print_output("Invalid choice, try again.")