#!/usr/bin/env python3
"""
feat_movepool.py  Full learnable move list

Displays all moves a Pokemon can learn in the selected game, grouped by
learn method (level-up, TM/HM, tutor, egg), with type/category/power/
accuracy/PP for each move.

Move details come from moves.json (lazy-fetched per move on cache miss).
Learnset comes from the learnset cache (lazy-fetched on first use).

Entry points:
  run(pkm_ctx, game_ctx, constraints, ui=None)  called from pokemain
  main()                                        standalone
"""

import sys

try:
    from pkm_session import select_game, select_pokemon, print_session_header
    import pkm_cache as cache
    import pkm_pokeapi as pokeapi
    import matchup_calculator as calc
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Move detail resolution ────────────────────────────────────────────────────

def _get_move_details(move_name: str, game_ctx: dict) -> dict | None:
    """
    Return the versioned move entry for this game, fetching from PokeAPI
    if not yet in moves.json.  Returns None if the move can't be resolved.
    """
    entries = cache.get_move(move_name)
    if entries is None:
        try:
            entries = pokeapi.fetch_move(move_name)
            # get canonical display name for storage
            slug = pokeapi._name_to_slug(move_name)
            data = pokeapi._get(f"move/{slug}")
            canonical = pokeapi._en_name(data.get("names", []), None) or move_name
            cache.upsert_move(canonical, entries)
        except (ValueError, ConnectionError):
            return None

    return cache.resolve_move(
        {move_name: entries}, move_name,
        game_ctx["game"], game_ctx["game_gen"]
    )


async def _prefetch_missing(ui, all_moves: list, game_ctx: dict) -> None:
    missing = [m for m in all_moves if cache.get_move(m) is None]
    if not missing:
        return

    total = len(missing)
    await ui.print_output(f"\n  Fetching details for {total} move(s) not yet in cache...")
    batch = {}
    for i, name in enumerate(missing, start=1):
        await ui.print_progress(f"  {i}/{total}  {name:<24}", end="\r", flush=True)
        try:
            entries = pokeapi.fetch_move(name)
            batch[name] = entries
        except (ValueError, ConnectionError):
            pass
    if batch:
        cache.upsert_move_batch(batch)
    await ui.print_progress("  Done — move details cached.             ")


# ── Display helpers ───────────────────────────────────────────────────────────

_COL_LABEL    =  7   # "Lv 46 " / "TM38  " / "      "
_COL_NAME     = 22   # move name
_COL_TYPE     = 10   # type
_COL_CAT      = 10   # category
_COL_PWR      =  5   # power
_COL_ACC      =  6   # accuracy
_COL_PP       =  5   # pp

_SEP_WIDTH = _COL_LABEL + _COL_NAME + _COL_TYPE + _COL_CAT + _COL_PWR + _COL_ACC + _COL_PP + 2

def _fmt_move_row(label: str, move_name: str, details: dict | None) -> str:
    if details:
        pwr = str(details["power"])    if details.get("power")    is not None else "--"
        acc = str(details["accuracy"]) if details.get("accuracy") is not None else "--"
        pp  = str(details["pp"])       if details.get("pp")       is not None else "--"
        typ = details.get("type", "?")
        cat = details.get("category", "?")
        acc_str = f"{acc}%"
        pp_str  = f"{pp}pp"
    else:
        pwr = acc_str = pp_str = typ = cat = "?"

    return (f"  {label:<{_COL_LABEL}}"
            f"  {move_name:<{_COL_NAME}}"
            f"  {typ:<{_COL_TYPE}}"
            f"  {cat:<{_COL_CAT}}"
            f"  {pwr:>{_COL_PWR}}"
            f"  {acc_str:>{_COL_ACC}}"
            f"  {pp_str:>{_COL_PP}}")

async def _section_header(ui, title: str) -> None:
    await ui.print_output(f"\n  ── {title} {'─' * max(0, _SEP_WIDTH - len(title) - 5)}")

async def _print_header_row(ui) -> None:
    await ui.print_output(_fmt_move_row("", "Move", "Type", "Cat", "Pwr", "Acc", "PP")
                    .replace("  Type      ", "  Type      ")  # already correct
                    )

