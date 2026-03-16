#!/usr/bin/env python3
"""
feat_team_moveset.py  Team moveset synergy

Orchestrates team-level moveset recommendations by running the single-Pokemon
scoring engine across all team members and aggregating results into a team
offensive coverage summary.

Accessible via menu key S (needs team + game).

Public API (step 4.1 stub — scoring logic implemented in step 4.2,
display in step 4.3, menu wiring in step 4.4):
  recommend_team_movesets(team_ctx, game_ctx, mode) -> list[dict]
  run(team_ctx, game_ctx)   called from pokemain (key S)
  main()                    standalone

Member result structure (one dict per filled team slot):
  {
    "form_name":      str,        # Pokemon display name
    "moves":          list[dict], # recommended moves (empty in stub)
    "weakness_types": list[str],  # types the Pokemon is weak to
    "se_types":       list[str],  # types the moveset hits SE
  }
"""

import sys

try:
    from feat_team_loader import team_slots, team_size
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Constants ─────────────────────────────────────────────────────────────────

_MODES = {
    "c": "coverage",
    "u": "counter",
    "s": "stab",
}


# ── Placeholder structure ─────────────────────────────────────────────────────

def _empty_member_result(form_name: str) -> dict:
    """
    Return an empty member result dict with the correct shape.
    Used as a placeholder until step 4.2 fills in real move data.
    """
    return {
        "form_name":      form_name,
        "moves":          [],
        "weakness_types": [],
        "se_types":       [],
    }


# ── Core logic (stub) ─────────────────────────────────────────────────────────

# ── Core logic ────────────────────────────────────────────────────────────────

from feat_moveset import build_candidate_pool, select_combo, calc, rank_status_moves

def recommend_team_movesets(team_ctx: list, game_ctx: dict,
                            mode: str) -> list:
    """
    Compute recommended movesets for each filled team slot using the
    single-Pokemon scoring engine from feat_moveset.py.

    mode — "coverage" | "counter" | "stab"

    Returns a list of member result dicts (one per filled slot, in slot order).
    Each dict has:
      - form_name: Pokemon display name
      - moves: list of recommended moves (dicts)
      - weakness_types: list of types this Pokemon is weak to
      - se_types: list of types the moveset hits SE
    """
    results = []

    for _idx, pkm_ctx in team_slots(team_ctx):
        if pkm_ctx is None:
            continue

        result = _empty_member_result(pkm_ctx["form_name"])

        # Build scored pool for this Pokemon
        try:
            pool = build_candidate_pool(pkm_ctx, game_ctx)
        except (ConnectionError, ValueError):
            results.append(result)
            continue

        damage_pool = pool.get("damage", [])
        if not damage_pool:
            results.append(result)
            continue

        # Compute weaknesses
        defense = calc.compute_defense(game_ctx["era_key"],
                                       pkm_ctx["type1"], pkm_ctx["type2"])
        weak_types = sorted([t for t, m in defense.items() if m > 1.0])
        result["weakness_types"] = weak_types

        # Rank status moves (optional — could store top 3)
        status_ranked = rank_status_moves(pool.get("status", []), top_n=3)

        # Select combo based on mode
        combo = select_combo(damage_pool, mode, weak_types, game_ctx["era_key"])
        result["moves"] = combo

        # Compute SE types
        se_types, _ = calc._compute_coverage(combo, game_ctx["era_key"]) \
                      if combo else ([], [])
        result["se_types"] = se_types

        results.append(result)

    return results


# ── Display helpers (stub) ────────────────────────────────────────────────────

def _mode_prompt() -> str:
    """
    Prompt the user to select a recommendation mode.
    Returns "coverage", "counter", or "stab".
    """
    while True:
        print("\n  Select mode:")
        print("    (C)overage")
        print("    co(U)nter")
        print("    (S)TAB")
        choice = input("  Mode: ").strip().lower()
        if choice in _MODES:
            return _MODES[choice]
        print("  Invalid choice — press C, U or S.")


# ── Entry points ──────────────────────────────────────────────────────────────

