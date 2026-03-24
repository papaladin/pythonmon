#!/usr/bin/env python3
"""
core_opponent.py  Pure opponent‑analysis logic (no I/O, no display)

Functions:
  analyze_matchup(team_ctx, opponent_team, era_key) → list[dict]
  uncovered_threats(matchup_results) → list[dict]
  recommended_leads(matchup_results, team_ctx) → list[str]
"""

import sys

try:
    import matchup_calculator as calc
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


def analyze_matchup(team_ctx: list, opponent_team: list, era_key: str) -> list:
    """
    Analyze team coverage vs a single opponent trainer.

    MOVESET-AWARE logic:
      - For YOUR team:
        * Threats = team member's DEFENSIVE types (what hits them SE)
        * Counters = team member's STAB move types (assume STAB moves)
      - For OPPONENT:
        * Threats = opponent's ACTUAL move types (from their moveset)
        * Resists = opponent's ACTUAL move types (from their moveset)

    Args:
      team_ctx (list): Team context — list of team member dicts with form_name, type1, type2
      opponent_team (list): List of opponent Pokémon dicts, each containing:
          name (str), types (list[str]), level (int), move_types (list[str])
      era_key (str): "era1", "era2", or "era3"

    Returns:
      list[dict]: One result dict per opponent Pokemon
        {
          "name": str,
          "types": [str, str],
          "level": int,
          "threats": [{"form_name": str, "multiplier": float, "move_types": [str]}, ...],
          "resists": [{"form_name": str, "multiplier": float, "move_types": [str]}, ...],
          "counters": [{"form_name": str, "move_types": [str]}, ...],
        }
    """
    if not opponent_team:
        return []

    results = []

    for opponent_pkm in opponent_team:
        opp_name = opponent_pkm.get("name", "Unknown")
        opp_types = opponent_pkm.get("types", [])
        opp_level = opponent_pkm.get("level", 1)

        opp_move_types = opponent_pkm.get("move_types", [])

        threats = []
        resists = []
        counters = []

        for member in team_ctx:
            if not member:
                continue
            form_name = member.get("form_name", "Unknown")
            member_type1 = member.get("type1", "Normal")
            member_type2 = member.get("type2", "None")

            # THREATS: Team member's DEFENSIVE types vs opponent's ACTUAL moves
            member_defense = calc.compute_defense(era_key, member_type1, member_type2)
            threats_from_opponent = []
            threatening_move_types = []

            for move_type in opp_move_types:
                mult = member_defense.get(move_type, 1.0)
                if mult > 1.0:
                    threats_from_opponent.append(mult)
                    if move_type not in threatening_move_types:
                        threatening_move_types.append(move_type)

            if threats_from_opponent:
                threats.append({
                    "form_name": form_name,
                    "multiplier": max(threats_from_opponent),
                    "move_types": threatening_move_types
                })

            # RESISTS: Team member's DEFENSIVE types vs opponent's ACTUAL moves
            resists_from_opponent = []
            resisting_move_types = []

            for move_type in opp_move_types:
                mult = member_defense.get(move_type, 1.0)
                if mult < 1.0:
                    resists_from_opponent.append(mult)
                    if move_type not in resisting_move_types:
                        resisting_move_types.append(move_type)

            if resists_from_opponent:
                resists.append({
                    "form_name": form_name,
                    "multiplier": min(resists_from_opponent),
                    "move_types": resisting_move_types
                })

            # COUNTERS: Team member's STAB types vs opponent's DEFENSIVE types
            member_stab_types = [member_type1]
            if member_type2 != "None":
                member_stab_types.append(member_type2)

            se_move_types = []
            for stab_type in member_stab_types:
                for opp_type in opp_types:
                    mult = calc.get_multiplier(era_key, stab_type, opp_type)
                    if mult >= 2.0 and stab_type not in se_move_types:
                        se_move_types.append(stab_type)

            if se_move_types:
                counters.append({
                    "form_name": form_name,
                    "move_types": se_move_types
                })

        results.append({
            "name": opp_name,
            "types": opp_types,
            "level": opp_level,
            "threats": threats,
            "resists": resists,
            "counters": counters,
        })

    return results


def uncovered_threats(matchup_results: list) -> list:
    """
    Return opponent Pokemon that no team member can hit SE.

    Args:
      matchup_results (list): Output from analyze_matchup()

    Returns:
      list[dict]: Subset of matchup_results where counters is empty
    """
    return [result for result in matchup_results if not result.get("counters", [])]


