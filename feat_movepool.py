#!/usr/bin/env python3
"""
feat_movepool.py  Full learnable move list

Displays all moves a Pokemon can learn in the selected game, grouped by
learn method (level-up, TM/HM, tutor, egg), with type/category/power/
accuracy/PP for each move.

Move details come from moves.json (lazy-fetched per move on cache miss).
Learnset comes from the learnset cache (lazy-fetched on first use).

Entry points:
  run(pkm_ctx, game_ctx, constraints)  called from pokemain
  main()                               standalone
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


def _prefetch_missing(all_moves: list, game_ctx: dict) -> None:
    """
    For each move name in all_moves not yet in moves.json, fetch from PokeAPI.
    Shows a progress line while fetching. Writes in a single batch operation.
    """
    missing = [m for m in all_moves if cache.get_move(m) is None]
    if not missing:
        return

    total = len(missing)
    print(f"\n  Fetching details for {total} move(s) not yet in cache...")
    batch = {}
    for i, name in enumerate(missing, start=1):
        print(f"  {i}/{total}  {name:<24}", end="\r", flush=True)
        try:
            entries     = pokeapi.fetch_move(name)
            batch[name] = entries
        except (ValueError, ConnectionError):
            pass
    if batch:
        cache.upsert_move_batch(batch)
    print(f"  Done — move details cached.             ")


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

def _section_header(title: str) -> None:
    print(f"\n  ── {title} {'─' * max(0, _SEP_WIDTH - len(title) - 5)}")

def _print_header_row() -> None:
    print(_fmt_move_row("", "Move", "Type", "Cat", "Pwr", "Acc", "PP")
          .replace("  Type      ", "  Type      ")  # already correct
          )

def _print_col_headers() -> None:
    print(f"\n  {'':>{_COL_LABEL}}  "
          f"{'Move':<{_COL_NAME}}  "
          f"{'Type':<{_COL_TYPE}}  "
          f"{'Category':<{_COL_CAT}}  "
          f"{'Pwr':>{_COL_PWR}}  "
          f"{'Acc':>{_COL_ACC}}  "
          f"{'PP':>{_COL_PP}}")
    print(f"  {'─'*(_SEP_WIDTH + 4)}")


# ── Core display ──────────────────────────────────────────────────────────────

def _display_learnset(learnset: dict, pkm_ctx: dict, game_ctx: dict,
                      constraints: list) -> None:
    """Render the full learnset for a form."""
    # Find the right form in the learnset — fall back to first form
    form_name  = pkm_ctx["form_name"]
    forms_dict = learnset.get("forms", {})
    form_data  = forms_dict.get(form_name) or (
        next(iter(forms_dict.values())) if forms_dict else {}
    )

    if not form_data:
        print("\n  No move data found for this Pokemon / game combination.")
        return

    # Collect all move names for pre-fetch
    all_moves = []
    for method_entries in form_data.values():
        for e in method_entries:
            all_moves.append(e["move"])

    _prefetch_missing(all_moves, game_ctx)

    print_session_header(pkm_ctx, game_ctx, constraints)
    _print_col_headers()

    # ── Level-up ──────────────────────────────────────────────────────────────
    lvlup = form_data.get("level-up", [])
    if lvlup:
        _section_header("LEVEL-UP")
        for entry in lvlup:
            lv    = entry["level"]
            label = f"Lv{lv:>3}" if lv and lv > 0 else "Lv  --"
            details = _get_move_details(entry["move"], game_ctx)
            print(_fmt_move_row(label, entry["move"], details))

    # ── TM / HM ───────────────────────────────────────────────────────────────
    machines = form_data.get("machine", [])
    if machines:
        missing_labels = any("tm" not in e or not e["tm"] for e in machines)
        _section_header("TM / HM")
        if missing_labels:
            print("  (TM numbers unavailable — press T from main menu to fetch them,")
            print("   then press R to reload this Pokémon's data)")
        for entry in machines:
            label   = entry.get("tm", "")
            details = _get_move_details(entry["move"], game_ctx)
            print(_fmt_move_row(label, entry["move"], details))

    # ── Tutor ─────────────────────────────────────────────────────────────────
    tutors = form_data.get("tutor", [])
    if tutors:
        _section_header("TUTOR")
        for entry in tutors:
            details = _get_move_details(entry["move"], game_ctx)
            print(_fmt_move_row("", entry["move"], details))

    # ── Egg moves ─────────────────────────────────────────────────────────────
    eggs = form_data.get("egg", [])
    if eggs:
        _section_header("EGG MOVES")
        for entry in eggs:
            details = _get_move_details(entry["move"], game_ctx)
            print(_fmt_move_row("", entry["move"], details))

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(lvlup) + len(machines) + len(tutors) + len(eggs)
    print(f"\n  Total: {total} moves  "
          f"({len(lvlup)} level-up"
          f"  {len(machines)} TM/HM"
          f"  {len(tutors)} tutor"
          f"  {len(eggs)} egg)")

    # Mark locked moves if constraints are set
    if constraints:
        locked_found = [m for m in constraints if m in all_moves]
        locked_missing = [m for m in constraints if m not in all_moves]
        if locked_found:
            print(f"\n  Locked moves learnable here: {', '.join(locked_found)}")
        if locked_missing:
            print(f"  WARNING — locked moves NOT in pool: {', '.join(locked_missing)}")


# ── Entry points ──────────────────────────────────────────────────────────────

def run(pkm_ctx: dict, game_ctx: dict, constraints: list = None) -> None:
    """Called from pokemain with both contexts loaded."""
    name = pkm_ctx["pokemon"]
    game = game_ctx["game"]

    variety_slug = pkm_ctx.get("variety_slug") or name
    learnset = cache.get_learnset_or_fetch(variety_slug, pkm_ctx["form_name"], game)
    if learnset is None:
        print(f"\n  Could not load learnset for {pkm_ctx['form_name']} "
              f"in {game}.")
        input("\n  Press Enter to continue...")
        return

    _display_learnset(learnset, pkm_ctx, game_ctx, constraints or [])
    input("\n  Press Enter to continue...")


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

    _display_learnset(learnset, pkm_ctx, game_ctx, [])
    input("\n  Press Enter to exit...")



# ── Self-tests ────────────────────────────────────────────────────────────────

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
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _section_header("Level-up moves")
    out = buf.getvalue()
    if "Level-up moves" in out: ok("_section_header smoke")
    else: fail("_section_header", out[:60])

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
    total = 9 + (2 if with_cache else 0)
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
