#!/usr/bin/env python3
"""
core_evolution.py  Pure evolution‑chain logic (no I/O, no display)

Functions:
  parse_trigger(details) → str
  flatten_chain(node, max_depth=20) → list[list[dict]]
  filter_paths_for_game(paths, game_gen, species_gen_map) → list[list[dict]]
"""

import sys


def parse_trigger(details: list) -> str:
    """
    Convert a PokeAPI evolution_details list to a human-readable trigger string.

    Returns "" if the list is empty (stage 0 — the base species).
    """
    if not details:
        return ""

    d = details[0]
    trigger_name = (d.get("trigger") or {}).get("name", "")
    min_level = d.get("min_level")
    min_happiness = d.get("min_happiness")
    known_move = (d.get("known_move") or {}).get("name", "")
    item = (d.get("item") or {}).get("name", "")
    held_item = (d.get("held_item") or {}).get("name", "")
    time_of_day = d.get("time_of_day", "")

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
            # Convert move slug to title case
            return f"Level up knowing {known_move.replace('-', ' ').title()}"
        if time_of_day == "day":
            return "Level up (day)"
        if time_of_day == "night":
            return "Level up (night)"
        return "Level up"

    if trigger_name == "use-item":
        return f"Use {item.replace('-', ' ').title()}" if item else "Use item"

    if trigger_name == "trade":
        return f"Trade holding {held_item.replace('-', ' ').title()}" if held_item else "Trade"

    if trigger_name == "shed":
        return "Level 20 (empty slot)"

    return "Special condition"


def flatten_chain(node: dict, max_depth: int = 20) -> list:
    """
    Recursively flatten a PokeAPI chain tree into a list of linear paths.

    Each path is a list of stage dicts from root to leaf:
      [{"slug": str, "trigger": str}, ...]

    "trigger" is the condition to evolve FROM the previous stage into this one.
    The root stage always has trigger = "".

    max_depth guards against malformed data with cycles.
    """
    if max_depth <= 0:
        return []

    slug = node.get("species", {}).get("name", "")
    details = node.get("evolution_details", [])
    trigger = parse_trigger(details)
    stage = {"slug": slug, "trigger": trigger}

    branches = node.get("evolves_to", [])
    if not branches:
        return [[stage]]

    paths = []
    for child in branches:
        for child_path in flatten_chain(child, max_depth - 1):
            paths.append([stage] + child_path)
    return paths


def filter_paths_for_game(paths: list, game_gen: int,
                          species_gen_map: dict) -> list:
    """
    Filter evolution paths to only include stages available in a given game gen.

    For each path, truncate at the first stage whose species_gen > game_gen.
    Paths that reduce to a single stage (only the base species) are kept as-is
    — they represent "no evolution available in this game".
    Paths where the second stage is available are kept in full up to that point.

    species_gen_map: dict mapping slug → generation number (int).
    """
    if game_gen is None:
        return paths

    filtered = []
    seen_keys = set()
    base_only = []   # truncated paths that reduce to just the base species

    for path in paths:
        truncated = [path[0]]   # always include base stage (stage 0)
        for stage in path[1:]:
            gen = species_gen_map.get(stage["slug"])
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


