#!/usr/bin/env python3
"""
feat_team_offense.py  Team offensive coverage analysis

For each attacking type in the era, shows how many team members can hit that
type super-effectively (x2 or x4) using their own types.

Each member is shown with the best scored move for each hitting type:
  Char:Fire Blast, Wing Attack   (both Fire and Flying hit SE, one move each)
  Geng:Sludge Bomb               (only Poison hits SE)
When no move data is available the type-letter fallback is used: Char(F,F).

Entry points:
  run(team_ctx, game_ctx)   called from pokemain (key O)
  main()                    standalone
"""

import sys

try:
    import matchup_calculator as calc
    from feat_team_loader import team_slots, team_size
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Core logic ────────────────────────────────────────────────────────────────

def _hitting_types(era_key: str, type1: str, type2: str, target: str) -> list:
    """
    Return list of first-letters of the member's types that hit target SE (x2+).
    e.g. Charizard (Fire/Flying) vs Grass -> ['F', 'F']  (Fire=x2, Flying=x2)
         Gengar    (Ghost/Poison) vs Fairy -> ['P']       (Poison=x2, Ghost=x0)
    """
    letters = []
    if calc.get_multiplier(era_key, type1, target) >= 2.0:
        letters.append(type1[0])
    if type2 != "None" and calc.get_multiplier(era_key, type2, target) >= 2.0:
        letters.append(type2[0])
    return letters


def build_team_offense(team_ctx: list, era_key: str) -> dict:
    """
    For each defending type in the era, collect which team members can hit it SE
    and which of their own types are responsible.

    Returns:
      {
        def_type: [
          {
            "form_name":       str,
            "hitting_letters": [str, ...],   # first letters (fallback display)
            "hitting_types":   [str, ...],   # full type names (move lookup)
          },
          ...  one entry per member that hits SE (only hitters, not all members)
        ]
      }
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    result = {t: [] for t in valid_types}

    for _idx, pkm in team_slots(team_ctx):
        t1, t2 = pkm["type1"], pkm["type2"]
        for target in valid_types:
            letters = _hitting_types(era_key, t1, t2, target)
            if letters:
                full_types = [
                    t for t in [t1, t2]
                    if t != "None" and calc.get_multiplier(era_key, t, target) >= 2.0
                ]
                result[target].append({
                    "form_name":      pkm["form_name"],
                    "hitting_letters": letters,
                    "hitting_types":  full_types,
                })

    return result


def build_offense_rows(team_offense: dict, era_key: str) -> list:
    """
    Build one row per defending type, sorted: most covered first, gaps last.
    Rows with equal SE count are sorted alphabetically by type name.

    Each row:
      {
        "type":     str,
        "hitters":  [{"form_name": str, "hitting_letters": [...],
                      "hitting_types": [...], "best_moves": list|None}, ...]
      }
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    rows = []
    for t in valid_types:
        hitters = team_offense.get(t, [])
        rows.append({"type": t, "hitters": hitters})

    rows.sort(key=lambda r: (-len(r["hitters"]), r["type"]))
    return rows


def coverage_gaps(rows: list) -> list:
    """Return list of type names where no member can hit SE (hitters is empty)."""
    return [r["type"] for r in rows if not r["hitters"]]


# ── Move lookup helpers ───────────────────────────────────────────────────────

def _best_move_for_type(damage_pool: list, target_type: str):
    """
    Scan the scored damage_pool (sorted desc by score) for the highest-scored
    move whose type matches target_type.

    Pure logic — pool must be pre-built by the caller.
    Returns (move_name, score) or None if no move of that type is found.
    """
    for row in damage_pool:
        if row["type"] == target_type:
            return (row["name"], row["score"])
    return None


def _build_member_pools(team_ctx: list, game_ctx: dict,
                        hitter_names: set,
                        pool_cache: dict | None = None) -> dict:
    """
    For each team member whose form_name is in hitter_names, build the scored
    damage pool via feat_moveset_data.build_candidate_pool().

    pool_cache — optional session-level dict keyed by (variety_slug, game_slug).
                 When provided, pools already in the cache are reused without
                 re-scoring.  New pools are stored back into the dict.
                 Pass None (default) for the original single-call behaviour.

    May trigger learnset and move-detail fetches from PokeAPI (shows progress).
    Returns {form_name: damage_pool_list}.
    """
    import feat_moveset_data as msd

    game_slug = game_ctx.get("game_slug", game_ctx["game"])
    pools = {}
    for _idx, pkm in team_slots(team_ctx):
        if pkm["form_name"] not in hitter_names:
            continue
        cache_key = (pkm["variety_slug"], game_slug)
        if pool_cache is not None and cache_key in pool_cache:
            pools[pkm["form_name"]] = pool_cache[cache_key]
        else:
            pool = msd.build_candidate_pool(pkm, game_ctx)
            damage = pool["damage"]
            if pool_cache is not None:
                pool_cache[cache_key] = damage
            pools[pkm["form_name"]] = damage
    return pools


