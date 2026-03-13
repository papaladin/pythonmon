#!/usr/bin/env python3
"""
pkm_session.py  Game and Pokemon are two fully independent contexts.

  game_ctx  keys: game, era_key, game_gen
  pkm_ctx   keys: pokemon, variety_slug, form_name, types, type1, type2, abilities,
                  species_gen, form_gen, base_stats

Public API:
  select_game()
  select_pokemon(game_ctx=None)
  refresh_pokemon(pkm_ctx, game_ctx=None)
  select_from_list / select_form / print_session_header
"""

import sys

try:
    import matchup_calculator as calc
    import pkm_pokeapi
    import pkm_cache as cache
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Form generation helper ───────────────────────────────────────────────────

_FORM_GEN_KEYWORDS = [
    ("mega",     6),   # Mega Evolutions  — X/Y (Gen 6)
    ("alolan",   7),   # Alolan forms     — Sun/Moon (Gen 7)
    ("galarian", 8),   # Galarian forms   — Sword/Shield (Gen 8)
    ("hisuian",  8),   # Hisuian forms    — Legends: Arceus (Gen 8)
    ("paldean",  9),   # Paldean forms    — Scarlet/Violet (Gen 9)
]

def get_form_gen(form_name: str, species_gen) -> int | None:
    """
    Return the generation a specific form was introduced in.
    Keyword-based: first match wins. Falls back to species_gen for base forms.
    Special case: 'Mega ... Z' forms (e.g. Mega Garchomp Z) → Gen 9.
    """
    name_lower = form_name.lower()
    if "mega" in name_lower and name_lower.rstrip().endswith(" z"):
        return 9
    for keyword, gen in _FORM_GEN_KEYWORDS:
        if keyword in name_lower:
            return gen
    return species_gen


# ── Cache bridge ──────────────────────────────────────────────────────────────

def _cache_to_forms(data):
    # Include variety_slug from each form; fall back to the species slug
    # for old cache files that predate the variety_slug field.
    species_slug = data.get("pokemon", "")
    forms = [
        (f["name"], f["types"], f.get("variety_slug") or species_slug)
        for f in data["forms"]
    ]
    return forms, data.get("species_gen")


def _needs_variety_slug_upgrade(cached: dict) -> bool:
    """
    Return True if any form in the cache is missing variety_slug.
    This detects pre-§42 cache files and triggers a transparent re-fetch.
    """
    return any("variety_slug" not in f for f in cached.get("forms", []))


def _fetch_or_cache(name, force_refresh=False):
    """Return (forms, species_gen). Cache-first, PokeAPI on miss."""
    if not force_refresh:
        cached = cache.get_pokemon(name)
        if cached is not None:
            if _needs_variety_slug_upgrade(cached) or cache.needs_ability_upgrade(cached):
                print("  (cache outdated — re-fetching to get form data...)")
            else:
                print("  (loaded from cache)")
                return _cache_to_forms(cached)
    print(f"  Looking up '{name}' on PokeAPI...")
    data = pkm_pokeapi.fetch_pokemon(name)
    cache.save_pokemon(name, data)
    print("  (saved to cache)")
    return _cache_to_forms(data)

def _get_form_stats(name, form_name):
    data = cache.get_pokemon(name)
    if data:
        form = next((f for f in data["forms"] if f["name"] == form_name), None)
        if form:
            return form.get("base_stats", {})
    return {}


def _get_form_abilities(name, form_name):
    """Return abilities list for a specific form, or [] if not cached."""
    data = cache.get_pokemon(name)
    if data:
        form = next((f for f in data["forms"] if f["name"] == form_name), None)
        if form:
            return form.get("abilities", [])
    return []


# ── CLI helpers ───────────────────────────────────────────────────────────────

def select_from_list(prompt, options, allow_none=False):
    print(f"\n{prompt}")
    if allow_none:
        print("   0. None (single type)")
    for i, opt in enumerate(options, start=1):
        print(f"  {i:2d}. {opt}")
    while True:
        try:
            idx = int(input("  Enter number: ").strip())
            if allow_none and idx == 0:
                return "None"
            if 1 <= idx <= len(options):
                return options[idx - 1]
            print("  Invalid choice, try again.")
        except ValueError:
            print("  Please enter a number.")

