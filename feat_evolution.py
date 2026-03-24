#!/usr/bin/env python3
"""
feat_evolution.py  Evolution chain display

Shows the evolution chain for the loaded Pokemon at the bottom of option 1
(feat_quick_view.py). No standalone menu key — surfaced via option 1.

The chain is filtered by game generation: evolutions introduced after the
selected game are not shown. Eevee in FireRed shows only the Gen 1-2
Eeveelutions; Gen 4+ branches are silently dropped.

Types for all chain stages are fetched at display time: cache hit = instant,
cache miss = one API call + cache write per uncached stage. The ★ marker
uses pkm_ctx["pokemon"] (raw species slug) so alternate forms (Mega, regional)
are correctly identified in the chain.

Public API:
  get_or_fetch_chain(pkm_ctx)                    → list[list[dict]] | None
  display_evolution_block(pkm_ctx, paths,
                          game_gen=None)          → None  (called by feat_quick_view)

Internal helpers (cache-aware):
  _get_species_gen(slug)                         → int | None
  _get_types_for_slug(slug)                      → list[str]
  _type_tag(types)                               → str
"""

import sys

try:
    import pkm_cache as cache
    from core_evolution import parse_trigger, flatten_chain, filter_paths_for_game
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Type lookup helpers (cache-aware) ─────────────────────────────────────────

def _get_types_for_slug(slug: str) -> list[str]:
    """
    Return the type list for a species slug.
    Tries the pokemon cache first (instant). Falls back to fetching from
    PokeAPI on miss (one API call + cache write per uncached stage).
    Returns [] if unavailable.
    """
    data = cache.get_pokemon(slug)
    if data is not None:
        forms = data.get("forms", [])
        if forms:
            return forms[0].get("types", [])
    # Not cached — fetch and save
    try:
        import pkm_pokeapi as pokeapi
        data = pokeapi.fetch_pokemon(slug)
        cache.save_pokemon(slug, data)
        forms = data.get("forms", [])
        if forms:
            return forms[0].get("types", [])
    except (ValueError, ConnectionError):
        pass
    return []


def _type_tag(types: list[str]) -> str:
    """Format a type list as a bracketed tag: ['Fire', 'Flying'] → '[Fire / Flying]'."""
    if not types:
        return "[?]"
    return f"[{' / '.join(types)}]"


def _get_species_gen(slug: str) -> int | None:
    """
    Return the generation a species was introduced, from the pokemon cache.
    Returns None if not cached (treated as unknown — not filtered out).
    """
    data = cache.get_pokemon(slug)
    if data is not None:
        return data.get("species_gen")
    return None


# ── Cache-aware chain fetch ───────────────────────────────────────────────────

def get_or_fetch_chain(pkm_ctx: dict) -> list | None:
    """
    Return the flattened evolution chain paths for the loaded Pokemon.

    Checks pkm_ctx["evolution_chain_id"], then reads from cache/evolution/.
    Fetches from PokeAPI on miss and saves to cache.

    Returns None if:
      - evolution_chain_id is None (event Pokemon with no chain)
      - network unavailable and cache empty
    """
    chain_id = pkm_ctx.get("evolution_chain_id")
    if chain_id is None:
        return None

    paths = cache.get_evolution_chain(chain_id)
    if paths is not None:
        return paths

    try:
        import pkm_pokeapi as pokeapi
        print("  Loading evolution chain...", end=" ", flush=True)
        node = pokeapi.fetch_evolution_chain(chain_id)
        paths = flatten_chain(node)
        cache.save_evolution_chain(chain_id, paths)
        print("done.")
        return paths
    except (ValueError, ConnectionError):
        return None


# ── Display ───────────────────────────────────────────────────────────────────

_SEP_WIDTH = 46


