#!/usr/bin/env python3
"""
ui_tui.py  Terminal UI implementation using textual.
"""

import asyncio
import sys
import traceback
from typing import Any
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, TextArea, Input, Button, ListView, ListItem, Label
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual import events
from ui_base import UI

from menu_builder import build_context_lines, build_menu_lines
from feat_team_loader import new_team, team_size, add_to_team, TeamFullError
from pkm_session import select_game, select_form, refresh_pokemon, get_form_gen  # added get_form_gen
import pkm_cache as cache
import pkm_pokeapi
import matchup_calculator as calc

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
                yield ListView(*items)
            yield Button("Cancel", id="cancel")
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None:
            self.result = self.game_names[idx]
            self.dismiss(self.result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
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
        """Refresh the list view based on current search text."""
        search = self.query_one("#search").value
        if search:
            self.filtered_slugs = index_search(search, self.index)
        else:
            self.filtered_slugs = self.all_slugs[:8]  # show first 8 for performance
        items = [ListItem(Label(f"{slug.replace('-', ' ').title()}")) for slug in self.filtered_slugs]
        list_view = self.query_one("#results")
        await list_view.clear()
        await list_view.extend(items)

    async def on_input_changed(self, event: Input.Changed) -> None:
        self.query_one("#error").update("")
        await self.update_list()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """When Enter is pressed, try to fetch the exact name from PokeAPI."""
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
        """Search PokeAPI for the exact name and return species data if found."""
        import pkm_pokeapi as pokeapi
        import pkm_cache as cache
        slug = pokeapi._name_to_slug(name)
        try:
            # Fetch from PokeAPI
            data = pokeapi.fetch_pokemon(slug)
            cache.save_pokemon(data["pokemon"], data)
            # Return the species data (not built pkm_ctx)
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
        self.forms = forms  # list of (form_name, types, variety_slug)
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
                yield ListView(*items)
            yield Button("Cancel", id="cancel")
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self.forms):
            self.result = self.forms[idx]
            self.dismiss(self.result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.result = (event.button.id == "yes")
        self.dismiss(self.result)


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
        overflow-y: auto;
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
        width: 20;
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
        self.ui = ui_instance  # reference to the TUI wrapper
        self.input_future = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Static("", id="context")
                yield Static("", id="menu")
            with Vertical(id="right-pane"):
                yield TextArea("", id="output", read_only=True)
        with Horizontal(id="input-bar"):
            yield Label("", id="input-prompt")
            yield Input(placeholder="", id="input-field", disabled=True)
        yield Footer()

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
        output.insert(text + "\n")
        output.scroll_end()

    def clear_output(self):
        self.query_one("#output").clear()

    def action_quit(self):
        self.exit()

    def on_key(self, event: events.Key):
        key = event.key.lower()
        # If input field is focused, let it handle the key (except for special keys like Q)
        if self.query_one("#input-field").has_focus:
            if key == "escape":
                self.cancel_input()
            return
        self.ui.handle_key(key)

    def set_input_prompt(self, prompt: str):
        """Show a prompt in the input bar and enable input."""
        self.query_one("#input-prompt").update(prompt)
        input_field = self.query_one("#input-field")
        input_field.disabled = False
        input_field.focus()
        input_field.value = ""

    def clear_input_prompt(self):
        """Disable the input bar and clear prompt."""
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
        """Show an input prompt and return the user's input."""
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

    async def print_header(self):
        pass

    async def print_menu(self, lines: list):
        pass

    async def print_output(self, text: str, end: str = "\n"):
        self.app.update_output(text + end)

    async def print_progress(self, text: str, end: str = "\n", flush: bool = False):
        self.app.update_output(text + end)

    async def input_prompt(self, prompt: str) -> str:
        """Use the persistent input bar to get user input."""
        return await self.app.get_input(prompt)

    async def confirm(self, prompt: str) -> bool:
        """Use a modal for confirmation."""
        return await self._wait_for_modal(ConfirmModal(prompt))

    async def select_from_list(self, prompt: str, options: list, allow_none: bool = False) -> str | None:
        """Use a modal for list selection."""
        return await self._wait_for_modal(ListSelectionModal(prompt, options, allow_none))

    async def select_pokemon(self, game_ctx=None) -> dict | None:
        """Show the Pokémon selection modal and return the pkm_ctx."""
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

    # --- Helper to wait for modal results ---
    async def _wait_for_modal(self, screen: Screen) -> Any:
        future = asyncio.Future()
        self.app.push_screen(screen, callback=lambda result: future.set_result(result))
        return await future

    # --- Key dispatch ---

    def handle_key(self, key: str):
        """Synchronous method called from the app's on_key."""
        asyncio.create_task(self._handle_key_async(key))

    async def _handle_key_async(self, key: str):
        """Async version of key handling."""
        if key == "q":
            self.app.exit()
            return

        elif key == "g":
            await self.print_output("DEBUG: Pressed G, waiting for game selection...")
            try:
                game_name = await self._wait_for_modal(GameSelectionScreen())
                await self.print_output(f"DEBUG: Modal returned with {game_name}")
                if game_name:
                    await self.print_output(f"DEBUG: Game selected: {game_name}")
                    from pkm_session import make_game_ctx
                    try:
                        self.game_ctx = make_game_ctx(game_name)
                        await self.print_output(f"DEBUG: game_ctx set to {self.game_ctx['game']}")
                        await asyncio.sleep(0.05)
                        self.app.refresh_left_pane()
                        await self.print_output("DEBUG: left pane refreshed")
                        await self.print_output(f"Game set to: {game_name}")
                    except ValueError as e:
                        await self.print_output(f"Error: {e}")
                else:
                    await self.print_output("DEBUG: Game selection cancelled")
            except Exception as e:
                await self.print_output(f"DEBUG: Exception in game selection: {e}")
                await self.print_output(traceback.format_exc())
            return

        elif key == "p":
            await self.print_output("DEBUG: Pressed P, waiting for Pokemon selection...")
            try:
                pkm_ctx = await self.select_pokemon()
                if pkm_ctx:
                    self.pkm_ctx = pkm_ctx
                    await self.print_output(f"DEBUG: pkm_ctx set to {self.pkm_ctx['form_name']}")
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
                    await self.print_output("DEBUG: Pokemon selection cancelled")
            except Exception as e:
                await self.print_output(f"DEBUG: Exception in Pokemon selection: {e}")
                await self.print_output(traceback.format_exc())
            return

        elif key == "t":
            if self.game_ctx is None:
                await self.print_output("Please select a game first (press G).")
            else:
                from feat_team_loader import run as team_loader_run
                self.team_ctx = await team_loader_run(self, self.game_ctx, self.team_ctx)
                self.app.refresh_left_pane()
            return

        # ---- Move lookup ----
        elif key == "m":
            if self.game_ctx is None:
                await self.print_output("Select a game first (press G).")
            else:
                import feat_move_lookup
                await feat_move_lookup.run(self.game_ctx, ui=self)
            return

        # ---- Browsers ----
        elif key == "b":
            import feat_type_browser
            await feat_type_browser.run(game_ctx=self.game_ctx, ui=self)
        elif key == "n":
            import feat_nature_browser
            await feat_nature_browser.run(game_ctx=self.game_ctx, pkm_ctx=self.pkm_ctx, ui=self)
        elif key == "a":
            import feat_ability_browser
            await feat_ability_browser.run(game_ctx=self.game_ctx, pkm_ctx=self.pkm_ctx, ui=self)
        elif key == "l":
            if self.pkm_ctx is None:
                await self.print_output("Load a Pokemon first (press P).")
            elif self.game_ctx is None:
                await self.print_output("Select a game first (press G).")
            else:
                import feat_learnset_compare
                await feat_learnset_compare.run(self.pkm_ctx, self.game_ctx, ui=self)
        elif key == "e":
            if self.pkm_ctx is None:
                await self.print_output("Load a Pokemon first (press P).")
            else:
                import feat_egg_group
                await feat_egg_group.run(self.pkm_ctx, ui=self)

        # ---- Team features ----
        elif key in ("v", "o", "s", "h", "x"):
            if self.game_ctx is None:
                await self.print_output("Select a game first (press G).")
            elif team_size(self.team_ctx) == 0:
                await self.print_output("Load a team first (press T).")
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
                elif key == "x":
                    import feat_opponent
                    await feat_opponent.run(self.team_ctx, self.game_ctx, ui=self)

        # ---- Move table utilities ----
        elif key == "y":
            # Pre-load move table
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

        elif key == "w":
            # Pre-load TM/HM table
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

        elif key == "r":
            if self.pkm_ctx is None:
                await self.print_output("No Pokemon loaded to refresh.")
            else:
                chain_id = self.pkm_ctx.get("evolution_chain_id")
                if chain_id is not None:
                    cache.invalidate_evolution_chain(chain_id)
                self.pkm_ctx = refresh_pokemon(self.pkm_ctx, game_ctx=self.game_ctx)
                self.app.refresh_left_pane()
                await self.print_output(f"Refreshed {self.pkm_ctx['form_name']}.")

        # ---- Numbered features ----
        elif key.isdigit():
            idx = int(key)
            if idx < 1 or idx > len(PKM_FEATURES):
                await self.print_output("Invalid choice.")
                return
            label, module_name, entry_fn, needs_pkm, needs_game, avail = PKM_FEATURES[idx - 1]
            if not avail:
                await self.print_output(f"'{label}' is not yet available.")
                return
            if needs_game and self.game_ctx is None:
                await self.print_output("This feature needs a game selected first. Press G to select a game.")
                return
            if needs_pkm and self.pkm_ctx is None:
                await self.print_output("This feature needs a Pokemon loaded first. Press P to load a Pokemon.")
                return
            module = __import__(module_name)
            await getattr(module, entry_fn)(self.pkm_ctx, self.game_ctx, ui=self)

        else:
            await self.print_output(f"Key '{key}' not yet handled in TUI. Use CLI for now.")

    async def run(self):
        """Start the textual app."""
        await self.app.run_async()