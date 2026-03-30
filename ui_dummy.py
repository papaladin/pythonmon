#!/usr/bin/env python3
"""
ui_dummy.py  Dummy UI implementation for standalone mode (no real UI).

When a feature module is run directly (via its main() function), it creates
a DummyUI instance to handle output and input using standard console I/O.
"""

import builtins
from ui_base import UI


class DummyUI(UI):
    """Fallback UI that uses builtins.print() and builtins.input()."""

    async def print_header(self):
        pass

    async def print_menu(self, lines: list):
        pass

    async def print_output(self, text: str, end: str = "\n"):
        builtins.print(text, end=end)

    async def print_progress(self, text: str, end: str = "\n", flush: bool = False):
        builtins.print(text, end=end, flush=flush)

    async def input_prompt(self, prompt: str) -> str:
        return builtins.input(prompt).strip()

    async def confirm(self, prompt: str) -> bool:
        return builtins.input(prompt + " (y/n): ").strip().lower() == "y"

    async def select_from_list(self, prompt: str, options: list, allow_none: bool = False) -> str | None:
        from pkm_session import select_from_list as _sfl
        return _sfl(prompt, options, allow_none)

    async def select_pokemon(self, game_ctx=None) -> dict | None:
        from pkm_session import select_pokemon as _sp
        return _sp(game_ctx)

    async def select_game(self, pkm_ctx=None) -> dict | None:
        from pkm_session import select_game as _sg
        return _sg(pkm_ctx)

    async def select_form(self, forms: list) -> tuple:
        from pkm_session import select_form as _sf
        return _sf(forms)

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
        builtins.print("\n  [ " + "  •  ".join(parts) + " ]")

    async def show_error(self, message: str) -> None:
        builtins.print(f"\n  ERROR: {message}")

    async def run(self):
        # Not used in standalone mode
        pass