def select_form(forms):
    print("\n  Multiple forms with different types found — pick one:")
    for i, (form_name, types, _vs) in enumerate(forms, start=1):
        print(f"  {i:2d}. {form_name:<28} ({' / '.join(types)})")
    while True:
        try:
            idx = int(input("  Enter number: ").strip())
            if 1 <= idx <= len(forms):
                return forms[idx - 1]
            print("  Invalid choice, try again.")
        except ValueError:
            print("  Please enter a number.")


# ── Game selection ────────────────────────────────────────────────────────────

def select_game(pkm_ctx=None):
    """
    Returns {game, era_key, game_gen}.

    If pkm_ctx is provided, validates that the loaded Pokemon/form existed
    in the selected game (form_gen <= game_gen). Loops until a compatible
    game is chosen, or the user aborts.
    """
    game_names = [g[0] for g in calc.GAMES]
    while True:
        game_choice = select_from_list("  Select GAME:", game_names)
        entry    = next(g for g in calc.GAMES if g[0] == game_choice)
        game_ctx = {"game": entry[0], "era_key": entry[1], "game_gen": entry[2]}

        if pkm_ctx is not None:
            form_gen  = pkm_ctx.get("form_gen")
            game_gen  = game_ctx["game_gen"]
            form_name = pkm_ctx["form_name"]
            game      = game_ctx["game"]
            if form_gen is not None and form_gen > game_gen:
                gen_label = calc.GENERATIONS.get(form_gen, {}).get("label",
                                                  f"Generation {form_gen}")
                print(f"\n  {form_name} was introduced in {gen_label}"
                      f" and did not exist in {game}.")
                print("  Please select a game from that generation or later.")
                if input("  Try another game? (y/n): ").strip().lower() != "y":
                    return None
                continue

        return game_ctx

# ── Pokemon selection ─────────────────────────────────────────────────────────

def _lookup_pokemon_name(force_refresh=False):
    """Prompt for name, fetch, return (name, forms, species_gen) or (None,None,None)."""
    while True:
        name = input("\n  Enter Pokemon name (e.g. Charizard, Garchomp, Rotom): ").strip()
        if not name:
            print("  Please enter a name.")
            continue
        if name.isdigit():
            print("  Please enter a name, not a Pokedex number.")
            continue
        try:
            forms, species_gen = _fetch_or_cache(name, force_refresh=force_refresh)
            return name, forms, species_gen
        except ValueError as e:
            print(f"\n  {e}")
            if input("  Try another name? (y/n): ").strip().lower() != "y":
                return None, None, None
        except ConnectionError as e:
            print(f"\n  Connection error: {e}")
            if input("  Try again? (y/n): ").strip().lower() != "y":
                return None, None, None

def select_pokemon(game_ctx=None, force_refresh=False):
    """
    Full Pokemon selection:
      1. Ask for name  2. Form selection  3. Era validation (if game_ctx)
    Returns pkm_ctx dict or None if aborted.

    If game_ctx is provided:
      - Blocks Pokemon/forms that did not exist in the selected game
        (form_gen > game_gen). User must pick another Pokemon or abort.
      - Blocks Pokemon whose primary type did not exist in the era.
      - Silently drops secondary type if it didn't exist in the era.
    """
    while True:
        name, forms, species_gen = _lookup_pokemon_name(force_refresh=force_refresh)
        if name is None:
            return None

        form_name, types, variety_slug = select_form(forms) if len(forms) > 1 else forms[0]
        type1 = types[0]
        type2 = types[1] if len(types) > 1 else "None"
        dual  = f"{type1} / {type2}" if type2 != "None" else type1
        print(f"\n  Loaded: {form_name} — {dual} type")

        form_gen = get_form_gen(form_name, species_gen)

        if game_ctx is not None:
            era_key  = game_ctx["era_key"]
            game_gen = game_ctx["game_gen"]
            game     = game_ctx["game"]
            _, valid_types, _ = calc.CHARTS[era_key]

            if form_gen is not None and form_gen > game_gen:
                gen_label = calc.GENERATIONS.get(form_gen, {}).get("label",
                                                  f"Generation {form_gen}")
                print(f"\n  {form_name} was introduced in {gen_label}"
                      f" and did not exist in {game}.")
                print("  Please choose a Pokemon that existed in that game.")
                if input("  Try another Pokemon? (y/n): ").strip().lower() != "y":
                    return None
                continue   # loop — ask for a new name

            if type1 not in valid_types:
                print(f"\n  {type1} type did not exist in {game}.")
                print(f"  Please select a game from the era when {type1} was introduced.")
                return None

            if type2 != "None" and type2 not in valid_types:
                print(f"\n  {type2} type did not exist in {game}.")
                print(f"  Treating {form_name} as single-type ({type1}) for this era.")
                type2 = "None"

        return {
            "pokemon"     : name,
            "variety_slug": variety_slug,
            "form_name"   : form_name,
            "types"       : types,
            "type1"       : type1,
            "type2"       : type2,
            "species_gen" : species_gen,
            "form_gen"    : form_gen,
            "base_stats"  : _get_form_stats(name, form_name),
            "abilities"   : _get_form_abilities(name, form_name),
        }

