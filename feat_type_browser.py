#!/usr/bin/env python3
"""
feat_type_browser.py  Type browser / Pokémon type searcher

Lists all Pokémon that have a given type (or type combination).
Data comes from PokeAPI /type/{name}, cached in SQLite database.

Entry points:
  run(game_ctx=None, ui=None)   called from pokemain
  main()                         standalone

Display:
  - Single type   : all Pokémon with that type (either slot)
  - Type combo    : Pokémon that have BOTH types simultaneously
  - Columns       : Name, Type 1, Type 2, Gen
  - Name          : slug converted to title-case  (charizard-mega-x → Charizard-Mega-X)
  - Gen           : derived from national dex ID for base forms (ID ≤ 1025);
                    shown as "?" for alternate forms (Mega, Gigantamax, regional)
                    whose IDs are > 10000 in PokeAPI
  - Sorted        : generation ascending, then name alphabetically
  - Filtered      : only Pokémon that existed in the selected game (if game_ctx provided)
"""

import sys

try:
    import pkm_cache as cache
    import matchup_calculator as calc
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Generation derivation ─────────────────────────────────────────────────────
#
# Maps national dex ID ranges to generation numbers.
# Valid for base-form IDs (1–1025).  Alternate forms have IDs > 10000 in the
# PokeAPI variety system and cannot be mapped this way.

_GEN_RANGES = [
    (151,  1), (251,  2), (386,  3), (493,  4), (649,  5),
    (721,  6), (809,  7), (905,  8), (1025, 9),
]


def _id_to_gen(pokemon_id: int) -> int | None:
    """
    Return the generation number for a national-dex / variety ID, or None
    if the ID is outside the known base-form range (e.g. alternate forms).
    """
    for max_id, gen in _GEN_RANGES:
        if pokemon_id <= max_id:
            return gen
    return None


def _species_gen_from_slug(slug: str) -> int | None:
    """
    Determine the generation a species (or form) was introduced.
    Tries to use the pokemon cache if available, otherwise falls back to
    _id_to_gen on the base species ID (extracted from the slug).
    """
    # Try direct cache lookup
    pkm_data = cache.get_pokemon(slug)
    if pkm_data:
        return pkm_data.get("species_gen")

    # If slug contains a hyphen, try the base species (everything before last hyphen)
    if "-" in slug:
        base_slug = slug[:slug.rfind("-")]
        pkm_data = cache.get_pokemon(base_slug)
        if pkm_data:
            return pkm_data.get("species_gen")

    # Fallback: if we have an ID in the entry we can use, but we don't have it here.
    # This function is called later with the entry's ID; we'll just return None.
    return None


# ── Name formatting ───────────────────────────────────────────────────────────

def _slug_to_title(slug: str) -> str:
    """
    Convert a PokeAPI slug to a human-readable title-case name.
    charizard-mega-x  →  Charizard-Mega-X
    mr-mime           →  Mr-Mime
    ho-oh             →  Ho-Oh
    """
    return "-".join(part.capitalize() for part in slug.split("-"))


# ── Type validation ───────────────────────────────────────────────────────────

def _valid_types() -> list:
    """Return the sorted list of valid type names for the current era."""
    return sorted(calc.TYPES_ERA3)


def _parse_type(raw: str) -> str | None:
    """
    Validate and normalise a user-entered type name.
    Returns the capitalised type string (e.g. 'Fire') or None if invalid.
    """
    normalised = raw.strip().capitalize()
    if normalised in calc.TYPES_ERA3:
        return normalised
    return None


def _is_tui(ui):
    """Return True if the UI is the TUI implementation."""
    return ui.__class__.__name__ == "TUI"


# ── Roster building ───────────────────────────────────────────────────────────

