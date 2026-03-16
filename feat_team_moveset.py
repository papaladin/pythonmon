#!/usr/bin/env python3
"""
feat_team_moveset.py  Team moveset synergy

Orchestrates team-level moveset recommendations by running the single-Pokemon
scoring engine across all team members and aggregating results into a team
offensive coverage summary.

Accessible via menu key S (needs team + game).

Public API:
  recommend_team_movesets(team_ctx, game_ctx, mode) -> list[dict]
  run(team_ctx, game_ctx)   called from pokemain (key S)
  main()                    standalone

Member result structure (one dict per filled team slot):
  {
    "form_name":      str,
    "types":          list[str],   # e.g. ["Fire", "Flying"]
    "moves":          list[dict],  # recommended moves (full engine dicts)
    "weakness_types": list[str],
    "se_types":       list[str],
  }
"""

import sys

try:
    from feat_team_loader import team_slots, team_size
    from feat_moveset_data import build_candidate_pool, select_combo
    import matchup_calculator as calc
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Constants ──────────────────────────────────────────────────────────────

_MODES = {
    "c": "coverage",
    "u": "counter",
    "s": "stab",
}

_COL_MOVE   = 22   # left move-name column width (matches feat_moveset.py)
_BLOCK_SEP  = 56   # width of ═ / ─ separators


# ── Member result structure ────────────────────────────────────────────────

def _empty_member_result(form_name: str) -> dict:
    """Return a correctly-shaped member result with empty move/type lists."""
    return {
        "form_name":      form_name,
        "types":          [],
        "moves":          [],
        "weakness_types": [],
        "se_types":       [],
    }


# ── Pure logic helpers ─────────────────────────────────────────────────────

def _weakness_types(pkm_ctx: dict, era_key: str) -> list:
    """Return types that hit this Pokemon SE (multiplier > 1.0)."""
    defense = calc.compute_defense(era_key, pkm_ctx["type1"], pkm_ctx["type2"])
    return [t for t, m in defense.items() if m > 1.0]


def _se_types(combo: list, era_key: str) -> list:
    """
    Return types hit SE (>= 2x) by at least one move in the combo,
    over all valid single-type defenders for the era.
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    move_types = [mv["type"] for mv in combo if mv.get("type")]
    if not move_types:
        return []
    se = []
    for def_type in valid_types:
        best = max(calc.get_multiplier(era_key, mt, def_type) for mt in move_types)
        if best >= 2.0:
            se.append(def_type)
    return se


# ── Core logic ─────────────────────────────────────────────────────────────

def recommend_team_movesets(team_ctx: list, game_ctx: dict, mode: str) -> list:
    """
    Compute a recommended moveset for each filled team slot.

    Calls build_candidate_pool + select_combo from feat_moveset_data for each
    member — no scoring logic is duplicated here.  If a member's pool is empty
    (cache miss / network unavailable), the result is correctly shaped with
    empty lists rather than crashing.

    mode — "coverage" | "counter" | "stab"

    Returns list[dict], one entry per filled slot:
      { form_name, moves (list[dict]), weakness_types (list[str]),
        se_types (list[str]) }
    """
    era_key = game_ctx["era_key"]
    results = []

    for _idx, pkm in team_slots(team_ctx):
        pool        = build_candidate_pool(pkm, game_ctx)
        damage_pool = pool["damage"]
        weak_types  = _weakness_types(pkm, era_key)
        combo       = select_combo(damage_pool, mode, weak_types, era_key)
        se          = _se_types(combo, era_key)

        results.append({
            "form_name":      pkm["form_name"],
            "types":          pkm.get("types", []),
            "moves":          combo,
            "weakness_types": weak_types,
            "se_types":       se,
        })

    return results


# ── Coverage aggregation ──────────────────────────────────────────────────

def build_offensive_coverage(member_results: list, era_key: str) -> dict:
    """
    Aggregate SE coverage across all member results.

    Does NOT recompute movesets — reads se_types from each result dict as
    produced by recommend_team_movesets().

    Returns:
      {
        "counts":      {type: int},   — how many members cover each type SE
        "covered":     list[str],     — types covered by ≥1 member (count ≥1)
        "gaps":        list[str],     — types covered by 0 members
        "overlap":     [(type, int)], — types covered by ≥3 members, desc count
        "total_types": int,           — total type count for the era
      }
    """
    _, valid_types, _ = calc.CHARTS[era_key]

    counts = {t: 0 for t in valid_types}
    for result in member_results:
        for t in result.get("se_types", []):
            if t in counts:
                counts[t] += 1

    covered = [t for t in valid_types if counts[t] >= 1]
    gaps    = [t for t in valid_types if counts[t] == 0]
    overlap = sorted(
        [(t, counts[t]) for t in valid_types if counts[t] >= 3],
        key=lambda x: (-x[1], x[0]),
    )

    return {
        "counts":      counts,
        "covered":     covered,
        "gaps":        gaps,
        "overlap":     overlap,
        "total_types": len(valid_types),
    }


# ── Pure formatting helpers ────────────────────────────────────────────────

def _format_weak_line(weakness_types: list) -> str:
    """
    Format the weakness summary line for one member block.

    Examples:
      ["Rock", "Water", "Electric"]  →  "Weak:  Rock  Water  Electric"
      []                             →  "Weak:  —"
    """
    if not weakness_types:
        return "Weak:  —"
    return "Weak:  " + "  ".join(weakness_types)


def _format_move_pair(left: str | None, right: str | None) -> str:
    """
    Format two move names side by side.  None renders as "—".
    Left column is _COL_MOVE characters wide.

    Example:
      ("Flamethrower", "Air Slash")  →  "Flamethrower           Air Slash"
      ("Surf", None)                 →  "Surf                   —"
      (None, None)                   →  "—                      —"
    """
    l = left  if left  is not None else "—"
    r = right if right is not None else "—"
    return f"{l:<{_COL_MOVE}}  {r}"


def _format_se_line(se_types: list, era_key: str) -> str:
    """
    Format the SE coverage count line.

    Example (era3, 6 SE types):  "SE: 6 / 18 types"
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    return f"SE: {len(se_types)} / {len(valid_types)} types"