def refresh_pokemon(pkm_ctx, game_ctx=None):
    """Re-fetch and re-resolve current Pokemon. Returns updated pkm_ctx."""
    name = pkm_ctx["pokemon"]
    try:
        forms, species_gen = _fetch_or_cache(name, force_refresh=True)
    except (ValueError, ConnectionError) as e:
        print(f"\n  Could not refresh '{name}': {e}")
        print("  Keeping existing Pokemon data.")
        return pkm_ctx

    form_name = pkm_ctx["form_name"]
    match = next(((fn, t, vs) for fn, t, vs in forms if fn == form_name), None)
    if match is None:
        print(f"\n  Form '{form_name}' no longer found — defaulting to first form.")
        match = forms[0]

    form_name, types, variety_slug = match
    type1 = types[0]
    type2 = types[1] if len(types) > 1 else "None"
    print(f"  Refreshed: {form_name} — {' / '.join(types) if len(types)>1 else types[0]} type")

    form_gen = get_form_gen(form_name, species_gen)

    if game_ctx:
        _, valid_types, _ = calc.CHARTS[game_ctx["era_key"]]
        if type2 != "None" and type2 not in valid_types:
            print(f"  {type2} type didn't exist in {game_ctx['game']} — treating as single-type.")
            type2 = "None"

    return {**pkm_ctx, "variety_slug": variety_slug, "form_name": form_name,
            "types": types, "type1": type1, "type2": type2,
            "species_gen": species_gen, "form_gen": form_gen,
            "base_stats": _get_form_stats(name, form_name),
            "abilities" : _get_form_abilities(name, form_name)}


# ── Learnset lazy fetch ──────────────────────────────────────────────────────

# ── Header helper ─────────────────────────────────────────────────────────────