async def _print_col_headers(ui) -> None:
    await ui.print_output(f"\n  {'':>{_COL_LABEL}}  "
                    f"{'Move':<{_COL_NAME}}  "
                    f"{'Type':<{_COL_TYPE}}  "
                    f"{'Category':<{_COL_CAT}}  "
                    f"{'Pwr':>{_COL_PWR}}  "
                    f"{'Acc':>{_COL_ACC}}  "
                    f"{'PP':>{_COL_PP}}")
    await ui.print_output(f"  {'─'*(_SEP_WIDTH + 4)}")


# ── Filter helpers ────────────────────────────────────────────────────────────

def _passes_filter(details: dict | None, f: dict) -> bool:
    """
    Return True if a move passes the filter spec.

    f keys (all optional / None = no constraint):
      "type"      — case-insensitive type match  e.g. "Fire"
      "category"  — "Physical" | "Special" | "Status"
      "min_power" — inclusive lower bound on power (int)

    Moves with details=None (not yet in cache) always pass — same
    graceful behaviour as the rest of the display code.
    """
    if details is None:
        return True
    if f.get("type"):
        if details.get("type", "").lower() != f["type"].lower():
            return False
    if f.get("category"):
        if details.get("category", "").lower() != f["category"].lower():
            return False
    if f.get("min_power") is not None:
        power = details.get("power")
        if power is None:          # status move — excluded by any power filter
            return False
        if power < f["min_power"]:
            return False
    return True


def _apply_filter(entries: list, f: dict) -> list:
    """
    Filter a flat list of (label, move_name, details_or_None) tuples.
    Returns the subset that passes _passes_filter.
    Pure — no I/O.
    """
    if not f or not any(v is not None for v in f.values()):
        return list(entries)
    return [e for e in entries if _passes_filter(e[2], f)]


def _filter_summary(f: dict) -> str:
    """Return a short human-readable description of active filter constraints."""
    parts = []
    if f.get("type"):
        parts.append(f"type={f['type']}")
    if f.get("category"):
        parts.append(f"cat={f['category']}")
    if f.get("min_power") is not None:
        parts.append(f"pwr≥{f['min_power']}")
    return "  |  ".join(parts) if parts else ""


async def _prompt_filter(ui) -> dict:
    """
    Interactively ask the user for up to three filter constraints.
    Returns a filter dict suitable for _passes_filter / _apply_filter.
    All fields are optional — pressing Enter on any question leaves it None.
    """
    _CAT_MAP = {
        "p": "Physical", "ph": "Physical", "physical": "Physical",
        "s": "Special",  "sp": "Special",  "special":  "Special",
        "t": "Status",   "st": "Status",   "sta": "Status", "status": "Status",
    }

    await ui.print_output("\n  Filter options (press Enter to skip any):")
    type_raw = await ui.input_prompt("    Type      (e.g. Fire, Water): ")
    cat_raw  = (await ui.input_prompt("    Category  (P)hysical / (S)pecial / (T) Status: ")).strip().lower()
    pow_raw  = await ui.input_prompt("    Min power (e.g. 80): ")

    return {
        "type"     : type_raw.capitalize() if type_raw else None,
        "category" : _CAT_MAP.get(cat_raw),
        "min_power": int(pow_raw) if pow_raw.isdigit() else None,
    }


def _is_tui(ui):
    """Return True if the UI is the TUI implementation."""
    return ui.__class__.__name__ == "TUI"


# ── Core display ──────────────────────────────────────────────────────────────