def _enrich_rows_with_moves(rows: list, member_pools: dict) -> None:
    """
    For each hitter entry in each row, attach 'best_moves': a list of the
    best scored move name per hitting type (aligned with hitting_types order).
    Elements are move name strings or None when no move of that type is found.

    Modifies rows in place.
    """
    for r in rows:
        for h in r["hitters"]:
            fname    = h["form_name"]
            dmg_pool = member_pools.get(fname, [])
            best_moves = []
            for htype in h.get("hitting_types", []):
                entry = _best_move_for_type(dmg_pool, htype)
                best_moves.append(entry[0] if entry else None)
            h["best_moves"] = best_moves


# ── Display helpers ───────────────────────────────────────────────────────────

_COL_TYPE    = 10
_COL_HITTERS = 70   # wide enough for ~3 hitters with move names
_NAME_LEN    = 4    # same as feat_team_analysis._abbrev
_MOVE_NAME_LEN = 12  # max characters of move name shown in hitter cell


def _abbrev(name: str) -> str:
    return name[:_NAME_LEN]


def _hitter_tag(form_name: str, hitting_types: list,
                best_moves: list = None) -> str:
    """
    Format a hitter entry.

    With move data available:
      Abbrev:Move1[, Move2]
      e.g.  Char:Flamethrower, Fly   (Fire → Flamethrower, Flying → Fly)
            Geng:Sludge Bomb         (Poison only)
      If a move is missing for one type, the type's first letter is used instead:
      e.g.  Char:Flamethrower, F     (no Flying-type move found)

    Fallback (no move data):
      Abbrev(L,L)
      e.g.  Char(F,F)   Geng(P)
    """
    short = _abbrev(form_name)

    has_moves = best_moves and any(m is not None for m in best_moves)
    if not has_moves:
        letters = [t[0] for t in hitting_types]
        return f"{short}({','.join(letters)})"

    parts = []
    for i, htype in enumerate(hitting_types):
        move = best_moves[i] if i < len(best_moves) else None
        parts.append(move[:_MOVE_NAME_LEN] if move else htype[0])
    return f"{short}:{', '.join(parts)}"


def _hitters_cell(hitters: list) -> str:
    """Space-separated list of tagged hitter names, or '-' if empty."""
    if not hitters:
        return "-"
    return "  ".join(
        _hitter_tag(h["form_name"], h["hitting_types"], h.get("best_moves"))
        for h in hitters
    )


def _print_offense_table(rows: list) -> None:
    hdr = (f"  {'Type':<{_COL_TYPE}}"
           f" | {'Who hits SE  (:moves per hitting type, letter=fallback)':<{_COL_HITTERS}}"
           f" | Comments")
    sep = (f"  {'-'*_COL_TYPE}"
           f"-+-{'-'*_COL_HITTERS}"
           f"-+-{'-'*10}")
    print()
    print(hdr)
    print(sep)
    for r in rows:
        cell    = _hitters_cell(r["hitters"])
        comment = "GAP" if not r["hitters"] else ""
        print(f"  {r['type']:<{_COL_TYPE}}"
              f" | {cell:<{_COL_HITTERS}}"
              f" | {comment}")