def display_evolution_block(pkm_ctx: dict, paths: list,
                            game_gen: int | None = None) -> None:
    """
    Print the compact evolution chain block for embedding in option 1.

    game_gen: if provided, filters out evolutions introduced after that
    generation. Eevee in FireRed (gen 3) will only show the 3 Gen-1/2
    Eeveelutions, not Espeon, Umbreon, Glaceon, Leafeon, Sylveon.
    """
    current_slug = pkm_ctx.get("pokemon", "")

    # Build species_gen_map for all slugs in the paths
    all_slugs = {stage["slug"] for path in paths for stage in path}
    species_gen_map = {}
    for slug in all_slugs:
        gen = _get_species_gen(slug)
        if gen is not None:
            species_gen_map[slug] = gen

    # Apply game-gen filter
    display_paths = filter_paths_for_game(paths, game_gen, species_gen_map) if game_gen else paths

    print(f"\n  Evolution chain")
    print("  " + "─" * _SEP_WIDTH)

    # Pre-fetch types for all unique slugs not already in cache
    need_fetch = [s for s in all_slugs if cache.get_pokemon(s) is None]
    if need_fetch:
        print(f"  Fetching types for {len(need_fetch)} stage(s)...",
              end=" ", flush=True)
        for s in need_fetch:
            _get_types_for_slug(s)   # side-effect: populates cache
        print("done.")

    if len(display_paths) == 1 and len(display_paths[0]) == 1:
        # Single-stage — does not evolve (or all evolutions filtered for this game)
        stage = display_paths[0][0]
        types = _get_types_for_slug(stage["slug"])
        marker = " ★" if stage["slug"] == current_slug else ""
        no_evo_note = "no further evolution in this game" \
            if game_gen and len(paths) > 1 else "does not evolve"
        print(f"  {stage['slug'].replace('-', ' ').title()} "
              f"{_type_tag(types)}{marker}  — {no_evo_note}")
    else:
        for path in display_paths:
            parts = []
            for i, stage in enumerate(path):
                types = _get_types_for_slug(stage["slug"])
                marker = " ★" if stage["slug"] == current_slug else ""
                name = stage["slug"].replace("-", " ").title()
                entry = f"{name} {_type_tag(types)}{marker}"
                if i > 0 and stage["trigger"]:
                    parts.append(f"→  {stage['trigger']}  →  {entry}")
                else:
                    parts.append(entry)
            print("  " + "  ".join(parts))

    print()
    print("  ★ = current Pokémon")


# ── Self‑tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import io, contextlib, sys as _sys
    errors = []
    def ok(label):  print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_evolution.py — self-test\n")

    # Most of the pure logic tests are now in core_evolution.py.
    # Here we keep only the tests that involve cache and display.

    # Mock get_or_fetch_chain and type fetching to avoid network
    _orig_get = globals().get("get_or_fetch_chain")
    _orig_types = globals().get("_get_types_for_slug")

    def _mock_types(slug):
        return {"charmander": ["Fire"], "charmeleon": ["Fire"],
                "charizard": ["Fire", "Flying"], "eevee": ["Normal"],
                "espeon": ["Psychic"], "umbreon": ["Dark"]}.get(slug, [])

    def _mock_chain(pkm_ctx):
        return [
            [{"slug": "charmander", "trigger": ""},
             {"slug": "charmeleon", "trigger": "Level 16"},
             {"slug": "charizard", "trigger": "Level 36"}]
        ]

    _sys.modules[__name__].get_or_fetch_chain = _mock_chain
    _sys.modules[__name__]._get_types_for_slug = _mock_types

    try:
        pkm_charizard = {"pokemon": "charizard", "evolution_chain_id": 1}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            display_evolution_block(pkm_charizard,
                                    _mock_chain(pkm_charizard))
        out = buf.getvalue()

        if "Charmander" in out and "Charmeleon" in out and "Charizard" in out:
            ok("display_evolution_block: all stage names present")
        else:
            fail("display_evolution_block names", out[:120])

        if "★" in out:
            ok("display_evolution_block: ★ marker present")
        else:
            fail("display_evolution_block ★", out[:120])

        if "[Fire / Flying]" in out:
            ok("display_evolution_block: type tags shown")
        else:
            fail("display_evolution_block types", out[:120])

        if "Level 16" in out and "Level 36" in out:
            ok("display_evolution_block: triggers shown")
        else:
            fail("display_evolution_block triggers", out[:120])

    finally:
        _sys.modules[__name__].get_or_fetch_chain = _orig_get
        _sys.modules[__name__]._get_types_for_slug = _orig_types

    print()
    total = 4
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
    else:
        main()