async def _display_learnset(ui, learnset: dict, pkm_ctx: dict, game_ctx: dict,
                            constraints: list,
                            filter_spec: dict | None = None) -> None:
    """Render the learnset for a form, optionally filtered."""
    # Find the right form in the learnset — fall back to first form
    form_name  = pkm_ctx["form_name"]
    forms_dict = learnset.get("forms", {})
    form_data  = forms_dict.get(form_name) or (
        next(iter(forms_dict.values())) if forms_dict else {}
    )

    if not form_data:
        await ui.print_output("\n  No move data found for this Pokemon / game combination.")
        return

    # Collect all move names for pre-fetch
    all_moves = []
    for method_entries in form_data.values():
        for e in method_entries:
            all_moves.append(e["move"])

    await _prefetch_missing(ui, all_moves, game_ctx)

    active = (filter_spec is not None
              and any(v is not None for v in filter_spec.values()))

    await ui.print_session_header(pkm_ctx, game_ctx, constraints)
    if active:
        await ui.print_output(f"  [ filter: {_filter_summary(filter_spec)} ]")
    await _print_col_headers(ui)

    # ── Helper: build one section's row list ──────────────────────────────────
    def _section_rows(entries, label_fn):
        """Return list of (label, move_name, details) for this section."""
        rows = []
        for entry in entries:
            details = _get_move_details(entry["move"], game_ctx)
            rows.append((label_fn(entry), entry["move"], details))
        return rows

    # ── Level-up ──────────────────────────────────────────────────────────────
    lvlup_entries = form_data.get("level-up", [])
    lvlup_rows = _section_rows(
        lvlup_entries,
        lambda e: f"Lv{e['level']:>3}" if e.get("level") and e["level"] > 0 else "Lv  --"
    )
    lvlup_shown = _apply_filter(lvlup_rows, filter_spec or {})
    if lvlup_shown or not active:
        await _section_header(ui, "LEVEL-UP")
        for label, name, details in (lvlup_shown if active else lvlup_rows):
            await ui.print_output(_fmt_move_row(label, name, details))

    # ── TM / HM ───────────────────────────────────────────────────────────────
    machine_entries = form_data.get("machine", [])
    machine_rows = _section_rows(machine_entries, lambda e: e.get("tm", ""))
    machine_shown = _apply_filter(machine_rows, filter_spec or {})
    if machine_shown or (not active and machine_entries):
        missing_labels = any("tm" not in e or not e["tm"] for e in machine_entries)
        await _section_header(ui, "TM / HM")
        if missing_labels and machine_entries:
            await ui.print_output("  (TM numbers unavailable — press W from main menu to fetch them,")
            await ui.print_output("   then press R to reload this Pokémon's data)")
        for label, name, details in (machine_shown if active else machine_rows):
            await ui.print_output(_fmt_move_row(label, name, details))

    # ── Tutor ─────────────────────────────────────────────────────────────────
    tutor_entries = form_data.get("tutor", [])
    tutor_rows = _section_rows(tutor_entries, lambda e: "")
    tutor_shown = _apply_filter(tutor_rows, filter_spec or {})
    if tutor_shown or (not active and tutor_entries):
        await _section_header(ui, "TUTOR")
        for label, name, details in (tutor_shown if active else tutor_rows):
            await ui.print_output(_fmt_move_row(label, name, details))

    # ── Egg moves ─────────────────────────────────────────────────────────────
    egg_entries = form_data.get("egg", [])
    egg_rows = _section_rows(egg_entries, lambda e: "")
    egg_shown = _apply_filter(egg_rows, filter_spec or {})
    if egg_shown or (not active and egg_entries):
        await _section_header(ui, "EGG MOVES")
        for label, name, details in (egg_shown if active else egg_rows):
            await ui.print_output(_fmt_move_row(label, name, details))

    # ── Summary ───────────────────────────────────────────────────────────────
    n_lvlup    = len(lvlup_entries)
    n_machine  = len(machine_entries)
    n_tutor    = len(tutor_entries)
    n_egg      = len(egg_entries)
    total_all  = n_lvlup + n_machine + n_tutor + n_egg

    if active:
        s_lvlup   = len(lvlup_shown)
        s_machine = len(machine_shown)
        s_tutor   = len(tutor_shown)
        s_egg     = len(egg_shown)
        total_shown = s_lvlup + s_machine + s_tutor + s_egg
        await ui.print_output(f"\n  Showing {total_shown} of {total_all} moves (filtered)"
                        f"  ({s_lvlup} level-up"
                        f"  {s_machine} TM/HM"
                        f"  {s_tutor} tutor"
                        f"  {s_egg} egg)")
    else:
        await ui.print_output(f"\n  Total: {total_all} moves  "
                        f"({n_lvlup} level-up"
                        f"  {n_machine} TM/HM"
                        f"  {n_tutor} tutor"
                        f"  {n_egg} egg)")

    # Mark locked moves if constraints are set
    if constraints:
        locked_found   = [m for m in constraints if m in all_moves]
        locked_missing = [m for m in constraints if m not in all_moves]
        if locked_found:
            await ui.print_output(f"\n  Locked moves learnable here: {', '.join(locked_found)}")
        if locked_missing:
            await ui.print_output(f"  WARNING — locked moves NOT in pool: {', '.join(locked_missing)}")


# ── Entry points ──────────────────────────────────────────────────────────────