def display_team_offense(team_ctx: list, game_ctx: dict,
                         pool_cache: dict | None = None) -> None:
    era_key = game_ctx["era_key"]
    game    = game_ctx["game"]
    filled  = team_size(team_ctx)

    if filled == 0:
        print("\n  Team is empty -- load some Pokemon first (press T).")
        return

    # ── Roster header ─────────────────────────────────────────────────────────
    print(f"\n  Team offensive coverage  |  {game}")
    print("  " + "=" * 56)
    for _idx, pkm in team_slots(team_ctx):
        dual = (f"{pkm['type1']} / {pkm['type2']}"
                if pkm["type2"] != "None" else pkm["type1"])
        print(f"  {pkm['form_name']:<24}  {dual}")
    print("  " + "=" * 56)

    # ── Build type-based offense table ────────────────────────────────────────
    team_off = build_team_offense(team_ctx, era_key)
    rows     = build_offense_rows(team_off, era_key)

    # ── Enrich hitters with best scored move per hitting type ──────────────────
    hitter_names = {
        h["form_name"]
        for hlist in team_off.values()
        for h in hlist
    }
    if hitter_names:
        # Show loading message only when at least one pool will be computed
        game_slug = game_ctx.get("game_slug", game_ctx["game"])
        slug_by_name = {pkm["form_name"]: pkm["variety_slug"]
                        for _, pkm in team_slots(team_ctx)}
        needs_fetch = pool_cache is None or any(
            (slug_by_name.get(h), game_slug) not in pool_cache
            for h in hitter_names
        )
        if needs_fetch:
            print(f"\n  Loading move data for {len(hitter_names)} member(s)...")
        member_pools = _build_member_pools(team_ctx, game_ctx, hitter_names,
                                           pool_cache=pool_cache)
        _enrich_rows_with_moves(rows, member_pools)

    # ── Table ─────────────────────────────────────────────────────────────────
    gaps = coverage_gaps(rows)

    print("\n  Abbrev:Move1[, Move2] = best scored move per hitting type"
          "  |  letter = type fallback")
    _print_offense_table(rows)

    # ── Summary ───────────────────────────────────────────────────────────────
    _, valid_types, _ = calc.CHARTS[era_key]
    total    = len(valid_types)
    covered  = total - len(gaps)
    print(f"\n  Coverage: {covered} / {total} types", end="")
    if gaps:
        print(f"  |  Gaps: {' / '.join(gaps)}")
    else:
        print("  |  Full coverage!")


# ── Entry points ──────────────────────────────────────────────────────────────