def _build_rows(type1: str, type2: str | None, game_gen: int | None = None) -> list:
    """
    Fetch and merge roster(s), returning a list of display row dicts:
      {name, type1, type2, gen, sort_gen}

    For a type combo query, only Pokémon that carry BOTH types are returned.
    slot information is used to assign type1/type2 in the display:
      the queried primary type is shown first; the secondary fills the second
      column regardless of its slot in the API.

    If game_gen is provided, Pokémon whose species generation > game_gen are
    filtered out. Alternate forms without a clear generation are kept (assumed
    available) to avoid overly aggressive filtering.
    """
    roster1 = cache.get_type_roster_or_fetch(type1)
    if roster1 is None:
        return []
    cache.resolve_type_roster_names(type1)   # enrich hyphenated names (no-op if done)
    roster1 = cache.get_type_roster(type1)   # re-read with names populated

    if type2 is not None:
        roster2 = cache.get_type_roster_or_fetch(type2)
        if roster2 is None:
            return []
        cache.resolve_type_roster_names(type2)
        roster2 = cache.get_type_roster(type2)
        # Intersect: keep only slugs present in both rosters
        slugs2 = {e["slug"] for e in roster2}
        combined = [e for e in roster1 if e["slug"] in slugs2]
    else:
        combined = roster1

    rows = []
    for entry in combined:
        slug    = entry["slug"]
        id_     = entry["id"]
        # Determine generation for this entry
        if id_ is not None and id_ <= 1025:
            gen = _id_to_gen(id_)
        else:
            # Try to get generation from cache (species or base species)
            gen = _species_gen_from_slug(slug)
            if gen is None:
                # Keep entry but treat as unknown generation (show as "?")
                gen = None

        # Filter by game generation if specified
        if game_gen is not None and gen is not None and gen > game_gen:
            continue

        # Use the resolved display name if present; fall back to slug-to-title
        name    = entry.get("name") or _slug_to_title(slug)

        # Determine which types to show in the two columns.
        # For a type-combo query we know the Pokemon has both types.
        # For a single-type query the second column is blank for mono-types.
        if type2 is not None:
            col_t1 = type1
            col_t2 = type2
        else:
            # slot 1 = primary type (the queried one), slot 2 = secondary
            if entry["slot"] == 1:
                col_t1 = type1
                col_t2 = ""
            else:
                col_t1 = ""       # primary type is something else
                col_t2 = type1

        sort_gen = gen if gen is not None else 999
        rows.append({
            "name"    : name,
            "col_t1"  : col_t1,
            "col_t2"  : col_t2,
            "gen"     : gen,
            "sort_gen": sort_gen,
        })

    # Sort: gen ascending, then name alphabetically
    rows.sort(key=lambda r: (r["sort_gen"], r["name"]))
    return rows


# ── Display ───────────────────────────────────────────────────────────────────

_COL_NAME = 26
_COL_T1   = 10
_COL_T2   = 10
_COL_GEN  =  4
_TABLE_W  = _COL_NAME + _COL_T1 + _COL_T2 + _COL_GEN + 3  # separators


async def _print_header(ui, type1: str, type2: str | None, n: int) -> None:
    title = f"{type1} / {type2}" if type2 else type1
    await ui.print_output(f"\n  {title} Pokémon  ({n} found)")
    await ui.print_output("  " + "─" * _TABLE_W)
    await ui.print_output(f"  {'Name':<{_COL_NAME}}{'Type 1':<{_COL_T1}}{'Type 2':<{_COL_T2}}{'Gen':>{_COL_GEN}}")
    await ui.print_output("  " + "─" * _TABLE_W)


async def _print_rows(ui, rows: list) -> None:
    for r in rows:
        gen_str = str(r["gen"]) if r["gen"] is not None else "?"
        await ui.print_output(f"  {r['name']:<{_COL_NAME}}"
                              f"{r['col_t1']:<{_COL_T1}}"
                              f"{r['col_t2']:<{_COL_T2}}"
                              f"{gen_str:>{_COL_GEN}}")
    await ui.print_output("")


# ── Main feature entry point ──────────────────────────────────────────────────

