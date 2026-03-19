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
  filter_paths_for_game(paths, game_gen)         → list[list[dict]]

Internal pure helpers (testable offline):
  _parse_trigger(details)                        → str
  _flatten_chain(node, max_depth=20)             → list[list[dict]]
  _get_species_gen(slug)                         → int | None
  _get_types_for_slug(slug)                      → list[str]
  _type_tag(types)                               → str
"""

import sys

try:
    import pkm_cache as cache
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Pure parsing helpers ──────────────────────────────────────────────────────

def _slug_to_title(slug: str) -> str:
    """Convert a hyphenated slug to title case: 'fire-stone' → 'Fire Stone'."""
    return slug.replace("-", " ").title() if slug else ""


def _parse_trigger(details: list) -> str:
    """
    Convert a PokeAPI evolution_details list to a human-readable trigger string.

    evolution_details is a list of condition dicts. Uses the first entry.
    Returns "" if the list is empty (stage 0 — the base species).

    Priority order within a level-up trigger:
      min_level > min_happiness > known_move > time_of_day > bare level-up
    """
    if not details:
        return ""

    d = details[0]
    trigger_name  = (d.get("trigger") or {}).get("name", "")
    min_level     = d.get("min_level")
    min_happiness = d.get("min_happiness")
    known_move    = (d.get("known_move") or {}).get("name", "")
    item          = (d.get("item") or {}).get("name", "")
    time_of_day   = d.get("time_of_day", "")

    if trigger_name == "level-up":
        if min_level:
            return f"Level {min_level}"
        if min_happiness:
            if time_of_day == "day":
                return "High Friendship (day)"
            if time_of_day == "night":
                return "High Friendship (night)"
            return "High Friendship"
        if known_move:
            return f"Level up knowing {_slug_to_title(known_move)}"
        if time_of_day == "day":
            return "Level up (day)"
        if time_of_day == "night":
            return "Level up (night)"
        return "Level up"

    if trigger_name == "use-item":
        return f"Use {_slug_to_title(item)}" if item else "Use item"

    if trigger_name == "trade":
        held = (d.get("held_item") or {}).get("name", "")
        return f"Trade holding {_slug_to_title(held)}" if held else "Trade"

    if trigger_name == "shed":
        return "Level 20 (empty slot)"

    return "Special condition"


def _flatten_chain(node: dict, max_depth: int = 20) -> list:
    """
    Recursively flatten a PokeAPI chain tree into a list of linear paths.

    Each path is a list of stage dicts from root to leaf:
      [{"slug": str, "trigger": str}, ...]

    "trigger" is the condition to evolve FROM the previous stage into this one.
    The root stage always has trigger = "".

    For branching chains (Eevee, Slowpoke) one path is produced per branch.
    max_depth guards against malformed data with cycles.

    Returns list[list[dict]].
    """
    if max_depth <= 0:
        return []

    slug    = node.get("species", {}).get("name", "")
    details = node.get("evolution_details", [])
    trigger = _parse_trigger(details)
    stage   = {"slug": slug, "trigger": trigger}

    branches = node.get("evolves_to", [])
    if not branches:
        # Leaf node — this is a complete path
        return [[stage]]

    paths = []
    for child in branches:
        for child_path in _flatten_chain(child, max_depth - 1):
            paths.append([stage] + child_path)
    return paths


# ── Type lookup helper ────────────────────────────────────────────────────────

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


def filter_paths_for_game(paths: list, game_gen: int) -> list:
    """
    Filter evolution paths to only include stages available in a given game gen.

    For each path, truncate at the first stage whose species_gen > game_gen.
    Paths that reduce to a single stage (only the base species) are kept as-is
    — they represent "no evolution available in this game".
    Paths where the second stage is available are kept in full up to that point.

    Pure function — no I/O. Species gen looked up from cache via _get_species_gen.

    Returns the filtered path list. De-duplicates paths that become identical
    after truncation (e.g. multiple Eevee branches all truncate to [Eevee]).
    """
    if game_gen is None:
        return paths

    filtered = []
    seen_keys = set()
    base_only = []   # truncated paths that reduce to just the base species

    for path in paths:
        truncated = [path[0]]   # always include base stage (stage 0)
        for stage in path[1:]:
            gen = _get_species_gen(stage["slug"])
            if gen is not None and gen > game_gen:
                break   # this evolution and all later ones are unavailable
            truncated.append(stage)

        key = tuple(s["slug"] for s in truncated)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        if len(truncated) == 1:
            base_only.append(truncated)   # collect separately
        else:
            filtered.append(truncated)

    # Only include the base-only stub if there are no valid evolution paths
    # (i.e. all evolutions were filtered out for this game)
    if not filtered:
        result = base_only[:1] if base_only else paths[:1]
    else:
        result = filtered

    return result


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
        node  = pokeapi.fetch_evolution_chain(chain_id)
        paths = _flatten_chain(node)
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

    # Apply game-gen filter before any display
    display_paths = filter_paths_for_game(paths, game_gen) if game_gen else paths

    print(f"\n  Evolution chain")
    print("  " + "─" * _SEP_WIDTH)

    # Pre-fetch types for all unique slugs not already in cache
    all_slugs = {stage["slug"] for path in display_paths for stage in path}
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
                types  = _get_types_for_slug(stage["slug"])
                marker = " ★" if stage["slug"] == current_slug else ""
                name   = stage["slug"].replace("-", " ").title()
                entry  = f"{name} {_type_tag(types)}{marker}"
                if i > 0 and stage["trigger"]:
                    parts.append(f"→  {stage['trigger']}  →  {entry}")
                else:
                    parts.append(entry)
            print("  " + "  ".join(parts))

    print()
    print("  ★ = current Pokémon")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):  print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_evolution.py — self-test\n")

    # ── _parse_trigger ────────────────────────────────────────────────────────

    def _d(trigger_name, **kwargs):
        """Build a minimal evolution_details list for testing."""
        d = {"trigger": {"name": trigger_name}}
        if "min_level" in kwargs:
            d["min_level"] = kwargs["min_level"]
        if "min_happiness" in kwargs:
            d["min_happiness"] = kwargs["min_happiness"]
        if "known_move" in kwargs:
            d["known_move"] = {"name": kwargs["known_move"]}
        if "item" in kwargs:
            d["item"] = {"name": kwargs["item"]}
        if "held_item" in kwargs:
            d["held_item"] = {"name": kwargs["held_item"]}
        if "time_of_day" in kwargs:
            d["time_of_day"] = kwargs["time_of_day"]
        return [d]

    r = _parse_trigger(_d("level-up", min_level=16))
    if r == "Level 16": ok("_parse_trigger: level-up + min_level → Level N")
    else: fail("_parse_trigger level min_level", r)

    r = _parse_trigger(_d("level-up", min_happiness=160, time_of_day="day"))
    if r == "High Friendship (day)": ok("_parse_trigger: level-up + min_happiness + day → High Friendship (day)")
    else: fail("_parse_trigger happiness day", r)

    r = _parse_trigger(_d("level-up", min_happiness=160, time_of_day="night"))
    if r == "High Friendship (night)": ok("_parse_trigger: level-up + min_happiness + night → High Friendship (night)")
    else: fail("_parse_trigger happiness night", r)

    r = _parse_trigger(_d("level-up", min_happiness=220))
    if r == "High Friendship": ok("_parse_trigger: level-up + min_happiness (no time) → High Friendship")
    else: fail("_parse_trigger level happiness", r)

    r = _parse_trigger(_d("level-up", known_move="solar-beam"))
    if r == "Level up knowing Solar Beam":
        ok("_parse_trigger: level-up + known_move → Level up knowing <Move>")
    else: fail("_parse_trigger level known_move", r)

    r = _parse_trigger(_d("level-up", time_of_day="day"))
    if r == "Level up (day)": ok("_parse_trigger: level-up + day → Level up (day)")
    else: fail("_parse_trigger level day", r)

    r = _parse_trigger(_d("level-up", time_of_day="night"))
    if r == "Level up (night)": ok("_parse_trigger: level-up + night → Level up (night)")
    else: fail("_parse_trigger level night", r)

    r = _parse_trigger(_d("level-up"))
    if r == "Level up": ok("_parse_trigger: bare level-up → Level up")
    else: fail("_parse_trigger bare level-up", r)

    r = _parse_trigger(_d("use-item", item="fire-stone"))
    if r == "Use Fire Stone": ok("_parse_trigger: use-item → Use <Item>")
    else: fail("_parse_trigger use-item", r)

    r = _parse_trigger(_d("trade"))
    if r == "Trade": ok("_parse_trigger: trade (no item) → Trade")
    else: fail("_parse_trigger trade bare", r)

    r = _parse_trigger(_d("trade", held_item="metal-coat"))
    if r == "Trade holding Metal Coat":
        ok("_parse_trigger: trade + held_item → Trade holding <Item>  (PokeAPI field)")
    else: fail("_parse_trigger trade held_item", r)

    r = _parse_trigger(_d("shed"))
    if r == "Level 20 (empty slot)": ok("_parse_trigger: shed → Level 20 (empty slot)")
    else: fail("_parse_trigger shed", r)

    r = _parse_trigger([])
    if r == "": ok("_parse_trigger: empty list → empty string (stage 0)")
    else: fail("_parse_trigger empty", repr(r))

    r = _parse_trigger(_d("other"))
    if r == "Special condition": ok("_parse_trigger: unknown trigger → Special condition")
    else: fail("_parse_trigger unknown", r)

    # ── _flatten_chain ────────────────────────────────────────────────────────

    def _node(slug, details=None, children=None):
        return {
            "species"          : {"name": slug},
            "evolution_details": details or [],
            "evolves_to"       : children or [],
        }

    # Linear 3-stage chain: Bulbasaur → Ivysaur → Venusaur
    linear = _node("bulbasaur", children=[
        _node("ivysaur",   details=_d("level-up", min_level=16), children=[
            _node("venusaur", details=_d("level-up", min_level=32))
        ])
    ])
    paths = _flatten_chain(linear)
    if (len(paths) == 1
            and len(paths[0]) == 3
            and paths[0][0]["slug"] == "bulbasaur"
            and paths[0][1]["slug"] == "ivysaur"
            and paths[0][1]["trigger"] == "Level 16"
            and paths[0][2]["slug"] == "venusaur"
            and paths[0][2]["trigger"] == "Level 32"):
        ok("_flatten_chain: linear 3-stage → 1 path, 3 stages, triggers correct")
    else:
        fail("_flatten_chain linear", str([(s["slug"], s["trigger"]) for s in paths[0]] if paths else "no paths"))

    # 2-branch chain: Slowpoke → Slowbro | Slowking
    branching = _node("slowpoke", children=[
        _node("slowbro",  details=_d("level-up", min_level=37)),
        _node("slowking", details=_d("trade", item="kings-rock")),
    ])
    paths = _flatten_chain(branching)
    slugs_per_path = [[s["slug"] for s in p] for p in paths]
    if (len(paths) == 2
            and ["slowpoke", "slowbro"]  in slugs_per_path
            and ["slowpoke", "slowking"] in slugs_per_path):
        ok("_flatten_chain: 2-branch → 2 paths, correct slugs")
    else:
        fail("_flatten_chain branching", str(slugs_per_path))

    # Single-stage (no evolution): Kangaskhan
    single = _node("kangaskhan")
    paths = _flatten_chain(single)
    if len(paths) == 1 and len(paths[0]) == 1 and paths[0][0]["slug"] == "kangaskhan":
        ok("_flatten_chain: single-stage → 1 path, 1 stage")
    else:
        fail("_flatten_chain single", str(paths))

    # max_depth guard: artificially deep chain truncates rather than crashing
    deep = _node("a")
    node = deep
    for letter in "bcdefghijklmnopqrstuvwxyz":
        child = _node(letter, details=_d("level-up", min_level=1))
        node["evolves_to"] = [child]
        node = child
    try:
        paths = _flatten_chain(deep, max_depth=5)
        ok("_flatten_chain: max_depth guard → no crash, returns partial paths")
    except RecursionError:
        fail("_flatten_chain max_depth", "RecursionError raised")

    # ── filter_paths_for_game ─────────────────────────────────────────────────

    # Mock _get_species_gen to avoid cache
    import sys as _sys3
    _self2 = _sys3.modules[__name__]
    _orig_gen = _self2._get_species_gen

    _GEN_MAP = {
        "eevee": 1, "vaporeon": 1, "jolteon": 1, "flareon": 1,
        "espeon": 2, "umbreon": 2,
        "leafeon": 4, "glaceon": 4, "sylveon": 6,
        "charmander": 1, "charmeleon": 1, "charizard": 1,
    }
    _self2._get_species_gen = lambda slug: _GEN_MAP.get(slug)

    try:
        # All 8 Eevee branches, gen 3 game → only gen 1 + gen 2 remain
        eevee_paths = [
            [{"slug":"eevee","trigger":""}, {"slug":"vaporeon","trigger":"Use Water Stone"}],
            [{"slug":"eevee","trigger":""}, {"slug":"jolteon", "trigger":"Use Thunder Stone"}],
            [{"slug":"eevee","trigger":""}, {"slug":"flareon", "trigger":"Use Fire Stone"}],
            [{"slug":"eevee","trigger":""}, {"slug":"espeon",  "trigger":"High Friendship (day)"}],
            [{"slug":"eevee","trigger":""}, {"slug":"umbreon", "trigger":"High Friendship (night)"}],
            [{"slug":"eevee","trigger":""}, {"slug":"leafeon", "trigger":"Level up near Moss Rock"}],
            [{"slug":"eevee","trigger":""}, {"slug":"glaceon", "trigger":"Level up near Ice Rock"}],
            [{"slug":"eevee","trigger":""}, {"slug":"sylveon", "trigger":"High Friendship (Fairy move)"}],
        ]
        filtered = filter_paths_for_game(eevee_paths, game_gen=3)
        filtered_targets = [p[1]["slug"] for p in filtered if len(p) > 1]
        expected = {"vaporeon", "jolteon", "flareon", "espeon", "umbreon"}
        if set(filtered_targets) == expected and len(filtered) == 5:
            ok("filter_paths_for_game: Eevee gen3 → 5 branches (no gen4/6)")
        else:
            fail("filter_paths_for_game Eevee gen3",
                 f"got {filtered_targets}")

        # No filter (game_gen=None) → all paths returned
        result = filter_paths_for_game(eevee_paths, game_gen=None)
        if result is eevee_paths:
            ok("filter_paths_for_game: game_gen=None → paths unchanged")
        else:
            fail("filter_paths_for_game None", str(len(result)))

        # All evolutions filtered → de-duplicated to single base-only path
        filtered2 = filter_paths_for_game(eevee_paths, game_gen=0)
        if len(filtered2) == 1 and len(filtered2[0]) == 1 \
                and filtered2[0][0]["slug"] == "eevee":
            ok("filter_paths_for_game: all filtered → single base-only path")
        else:
            fail("filter_paths_for_game all filtered", str(filtered2))

        # Linear chain unaffected when all stages within game_gen
        charmander_paths = [
            [{"slug":"charmander","trigger":""},
             {"slug":"charmeleon","trigger":"Level 16"},
             {"slug":"charizard", "trigger":"Level 36"}]
        ]
        result2 = filter_paths_for_game(charmander_paths, game_gen=1)
        if result2 == charmander_paths:
            ok("filter_paths_for_game: gen1 chain in gen1 game → unchanged")
        else:
            fail("filter_paths_for_game linear", str(result2))

    finally:
        _self2._get_species_gen = _orig_gen

    # ── display_evolution_block (stdout capture + mock type lookup) ───────────
    import io, contextlib, sys as _sys

    # Mock _get_types_for_slug to avoid cache/network
    import sys as _sys2
    _self = _sys2.modules[__name__]
    _orig_types = _self._get_types_for_slug

    _TYPE_MAP = {
        "charmander": ["Fire"],
        "charmeleon" : ["Fire"],
        "charizard"  : ["Fire", "Flying"],
        "eevee"      : ["Normal"],
        "espeon"     : ["Psychic"],
        "umbreon"    : ["Dark"],
        "kangaskhan" : ["Normal"],
    }
    _self._get_types_for_slug = lambda slug: _TYPE_MAP.get(slug, [])

    try:
        # Linear chain — all names + ★ marker
        linear_paths = [
            [{"slug": "charmander", "trigger": ""},
             {"slug": "charmeleon", "trigger": "Level 16"},
             {"slug": "charizard",  "trigger": "Level 36"}]
        ]
        pkm_charizard = {"pokemon": "charizard", "evolution_chain_id": 1}

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            display_evolution_block(pkm_charizard, linear_paths)
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

        # Branching chain — two lines
        branching_paths = [
            [{"slug": "eevee", "trigger": ""}, {"slug": "espeon",  "trigger": "High Friendship (day)"}],
            [{"slug": "eevee", "trigger": ""}, {"slug": "umbreon", "trigger": "High Friendship (night)"}],
        ]
        pkm_eevee = {"pokemon": "eevee", "evolution_chain_id": 67}

        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            display_evolution_block(pkm_eevee, branching_paths)
        out2 = buf2.getvalue()

        lines = [l for l in out2.splitlines() if "→" in l]
        if len(lines) == 2:
            ok("display_evolution_block: branching chain → 2 lines")
        else:
            fail("display_evolution_block branching", f"{len(lines)} arrow lines: {out2[:120]}")

        if "Espeon" in out2 and "Umbreon" in out2:
            ok("display_evolution_block: both branch targets present")
        else:
            fail("display_evolution_block branches", out2[:120])

        # Single-stage — does not evolve
        single_paths = [[{"slug": "kangaskhan", "trigger": ""}]]
        pkm_kanga = {"pokemon": "kangaskhan", "evolution_chain_id": 99}

        buf3 = io.StringIO()
        with contextlib.redirect_stdout(buf3):
            display_evolution_block(pkm_kanga, single_paths)
        out3 = buf3.getvalue()

        if "does not evolve" in out3:
            ok("display_evolution_block: single-stage → does not evolve")
        else:
            fail("display_evolution_block single", out3[:80])

        if "Kangaskhan" in out3 and "★" in out3:
            ok("display_evolution_block: single-stage name + ★ present")
        else:
            fail("display_evolution_block single name/★", out3[:80])

        # chain_id=None → get_or_fetch_chain returns None
        # (no network call needed — pure guard check)
        result = get_or_fetch_chain({"pokemon": "celebi", "evolution_chain_id": None})
        if result is None:
            ok("get_or_fetch_chain: chain_id=None → None (no fetch)")
        else:
            fail("get_or_fetch_chain None", str(result))

        # game_gen filter applied in display — Eevee in gen1 game shows only gen1 branches
        _TYPE_MAP2 = {"eevee": ["Normal"], "vaporeon": ["Water"],
                      "jolteon": ["Electric"], "flareon": ["Fire"],
                      "espeon": ["Psychic"], "leafeon": ["Grass"]}
        _self._get_types_for_slug = lambda s: _TYPE_MAP2.get(s, [])

        # Also mock _get_species_gen for display filter
        _GEN_MAP2 = {"eevee": 1, "vaporeon": 1, "jolteon": 1, "flareon": 1,
                     "espeon": 2, "leafeon": 4}
        _self._get_species_gen = lambda s: _GEN_MAP2.get(s)

        eevee_all = [
            [{"slug":"eevee","trigger":""}, {"slug":"vaporeon","trigger":"Use Water Stone"}],
            [{"slug":"eevee","trigger":""}, {"slug":"jolteon", "trigger":"Use Thunder Stone"}],
            [{"slug":"eevee","trigger":""}, {"slug":"flareon", "trigger":"Use Fire Stone"}],
            [{"slug":"eevee","trigger":""}, {"slug":"espeon",  "trigger":"High Friendship"}],
            [{"slug":"eevee","trigger":""}, {"slug":"leafeon", "trigger":"Level up near Moss Rock"}],
        ]
        pkm_eevee2 = {"pokemon": "eevee", "evolution_chain_id": 67}

        buf4 = io.StringIO()
        with contextlib.redirect_stdout(buf4):
            display_evolution_block(pkm_eevee2, eevee_all, game_gen=1)
        out4 = buf4.getvalue()
        lines4 = [l for l in out4.splitlines() if "→" in l]
        if len(lines4) == 3 and "Leafeon" not in out4 and "Espeon" not in out4:
            ok("display_evolution_block: game_gen filter removes gen2/4 branches")
        else:
            fail("display_evolution_block game_gen filter",
                 f"{len(lines4)} lines, leafeon={'Leafeon' in out4}, espeon={'Espeon' in out4}")

    finally:
        _self._get_types_for_slug = _orig_types

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 35
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