def recommended_leads(matchup_results: list, team_ctx: list) -> list:
    """
    Rank team members by number of opponent Pokemon they hit SE.

    Args:
      matchup_results (list): Output from analyze_matchup()
      team_ctx (list): Team context — list of team member dicts

    Returns:
      list[str]: Team member form_names sorted by SE coverage (descending),
                 then by team order (position in team_ctx)
    """
    if not team_ctx:
        return []

    coverage = {}
    for i, member in enumerate(team_ctx):
        if not member:
            continue
        form_name = member.get("form_name", "Unknown")
        coverage[form_name] = (0, i)  # (count, position)

    for result in matchup_results:
        for counter in result.get("counters", []):
            form_name = counter.get("form_name")
            if form_name in coverage:
                count, pos = coverage[form_name]
                coverage[form_name] = (count + 1, pos)

    sorted_leads = sorted(coverage.items(), key=lambda x: (-x[1][0], x[1][1]))
    return [form_name for form_name, _ in sorted_leads]


# ── Self‑tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import sys
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

    print("\n  core_opponent.py — self-test\n")

    # Fixture
    def _pkm(name, t1, t2="None"):
        return {"form_name": name, "type1": t1, "type2": t2}

    team_lapras = [_pkm("Lapras", "Water", "Ice")]
    brock_opponents = [
        {"name": "Geodude", "types": ["Rock", "Ground"], "level": 12,
         "move_types": ["Normal", "Normal"]},  # Tackle, Defense Curl
        {"name": "Onix", "types": ["Rock", "Ground"], "level": 14,
         "move_types": ["Normal", "Normal", "Normal"]},  # Tackle, Bind, Screech
    ]

    # Test analyze_matchup
    results = analyze_matchup(team_lapras, brock_opponents, "era1")
    if len(results) == 2:
        ok("analyze_matchup: returns result for each opponent Pokemon")
    else:
        fail("analyze_matchup count", f"expected 2, got {len(results)}")

    geodude = next((r for r in results if r["name"] == "Geodude"), None)
    if geodude:
        # Geodude's Normal moves should not threaten Lapras
        threats_lapras = [t for t in geodude["threats"] if t["form_name"] == "Lapras"]
        if not threats_lapras:
            ok("analyze_matchup: Geodude's Normal moves don't threaten Lapras")
        else:
            fail("analyze_matchup threat", f"Unexpected threat: {threats_lapras}")

        # Lapras should counter Geodude via Water type
        counters_lapras = [c for c in geodude["counters"] if c["form_name"] == "Lapras"]
        if counters_lapras and "Water" in counters_lapras[0]["move_types"]:
            ok("analyze_matchup: Lapras counters Geodude with Water")
        else:
            fail("analyze_matchup counter", str(counters_lapras))

    # Test uncovered_threats
    uncovered = uncovered_threats(results)
    if len(uncovered) == 0:
        ok("uncovered_threats: all threats covered (Lapras counters both)")
    else:
        fail("uncovered_threats", str(uncovered))

    # Test recommended_leads
    leads = recommended_leads(results, team_lapras)
    if leads == ["Lapras"]:
        ok("recommended_leads: Lapras ranked first")
    else:
        fail("recommended_leads", str(leads))

    # Additional test for uncovered_threats when no counters
    team_empty = [None] * 6
    empty_results = analyze_matchup(team_empty, brock_opponents, "era1")
    uncovered2 = uncovered_threats(empty_results)
    if len(uncovered2) == len(brock_opponents):
        ok("uncovered_threats: no counters -> all uncovered")
    else:
        fail("uncovered_threats empty team", str(uncovered2))

    # Test recommended_leads with multiple members
    team_multi = [
        _pkm("Charizard", "Fire", "Flying"),
        _pkm("Blastoise", "Water"),
        _pkm("Venusaur", "Grass", "Poison")
    ]
    misty_opponents = [
        {"name": "Staryu", "types": ["Water"], "level": 18,
         "move_types": ["Normal", "Water"]},
        {"name": "Starmie", "types": ["Water", "Psychic"], "level": 21,
         "move_types": ["Water", "Psychic"]},
    ]
    results_misty = analyze_matchup(team_multi, misty_opponents, "era1")
    leads_misty = recommended_leads(results_misty, team_multi)
    if leads_misty and leads_misty[0] == "Venusaur":  # Grass beats Water
        ok("recommended_leads: Venusaur ranked first (Grass beats Water)")
    else:
        fail("recommended_leads ranking", str(leads_misty))

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