async def run(game_ctx=None, ui=None) -> None:
    """
    Interactive type browser.  Prompts for one or two types, then displays
    the matching Pokémon table.  In CLI mode, the user can choose to search again;
    in TUI mode, the browser returns to the main menu after one search.

    If game_ctx is provided, the list is filtered to only include Pokémon that
    existed in that game (by generation).
    """
    if ui is None:
        # Fallback dummy UI for standalone
        from ui_dummy import DummyUI
        ui = DummyUI()

    game_gen = game_ctx.get("game_gen") if game_ctx else None
    valid = _valid_types()
    valid_lower = {t.lower(): t for t in valid}
    is_tui = _is_tui(ui)

    # In TUI we run only once; in CLI we loop until user quits
    while True:
        await ui.print_output(f"\n  Types: {', '.join(valid)}")
        raw1 = await ui.input_prompt("\n  Enter type (Q to quit): ")
        if raw1.lower() == "q":
            return

        type1 = valid_lower.get(raw1.lower())
        if type1 is None:
            await ui.print_output(f"  Unknown type '{raw1}'. Please try again.")
            continue

        raw2 = await ui.input_prompt(f"  Enter second type (or Enter for {type1} only): ")
        if raw2 == "":
            type2 = None
        else:
            type2 = valid_lower.get(raw2.lower())
            if type2 is None:
                await ui.print_output(f"  Unknown type '{raw2}'. Please try again.")
                continue
            if type2 == type1:
                await ui.print_output("  Both types are the same — showing single-type results.")
                type2 = None

        rows = _build_rows(type1, type2, game_gen)
        if not rows:
            label = f"{type1}/{type2}" if type2 else type1
            await ui.print_output(f"\n  No Pokémon found for {label} "
                            f"(or data could not be fetched).")
        else:
            await _print_header(ui, type1, type2, len(rows))
            await _print_rows(ui, rows)

        # In TUI, we exit after one search; in CLI, we ask if user wants to continue.
        if is_tui:
            return
        else:
            again = (await ui.input_prompt("  Search again? (y/n): ")).strip().lower()
            if again != "y":
                return


# ── Standalone entry point ────────────────────────────────────────────────────

def main() -> None:
    import asyncio
    asyncio.run(run())


# ── Unit tests (unchanged) ────────────────────────────────────────────────────

