#!/usr/bin/env python3
"""
ui_tui.py  Terminal UI implementation using textual.
"""

import asyncio
import sys
import traceback
import re
from typing import Any
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, RichLog, Input, Button, ListView, ListItem, Label, ProgressBar
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual import events
from ui_base import UI

from menu_builder import build_context_lines, build_menu_lines
from feat_team_loader import new_team, team_size, add_to_team, TeamFullError
from pkm_session import refresh_pokemon, get_form_gen
import pkm_cache as cache
import pkm_pokeapi
import matchup_calculator as calc

# Compiled regex for progress bar pattern (e.g., "12/34")
_PROGRESS_PATTERN = re.compile(r'(\d+)/(\d+)')

# Feature registry
PKM_FEATURES = [
    ("Quick view  (stats / abilities / types)", "feat_quick_view", "run", True, True, True),
    ("Learnable move list (conditions)", "feat_movepool", "run", True, True, True),
    ("Learnable move list (scored)", "feat_moveset", "run_scored_pool", True, True, True),
    ("Moveset recommendation", "feat_moveset", "run", True, True, True),
]

# ── Index search (copied from pkm_session for TUI independence) ──────────────
def index_search(needle: str, index: dict) -> list:
    """Return list of matching slugs (exact, prefix, substring) from the Pokemon index."""
    needle_lo = needle.strip().lower()
    if not needle_lo:
        return []
    if needle_lo in index:
        return [needle_lo]
    prefix = sorted(k for k in index if k.startswith(needle_lo))
    substr = sorted(k for k in index if needle_lo in k and not k.startswith(needle_lo))
    return (prefix + substr)[:8]  # cap at 8 suggestions


# ── Modal screens ─────────────────────────────────────────────────────────────

class GameSelectionScreen(Screen):
    """A modal screen to select a game from the list."""
    def __init__(self):
        super().__init__()
        self.game_names = [game[0] for game in calc.GAMES]
        self.result = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label("Select a game (use arrow keys, then Enter):", id="prompt")
            with ScrollableContainer():
                items = [ListItem(Label(f"{i+1}. {name}")) for i, name in enumerate(self.game_names)]
                yield ListView(*items, id="game-list")
            yield Button("Cancel", id="cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#game-list").focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None:
            self.result = self.game_names[idx]
            self.dismiss(self.result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)


class PokemonSelectionScreen(Screen):
    """Modal screen to search and select a Pokémon (returns species data)."""
    def __init__(self):
        super().__init__()
        self.index = cache.get_index()
        self.all_slugs = list(self.index.keys())
        self.filtered_slugs = self.all_slugs[:]
        self.result = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label("Search for a Pokémon:", id="prompt")
            yield Input(placeholder="Type name...", id="search")
            with ScrollableContainer():
                yield ListView(id="results")
            with Horizontal():
                yield Button("Search PokeAPI", id="search_api")
                yield Button("Cancel", id="cancel")
            yield Label("", id="error")
        yield Footer()

    async def on_mount(self) -> None:
        await self.update_list()

    async def update_list(self):
        search = self.query_one("#search").value
        if search:
            self.filtered_slugs = index_search(search, self.index)
        else:
            self.filtered_slugs = self.all_slugs[:8]
        items = [ListItem(Label(f"{slug.replace('-', ' ').title()}")) for slug in self.filtered_slugs]
        list_view = self.query_one("#results")
        await list_view.clear()
        await list_view.extend(items)

    async def on_input_changed(self, event: Input.Changed) -> None:
        self.query_one("#error").update("")
        await self.update_list()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if not name:
            return
        await self.search_pokeapi(name)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "search_api":
            name = self.query_one("#search").value.strip()
            if name:
                await self.search_pokeapi(name)

    async def search_pokeapi(self, name: str):
        import pkm_pokeapi as pokeapi
        import pkm_cache as cache
        slug = pokeapi._name_to_slug(name)
        try:
            data = pokeapi.fetch_pokemon(slug)
            cache.save_pokemon(data["pokemon"], data)
            self.result = data
            self.dismiss(self.result)
        except ValueError:
            error_label = self.query_one("#error")
            error_label.update(f"Pokémon '{name}' not found.")
        except ConnectionError as e:
            error_label = self.query_one("#error")
            error_label.update(f"Connection error: {e}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and idx < len(self.filtered_slugs):
            slug = self.filtered_slugs[idx]
            data = cache.get_pokemon(slug)
            if data and data.get("forms"):
                self.result = data
                self.dismiss(self.result)
            else:
                self.dismiss(None)


class FormSelectionScreen(Screen):
    """Modal screen to select a Pokémon form."""
    def __init__(self, forms: list):
        super().__init__()
        self.forms = forms
        self.result = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label("Select a form (use arrow keys, then Enter):", id="prompt")
            with ScrollableContainer():
                items = []
                for form_name, types, variety_slug in self.forms:
                    type_str = " / ".join(types) if types else "?"
                    label = f"{form_name}  [{type_str}]"
                    items.append(ListItem(Label(label)))
                yield ListView(*items, id="form-list")
            yield Button("Cancel", id="cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#form-list").focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self.forms):
            self.result = self.forms[idx]
            self.dismiss(self.result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)