async def run(pkm_ctx: dict, game_ctx: dict, constraints: list = None, ui=None) -> None:
    """Called from pokemain with both contexts loaded."""
    if ui is None:
        # Fallback dummy UI for standalone
        import builtins
        class DummyUI:
            async def print_output(self, text, end="\n"): builtins.print(text, end=end)
            async def print_progress(self, text, end="\n", flush=False): builtins.print(text, end=end, flush=flush)
            async def input_prompt(self, prompt): return builtins.input(prompt)
            async def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
        ui = DummyUI()

    name = pkm_ctx["pokemon"]
    game = game_ctx["game"]

    variety_slug = pkm_ctx.get("variety_slug") or name
    learnset = cache.get_learnset_or_fetch(variety_slug, pkm_ctx["form_name"], game)
    if learnset is None:
        await ui.print_output(f"\n  Could not load learnset for {pkm_ctx['form_name']} "
                              f"in {game}.")
        await ui.input_prompt("\n  Press Enter to continue...")
        return

    age = cache.get_learnset_age_days(variety_slug, game)
    if age is not None and age > cache.LEARNSET_STALE_DAYS:
        await ui.print_output(f"  [ learnset cached {age} days ago — press R to refresh ]")

    await _display_learnset(ui, learnset, pkm_ctx, game_ctx, constraints or [])

    # In TUI, skip filter prompt entirely
    if _is_tui(ui):
        await ui.input_prompt("\n  Press Enter to continue...")
        return

    # CLI: offer filter
    choice = (await ui.input_prompt("\n  Filter? (f to filter, Enter to return): ")).strip().lower()
    if choice == "f":
        f = await _prompt_filter(ui)
        if any(v is not None for v in f.values()):
            await _display_learnset(ui, learnset, pkm_ctx, game_ctx, constraints or [],
                                    filter_spec=f)
        else:
            await ui.print_output("  (no filter set)")
        await ui.input_prompt("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("╔══════════════════════════════════════════╗")
    print("║         Full Learnable Move List         ║")
    print("╚══════════════════════════════════════════╝")

    game_ctx = select_game()
    if game_ctx is None:
        sys.exit(0)

    pkm_ctx = select_pokemon(game_ctx=game_ctx)
    if pkm_ctx is None:
        sys.exit(0)

    variety_slug = pkm_ctx.get("variety_slug") or pkm_ctx["pokemon"]
    learnset = cache.get_learnset_or_fetch(variety_slug, pkm_ctx["form_name"], game_ctx["game"])
    if learnset is None:
        print("\n  Could not load learnset.")
        sys.exit(1)

    # Use dummy UI for standalone (synchronous)
    import builtins
    class DummyUI:
        async def print_output(self, text, end="\n"): builtins.print(text, end=end)
        async def print_progress(self, text, end="\n", flush=False): builtins.print(text, end=end, flush=flush)
        async def input_prompt(self, prompt): return builtins.input(prompt)
        async def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
    ui = DummyUI()

    import asyncio
    asyncio.run(run(pkm_ctx, game_ctx, [], ui))


# ── Self-tests (unchanged) ────────────────────────────────────────────────────

def _run_tests(with_cache=False):
    import sys
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_movepool.py — self-test\n")

    # ── _fmt_move_row ─────────────────────────────────────────────────────────
    details = {"power": 90, "accuracy": 100, "pp": 10,
               "type": "Fire", "category": "Special"}
    row = _fmt_move_row("Lv 36", "Flamethrower", details)

    # Must contain all key fields
    if "Flamethrower" in row: ok("_fmt_move_row move name present")
    else: fail("_fmt_move_row name", row[:60])

    if "Fire" in row: ok("_fmt_move_row type present")
    else: fail("_fmt_move_row type", row[:60])

    if "90" in row: ok("_fmt_move_row power present")
    else: fail("_fmt_move_row power", row[:60])

    if "100%" in row: ok("_fmt_move_row accuracy with % suffix")
    else: fail("_fmt_move_row accuracy", row[:60])

    if "10pp" in row: ok("_fmt_move_row pp with pp suffix")
    else: fail("_fmt_move_row pp", row[:60])

    if "Lv 36" in row: ok("_fmt_move_row label present")
    else: fail("_fmt_move_row label", row[:60])

    # None details → all ? placeholders
    row_none = _fmt_move_row("TM01", "Cut", None)
    if row_none.count("?") >= 4: ok("_fmt_move_row None details → ? placeholders")
    else: fail("_fmt_move_row None", row_none[:60])

    # Status move: no power → "--"
    details_status = {"power": None, "accuracy": None, "pp": 20,
                      "type": "Normal", "category": "Status"}
    row_s = _fmt_move_row("", "Swords Dance", details_status)
    if "--" in row_s: ok("_fmt_move_row status move power → --")
    else: fail("_fmt_move_row status power", row_s[:60])

    # ── _section_header (smoke — just check no exception) ─────────────────────
    import io, contextlib
    class DummyUI:
        def __init__(self): self.buf = io.StringIO()
        async def print_output(self, text): self.buf.write(text + "\n")
        async def input_prompt(self, prompt): return ""
    import asyncio
    dummy = DummyUI()
    asyncio.run(_section_header(dummy, "Level-up moves"))
    out = dummy.buf.getvalue()
    if "Level-up moves" in out: ok("_section_header smoke")
    else: fail("_section_header", out[:60])

    # ── _apply_filter ─────────────────────────────────────────────────────────
    fire_sp  = ("Lv 1", "Flamethrower", {"type": "Fire",   "category": "Special",  "power": 90})
    water_ph = ("TM55", "Waterfall",    {"type": "Water",  "category": "Physical", "power": 80})
    norm_st  = ("",     "Swords Dance", {"type": "Normal", "category": "Status",   "power": None})
    fire_ph  = ("Lv 5", "Fire Punch",   {"type": "Fire",   "category": "Physical", "power": 75})
    entries  = [fire_sp, water_ph, norm_st, fire_ph]

    # Type filter
    r = _apply_filter(entries, {"type": "Fire", "category": None, "min_power": None})
    if [e[1] for e in r] == ["Flamethrower", "Fire Punch"]:
        ok("_apply_filter type=Fire → 2 moves")
    else: fail("_apply_filter type", str([e[1] for e in r]))

    # Category filter
    r = _apply_filter(entries, {"type": None, "category": "Special", "min_power": None})
    if [e[1] for e in r] == ["Flamethrower"]:
        ok("_apply_filter category=Special → 1 move")
    else: fail("_apply_filter category", str([e[1] for e in r]))

    # Min power filter
    r = _apply_filter(entries, {"type": None, "category": None, "min_power": 80})
    if [e[1] for e in r] == ["Flamethrower", "Waterfall"]:
        ok("_apply_filter min_power=80 → 2 moves")
    else: fail("_apply_filter min_power", str([e[1] for e in r]))

    # Combined: Fire + Physical
    r = _apply_filter(entries, {"type": "Fire", "category": "Physical", "min_power": None})
    if [e[1] for e in r] == ["Fire Punch"]:
        ok("_apply_filter type=Fire + category=Physical → 1 move")
    else: fail("_apply_filter combined", str([e[1] for e in r]))

    # No filter (all None) → all moves returned unchanged
    r = _apply_filter(entries, {"type": None, "category": None, "min_power": None})
    if r == list(entries):
        ok("_apply_filter no filter → all moves returned")
    else: fail("_apply_filter no filter", str([e[1] for e in r]))

    # Filter that matches nothing → []
    r = _apply_filter(entries, {"type": "Dragon", "category": None, "min_power": None})
    if r == []:
        ok("_apply_filter no match → []")
    else: fail("_apply_filter no match", str([e[1] for e in r]))

    # Status move (power=None): excluded by min_power, included when min_power=None
    r_excl = _apply_filter([norm_st], {"type": None, "category": None, "min_power": 1})
    r_incl = _apply_filter([norm_st], {"type": None, "category": None, "min_power": None})
    if r_excl == [] and r_incl == [norm_st]:
        ok("_apply_filter status move excluded by min_power, included without")
    else: fail("_apply_filter status+min_power", f"excl={r_excl} incl={r_incl}")

    # ── _get_move_details (requires cache) ────────────────────────────────────
    if with_cache:
        game_ctx = {"game": "Scarlet / Violet", "era_key": "era3", "game_gen": 9}
        d = _get_move_details("Flamethrower", game_ctx)
        if d and d.get("type") == "Fire" and d.get("power") == 90:
            ok("_get_move_details Flamethrower → Fire 90bp")
        else:
            fail("_get_move_details", str(d)[:80])

        d2 = _get_move_details("Earthquake", game_ctx)
        if d2 and d2.get("category") == "Physical":
            ok("_get_move_details Earthquake Physical")
        else:
            fail("_get_move_details Earthquake", str(d2)[:80])

    # ── summary ──────────────────────────────────────────────────────────────
    print()
    total = 16 + (2 if with_cache else 0)
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if "--autotest" in args:
        _run_tests(with_cache="--withcache" in args)
    else:
        main()