def print_session_header(pkm_ctx, game_ctx, constraints=None):
    """Compact context line above feature output."""
    parts = []
    if pkm_ctx:
        dual = (f"{pkm_ctx['type1']} / {pkm_ctx['type2']}"
                if pkm_ctx["type2"] != "None" else pkm_ctx["type1"])
        parts.append(f"{pkm_ctx['form_name']}  •  {dual}")
    if game_ctx:
        parts.append(game_ctx["game"])
    if constraints:
        parts.append(f"Locked: {', '.join(constraints)}")
    print("\n  [ " + "  •  ".join(parts) + " ]")


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os, tempfile
    import pkm_cache as _cache
    import pkm_session as _self

    print("\n  pkm_session.py — self-test\n")
    errors = []

    with tempfile.TemporaryDirectory() as tmp:
        _cache._BASE         = tmp
        _cache._POKEMON_DIR  = os.path.join(tmp, "pokemon")
        _cache._LEARNSET_DIR = os.path.join(tmp, "learnsets")
        _cache._MOVES_FILE   = os.path.join(tmp, "moves.json")
        _cache._ensure_dirs()

        def ok(label):   print(f"  [OK]   {label}")
        def fail(label, msg):
            print(f"  [FAIL] {label}: {msg}")
            errors.append(label)

        api_calls = []
        def fake_api(name):
            api_calls.append(name)
            if name.lower() == "fakizard":
                return {"pokemon": "fakizard", "species_gen": 1,
                        "forms": [
                            {"name": "Fakizard",       "variety_slug": "fakizard",       "types": ["Fire","Flying"], "base_stats": {"hp":78}, "abilities": [{"slug":"blaze","is_hidden":False}]},
                            {"name": "Mega Fakizard X","variety_slug": "fakizard-mega-x","types": ["Fire","Dragon"], "base_stats": {"hp":78}, "abilities": [{"slug":"blaze","is_hidden":False}]},
                        ]}
            raise ValueError(f"Pokemon '{name}' not found.")
        _self.pkm_pokeapi.fetch_pokemon = fake_api

        # T1: cache miss
        api_calls.clear()
        forms, sg = _self._fetch_or_cache("fakizard")
        if len(api_calls)==1 and forms[0]==("Fakizard",["Fire","Flying"],"fakizard"): ok("T1 cache miss → API")
        else: fail("T1", f"calls={api_calls} forms={forms}")

        # T2: cache hit (data has variety_slug → no re-fetch)
        api_calls.clear()
        forms2, _ = _self._fetch_or_cache("fakizard")
        if len(api_calls)==0 and forms2==forms: ok("T2 cache hit → no API")
        else: fail("T2", f"calls={api_calls}")

        # T2b: old cache without variety_slug → auto-upgrade (re-fetch once)
        api_calls.clear()
        old_fmt = {"pokemon": "fakizard", "species_gen": 1,
                   "forms": [{"name": "Fakizard", "types": ["Fire","Flying"], "base_stats": {}}]}
        _cache.save_pokemon("fakizard-old", old_fmt)
        _self.pkm_pokeapi.fetch_pokemon = lambda n: fake_api("fakizard")  # reuse same mock
        forms_upg, _ = _self._fetch_or_cache("fakizard-old")
        # Should have called API once (upgrade) and now have variety_slug in tuples
        has_slug = all(len(f)==3 and f[2] for f in forms_upg)
        if len(api_calls)==1 and has_slug: ok("T2b old cache auto-upgrade → re-fetch")
        else: fail("T2b", f"calls={api_calls} forms={forms_upg}")
        _self.pkm_pokeapi.fetch_pokemon = fake_api  # restore

        # T3: force_refresh
        api_calls.clear()
        _self._fetch_or_cache("fakizard", force_refresh=True)
        if len(api_calls)==1: ok("T3 force_refresh")
        else: fail("T3", f"calls={api_calls}")

        # T4: corrupt cache → re-fetch
        api_calls.clear()
        with open(_cache._pokemon_path("fakizard"), "w") as f: f.write("{bad}")
        _self._fetch_or_cache("fakizard")
        if len(api_calls)==1: ok("T4 corrupt cache → re-fetch")
        else: fail("T4", f"calls={api_calls}")

        # T5: _get_form_stats
        s = _self._get_form_stats("fakizard", "Fakizard")
        if s=={"hp":78}: ok("T5 _get_form_stats correct")
        else: fail("T5", f"got {s}")

        # T6: select_game
        orig = _self.select_from_list
        _self.select_from_list = lambda *a, **kw: "Scarlet / Violet"
        gctx = _self.select_game()
        _self.select_from_list = orig
        if gctx and gctx["game"]=="Scarlet / Violet" and gctx["game_gen"]==9:
            ok("T6 select_game correct")
        else: fail("T6", f"got {gctx}")

        # T7: print_session_header smoke
        print_session_header(
            {"form_name":"Garchomp","type1":"Dragon","type2":"Ground","types":["Dragon","Ground"]},
            {"game":"Scarlet / Violet","era_key":"era3","game_gen":9},
            ["Earthquake"])
        ok("T7 print_session_header no exception")

        # T8: refresh_pokemon
        api_calls.clear()
        _cache.invalidate_pokemon("fakizard")
        pctx = {"pokemon":"fakizard","form_name":"Fakizard","types":["Fire","Flying"],
                "type1":"Fire","type2":"Flying","species_gen":1,"form_gen":1,"base_stats":{}}
        r = _self.refresh_pokemon(pctx)
        if len(api_calls)==1 and r["form_name"]=="Fakizard": ok("T8 refresh_pokemon correct")
        else: fail("T8", f"calls={api_calls} form={r.get('form_name')}")


        # T9: select_pokemon blocks Pokemon not yet existing in selected game
        # Fakizard species_gen=1, Mega form_gen=6; game Gen 5 → should block Mega
        import builtins
        real_input = builtins.input

        game_gen5 = {"game": "Black / White", "era_key": "era2", "game_gen": 5}
        game_gen9 = {"game": "Scarlet / Violet", "era_key": "era3", "game_gen": 9}

        # Attempt Mega (form_gen 6) in Gen 5 game → blocked, then abort
        responses = iter(["fakizard", "2", "n"])   # name, pick form 2 (Mega), abort
        builtins.input = lambda p="": next(responses)
        result = _self.select_pokemon(game_ctx=game_gen5)
        if result is None: ok("T9 Mega Fakizard blocked in Gen 5 game")
        else: fail("T9", f"expected None, got {result.get('form_name')}")

        # T10: select_pokemon blocks Pokemon not yet existing → retry → success with base form
        responses = iter(["fakizard", "2", "y",   # try Mega → blocked → retry
                          "fakizard", "1"])         # try base form → accepted
        builtins.input = lambda p="": next(responses)
        result = _self.select_pokemon(game_ctx=game_gen5)
        if result and result["form_name"] == "Fakizard":
            ok("T10 Mega blocked → retry → base form accepted")
        else: fail("T10", f"got {result}")

        # T11: base form (form_gen=species_gen=1) always accepted in any game
        responses = iter(["fakizard", "1"])
        builtins.input = lambda p="": next(responses)
        result = _self.select_pokemon(game_ctx=game_gen5)
        if result and result["form_name"] == "Fakizard":
            ok("T11 Base form (gen 1) accepted in Gen 5 game")
        else: fail("T11", f"got {result}")

        # T12: Mega form accepted in Gen 9 game (form_gen 6 <= game_gen 9)
        responses = iter(["fakizard", "2"])
        builtins.input = lambda p="": next(responses)
        result = _self.select_pokemon(game_ctx=game_gen9)
        if result and result["form_name"] == "Mega Fakizard X":
            ok("T12 Mega Fakizard accepted in Gen 9 game")
        else: fail("T12", f"got {result}")

        # T13: select_game blocks game where loaded Pokemon didn't exist
        # Mega Fakizard X form_gen=6; try Gen 5 → blocked, then abort
        mega_ctx = {"form_name": "Mega Fakizard X", "form_gen": 6}
        responses = iter(["Black / White", "n"])   # pick gen5 game, then abort
        builtins.input = lambda p="": (
            _self.select_from_list.__wrapped__(p) if hasattr(_self.select_from_list, "__wrapped__")
            else next(responses)
        )
        # Override select_from_list to return the game name directly
        orig_sfl = _self.select_from_list
        games_iter = iter(["Black / White", "Scarlet / Violet"])
        _self.select_from_list = lambda *a, **kw: next(games_iter)
        responses = iter(["n"])
        builtins.input = lambda p="": next(responses)
        result = _self.select_game(pkm_ctx=mega_ctx)
        _self.select_from_list = orig_sfl
        if result is None: ok("T13 select_game blocks Gen 5 for Mega form")
        else: fail("T13", f"expected None, got {result}")

        # T14: select_game blocks then retries with valid game
        mega_ctx2 = {"form_name": "Mega Fakizard X", "form_gen": 6}
        orig_sfl = _self.select_from_list
        games_iter = iter(["Black / White", "Scarlet / Violet"])
        _self.select_from_list = lambda *a, **kw: next(games_iter)
        responses = iter(["y"])   # yes, try another game
        builtins.input = lambda p="": next(responses)
        result = _self.select_game(pkm_ctx=mega_ctx2)
        _self.select_from_list = orig_sfl
        if result and result["game_gen"] == 9:
            ok("T14 select_game blocked Gen5 → retry → Gen9 accepted")
        else: fail("T14", f"got {result}")

        builtins.input = real_input
    print()
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {14} tests passed\n")