# ── Display functions ──────────────────────────────────────────────────────

def _display_member_block(result: dict, era_key: str) -> None:
    """Print the 5-line compact block for one team member."""
    form_name = result["form_name"]
    types_str = " / ".join(result["types"]) if result["types"] else "?"

    # Pad move list to exactly 4 slots (None = empty)
    names = [m["name"] for m in result["moves"]]
    names += [None] * (4 - len(names))

    print(f"  {form_name}  [{types_str}]")
    print(f"  {_format_weak_line(result['weakness_types'])}")
    print(f"  {_format_move_pair(names[0], names[1])}")
    print(f"  {_format_move_pair(names[2], names[3])}")
    print(f"  {_format_se_line(result['se_types'], era_key)}")


def display_team_movesets(results: list, game_ctx: dict, mode: str) -> None:
    """
    Print the full team moveset synergy screen.

    One compact block per filled slot, framed by ═ separators,
    followed by the team offensive coverage summary.
    """
    era_key = game_ctx["era_key"]
    game    = game_ctx["game"]

    print(f"\n  Team moveset synergy  |  {mode}  |  {game}")
    print("  " + "═" * _BLOCK_SEP)

    for i, result in enumerate(results):
        if i > 0:
            print("  " + "─" * _BLOCK_SEP)
        _display_member_block(result, era_key)

    print("  " + "═" * _BLOCK_SEP)

    coverage = build_offensive_coverage(results, era_key)
    _display_coverage_summary(coverage)
    print("  " + "═" * _BLOCK_SEP)


def _display_coverage_summary(coverage: dict) -> None:
    """
    Print the team offensive coverage summary block.

    Always shown:  Covered line (N / total types hit SE)
    Shown if any:  Gaps line
    Shown if any:  Overlap line (types covered by ≥3 members)
    """
    total   = coverage["total_types"]
    covered = coverage["covered"]
    gaps    = coverage["gaps"]
    overlap = coverage["overlap"]

    print("  ── Team coverage " + "─" * (_BLOCK_SEP - 17))
    print(f"  Covered:  {len(covered)} / {total} types hit SE")

    if gaps:
        print("  Gaps:     " + "  ".join(gaps))
    else:
        print("  Full coverage!")

    if overlap:
        parts = [f"{t} ({n})" for t, n in overlap]
        print("  Overlap:  " + "  ".join(parts))


# ── Interactive helpers ────────────────────────────────────────────────────