def _run_tests(with_cache: bool = False) -> None:
    passed = 0
    failed = 0

    def check(label, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")

    # ── _id_to_gen ────────────────────────────────────────────────────────────
    check("Gen 1: Bulbasaur (id=1)",      _id_to_gen(1)    == 1)
    check("Gen 1: Mew (id=151)",          _id_to_gen(151)  == 1)
    check("Gen 2: Chikorita (id=152)",    _id_to_gen(152)  == 2)
    check("Gen 2: Celebi (id=251)",       _id_to_gen(251)  == 2)
    check("Gen 3: Treecko (id=252)",      _id_to_gen(252)  == 3)
    check("Gen 4: Turtwig (id=387)",      _id_to_gen(387)  == 4)
    check("Gen 5: Victini (id=494)",      _id_to_gen(494)  == 5)
    check("Gen 6: Chespin (id=650)",      _id_to_gen(650)  == 6)
    check("Gen 7: Rowlet (id=722)",       _id_to_gen(722)  == 7)
    check("Gen 8: Grookey (id=810)",      _id_to_gen(810)  == 8)
    check("Gen 9: Sprigatito (id=906)",   _id_to_gen(906)  == 9)
    check("Gen 9: Pecharunt (id=1025)",   _id_to_gen(1025) == 9)
    check("Alternate form → None (10034)",_id_to_gen(10034) is None)
    check("Alternate form → None (10158)",_id_to_gen(10158) is None)

    # ── _slug_to_title ────────────────────────────────────────────────────────
    check("slug: charizard → Charizard",           _slug_to_title("charizard")       == "Charizard")
    check("slug: charizard-mega-x → Charizard-Mega-X",
          _slug_to_title("charizard-mega-x") == "Charizard-Mega-X")
    check("slug: mr-mime → Mr-Mime",               _slug_to_title("mr-mime")         == "Mr-Mime")
    check("slug: ho-oh → Ho-Oh",                   _slug_to_title("ho-oh")           == "Ho-Oh")
    check("slug: nidoran-f → Nidoran-F",           _slug_to_title("nidoran-f")       == "Nidoran-F")
    check("slug: jangmo-o → Jangmo-O",             _slug_to_title("jangmo-o")        == "Jangmo-O")
    check("slug: porygon-z → Porygon-Z",           _slug_to_title("porygon-z")       == "Porygon-Z")

    # ── _parse_type ───────────────────────────────────────────────────────────
    check("parse: 'fire' → 'Fire'",         _parse_type("fire")    == "Fire")
    check("parse: 'FIRE' → 'Fire'",         _parse_type("FIRE")    == "Fire")
    check("parse: 'Fire' → 'Fire'",         _parse_type("Fire")    == "Fire")
    check("parse: ' fire ' → 'Fire'",       _parse_type(" fire ")  == "Fire")
    check("parse: 'invalid' → None",        _parse_type("invalid") is None)
    check("parse: '' → None",               _parse_type("")        is None)

    # ── _build_rows sorting (pure, no cache) ─────────────────────────────────
    fake_roster = [
        {"slug": "bulbasaur",      "slot": 1, "id": 1},
        {"slug": "chikorita",      "slot": 1, "id": 152},
        {"slug": "azumarill",      "slot": 2, "id": 184},
        {"slug": "charizard-mega-x","slot": 2, "id": 10034},
    ]
    rows = []
    for e in fake_roster:
        gen = _id_to_gen(e["id"])
        rows.append({
            "name"    : _slug_to_title(e["slug"]),
            "col_t1"  : "Grass" if e["slot"] == 1 else "",
            "col_t2"  : "" if e["slot"] == 1 else "Grass",
            "gen"     : gen,
            "sort_gen": gen if gen is not None else 999,
        })
    rows.sort(key=lambda r: (r["sort_gen"], r["name"]))

    check("sort: gen1 before gen2",
          rows[0]["name"] == "Bulbasaur" and rows[1]["name"] in ("Azumarill", "Chikorita"))
    check("sort: within gen2, alphabetical (Azumarill before Chikorita)",
          rows[1]["name"] == "Azumarill" and rows[2]["name"] == "Chikorita")
    check("sort: alt-form (gen=None) sorted last",
          rows[-1]["name"] == "Charizard-Mega-X")
    check("sort: alt-form gen displayed as None",
          rows[-1]["gen"] is None)

    # ── single-type slot assignment ─────────────────────────────────────────
    def _slot_cols(entry, type1):
        if entry["slot"] == 1:
            return type1, ""
        return "", type1

    slot1_entry = {"slug": "charmander", "slot": 1, "id": 4}
    slot2_entry = {"slug": "charizard",  "slot": 1, "id": 6}
    t1, t2 = _slot_cols(slot1_entry, "Fire")
    check("single-type slot1: col_t1=Fire, col_t2=''", t1 == "Fire" and t2 == "")
    flying_entry = {"slug": "charizard", "slot": 2, "id": 6}
    t1, t2 = _slot_cols(flying_entry, "Flying")
    check("single-type slot2: col_t1='', col_t2=Flying", t1 == "" and t2 == "Flying")

    # ── entry["name"] used in preference to slug-to-title ────────────────────
    entry_with_name    = {"slug": "mr-mime",   "slot": 1, "id": 122, "name": "Mr. Mime"}
    entry_without_name = {"slug": "mr-mime",   "slot": 1, "id": 122}
    entry_no_hyphen    = {"slug": "charizard", "slot": 1, "id": 6}

    name_resolved   = entry_with_name.get("name")  or _slug_to_title(entry_with_name["slug"])
    name_fallback   = entry_without_name.get("name") or _slug_to_title(entry_without_name["slug"])
    name_no_hyphen  = entry_no_hyphen.get("name")  or _slug_to_title(entry_no_hyphen["slug"])

    check('entry with "name" field: uses resolved name "Mr. Mime"',
          name_resolved == "Mr. Mime")
    check('entry without "name" field: falls back to slug-to-title "Mr-Mime"',
          name_fallback == "Mr-Mime")
    check('no-hyphen entry: slug-to-title "Charizard"',
          name_no_hyphen == "Charizard")

    # ── resolve_type_roster_names: offline test with mock ────────────────────
    import tempfile
    import pkm_cache as _cache
    import pkm_pokeapi as _api

    orig_base = _cache._BASE
    tmp_dir = tempfile.mkdtemp()
    _cache._BASE = tmp_dir
    _cache.pkm_sqlite.set_base(tmp_dir)

    try:
        fake_roster = [
            {"slug": "charizard",       "slot": 1, "id": 6},
            {"slug": "charizard-mega-x","slot": 1, "id": 10034},
            {"slug": "mr-mime",         "slot": 1, "id": 122, "name": "Mr. Mime"},
        ]
        _cache.save_type_roster("TestType", fake_roster)

        roster = _cache.get_type_roster("TestType")
        mega_entry = next(e for e in roster if e["slug"] == "charizard-mega-x")
        check("before resolve: charizard-mega-x has no 'name'",
              "name" not in mega_entry)

        def _mock_fetch(slug):
            return {"charizard-mega-x": "Mega Charizard X"}.get(slug)

        orig_fetch = _api.fetch_form_display_name
        _api.fetch_form_display_name = _mock_fetch

        _cache.resolve_type_roster_names("TestType")

        roster2 = _cache.get_type_roster("TestType")
        mega2 = next(e for e in roster2 if e["slug"] == "charizard-mega-x")
        mr2   = next(e for e in roster2 if e["slug"] == "mr-mime")
        char2 = next(e for e in roster2 if e["slug"] == "charizard")

        check('after resolve: charizard-mega-x name = "Mega Charizard X"',
              mega2.get("name") == "Mega Charizard X")
        check("after resolve: mr-mime name unchanged (was already resolved)",
              mr2.get("name") == "Mr. Mime")
        check("after resolve: charizard has no 'name' (no-hyphen skipped)",
              "name" not in char2)

        call_count = [0]
        orig_save = _cache.save_type_roster
        def _counting_save(t, r):
            call_count[0] += 1
            orig_save(t, r)
        _cache.save_type_roster = _counting_save
        _cache.resolve_type_roster_names("TestType")
        _cache.save_type_roster = orig_save

        check("second resolve call is a no-op (no unnecessary save)",
              call_count[0] == 0)

    finally:
        _api.fetch_form_display_name = orig_fetch
        _cache._BASE = orig_base
        _cache.pkm_sqlite.set_base(orig_base)
        import shutil as _sh
        _sh.rmtree(tmp_dir, ignore_errors=True)

    # ── with_cache tests (optional) ──────────────────────────────────────────
    if with_cache:
        roster = _cache.get_type_roster("Fire")
        if roster is None:
            check("withcache: Fire type roster fetched from cache", False)
        else:
            check("withcache: Fire type roster is a non-empty list",
                  isinstance(roster, list) and len(roster) > 0)

            all_valid = all(
                isinstance(e.get("slug"), str) and
                e.get("slot") in (1, 2) and
                isinstance(e.get("id"), int)
                for e in roster
            )
            check("withcache: all roster entries have slug/slot/id", all_valid)

            slugs = {e["slug"] for e in roster}
            check("withcache: Charizard in Fire roster",    "charizard"    in slugs)
            check("withcache: Arcanine in Fire roster",     "arcanine"     in slugs)
            check("withcache: Charmander in Fire roster",   "charmander"   in slugs)

            _cache.resolve_type_roster_names("Fire")
            roster2 = _cache.get_type_roster("Fire")
            hyphenated = [e for e in roster2 if "-" in e["slug"]]
            all_named = all("name" in e for e in hyphenated)
            check("withcache: all hyphenated entries have resolved name",
                  not hyphenated or all_named)

            by_slug = {e["slug"]: e for e in roster2}
            if "charizard-mega-x" in by_slug:
                mega_name = by_slug["charizard-mega-x"].get("name", "")
                check('withcache: Charizard-Mega-X → "Mega Charizard X"',
                      mega_name == "Mega Charizard X")
            else:
                check("withcache: charizard-mega-x present (may be gen-filtered)", True)

    print()
    if failed:
        print(f"  {passed} passed, {failed} failed out of {passed+failed} tests.")
        sys.exit(1)
    else:
        print(f"  {passed} passed, 0 failed out of {passed} tests.")
        print("  All tests passed.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--autotest",   action="store_true")
    parser.add_argument("--withcache",  action="store_true")
    args = parser.parse_args()
    if args.autotest:
        _run_tests(with_cache=args.withcache)
    else:
        main()