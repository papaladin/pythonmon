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

def recommend_team_movesets(team_ctx: list, game_ctx: dict,
                            mode: str) -> list:
    """
    Compute a recommended moveset for each filled team slot.

    mode — "coverage" | "counter" | "stab"

    Returns a list of member result dicts (one per filled slot, in slot order).
    Full implementation deferred to step 4.2 — currently returns placeholder
    dicts with empty move lists.
    """
    results = []
    for _idx, pkm in team_slots(team_ctx):
        results.append(_empty_member_result(pkm["form_name"]))
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

def _run_tests():
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_moveset.py -- self-test (stub)\n")

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
    if result["form_name"] == "Charizard":
        ok("_empty_member_result: form_name set correctly")
    else:
        fail("_empty_member_result form_name", str(result.get("form_name")))

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

    # ── recommend_team_movesets — 1-member team ───────────────────────────────

    results1 = recommend_team_movesets(team1, game_ctx, "stab")
    if len(results1) == 1 and results1[0]["form_name"] == "Charizard":
        ok("recommend_team_movesets: 1-member team -> 1 result with correct name")
    else:
        fail("recommend_team_movesets one member", str(results1))

    # ── recommend_team_movesets — result has required keys ────────────────────

    required_keys = {"form_name", "moves", "weakness_types", "se_types"}
    missing = required_keys - set(results1[0].keys())
    if not missing:
        ok("recommend_team_movesets: result dict has all required keys")
    else:
        fail("recommend_team_movesets keys", str(missing))

    # ── recommend_team_movesets — 6-member team ───────────────────────────────

    results6 = recommend_team_movesets(team6, game_ctx, "coverage")
    if len(results6) == 6:
        ok("recommend_team_movesets: 6-member team -> 6 results")
    else:
        fail("recommend_team_movesets 6-member", str(len(results6)))

    # ── _MODES constant ───────────────────────────────────────────────────────

    for key, mode in [("c", "coverage"), ("u", "counter"), ("s", "stab")]:
        if _MODES.get(key) == mode:
            ok(f"_MODES: '{key}' -> '{mode}'")
        else:
            fail(f"_MODES key {key}", str(_MODES.get(key)))

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 11
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
