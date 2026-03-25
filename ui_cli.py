# ui_cli.py
#!/usr/bin/env python3
"""
ui_cli.py  CLI implementation of the UI abstract base class.
"""

import sys

from ui_base import UI
import pkm_cache as cache
import matchup_calculator as calc
import pkm_pokeapi


class CLI(UI):
    def __init__(self):
        # We'll import pkm_session functions later to avoid circular imports
        pass

    def print_header(self):
        W = 52
        def box_line(text=""):
            return f"│  {text:<{W}}│"
        print()
        print("╔" + "═"*(W+2) + "╗")
        print(box_line("Pokemon Toolkit"))
        print("╚" + "═"*(W+2) + "╝")

    def print_menu(self, lines: list):
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

    def print_output(self, text: str, end: str = "\n"):
        print(text, end=end)

    def print_progress(self, text: str, end: str = "\n", flush: bool = False):
        print(text, end=end, flush=flush)

    def input_prompt(self, prompt: str) -> str:
        return input(prompt).strip()

    def confirm(self, prompt: str) -> bool:
        return input(prompt + " (y/n): ").strip().lower() == "y"

    def select_from_list(self, prompt: str, options: list, allow_none: bool = False) -> str | None:
        # Implementation copied from pkm_session.select_from_list
        print(f"\n{prompt}")
        if allow_none:
            print("   0. None (single type)")
        for i, opt in enumerate(options, start=1):
            print(f"  {i:2d}. {opt}")
        while True:
            try:
                idx = int(self.input_prompt("Enter number: "))
                if allow_none and idx == 0:
                    return "None"
                if 1 <= idx <= len(options):
                    return options[idx - 1]
                print("  Invalid choice, try again.")
            except ValueError:
                print("  Please enter a number.")

    def select_pokemon(self, game_ctx=None) -> dict | None:
        # Temporary: use existing function from pkm_session
        from pkm_session import select_pokemon as _select_pokemon
        return _select_pokemon(game_ctx)

    def select_game(self, pkm_ctx=None) -> dict | None:
        from pkm_session import select_game as _select_game
        return _select_game(pkm_ctx)

    def select_form(self, forms: list) -> tuple:
        from pkm_session import select_form as _select_form
        return _select_form(forms)

    def print_session_header(self, pkm_ctx: dict, game_ctx: dict, constraints: list = None):
        parts = []
        if pkm_ctx:
            dual = (f"{pkm_ctx['type1']} / {pkm_ctx['type2']}"
                    if pkm_ctx["type2"] != "None" else pkm_ctx["type1"])
            parts.append(f"{pkm_ctx['form_name']}  •  {dual}")
        if game_ctx:
            parts.append(game_ctx["game"])
        if constraints:
            parts.append(f"Locked: {', '.join(constraints)}")
        self.print_output("\n  [ " + "  •  ".join(parts) + " ]")