class InputModal(Screen):
    """Modal screen for text input."""
    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt
        self.result = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(self.prompt, id="prompt")
            yield Input(placeholder="Type here...", id="input")
            with Horizontal():
                yield Button("OK", id="ok")
                yield Button("Cancel", id="cancel")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            self.result = self.query_one("#input").value
            self.dismiss(self.result)
        elif event.button.id == "cancel":
            self.dismiss("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.result = event.value
        self.dismiss(self.result)


class ConfirmModal(Screen):
    """Modal screen for yes/no confirmation."""
    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt
        self.result = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(self.prompt, id="prompt")
            with Horizontal():
                yield Button("Yes", id="yes")
                yield Button("No", id="no")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#yes").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.result = (event.button.id == "yes")
        self.dismiss(self.result)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.result = False
            self.dismiss(False)


class ListSelectionModal(Screen):
    """Modal screen for choosing an option from a list."""
    def __init__(self, prompt: str, options: list, allow_none: bool = False):
        super().__init__()
        self.prompt = prompt
        self.options = options
        self.allow_none = allow_none
        self.result = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(self.prompt, id="prompt")
            with ScrollableContainer():
                items = [ListItem(Label(f"{i+1}. {opt}")) for i, opt in enumerate(self.options)]
                if self.allow_none:
                    items.append(ListItem(Label("0. None")))
                yield ListView(*items)
            yield Button("Cancel", id="cancel")
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None:
            if self.allow_none and idx == len(self.options):
                self.result = None
            elif 0 <= idx < len(self.options):
                self.result = self.options[idx]
            else:
                return
            self.dismiss(self.result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)


class ErrorModal(Screen):
    """Modal screen for displaying an error message."""
    def __init__(self, message: str):
        super().__init__()
        self.message = message
        self.result = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(self.message, id="message")
            with Horizontal():
                yield Button("OK", id="ok")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            self.dismiss(None)


# ── Main application with persistent input bar ────────────────────────────────

class PokemonApp(App):
    """Textual app for the Pokemon Toolkit."""
    CSS = """
    Screen {
        background: $surface;
    }
    Horizontal {
        height: 1fr;
    }
    #left-pane {
        width: 40;
        border-right: solid $primary;
        padding: 1;
        height: 100%;
    }
    #right-pane {
        height: 100%;
        padding: 1;
    }
    #context {
        width: 100%;
        border-bottom: solid $primary;
    }
    #menu {
        width: 100%;
    }
    #progress {
        height: 3;
        background: $surface;
        color: $text;
        padding: 0 1;
        border-bottom: solid $primary;
    }
    #output {
        height: 100%;
        width: 100%;
    }
    #input-bar {
        height: 3;
        border-top: solid $primary;
        padding: 0 1;
    }
    #input-prompt {
        width: 40;
        content-align: right middle;
    }
    #input-field {
        width: 1fr;
    }
    #error {
        color: $error;
        height: 1;
    }
    """

    def __init__(self, ui_instance):
        super().__init__()
        self.ui = ui_instance
        self.input_future = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with ScrollableContainer(id="left-pane"):
                yield Static("", id="context")
                yield Static("", id="menu")
            with Vertical(id="right-pane"):
                yield ProgressBar(id="progress", total=100, show_eta=False)
                yield RichLog(id="output", wrap=True, markup=True)
        with Horizontal(id="input-bar"):
            yield Label("", id="input-prompt")
            yield Input(placeholder="", id="input-field", disabled=True)
        # No default footer

    def on_mount(self) -> None:
        self.refresh_left_pane()
        self.update_output("Welcome to Pokemon Toolkit TUI!\nPress G to select a game, P to load a Pokemon, Q to quit.")

    def refresh_left_pane(self):
        context_lines = build_context_lines(self.ui.pkm_ctx, self.ui.game_ctx, self.ui.team_ctx)
        menu_lines = build_menu_lines(self.ui.pkm_ctx, self.ui.game_ctx, self.ui.team_ctx, PKM_FEATURES)
        self.query_one("#context").update("\n".join(context_lines))
        self.query_one("#menu").update("\n".join(menu_lines))

    def update_output(self, text: str):
        output = self.query_one("#output")
        output.write(text)

    def clear_output(self):
        self.query_one("#output").clear()

    def update_progress(self, percent: int, text: str = ""):
        bar = self.query_one("#progress")
        bar.progress = percent
        if text:
            bar.label = text

    def clear_progress(self):
        bar = self.query_one("#progress")
        bar.progress = 0
        bar.label = ""

    def action_quit(self):
        self.exit()

    def on_key(self, event: events.Key):
        key = event.key.lower()
        if self.query_one("#input-field").has_focus:
            if key == "escape":
                self.cancel_input()
            return
        self.ui.handle_key(key)

    def set_input_prompt(self, prompt: str):
        self.query_one("#input-prompt").update(prompt)
        input_field = self.query_one("#input-field")
        input_field.disabled = False
        input_field.focus()
        input_field.value = ""

    def clear_input_prompt(self):
        input_field = self.query_one("#input-field")
        input_field.disabled = True
        self.query_one("#input-prompt").update("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.input_future and not self.input_future.done():
            self.input_future.set_result(event.value)
            self.clear_input_prompt()

    def cancel_input(self):
        if self.input_future and not self.input_future.done():
            self.input_future.set_result("")
            self.clear_input_prompt()

    async def get_input(self, prompt: str) -> str:
        self.input_future = asyncio.Future()
        self.set_input_prompt(prompt)
        result = await self.input_future
        return result


# ── TUI wrapper implementing UI abstract class ───────────────────────────────

class TUI(UI):
    """Wrapper that holds the state and runs the textual app."""

    def __init__(self):
        self.pkm_ctx = None
        self.game_ctx = None
        self.team_ctx = new_team()
        self.pool_cache = {}
        self.app = PokemonApp(self)

    # ----- Coloring rules -----
    def _colorize(self, text: str) -> str:
        """Apply markup to lines based on content."""
        lines = text.split("\n")
        colored_lines = []
        for line in lines:
            # Session header: starts with "  [ "
            if line.startswith("  [ "):
                line = f"[bold cyan]{line}[/bold cyan]"
            # Section header: starts with "  ── "
            elif line.startswith("  ── "):
                line = f"[bold white]{line}[/bold white]"
            # Error lines
            elif "ERROR" in line or "Connection error" in line:
                line = f"[red]{line}[/red]"
            # Warning lines
            elif "⚠" in line or "WARNING" in line:
                line = f"[yellow]{line}[/yellow]"
            # Success lines
            elif "✓" in line or "Done" in line or "cached." in line:
                line = f"[green]{line}[/green]"
            # Weakness coverage (team builder)
            elif line.startswith("  Weak to:") or line.startswith("  ✗"):
                line = f"[red]{line}[/red]"
            # Resistance / counter coverage
            elif line.startswith("  Resists:") or line.startswith("  ✓"):
                line = f"[green]{line}[/green]"
            # Profile headers (nature/EV)
            elif line.startswith("  ── Profile"):
                line = f"[bold magenta]{line}[/bold magenta]"
            # Dot rating (team builder)
            elif "●" in line:
                # Keep other text default, only wrap the dot sequence
                # But we'll just color the whole line to keep it simple
                line = f"[yellow]{line}[/yellow]"

            colored_lines.append(line)
        return "\n".join(colored_lines)

    async def print_header(self):
        pass

    async def print_menu(self, lines: list):
        pass

    async def print_output(self, text: str, end: str = "\n", flush: bool = False):
        """Print colored output to the right pane."""
        colored = self._colorize(text)
        self.app.update_output(colored)

    async def print_progress(self, text: str, end: str = "\n", flush: bool = False):
        """Update the progress bar based on text containing 'X/Y' pattern."""
        match = _PROGRESS_PATTERN.search(text)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            percent = int(current * 100 / total)
            bar = self.app.query_one("#progress")
            if bar.total != total:
                bar.update(total=total)
            self.app.update_progress(percent, text)
        else:
            self.app.update_progress(0, text)

    async def input_prompt(self, prompt: str) -> str:
        return await self.app.get_input(prompt)

    async def confirm(self, prompt: str) -> bool:
        return await self._wait_for_modal(ConfirmModal(prompt))

    async def select_from_list(self, prompt: str, options: list, allow_none: bool = False) -> str | None:
        return await self._wait_for_modal(ListSelectionModal(prompt, options, allow_none))

    async def select_pokemon(self, game_ctx=None) -> dict | None:
        species_data = await self._wait_for_modal(PokemonSelectionScreen())
        if species_data is None:
            return None
        forms = species_data.get("forms", [])
        species_gen = species_data.get("species_gen", 1)
        if len(forms) == 1:
            form = forms[0]
        else:
            form_list = [(f["name"], f["types"], f.get("variety_slug", species_data["pokemon"])) for f in forms]
            selected = await self._wait_for_modal(FormSelectionScreen(form_list))
            if selected is None:
                return None
            form = next((f for f in forms if f["name"] == selected[0]), forms[0])
        types = form.get("types", [])
        form_name = form.get("name", species_data["pokemon"].replace("-", " ").title())
        form_gen = get_form_gen(form_name, species_gen)
        pkm_ctx = {
            "pokemon": species_data["pokemon"],
            "variety_slug": form.get("variety_slug", species_data["pokemon"]),
            "form_name": form_name,
            "types": types,
            "type1": types[0] if types else "?",
            "type2": types[1] if len(types) > 1 else "None",
            "species_gen": species_gen,
            "form_gen": form_gen,
            "base_stats": form.get("base_stats", {}),
            "abilities": form.get("abilities", []),
            "egg_groups": species_data.get("egg_groups", []),
            "evolution_chain_id": species_data.get("evolution_chain_id"),
        }
        return pkm_ctx

    async def select_game(self, pkm_ctx=None) -> dict | None:
        # Not used directly (we use the modal for G key)
        return None

    async def select_form(self, forms: list) -> tuple:
        return await self._wait_for_modal(FormSelectionScreen(forms))

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
        await self._wait_for_modal(ErrorModal(message))

    async def _wait_for_modal(self, screen: Screen) -> Any:
        future = asyncio.Future()
        self.app.push_screen(screen, callback=lambda result: future.set_result(result))
        return await future

    # --- Key dispatch (unchanged) ---

    def handle_key(self, key: str):
        asyncio.create_task(self._handle_key_async(key))

    async def _handle_key_async(self, key: str):
        if key == "q":
            self.app.exit()
            return
        elif key == "g":
            try:
                game_name = await self._wait_for_modal(GameSelectionScreen())
                if game_name:
                    from pkm_session import make_game_ctx
                    try:
                        self.game_ctx = make_game_ctx(game_name)
                        await asyncio.sleep(0.05)
                        self.app.refresh_left_pane()
                        await self.print_output(f"Game set to: {game_name}")
                    except ValueError as e:
                        await self.show_error(str(e))
                else:
                    await self.print_output("Game selection cancelled")
            except Exception as e:
                await self.show_error(f"Game selection error: {e}")
                await self.print_output(traceback.format_exc())
            return

        elif key == "p":
            try:
                pkm_ctx = await self.select_pokemon()
                if pkm_ctx:
                    self.pkm_ctx = pkm_ctx
                    await asyncio.sleep(0.05)
                    self.app.refresh_left_pane()
                    await self.print_output(f"Loaded {self.pkm_ctx['form_name']}.")
                    if self.game_ctx is not None and team_size(self.team_ctx) < 6:
                        add = await self.confirm(f"Add {self.pkm_ctx['form_name']} to team?")
                        if add:
                            try:
                                self.team_ctx, slot = add_to_team(self.team_ctx, self.pkm_ctx)
                                await self.print_output(f"Added to slot {slot + 1}.")
                                self.app.refresh_left_pane()
                            except TeamFullError:
                                pass
                else:
                    await self.print_output("Pokemon selection cancelled")
            except Exception as e:
                await self.show_error(f"Pokemon selection error: {e}")
                await self.print_output(traceback.format_exc())
            return

        elif key == "t":
            if self.game_ctx is None:
                await self.show_error("Please select a game first (press G).")
            else:
                from feat_team_loader import run as team_loader_run
                self.team_ctx = await team_loader_run(self, self.game_ctx, self.team_ctx)
                self.app.refresh_left_pane()
            return

        elif key == "j":
            if self.game_ctx is None:
                await self.show_error("Select a game first (press G).")
            else:
                from feat_team_builder import run_joint_team
                await run_joint_team(self.team_ctx, self.game_ctx, ui=self)


        # ---- Move lookup ----
        elif key == "m":
            if self.game_ctx is None:
                await self.show_error("Select a game first (press G).")
            else:
                import feat_move_lookup
                await feat_move_lookup.run(self.game_ctx, ui=self)
            return

        # ---- Browsers ----
        elif key == "b":
            self.app.update_progress(0, "Fetching type data...")
            import feat_type_browser
            await feat_type_browser.run(game_ctx=self.game_ctx, ui=self)
            self.app.clear_progress()
        elif key == "n":
            import feat_nature_browser
            await feat_nature_browser.run(game_ctx=self.game_ctx, pkm_ctx=self.pkm_ctx, ui=self)
        elif key == "a":
            self.app.update_progress(0, "Fetching ability data...")
            import feat_ability_browser
            await feat_ability_browser.run(game_ctx=self.game_ctx, pkm_ctx=self.pkm_ctx, ui=self)
            self.app.clear_progress()
        elif key == "l":
            if self.pkm_ctx is None:
                await self.show_error("Load a Pokemon first (press P).")
            elif self.game_ctx is None:
                await self.show_error("Select a game first (press G).")
            else:
                import feat_learnset_compare
                await feat_learnset_compare.run(self.pkm_ctx, self.game_ctx, ui=self)
        elif key == "e":
            if self.pkm_ctx is None:
                await self.show_error("Load a Pokemon first (press P).")
            else:
                import feat_egg_group
                await feat_egg_group.run(self.pkm_ctx, ui=self)

        # ---- Team features ----
        elif key in ("v", "o", "s", "h", "x"):
            if self.game_ctx is None:
                await self.show_error("Select a game first (press G).")
            elif team_size(self.team_ctx) == 0:
                await self.show_error("Load a team first (press T).")
            else:
                if key == "v":
                    import feat_team_analysis
                    await feat_team_analysis.run(self.team_ctx, self.game_ctx, ui=self)
                elif key == "o":
                    import feat_team_offense
                    await feat_team_offense.run(self.team_ctx, self.game_ctx, pool_cache=self.pool_cache, ui=self)
                elif key == "s":
                    import feat_team_moveset
                    await feat_team_moveset.run(self.team_ctx, self.game_ctx, pool_cache=self.pool_cache, ui=self)
                elif key == "h":
                    import feat_team_builder
                    await feat_team_builder.run(self.team_ctx, self.game_ctx, ui=self)
                    self.app.clear_progress()
                elif key == "x":
                    import feat_opponent
                    await feat_opponent.run(self.team_ctx, self.game_ctx, ui=self)

        # ---- Move table utilities ----
        elif key == "y":
            existing = cache.get_moves()
            n_existing = len(existing) if existing else 0
            if n_existing > 0:
                await self.print_output(f"\nMove table has {n_existing} moves cached.")
                await self.print_output("R — re-fetch all moves (overwrite)")
                await self.print_output("Enter — cancel")
                sub = (await self.input_prompt("Choice: ")).lower()
                if sub != "r":
                    return
            else:
                await self.print_output("\nThis fetches type, power, accuracy and PP for all ~920 moves.")
                await self.print_output("Moves are also fetched lazily on first lookup — this just")
                await self.print_output("avoids any wait when browsing move lists or learnsets.\n")
                confirm = await self.confirm("Proceed?")
                if not confirm:
                    return

            def move_progress(current, total, name):
                if not hasattr(move_progress, "total_set"):
                    self.app.call_from_thread(lambda: self.app.query_one("#progress").update(total=total))
                    move_progress.total_set = True
                percent = int(current * 100 / total)
                label = f"Fetching moves: {current}/{total}  {name}..."
                self.app.call_from_thread(self.app.update_progress, percent, label)

            try:
                moves = await asyncio.to_thread(pkm_pokeapi.fetch_all_moves, False, move_progress)
                cache.save_moves(moves)
                await self.print_output(f"Done — {len(moves)} moves cached.")
            except ConnectionError as e:
                await self.show_error(f"Connection error: {e}")
            except Exception as e:
                await self.show_error(f"Unexpected error: {e}")
            finally:
                self.app.clear_progress()

        elif key == "w":
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
                def machine_progress(current, total, machine_id):
                    if not hasattr(machine_progress, "total_set"):
                        self.app.call_from_thread(lambda: self.app.query_one("#progress").update(total=total))
                        machine_progress.total_set = True
                    percent = int(current * 100 / total)
                    label = f"Fetching machines: {current}/{total}  {machine_id}..."
                    self.app.call_from_thread(self.app.update_progress, percent, label)

                try:
                    machines = await asyncio.to_thread(pkm_pokeapi.fetch_machines, machine_progress)
                    cache.save_machines(machines)
                    total = sum(len(v) for v in machines.values())
                    await self.print_output(f"Done — {total} TM/HM entries across {len(machines)} games cached.")
                except ConnectionError as e:
                    await self.show_error(f"Connection error: {e}")
                except Exception as e:
                    await self.show_error(f"Unexpected error: {e}")
                finally:
                    self.app.clear_progress()

        elif key == "r":
            if self.pkm_ctx is None:
                await self.show_error("No Pokemon loaded to refresh.")
            else:
                self.app.update_progress(0, f"Refreshing {self.pkm_ctx['form_name']}...")
                try:
                    chain_id = self.pkm_ctx.get("evolution_chain_id")
                    if chain_id is not None:
                        cache.invalidate_evolution_chain(chain_id)
                    self.pkm_ctx = refresh_pokemon(self.pkm_ctx, game_ctx=self.game_ctx)
                    self.app.refresh_left_pane()
                    await self.print_output(f"Refreshed {self.pkm_ctx['form_name']}.")
                except Exception as e:
                    await self.show_error(f"Refresh failed: {e}")
                finally:
                    self.app.clear_progress()

        # ---- Numbered features ----
        elif key.isdigit():
            idx = int(key)
            if idx < 1 or idx > len(PKM_FEATURES):
                await self.show_error("Invalid choice.")
                return
            label, module_name, entry_fn, needs_pkm, needs_game, avail = PKM_FEATURES[idx - 1]
            if not avail:
                await self.show_error(f"'{label}' is not yet available.")
                return
            if needs_game and self.game_ctx is None:
                await self.show_error("This feature needs a game selected first. Press G to select a game.")
                return
            if needs_pkm and self.pkm_ctx is None:
                await self.show_error("This feature needs a Pokemon loaded first. Press P to load a Pokemon.")
                return
            module = __import__(module_name)
            await getattr(module, entry_fn)(self.pkm_ctx, self.game_ctx, ui=self)

        else:
            await self.print_output(f"Key '{key}' not yet handled in TUI. Use CLI for now.")

    async def run(self):
        await self.app.run_async()
        
        
        
# ── Self‑tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import sys
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  ui_tui.py — self-test\n")

    # ── index_search ──────────────────────────────────────────────────────────
    # Mock index with a few Pokémon
    mock_index = {
        "charizard":   {"forms": [{"name": "Charizard",   "types": ["Fire","Flying"]}]},
        "charmander":  {"forms": [{"name": "Charmander",  "types": ["Fire"]}]},
        "charmeleon":  {"forms": [{"name": "Charmeleon",  "types": ["Fire"]}]},
        "blastoise":   {"forms": [{"name": "Blastoise",   "types": ["Water"]}]},
        "rotom-wash":  {"forms": [{"name": "Rotom-Wash",  "types": ["Water","Electric"]}]},
        "rotom-heat":  {"forms": [{"name": "Rotom-Heat",  "types": ["Fire","Electric"]}]},
        "rotom-frost": {"forms": [{"name": "Rotom-Frost", "types": ["Ice","Electric"]}]},
    }

    # Exact slug match → returns that slug alone
    r = index_search("charizard", mock_index)
    if r == ["charizard"]:
        ok("index_search: exact slug → single result")
    else:
        fail("index_search exact", str(r))

    # Prefix match → all three char* entries
    r = index_search("char", mock_index)
    if set(r) == {"charizard", "charmander", "charmeleon"}:
        ok("index_search: prefix match")
    else:
        fail("index_search prefix", str(r))

    # Case-insensitive
    r = index_search("CHAR", mock_index)
    if set(r) == {"charizard", "charmander", "charmeleon"}:
        ok("index_search: case-insensitive")
    else:
        fail("index_search case", str(r))

    # Substring match (rotom contains "oto")
    r = index_search("oto", mock_index)
    if all("rotom" in s for s in r) and len(r) == 3:
        ok("index_search: substring fallback")
    else:
        fail("index_search substring", str(r))

    # Prefix before substring
    r = index_search("cha", mock_index)
    prefix_names = {"charizard", "charmander", "charmeleon"}
    if set(r[:3]) == prefix_names:
        ok("index_search: prefix ranked before substring")
    else:
        fail("index_search prefix order", str(r))

    # No match → empty list
    r = index_search("pikachu", mock_index)
    if r == []:
        ok("index_search: no match → []")
    else:
        fail("index_search no match", str(r))

    # Empty needle → empty list
    r = index_search("", mock_index)
    if r == []:
        ok("index_search: empty needle → []")
    else:
        fail("index_search empty", str(r))

    # Empty index → empty list
    r = index_search("char", {})
    if r == []:
        ok("index_search: empty index → []")
    else:
        fail("index_search empty index", str(r))

    # Cap at _MAX_SUGGESTIONS (8) – we set _MAX_SUGGESTIONS=8 in ui_tui.py
    big_index = {f"rotom-{i}": {"forms": []} for i in range(20)}
    r = index_search("rotom", big_index)
    if len(r) == 8:
        ok("index_search: capped at 8 suggestions")
    else:
        fail("index_search cap", f"got {len(r)}")

    # ── Smoke test: ensure required imports and classes exist ─────────────────
    # This just verifies that the module structure is intact (no syntax errors).
    # We can check that the key classes are defined.
    try:
        # Attempt to instantiate some classes (no modal run, just existence)
        game_screen = GameSelectionScreen()
        pokemon_screen = PokemonSelectionScreen()
        form_screen = FormSelectionScreen([])
        input_modal = InputModal("")
        confirm_modal = ConfirmModal("")
        list_modal = ListSelectionModal("", [])
        error_modal = ErrorModal("")
        # Also verify that TUI class exists (it does)
        tui_instance = TUI()
        ok("ui_tui: all classes can be instantiated (smoke test)")
    except Exception as e:
        fail("ui_tui class instantiation", str(e))

    print()
    total = 10  # number of ok/fail calls above
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")
        
        
if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
    else:
        # Not meant to be run standalone
        print("This module is not meant to be run directly. Use --autotest to run self-tests.")