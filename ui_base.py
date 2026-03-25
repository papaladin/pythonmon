# ui_base.py
#!/usr/bin/env python3
"""
ui_base.py  Abstract base class for UI implementations.
"""

from abc import ABC, abstractmethod


class UI(ABC):
    @abstractmethod
    def print_header(self):
        """Print the main header (banner) of the application."""
        pass

    @abstractmethod
    def print_menu(self, lines: list):
        """Print a menu with a box around it. The list contains lines to print inside the box."""
        pass

    @abstractmethod
    def print_output(self, text: str, end: str = "\n"):
        """Print arbitrary text (without a box)."""
        pass

    @abstractmethod
    def print_progress(self, text: str, end: str = "\n", flush: bool = False):
        """Print a progress line that may be overwritten (like a counter)."""
        pass

    @abstractmethod
    def input_prompt(self, prompt: str) -> str:
        """Print a prompt and return user input."""
        pass

    @abstractmethod
    def confirm(self, prompt: str) -> bool:
        """Ask a yes/no question and return True if user answers yes."""
        pass

    @abstractmethod
    def select_from_list(self, prompt: str, options: list, allow_none: bool = False) -> str | None:
        """Display a numbered list and return the selected option."""
        pass

    @abstractmethod
    def select_pokemon(self, game_ctx=None) -> dict | None:
        """Prompt the user to select a Pokémon, returning a pkm_ctx dict."""
        pass

    @abstractmethod
    def select_game(self, pkm_ctx=None) -> dict | None:
        """Prompt the user to select a game, returning a game_ctx dict."""
        pass

    @abstractmethod
    def select_form(self, forms: list) -> tuple:
        """Given a list of form tuples, let the user pick one."""
        pass

    @abstractmethod
    def print_session_header(self, pkm_ctx: dict, game_ctx: dict, constraints: list = None):
        """Print the session header line."""
        pass