def run(team_ctx: list, game_ctx: dict,
        pool_cache: dict | None = None) -> None:
    """Called from pokemain."""
    display_team_offense(team_ctx, game_ctx, pool_cache=pool_cache)
    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("+===========================================+")
    print("|     Team Offensive Coverage               |")
    print("+===========================================+")

    try:
        from pkm_session import select_game, select_pokemon
        from feat_team_loader import new_team, add_to_team, TeamFullError
    except ModuleNotFoundError as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)

    game_ctx = select_game()
    if game_ctx is None:
        sys.exit(0)

    team_ctx = new_team()
    print("\n  Add up to 6 Pokemon (blank name to stop).")
    for _ in range(6):
        pkm = select_pokemon(game_ctx=game_ctx)
        if pkm is None:
            break
        try:
            team_ctx, slot = add_to_team(team_ctx, pkm)
            print(f"  Added to slot {slot + 1}.")
        except TeamFullError:
            break

    display_team_offense(team_ctx, game_ctx)
    input("\n  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_offense.py -- self-test\n")

    # ── Fixtures ──────────────────────────────────────────────────────────────
    def _pkm(name, t1, t2="None"):
        return {"form_name": name, "type1": t1, "type2": t2}

    charizard = _pkm("Charizard", "Fire",    "Flying")
    blastoise = _pkm("Blastoise", "Water")
    venusaur  = _pkm("Venusaur",  "Grass",   "Poison")
    gengar    = _pkm("Gengar",    "Ghost",   "Poison")
    pikachu   = _pkm("Pikachu",   "Electric")
    snorlax   = _pkm("Snorlax",   "Normal")

    team1      = [charizard, None, None, None, None, None]
    team6      = [charizard, blastoise, venusaur, gengar, pikachu, snorlax]
    team_empty = [None] * 6

    # ── _hitting_types ────────────────────────────────────────────────────────

    h = _hitting_types("era3", "Fire", "Flying", "Grass")
    if h == ["F", "F"]:
        ok("_hitting_types: Charizard vs Grass -> [F, F]")
    else:
        fail("_hitting_types Charizard/Grass", str(h))

    h = _hitting_types("era3", "Fire", "Flying", "Fighting")
    if h == ["F"]:
        ok("_hitting_types: Charizard vs Fighting -> [F] (Flying only)")
    else:
        fail("_hitting_types Charizard/Fighting", str(h))

    h = _hitting_types("era3", "Ghost", "Poison", "Fairy")
    if h == ["P"]:
        ok("_hitting_types: Gengar vs Fairy -> [P] (Poison only)")
    else:
        fail("_hitting_types Gengar/Fairy", str(h))

    h = _hitting_types("era3", "Ghost", "Poison", "Normal")
    if h == []:
        ok("_hitting_types: Gengar vs Normal -> [] (Ghost x0, Poison x1)")
    else:
        fail("_hitting_types Gengar/Normal", str(h))

    h = _hitting_types("era3", "Water", "None", "Fire")
    if h == ["W"]:
        ok("_hitting_types: Blastoise vs Fire -> [W]")
    else:
        fail("_hitting_types Blastoise/Fire", str(h))

    h = _hitting_types("era3", "Water", "None", "Grass")
    if h == []:
        ok("_hitting_types: Blastoise vs Grass -> [] (not SE)")
    else:
        fail("_hitting_types Blastoise/Grass", str(h))

    _, valid_era1, _ = calc.CHARTS["era1"]
    if "Fairy" not in valid_era1:
        ok("_hitting_types: era1 has no Fairy type")
    else:
        fail("_hitting_types era1 Fairy", "Fairy found in era1")

    # ── build_team_offense ────────────────────────────────────────────────────

    to1 = build_team_offense(team1, "era3")

    _, valid_era3, _ = calc.CHARTS["era3"]
    if set(to1.keys()) == set(valid_era3):
        ok("build_team_offense: keys match era3 type set")
    else:
        fail("build_team_offense keys", str(set(to1.keys()) ^ set(valid_era3)))

    grass_hitters = to1["Grass"]
    if len(grass_hitters) == 1 and grass_hitters[0]["form_name"] == "Charizard":
        if grass_hitters[0]["hitting_letters"] == ["F", "F"]:
            ok("build_team_offense: Charizard hits Grass SE with letters F,F")
        else:
            fail("build_team_offense Grass letters", str(grass_hitters[0]["hitting_letters"]))
    else:
        fail("build_team_offense Grass hitters", str(grass_hitters))

    if to1["Water"] == []:
        ok("build_team_offense: Charizard does not hit Water SE")
    else:
        fail("build_team_offense Water", str(to1["Water"]))

    if to1["Ground"] == []:
        ok("build_team_offense: Charizard does not hit Ground SE")
    else:
        fail("build_team_offense Ground", str(to1["Ground"]))

    to_e = build_team_offense(team_empty, "era3")
    if all(v == [] for v in to_e.values()):
        ok("build_team_offense: empty team -> all lists empty")
    else:
        fail("build_team_offense empty")

    _, valid_era2, _ = calc.CHARTS["era2"]
    if set(build_team_offense(team1, "era2").keys()) == set(valid_era2):
        ok("build_team_offense: era2 keys match era2 type set")
    else:
        fail("build_team_offense era2 keys")

    to6 = build_team_offense(team6, "era3")
    grass_names = [h["form_name"] for h in to6["Grass"]]
    if set(grass_names) == {"Charizard", "Venusaur", "Gengar"}:
        ok("build_team_offense: Grass hitters = Charizard + Venusaur + Gengar")
    else:
        fail("build_team_offense Grass 6-team", str(grass_names))

    if to6["Normal"] == []:
        ok("build_team_offense: Normal has no SE hitters (expected gap)")
    else:
        fail("build_team_offense Normal gap", str([h["form_name"] for h in to6["Normal"]]))

    # ── build_team_offense — hitting_types field ──────────────────────────────

    char_grass = to1["Grass"][0]
    if set(char_grass.get("hitting_types", [])) == {"Fire", "Flying"}:
        ok("build_team_offense: Charizard vs Grass hitting_types = [Fire, Flying]")
    else:
        fail("build_team_offense hitting_types Charizard/Grass",
             str(char_grass.get("hitting_types")))

    to_blast = build_team_offense([blastoise, None, None, None, None, None], "era3")
    blast_fire = to_blast.get("Fire", [])
    if blast_fire and blast_fire[0].get("hitting_types") == ["Water"]:
        ok("build_team_offense: Blastoise vs Fire hitting_types = [Water]")
    else:
        fail("build_team_offense hitting_types Blastoise/Fire",
             str(blast_fire[0].get("hitting_types") if blast_fire else "no entry"))

    for target, hitters in to6.items():
        for h in hitters:
            if len(h.get("hitting_types", [])) != len(h.get("hitting_letters", [])):
                fail(f"hitting_types/letters length mismatch on {h['form_name']} vs {target}")
                break
        else:
            continue
        break
    else:
        ok("build_team_offense: hitting_types length matches hitting_letters for all entries")

    # ── build_offense_rows ────────────────────────────────────────────────────

    rows1 = build_offense_rows(to1, "era3")

    if set(r["type"] for r in rows1) == set(valid_era3):
        ok("build_offense_rows: all era3 types present")
    else:
        fail("build_offense_rows types", str(set(valid_era3) - set(r["type"] for r in rows1)))

    if rows1[0]["hitters"]:
        ok("build_offense_rows: first row has hitters (most covered first)")
    else:
        fail("build_offense_rows sort: first row is empty")

    first_gap_idx = next((i for i, r in enumerate(rows1) if not r["hitters"]), None)
    last_hit_idx  = max((i for i, r in enumerate(rows1) if r["hitters"]), default=-1)
    if first_gap_idx is None or first_gap_idx > last_hit_idx:
        ok("build_offense_rows: all gap rows sort after all hitter rows")
    else:
        fail("build_offense_rows gap sort", f"gap at {first_gap_idx}, last hitter at {last_hit_idx}")

    # ── coverage_gaps ─────────────────────────────────────────────────────────

    rows6 = build_offense_rows(to6, "era3")
    gaps6 = coverage_gaps(rows6)

    if "Normal" in gaps6:
        ok("coverage_gaps: Normal is a gap for 6-team")
    else:
        fail("coverage_gaps Normal", str(gaps6))

    if "Grass" not in gaps6:
        ok("coverage_gaps: Grass is not a gap (3 hitters)")
    else:
        fail("coverage_gaps Grass false positive")

    rows_e = build_offense_rows(to_e, "era3")
    if set(coverage_gaps(rows_e)) == set(valid_era3):
        ok("coverage_gaps: empty team -> all types are gaps")
    else:
        fail("coverage_gaps empty")

    # ── _best_move_for_type ───────────────────────────────────────────────────

    fake_pool = [
        {"name": "Flamethrower", "type": "Fire",  "score": 135.0},
        {"name": "Surf",         "type": "Water", "score": 100.0},
        {"name": "Ember",        "type": "Fire",  "score": 60.0},
    ]

    if _best_move_for_type(fake_pool, "Fire") == ("Flamethrower", 135.0):
        ok("_best_move_for_type: returns first (highest scored) move of type")
    else:
        fail("_best_move_for_type first match", str(_best_move_for_type(fake_pool, "Fire")))

    if _best_move_for_type(fake_pool, "Grass") is None:
        ok("_best_move_for_type: no match -> None")
    else:
        fail("_best_move_for_type no match")

    if _best_move_for_type([], "Fire") is None:
        ok("_best_move_for_type: empty pool -> None")
    else:
        fail("_best_move_for_type empty pool")

    if _best_move_for_type(fake_pool, "Water") == ("Surf", 100.0):
        ok("_best_move_for_type: Water -> Surf (ignores Fire entries)")
    else:
        fail("_best_move_for_type Water", str(_best_move_for_type(fake_pool, "Water")))

    # ── _hitter_tag ───────────────────────────────────────────────────────────

    # Fallback format when no moves available
    tag = _hitter_tag("Charizard", ["Fire", "Flying"])
    if tag == "Char(F,F)":
        ok("_hitter_tag: no moves, dual types -> fallback Char(F,F)")
    else:
        fail("_hitter_tag no-move dual", repr(tag))

    tag = _hitter_tag("Gengar", ["Poison"])
    if tag == "Geng(P)":
        ok("_hitter_tag: no moves, single type -> fallback Geng(P)")
    else:
        fail("_hitter_tag no-move single", repr(tag))

    tag = _hitter_tag("Mew", ["Poison"])
    if tag == "Mew(P)":
        ok("_hitter_tag: short name -> fallback Mew(P)")
    else:
        fail("_hitter_tag short name", repr(tag))

    # Enriched format with moves
    tag = _hitter_tag("Charizard", ["Fire", "Flying"], ["Flamethrower", "Wing Attack"])
    if tag == "Char:Flamethrower, Wing Attack":
        ok("_hitter_tag: dual types, both moves -> Char:Flamethrower, Wing Attack")
    else:
        fail("_hitter_tag dual with moves", repr(tag))

    tag = _hitter_tag("Blastoise", ["Water"], ["Surf"])
    if tag == "Blas:Surf":
        ok("_hitter_tag: single type with move -> Blas:Surf")
    else:
        fail("_hitter_tag single with move", repr(tag))

    tag = _hitter_tag("Charizard", ["Fire", "Flying"], ["Flamethrower", None])
    if tag == "Char:Flamethrower, F":
        ok("_hitter_tag: dual types, one move missing -> type letter fallback")
    else:
        fail("_hitter_tag partial moves", repr(tag))

    long_name = "AVeryLongMoveName"
    tag = _hitter_tag("Charizard", ["Fire"], [long_name])
    if tag == f"Char:{long_name[:_MOVE_NAME_LEN]}":
        ok(f"_hitter_tag: move name truncated to {_MOVE_NAME_LEN} chars")
    else:
        fail("_hitter_tag truncation", repr(tag))

    # ── _enrich_rows_with_moves ───────────────────────────────────────────────

    # Single hitting type: best_moves = [move_name]
    rows_test = [{"type": "Fire", "hitters": [
        {"form_name": "Blastoise", "hitting_types": ["Water"], "hitting_letters": ["W"]}
    ]}]
    pools_test = {"Blastoise": [{"name": "Surf", "type": "Water", "score": 100.0}]}
    _enrich_rows_with_moves(rows_test, pools_test)
    bm = rows_test[0]["hitters"][0].get("best_moves")
    if bm == ["Surf"]:
        ok("_enrich_rows_with_moves: single type -> best_moves = ['Surf']")
    else:
        fail("_enrich_rows_with_moves single", str(bm))

    # Dual hitting types: best_moves = [move_fire, move_flying]
    rows_test2 = [{"type": "Grass", "hitters": [
        {"form_name": "Charizard", "hitting_types": ["Fire", "Flying"],
         "hitting_letters": ["F", "F"]}
    ]}]
    pools_test2 = {"Charizard": [
        {"name": "Flamethrower", "type": "Fire",   "score": 135.0},
        {"name": "Wing Attack",  "type": "Flying", "score": 90.0},
    ]}
    _enrich_rows_with_moves(rows_test2, pools_test2)
    bm2 = rows_test2[0]["hitters"][0].get("best_moves")
    if bm2 == ["Flamethrower", "Wing Attack"]:
        ok("_enrich_rows_with_moves: dual types -> best_moves = [fire_move, fly_move]")
    else:
        fail("_enrich_rows_with_moves dual", str(bm2))

    # No pool entry: best_moves all None
    rows_test3 = [{"type": "Grass", "hitters": [
        {"form_name": "Charizard", "hitting_types": ["Fire", "Flying"],
         "hitting_letters": ["F", "F"]}
    ]}]
    _enrich_rows_with_moves(rows_test3, {})
    bm3 = rows_test3[0]["hitters"][0].get("best_moves")
    if bm3 == [None, None]:
        ok("_enrich_rows_with_moves: no pool -> best_moves = [None, None]")
    else:
        fail("_enrich_rows_with_moves no pool", str(bm3))

    # ── _hitters_cell ─────────────────────────────────────────────────────────

    if _hitters_cell([]) == "-":
        ok("_hitters_cell: empty list -> dash")
    else:
        fail("_hitters_cell empty")

    hitters_no_move = [
        {"form_name": "Charizard", "hitting_types": ["Fire", "Flying"],
         "hitting_letters": ["F", "F"]},
        {"form_name": "Venusaur",  "hitting_types": ["Poison"],
         "hitting_letters": ["P"]},
    ]
    cell = _hitters_cell(hitters_no_move)
    if "Char(F,F)" in cell and "Venu(P)" in cell:
        ok("_hitters_cell: no moves -> fallback tags in cell")
    else:
        fail("_hitters_cell no-move tags", repr(cell))

    hitters_with_moves = [
        {"form_name": "Charizard", "hitting_types": ["Fire", "Flying"],
         "hitting_letters": ["F", "F"],
         "best_moves": ["Flamethrower", "Wing Attack"]},
        {"form_name": "Gengar",    "hitting_types": ["Poison"],
         "hitting_letters": ["P"],
         "best_moves": ["Sludge Bomb"]},
    ]
    cell = _hitters_cell(hitters_with_moves)
    if "Flamethrower" in cell and "Wing Attack" in cell and "Sludge Bomb" in cell:
        ok("_hitters_cell: with best_moves -> all move names present")
    else:
        fail("_hitters_cell with moves", repr(cell))

    # ── _print_offense_table ──────────────────────────────────────────────────

    import io, contextlib

    rows_print = build_offense_rows(to6, "era3")
    for r in rows_print:
        for h in r["hitters"]:
            h["best_moves"] = ["Thunderbolt"] * len(h["hitting_types"])

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_offense_table(rows_print)
    out = buf.getvalue()

    missing = [t for t in valid_era3 if t not in out]
    if not missing:
        ok("_print_offense_table: all era3 types present in output")
    else:
        fail("_print_offense_table missing types", str(missing))

    normal_line = next((l for l in out.splitlines() if l.strip().startswith("Normal")), None)
    if normal_line and "GAP" in normal_line:
        ok("_print_offense_table: Normal row shows GAP")
    else:
        fail("_print_offense_table Normal GAP", repr(normal_line))

    grass_line = next((l for l in out.splitlines() if l.strip().startswith("Grass")), None)
    if grass_line and "Char" in grass_line:
        ok("_print_offense_table: Grass row contains hitter names")
    else:
        fail("_print_offense_table Grass hitters", repr(grass_line))

    if "Thunderbolt" in out:
        ok("_print_offense_table: move names appear in output when enriched")
    else:
        fail("_print_offense_table move names")

    # ── _build_member_pools: pool_cache ───────────────────────────────────────

    import sys as _sys

    _call_count = [0]
    _orig_msd_bcp = None

    class _MockMSD:
        def build_candidate_pool(self, pkm_ctx, game_ctx):
            _call_count[0] += 1
            return {"damage": [{"name": "Tackle", "type": "Normal", "score": 10}],
                    "status": [], "skipped": 0}

    _real_msd = _sys.modules.get("feat_moveset_data")
    _sys.modules["feat_moveset_data"] = _MockMSD()

    game_ctx_fake = {"game": "TestGame", "era_key": "era3",
                     "game_gen": 9, "game_slug": "test-game"}
    hitters_all   = {"Charizard", "Blastoise"}
    team_two = [
        {"form_name": "Charizard", "type1": "Fire",  "type2": "Flying",
         "variety_slug": "charizard"},
        {"form_name": "Blastoise", "type1": "Water", "type2": "None",
         "variety_slug": "blastoise"},
        None, None, None, None,
    ]

    # pool_cache=None → normal behaviour, build_candidate_pool called per member
    _call_count[0] = 0
    _build_member_pools(team_two, game_ctx_fake, hitters_all, pool_cache=None)
    if _call_count[0] == 2:
        ok("_build_member_pools: pool_cache=None → build_candidate_pool called for each member")
    else:
        fail("_build_member_pools pool_cache=None call count", str(_call_count[0]))

    # pool_cache provided, empty → pools computed and stored
    _call_count[0] = 0
    cache1 = {}
    _build_member_pools(team_two, game_ctx_fake, hitters_all, pool_cache=cache1)
    if _call_count[0] == 2:
        ok("_build_member_pools: empty pool_cache → both pools computed")
    else:
        fail("_build_member_pools empty cache call count", str(_call_count[0]))

    if ("charizard", "test-game") in cache1 and ("blastoise", "test-game") in cache1:
        ok("_build_member_pools: computed pools stored in pool_cache")
    else:
        fail("_build_member_pools cache keys", str(list(cache1.keys())))

    # pool_cache provided, already populated → no recomputation
    _call_count[0] = 0
    _build_member_pools(team_two, game_ctx_fake, hitters_all, pool_cache=cache1)
    if _call_count[0] == 0:
        ok("_build_member_pools: populated pool_cache → build_candidate_pool NOT called")
    else:
        fail("_build_member_pools: should reuse cache, got calls", str(_call_count[0]))

    # Partial cache: one member cached, one not
    _call_count[0] = 0
    partial_cache = {("charizard", "test-game"): []}   # Charizard cached, Blastoise not
    _build_member_pools(team_two, game_ctx_fake, hitters_all, pool_cache=partial_cache)
    if _call_count[0] == 1:
        ok("_build_member_pools: partial cache → only missing member recomputed")
    else:
        fail("_build_member_pools partial cache call count", str(_call_count[0]))

    if _real_msd is not None:
        _sys.modules["feat_moveset_data"] = _real_msd
    else:
        del _sys.modules["feat_moveset_data"]

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 50
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