def _mode_prompt() -> str:
    """Interactive mode selector. Returns one of the _MODES values."""
    while True:
        print("\n  Select mode:")
        print("    (C)overage")
        print("    co(U)nter")
        print("    (S)TAB")
        choice = input("  Mode: ").strip().lower()
        if choice in _MODES:
            return _MODES[choice]
        print("  Invalid choice — press C, U or S.")


# ── Entry points ───────────────────────────────────────────────────────────

def run(team_ctx: list, game_ctx: dict) -> None:
    """Menu entry point for key S — Team Moveset Synergy."""
    if team_size(team_ctx) == 0:
        print("\n  Team is empty — load some Pokémon first (press T).")
        return

    mode    = _mode_prompt()
    results = recommend_team_movesets(team_ctx, game_ctx, mode)
    display_team_movesets(results, game_ctx, mode)

    print("\n  Press Enter to return to the main menu...")
    input()


def main() -> None:
    print()
    print("  This module is not usable standalone.")
    print("  Launch from pokemain.py instead.")
    print()
    input("  Press Enter to exit...")


# ── Self-tests ─────────────────────────────────────────────────────────────

def _run_tests():

    errors = []

    def ok(label):
        print(f"  [OK]   {label}")

    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_moveset.py — self-test (step 4.4)\n")

    # ── Shared fixtures ───────────────────────────────────────────────────

    def _pkm(name, t1, t2="None"):
        types = [t1] if t2 == "None" else [t1, t2]
        return {
            "form_name":    name,
            "types":        types,
            "type1":        t1,
            "type2":        t2,
            "pokemon":      name.lower(),
            "variety_slug": name.lower(),
            "species_gen":  1,
            "form_gen":     1,
            "base_stats": {
                "hp": 80, "attack": 80, "defense": 80,
                "special-attack": 80, "special-defense": 80, "speed": 80,
            },
        }

    def _mv(name, typ, pwr=80):
        """Minimal damage move dict matching build_candidate_pool output shape."""
        return {
            "name": name, "type": typ, "category": "Special",
            "power": pwr, "accuracy": 100, "pp": 10,
            "score": float(pwr), "is_stab": False,
            "counters_weaknesses": [], "is_two_turn": False,
            "low_accuracy": False, "priority": 0,
            "drain": 0, "effect_chance": 0, "ailment": None,
        }

    game_ctx = {
        "game":      "TestGame",
        "era_key":   "era3",
        "game_gen":  9,
        "game_slug": "test-game",
    }

    charizard = _pkm("Charizard", "Fire", "Flying")
    blastoise = _pkm("Blastoise", "Water")
    gengar    = _pkm("Gengar",    "Ghost", "Poison")

    team_empty = [None] * 6
    team1      = [charizard, None, None, None, None, None]
    team3      = [charizard, blastoise, gengar, None, None, None]
    team6      = [charizard, blastoise, charizard, blastoise, charizard, blastoise]

    # Fake pool: 5 distinct move types — satisfies TASKS note re. ≥4 types
    _fake_pool = [
        _mv("Flamethrower", "Fire",     90),
        _mv("Surf",         "Water",    90),
        _mv("Thunderbolt",  "Electric", 90),
        _mv("Energy Ball",  "Grass",    90),
        _mv("Rock Slide",   "Rock",     75),
    ]

    # ── Monkey-patch build_candidate_pool and select_combo ────────────────
    # calc runs for real — it is a pure type-chart library with no I/O.

    import sys as _sys
    _this = _sys.modules[__name__]

    _orig_build = _this.build_candidate_pool
    _orig_combo = _this.select_combo

    def _mock_pool(pkm_ctx, game_ctx):
        return {"damage": list(_fake_pool), "status": [], "skipped": 0}

    def _mock_pool_empty(pkm_ctx, game_ctx):
        return {"damage": [], "status": [], "skipped": 0}

    def _mock_combo(damage_pool, mode, weak_types, era_key, locked=None):
        return damage_pool[:4]

    # ── ## _MODES ─────────────────────────────────────────────────────────

    if set(_MODES.keys()) == {"c", "u", "s"}:
        ok("_MODES: has exactly keys c, u, s")
    else:
        fail("_MODES keys", str(_MODES.keys()))

    if set(_MODES.values()) == {"coverage", "counter", "stab"}:
        ok("_MODES: values are coverage / counter / stab")
    else:
        fail("_MODES values", str(_MODES.values()))

    # ── ## _empty_member_result ───────────────────────────────────────────

    result = _empty_member_result("Charizard")

    if result["form_name"] == "Charizard":
        ok("_empty_member_result: form_name stored correctly")
    else:
        fail("_empty_member_result: form_name", str(result))

    if isinstance(result["moves"], list) and result["moves"] == []:
        ok("_empty_member_result: moves is empty list")
    else:
        fail("_empty_member_result: moves", str(result["moves"]))

    if isinstance(result["weakness_types"], list) and result["weakness_types"] == []:
        ok("_empty_member_result: weakness_types is empty list")
    else:
        fail("_empty_member_result: weakness_types", str(result["weakness_types"]))

    if isinstance(result["se_types"], list) and result["se_types"] == []:
        ok("_empty_member_result: se_types is empty list")
    else:
        fail("_empty_member_result: se_types", str(result["se_types"]))

    # ── ## _weakness_types (real calc) ────────────────────────────────────

    char_weak = _weakness_types(charizard, "era3")

    if "Rock" in char_weak:
        ok("_weakness_types: Charizard Fire/Flying era3 — Rock is a weakness")
    else:
        fail("_weakness_types: Charizard missing Rock", str(char_weak))

    if "Electric" in char_weak:
        ok("_weakness_types: Charizard Fire/Flying era3 — Electric is a weakness")
    else:
        fail("_weakness_types: Charizard missing Electric", str(char_weak))

    if "Water" in char_weak:
        ok("_weakness_types: Charizard Fire/Flying era3 — Water is a weakness")
    else:
        fail("_weakness_types: Charizard missing Water", str(char_weak))

    if "Fire" not in char_weak:
        ok("_weakness_types: Charizard — Fire is NOT a weakness (resisted)")
    else:
        fail("_weakness_types: Charizard Fire should not be weakness", str(char_weak))

    blast_weak = _weakness_types(blastoise, "era3")

    if "Grass" in blast_weak:
        ok("_weakness_types: Blastoise Water era3 — Grass is a weakness")
    else:
        fail("_weakness_types: Blastoise missing Grass", str(blast_weak))

    if "Electric" in blast_weak:
        ok("_weakness_types: Blastoise Water era3 — Electric is a weakness")
    else:
        fail("_weakness_types: Blastoise missing Electric", str(blast_weak))

    # ── ## _se_types (real calc) ──────────────────────────────────────────

    se_empty = _se_types([], "era3")
    if se_empty == []:
        ok("_se_types: empty combo returns []")
    else:
        fail("_se_types: empty combo", str(se_empty))

    normal_combo = [_mv("Tackle", "Normal")]
    se_normal = _se_types(normal_combo, "era3")
    if se_normal == []:
        ok("_se_types: Normal-type move hits 0 types SE in era3")
    else:
        fail("_se_types: Normal should hit 0 SE", str(se_normal))

    fire_combo = [_mv("Flamethrower", "Fire")]
    se_fire = _se_types(fire_combo, "era3")
    if "Grass" in se_fire:
        ok("_se_types: Fire move hits Grass SE")
    else:
        fail("_se_types: Fire missing Grass", str(se_fire))

    if "Ice" in se_fire:
        ok("_se_types: Fire move hits Ice SE")
    else:
        fail("_se_types: Fire missing Ice", str(se_fire))

    water_combo = [_mv("Surf", "Water")]
    se_water = _se_types(water_combo, "era3")
    if "Fire" in se_water and "Rock" in se_water:
        ok("_se_types: Water move hits Fire and Rock SE")
    else:
        fail("_se_types: Water SE coverage", str(se_water))

    fire_water = [_mv("Flamethrower", "Fire"), _mv("Surf", "Water")]
    se_both = _se_types(fire_water, "era3")
    if len(se_both) > len(se_fire) and len(se_both) > len(se_water):
        ok("_se_types: Fire+Water combo covers more types than either alone")
    else:
        fail("_se_types: union should exceed each individual",
             f"fire={len(se_fire)} water={len(se_water)} both={len(se_both)}")

    # ── ## recommend_team_movesets (mocked pool + combo) ──────────────────

    _this.build_candidate_pool = _mock_pool
    _this.select_combo         = _mock_combo

    r_empty = recommend_team_movesets(team_empty, game_ctx, "coverage")
    if r_empty == []:
        ok("recommend_team_movesets: empty team returns []")
    else:
        fail("recommend_team_movesets: empty team", str(r_empty))

    r1 = recommend_team_movesets(team1, game_ctx, "coverage")
    if len(r1) == 1:
        ok("recommend_team_movesets: 1-slot team returns 1 result")
    else:
        fail("recommend_team_movesets: 1-slot count", str(len(r1)))

    if r1[0]["form_name"] == "Charizard":
        ok("recommend_team_movesets: result carries correct form_name")
    else:
        fail("recommend_team_movesets: form_name", str(r1[0]))

    required_keys = {"form_name", "types", "moves", "weakness_types", "se_types"}
    if required_keys <= set(r1[0].keys()):
        ok("recommend_team_movesets: result dict has all required keys")
    else:
        fail("recommend_team_movesets: missing keys",
             str(required_keys - set(r1[0].keys())))

    if len(r1[0]["moves"]) <= 4:
        ok("recommend_team_movesets: ≤4 moves per member")
    else:
        fail("recommend_team_movesets: too many moves", str(len(r1[0]["moves"])))

    # weakness_types uses real calc — Charizard Fire/Flying must have known weaknesses
    if "Rock" in r1[0]["weakness_types"] and "Water" in r1[0]["weakness_types"]:
        ok("recommend_team_movesets: weakness_types populated from real type chart")
    else:
        fail("recommend_team_movesets: weakness_types wrong",
             str(r1[0]["weakness_types"]))

    # se_types uses real calc on fake pool (Fire/Water/Electric/Grass/Rock moves)
    if len(r1[0]["se_types"]) > 0:
        ok("recommend_team_movesets: se_types populated for diverse fake pool")
    else:
        fail("recommend_team_movesets: se_types empty for Fire+Water+Electric+Grass+Rock combo",
             str(r1[0]["se_types"]))

    r6 = recommend_team_movesets(team6, game_ctx, "stab")
    if len(r6) == 6:
        ok("recommend_team_movesets: 6-slot team returns 6 results")
    else:
        fail("recommend_team_movesets: 6-slot count", str(len(r6)))

    # All three mode strings reach select_combo without error
    for m in ("coverage", "counter", "stab"):
        try:
            recommend_team_movesets(team1, game_ctx, m)
            ok(f"recommend_team_movesets: mode '{m}' accepted without error")
        except Exception as e:
            fail(f"recommend_team_movesets: mode '{m}' raised", str(e))

    # Empty pool → graceful degradation: no crash, empty moves and se_types
    _this.build_candidate_pool = _mock_pool_empty

    r_no_pool = recommend_team_movesets(team1, game_ctx, "coverage")
    if r_no_pool[0]["moves"] == []:
        ok("recommend_team_movesets: empty pool → moves == []")
    else:
        fail("recommend_team_movesets: empty pool moves", str(r_no_pool[0]["moves"]))

    if r_no_pool[0]["se_types"] == []:
        ok("recommend_team_movesets: empty pool → se_types == []")
    else:
        fail("recommend_team_movesets: empty pool se_types",
             str(r_no_pool[0]["se_types"]))

    # weakness_types still populated even when move pool is empty
    if "Rock" in r_no_pool[0]["weakness_types"]:
        ok("recommend_team_movesets: empty pool → weakness_types still computed")
    else:
        fail("recommend_team_movesets: empty pool weakness_types",
             str(r_no_pool[0]["weakness_types"]))

    # ── ## _format_weak_line ──────────────────────────────────────────────

    wl = _format_weak_line(["Rock", "Water", "Electric"])
    if "Rock" in wl and "Water" in wl and "Electric" in wl:
        ok("_format_weak_line: all type names present")
    else:
        fail("_format_weak_line: missing types", wl)

    wl_empty = _format_weak_line([])
    if "—" in wl_empty:
        ok("_format_weak_line: empty list renders '—'")
    else:
        fail("_format_weak_line: empty should render '—'", wl_empty)

    wl_single = _format_weak_line(["Fire"])
    if "Fire" in wl_single:
        ok("_format_weak_line: single-type renders correctly")
    else:
        fail("_format_weak_line: single type missing", wl_single)

    # ── ## _format_move_pair ──────────────────────────────────────────────

    mp_both = _format_move_pair("Flamethrower", "Air Slash")
    if "Flamethrower" in mp_both and "Air Slash" in mp_both:
        ok("_format_move_pair: both names present")
    else:
        fail("_format_move_pair: both names", mp_both)

    # Left is padded to _COL_MOVE chars before right name starts
    if mp_both.index("Air Slash") >= _COL_MOVE:
        ok("_format_move_pair: left column padded to _COL_MOVE width")
    else:
        fail("_format_move_pair: left padding insufficient", mp_both)

    mp_right_none = _format_move_pair("Surf", None)
    if "Surf" in mp_right_none and "—" in mp_right_none:
        ok("_format_move_pair: right=None renders '—'")
    else:
        fail("_format_move_pair: right=None", mp_right_none)

    mp_both_none = _format_move_pair(None, None)
    if mp_both_none.count("—") == 2:
        ok("_format_move_pair: both=None renders two '—'")
    else:
        fail("_format_move_pair: both None should give two dashes", mp_both_none)

    # ── ## _format_se_line ────────────────────────────────────────────────

    sl = _format_se_line(["Fire", "Grass", "Ice"], "era3")
    if "3" in sl and "18" in sl and "types" in sl:
        ok("_format_se_line: count, total, and 'types' present")
    else:
        fail("_format_se_line: content wrong", sl)

    sl_zero = _format_se_line([], "era3")
    if "0" in sl_zero and "types" in sl_zero:
        ok("_format_se_line: zero count renders correctly")
    else:
        fail("_format_se_line: zero count", sl_zero)

    # ── ## build_offensive_coverage ──────────────────────────────────────

    def _result(se):
        """Minimal member result with given se_types list."""
        return {"form_name": "X", "types": [], "moves": [],
                "weakness_types": [], "se_types": se}

    _, era3_types, _ = calc.CHARTS["era3"]
    n_era3 = len(era3_types)   # 18

    # Empty results → every type is a gap, nothing covered
    cov_empty = build_offensive_coverage([], "era3")
    if cov_empty["covered"] == []:
        ok("build_offensive_coverage: empty results → covered == []")
    else:
        fail("build_offensive_coverage: empty covered", str(cov_empty["covered"]))

    if len(cov_empty["gaps"]) == n_era3:
        ok("build_offensive_coverage: empty results → all types are gaps")
    else:
        fail("build_offensive_coverage: empty gaps count",
             f"{len(cov_empty['gaps'])} != {n_era3}")

    if cov_empty["overlap"] == []:
        ok("build_offensive_coverage: empty results → overlap == []")
    else:
        fail("build_offensive_coverage: empty overlap", str(cov_empty["overlap"]))

    if cov_empty["total_types"] == n_era3:
        ok("build_offensive_coverage: total_types == 18 for era3")
    else:
        fail("build_offensive_coverage: total_types", str(cov_empty["total_types"]))

    # Single member with known se_types
    r_fire = _result(["Grass", "Ice", "Bug", "Steel"])
    cov1 = build_offensive_coverage([r_fire], "era3")
    if "Grass" in cov1["covered"] and "Ice" in cov1["covered"]:
        ok("build_offensive_coverage: covered populated from single member")
    else:
        fail("build_offensive_coverage: single member covered", str(cov1["covered"]))

    if "Normal" in cov1["gaps"]:   # Fire doesn't hit Normal SE
        ok("build_offensive_coverage: un-covered type appears in gaps")
    else:
        fail("build_offensive_coverage: Normal should be gap for Fire-only",
             str(cov1["gaps"]))

    if len(cov1["covered"]) + len(cov1["gaps"]) == n_era3:
        ok("build_offensive_coverage: covered + gaps == total types")
    else:
        fail("build_offensive_coverage: covered+gaps sum",
             f"{len(cov1['covered'])}+{len(cov1['gaps'])} != {n_era3}")

    # counts dict contains every era3 type
    if set(cov1["counts"].keys()) == set(era3_types):
        ok("build_offensive_coverage: counts has entry for every era type")
    else:
        fail("build_offensive_coverage: counts keys mismatch")

    # Overlap: type covered by exactly 3 members → appears in overlap
    r_a = _result(["Rock"])
    r_b = _result(["Rock"])
    r_c = _result(["Rock"])
    r_d = _result(["Water"])   # only 1 member — should NOT be in overlap
    cov_overlap = build_offensive_coverage([r_a, r_b, r_c, r_d], "era3")
    overlap_types = [t for t, _ in cov_overlap["overlap"]]

    if "Rock" in overlap_types:
        ok("build_offensive_coverage: type covered by 3 members appears in overlap")
    else:
        fail("build_offensive_coverage: Rock (3 members) missing from overlap",
             str(overlap_types))

    if "Water" not in overlap_types:
        ok("build_offensive_coverage: type covered by 1 member NOT in overlap")
    else:
        fail("build_offensive_coverage: Water (1 member) should not be in overlap",
             str(overlap_types))

    # Overlap count correct
    rock_count = next((n for t, n in cov_overlap["overlap"] if t == "Rock"), None)
    if rock_count == 3:
        ok("build_offensive_coverage: overlap count is correct (3)")
    else:
        fail("build_offensive_coverage: overlap count", str(rock_count))

    # Overlap sorted descending by count
    r_e = _result(["Rock", "Fire"])
    r_f = _result(["Rock", "Fire"])
    r_g = _result(["Rock", "Fire"])
    r_h = _result(["Rock", "Fire"])   # Rock: 4 members, Fire: 4 members
    cov_sort = build_offensive_coverage([r_e, r_f, r_g, r_h], "era3")
    if len(cov_sort["overlap"]) >= 2:
        counts_desc = [n for _, n in cov_sort["overlap"]]
        if counts_desc == sorted(counts_desc, reverse=True):
            ok("build_offensive_coverage: overlap sorted descending by count")
        else:
            fail("build_offensive_coverage: overlap not sorted", str(cov_sort["overlap"]))
    else:
        fail("build_offensive_coverage: expected ≥2 overlap entries",
             str(cov_sort["overlap"]))

    # No gaps when all types covered
    all_types = list(era3_types)
    r_all = _result(all_types)
    cov_full = build_offensive_coverage([r_all], "era3")
    if cov_full["gaps"] == []:
        ok("build_offensive_coverage: full coverage → gaps == []")
    else:
        fail("build_offensive_coverage: full coverage still has gaps",
             str(cov_full["gaps"]))

    # ── ## _display_coverage_summary (stdout capture) ─────────────────────

    import io as _io, sys as _sys2
    _era_key = "era3"

    # Normal case: gaps and overlap present
    cov_display = {
        "covered":     ["Fire", "Water", "Grass"],
        "gaps":        ["Dragon", "Ghost"],
        "overlap":     [("Fire", 4), ("Water", 3)],
        "total_types": 18,
    }
    _buf = _io.StringIO()
    _sys2.stdout = _buf
    _display_coverage_summary(cov_display)
    _sys2.stdout = _sys2.__stdout__
    _out = _buf.getvalue()

    if "3" in _out and "18" in _out:
        ok("_display_coverage_summary: covered count and total present")
    else:
        fail("_display_coverage_summary: covered line", _out)

    if "Dragon" in _out and "Ghost" in _out:
        ok("_display_coverage_summary: gap types present")
    else:
        fail("_display_coverage_summary: gaps line", _out)

    if "Fire (4)" in _out and "Water (3)" in _out:
        ok("_display_coverage_summary: overlap entries present")
    else:
        fail("_display_coverage_summary: overlap line", _out)

    # No-gap case: "Full coverage!" shown, no gap types
    cov_full_display = {
        "covered":     list(era3_types),
        "gaps":        [],
        "overlap":     [],
        "total_types": 18,
    }
    _buf2 = _io.StringIO()
    _sys2.stdout = _buf2
    _display_coverage_summary(cov_full_display)
    _sys2.stdout = _sys2.__stdout__
    _out2 = _buf2.getvalue()

    if "Full coverage!" in _out2:
        ok("_display_coverage_summary: full coverage shows 'Full coverage!'")
    else:
        fail("_display_coverage_summary: full coverage message missing", _out2)

    # No overlap: overlap line omitted entirely
    cov_no_overlap = {
        "covered":     ["Fire"],
        "gaps":        ["Dragon"],
        "overlap":     [],
        "total_types": 18,
    }
    _buf3 = _io.StringIO()
    _sys2.stdout = _buf3
    _display_coverage_summary(cov_no_overlap)
    _sys2.stdout = _sys2.__stdout__
    _out3 = _buf3.getvalue()

    if "Overlap" not in _out3:
        ok("_display_coverage_summary: no overlap line when overlap is empty")
    else:
        fail("_display_coverage_summary: overlap line shown when empty", _out3)

    # ── Restore originals ─────────────────────────────────────────────────
    _this.build_candidate_pool = _orig_build
    _this.select_combo         = _orig_combo

    print()
    total = 61
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


# ── Main dispatch ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
    else:
        main()