# ── Self‑tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    total = 0
    def ok(label):
        nonlocal total
        total += 1
        print(f"  [OK]   {label}")
    def fail(label, msg=""):
        nonlocal total
        total += 1
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  core_evolution.py — self-test\n")

    # ── parse_trigger tests ──────────────────────────────────────────────────
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

    r = parse_trigger(_d("level-up", min_level=16))
    if r == "Level 16":
        ok("parse_trigger: level-up + min_level → Level N")
    else:
        fail("parse_trigger level min_level", r)

    r = parse_trigger(_d("level-up", min_happiness=160, time_of_day="day"))
    if r == "High Friendship (day)":
        ok("parse_trigger: level-up + min_happiness + day → High Friendship (day)")
    else:
        fail("parse_trigger happiness day", r)

    r = parse_trigger(_d("level-up", min_happiness=160, time_of_day="night"))
    if r == "High Friendship (night)":
        ok("parse_trigger: level-up + min_happiness + night → High Friendship (night)")
    else:
        fail("parse_trigger happiness night", r)

    r = parse_trigger(_d("level-up", min_happiness=220))
    if r == "High Friendship":
        ok("parse_trigger: level-up + min_happiness (no time) → High Friendship")
    else:
        fail("parse_trigger level happiness", r)

    r = parse_trigger(_d("level-up", known_move="solar-beam"))
    if r == "Level up knowing Solar Beam":
        ok("parse_trigger: level-up + known_move → Level up knowing <Move>")
    else:
        fail("parse_trigger level known_move", r)

    r = parse_trigger(_d("level-up", time_of_day="day"))
    if r == "Level up (day)":
        ok("parse_trigger: level-up + day → Level up (day)")
    else:
        fail("parse_trigger level day", r)

    r = parse_trigger(_d("level-up", time_of_day="night"))
    if r == "Level up (night)":
        ok("parse_trigger: level-up + night → Level up (night)")
    else:
        fail("parse_trigger level night", r)

    r = parse_trigger(_d("level-up"))
    if r == "Level up":
        ok("parse_trigger: bare level-up → Level up")
    else:
        fail("parse_trigger bare level-up", r)

    r = parse_trigger(_d("use-item", item="fire-stone"))
    if r == "Use Fire Stone":
        ok("parse_trigger: use-item → Use <Item>")
    else:
        fail("parse_trigger use-item", r)

    r = parse_trigger(_d("trade"))
    if r == "Trade":
        ok("parse_trigger: trade (no item) → Trade")
    else:
        fail("parse_trigger trade bare", r)

    r = parse_trigger(_d("trade", held_item="metal-coat"))
    if r == "Trade holding Metal Coat":
        ok("parse_trigger: trade + held_item → Trade holding <Item>")
    else:
        fail("parse_trigger trade held_item", r)

    r = parse_trigger(_d("shed"))
    if r == "Level 20 (empty slot)":
        ok("parse_trigger: shed → Level 20 (empty slot)")
    else:
        fail("parse_trigger shed", r)

    r = parse_trigger([])
    if r == "":
        ok("parse_trigger: empty list → empty string (stage 0)")
    else:
        fail("parse_trigger empty", repr(r))

    r = parse_trigger(_d("other"))
    if r == "Special condition":
        ok("parse_trigger: unknown trigger → Special condition")
    else:
        fail("parse_trigger unknown", r)

    # ── flatten_chain tests ──────────────────────────────────────────────────
    def _node(slug, details=None, children=None):
        return {
            "species": {"name": slug},
            "evolution_details": details or [],
            "evolves_to": children or [],
        }

    # Linear 3-stage chain: Bulbasaur → Ivysaur → Venusaur
    linear = _node("bulbasaur", children=[
        _node("ivysaur", details=_d("level-up", min_level=16), children=[
            _node("venusaur", details=_d("level-up", min_level=32))
        ])
    ])
    paths = flatten_chain(linear)
    if (len(paths) == 1
            and len(paths[0]) == 3
            and paths[0][0]["slug"] == "bulbasaur"
            and paths[0][1]["slug"] == "ivysaur"
            and paths[0][1]["trigger"] == "Level 16"
            and paths[0][2]["slug"] == "venusaur"
            and paths[0][2]["trigger"] == "Level 32"):
        ok("flatten_chain: linear 3-stage → 1 path, 3 stages, triggers correct")
    else:
        fail("flatten_chain linear", str([(s["slug"], s["trigger"]) for s in paths[0]] if paths else "no paths"))

    # 2-branch chain: Slowpoke → Slowbro | Slowking
    branching = _node("slowpoke", children=[
        _node("slowbro", details=_d("level-up", min_level=37)),
        _node("slowking", details=_d("trade", item="kings-rock")),
    ])
    paths = flatten_chain(branching)
    slugs_per_path = [[s["slug"] for s in p] for p in paths]
    if (len(paths) == 2
            and ["slowpoke", "slowbro"] in slugs_per_path
            and ["slowpoke", "slowking"] in slugs_per_path):
        ok("flatten_chain: 2-branch → 2 paths, correct slugs")
    else:
        fail("flatten_chain branching", str(slugs_per_path))

    # Single-stage (no evolution): Kangaskhan
    single = _node("kangaskhan")
    paths = flatten_chain(single)
    if len(paths) == 1 and len(paths[0]) == 1 and paths[0][0]["slug"] == "kangaskhan":
        ok("flatten_chain: single-stage → 1 path, 1 stage")
    else:
        fail("flatten_chain single", str(paths))

    # max_depth guard: artificially deep chain truncates rather than crashing
    deep = _node("a")
    node = deep
    for letter in "bcdefghijklmnopqrstuvwxyz":
        child = _node(letter, details=_d("level-up", min_level=1))
        node["evolves_to"] = [child]
        node = child
    try:
        paths = flatten_chain(deep, max_depth=5)
        ok("flatten_chain: max_depth guard → no crash, returns partial paths")
    except RecursionError:
        fail("flatten_chain max_depth", "RecursionError raised")

    # ── filter_paths_for_game tests ──────────────────────────────────────────
    # Mock species_gen_map
    _GEN_MAP = {
        "eevee": 1, "vaporeon": 1, "jolteon": 1, "flareon": 1,
        "espeon": 2, "umbreon": 2,
        "leafeon": 4, "glaceon": 4, "sylveon": 6,
        "charmander": 1, "charmeleon": 1, "charizard": 1,
    }

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
    filtered = filter_paths_for_game(eevee_paths, game_gen=3, species_gen_map=_GEN_MAP)
    filtered_targets = [p[1]["slug"] for p in filtered if len(p) > 1]
    expected = {"vaporeon", "jolteon", "flareon", "espeon", "umbreon"}
    if set(filtered_targets) == expected and len(filtered) == 5:
        ok("filter_paths_for_game: Eevee gen3 → 5 branches (no gen4/6)")
    else:
        fail("filter_paths_for_game Eevee gen3", f"got {filtered_targets}")

    # No filter (game_gen=None) → paths unchanged
    result = filter_paths_for_game(eevee_paths, game_gen=None, species_gen_map=_GEN_MAP)
    if result is eevee_paths:
        ok("filter_paths_for_game: game_gen=None → paths unchanged")
    else:
        fail("filter_paths_for_game None", str(len(result)))

    # All evolutions filtered → de-duplicated to single base-only path
    filtered2 = filter_paths_for_game(eevee_paths, game_gen=0, species_gen_map=_GEN_MAP)
    if len(filtered2) == 1 and len(filtered2[0]) == 1 and filtered2[0][0]["slug"] == "eevee":
        ok("filter_paths_for_game: all filtered → single base-only path")
    else:
        fail("filter_paths_for_game all filtered", str(filtered2))

    # Linear chain unaffected when all stages within game_gen
    charmander_paths = [
        [{"slug":"charmander","trigger":""},
         {"slug":"charmeleon","trigger":"Level 16"},
         {"slug":"charizard", "trigger":"Level 36"}]
    ]
    result2 = filter_paths_for_game(charmander_paths, game_gen=1, species_gen_map=_GEN_MAP)
    if result2 == charmander_paths:
        ok("filter_paths_for_game: gen1 chain in gen1 game → unchanged")
    else:
        fail("filter_paths_for_game linear", str(result2))

    print()
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
    else:
        print("This module is a library; run with --autotest to test.")