def run(team_ctx: list, game_ctx: dict) -> None:
    """Called from pokemain (key S). Stub — full display implemented in step 4.3."""
    if team_size(team_ctx) == 0:
        print("\n  Team is empty -- load some Pokemon first (press T).")
        return
    mode = _mode_prompt()
    print(f"\n  [Team moveset synergy — {mode} mode]")
    print("  (Full output available after step 4.3)")
    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("+===========================================+")
    print("|     Team Moveset Synergy                  |")
    print("+===========================================+")
    print()
    print("  Standalone entry not yet implemented (step 4.3).")
    input("  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import types
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_moveset.py -- self-test (with Task 4.2)\n")

    # ── Fixtures ──────────────────────────────────────────────────────────────
    def _pkm(name, t1, t2="None"):
        return {
            "form_name": name, "type1": t1, "type2": t2,
            "pokemon": name.lower(), "variety_slug": name.lower(),
            "species_gen": 1, "form_gen": 1,
            "base_stats": {"hp": 80, "attack": 80, "defense": 80,
                           "special-attack": 80, "special-defense": 80, "speed": 80},
        }

    game_ctx   = {"game": "Scarlet / Violet", "era_key": "era3",
                  "game_gen": 9, "game_slug": "scarlet-violet"}
    team_empty = [None] * 6
    charizard  = _pkm("Charizard", "Fire", "Flying")
    blastoise  = _pkm("Blastoise", "Water")
    team1      = [charizard, None, None, None, None, None]
    team6      = [charizard, blastoise, charizard, blastoise, charizard, blastoise]

    # ── _empty_member_result — shape ──────────────────────────────────────────
    result = _empty_member_result("Charizard")
    for field in ("moves", "weakness_types", "se_types"):
        if isinstance(result.get(field), list):
            ok(f"_empty_member_result: '{field}' is a list")
        else:
            fail(f"_empty_member_result {field} type", str(type(result.get(field))))

    # ── recommend_team_movesets — empty team ──────────────────────────────────
    results = recommend_team_movesets(team_empty, game_ctx, "coverage")
    if results == []:
        ok("recommend_team_movesets: empty team -> []")
    else:
        fail("recommend_team_movesets empty", str(results))

    # ── Monkey-patch feat_moveset functions for controlled tests ─────────────
    
    import sys

    this = sys.modules[__name__]

    def mock_build_candidate_pool(pkm_ctx, game_ctx):
        return {
            "damage": [{
                "name": "Tackle",
                "type": "Normal",
                "category": "Physical",
                "power": 50,
                "accuracy": 100,
                "priority": 0,
                "drain": 0,
                "effect_chance": 0,
                "counters_weaknesses": [],
                "is_stab": True,
                "score": 1,
                "is_two_turn": False,
                "low_accuracy": False,
                "ailment": None
            }],
            "status": [],
            "skipped": 0
        }

    def mock_select_combo(damage_pool, mode, weak_types, era_key, locked=None):
        return damage_pool

    def mock_compute_defense(era_key, t1, t2=None):
        return {"Fire": 2.0, "Water": 1.0, "Grass": 2.0}

    def mock_compute_coverage(combo, era_key):
        return ["Normal"], []

    # Apply mocks to THIS module
    this.build_candidate_pool = mock_build_candidate_pool
    this.select_combo = mock_select_combo
    this.calc.compute_defense = mock_compute_defense
    this.calc._compute_coverage = mock_compute_coverage

    # ── recommend_team_movesets — 1-member team ───────────────────────────────
    results1 = recommend_team_movesets(team1, game_ctx, "stab")
    if len(results1) == 1 and results1[0]["form_name"] == "Charizard":
        ok("recommend_team_movesets: 1-member team -> 1 result with correct name")
    else:
        fail("recommend_team_movesets one member", str(results1))

    # Check keys
    required_keys = {"form_name", "moves", "weakness_types", "se_types"}
    missing = required_keys - set(results1[0].keys())
    if not missing:
        ok("recommend_team_movesets: result dict has all required keys")
    else:
        fail("recommend_team_movesets keys", str(missing))

    # Check moves content
    if results1[0]["moves"] and results1[0]["moves"][0]["name"] == "Tackle":
        ok("recommend_team_movesets: moves populated correctly")
    else:
        fail("recommend_team_movesets moves", str(results1[0]["moves"]))

    # Check weaknesses
    if results1[0]["weakness_types"] == ["Fire", "Grass"]:
        ok("recommend_team_movesets: weaknesses populated correctly")
    else:
        fail("recommend_team_movesets weaknesses", results1[0]["weakness_types"])

    # Check SE types
    if results1[0]["se_types"] == ["Normal"]:
        ok("recommend_team_movesets: se_types populated correctly")
    else:
        fail("recommend_team_movesets se_types", results1[0]["se_types"])

    # ── recommend_team_movesets — 6-member team ───────────────────────────────
    results6 = recommend_team_movesets(team6, game_ctx, "coverage")
    if len(results6) == 6:
        ok("recommend_team_movesets: 6-member team -> 6 results")
    else:
        fail("recommend_team_movesets 6-member", str(len(results6)))

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 12
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")
        
        
# ── Standalone / autotest entry point ──────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if "--autotest" in sys.argv:
        try:
            _run_tests()
        except Exception as e:
            print(f"\n[ERROR] Self-test failed: {e}")
            sys.exit(1)
    else:
        # Standalone run message
        print()
        print("+===========================================+")
        print("|     Team Moveset Synergy                  |")
        print("+===========================================+")
        print()
        print("  Standalone execution not yet implemented.")
        print("  Use this module from pokemain.py (key S).")
        input("  Press Enter to exit...")
