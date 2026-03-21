#!/usr/bin/env python3
"""
feat_opponent.py  Team coverage vs in-game opponents

Loads a static trainer database (data/trainers.json) bundled with the project
and lets the player evaluate their loaded team against a named gym leader,
Elite Four member, Champion, or rival.

The trainer data is source data, not user cache — it lives in data/ not cache/.
Move names in trainers.json must match moves.json display names exactly so that
the existing cache.resolve_move() pipeline can look them up.

Data policy (recorded in trainers.json _meta):
  - First encounter, normal difficulty
  - Most feature-complete version of each game group
    (e.g. Platinum over Diamond/Pearl, Emerald over Ruby/Sapphire)
  - Version differences and rematches are separate entries
  - Types are era-correct for the game (Clefable is Normal in Gen 1–5)

Entry points:
  run(team_ctx, game_ctx)   called from pokemain (key X)
  main()                    standalone

Public API (Iteration A — loader):
  load_trainer_data()                → dict
  get_trainers_for_game(game_slug)   → dict
  list_trainer_names(game_slug)      → list[str]
"""

import json
import os
import sys

try:
    import pkm_cache as cache
    import matchup_calculator as calc
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Data file path ────────────────────────────────────────────────────────────

_DATA_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_TRAINERS_FILE = os.path.join(_DATA_DIR, "trainers.json")

# Module-level cache so the file is read once per session
_trainer_data: dict | None = None


# ── Loader ────────────────────────────────────────────────────────────────────

def load_trainer_data() -> dict:
    """
    Load trainers.json from the data/ directory.

    Reads once and caches in memory for the rest of the session.
    Returns {} if the file is missing or malformed — caller should check.
    """
    global _trainer_data
    if _trainer_data is not None:
        return _trainer_data
    try:
        with open(_TRAINERS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Strip metadata key — callers only need game entries
        _trainer_data = {k: v for k, v in raw.items() if not k.startswith("_")}
        return _trainer_data
    except FileNotFoundError:
        print(f"  Warning: trainer data file not found at {_TRAINERS_FILE}")
        _trainer_data = {}
        return {}
    except json.JSONDecodeError as e:
        print(f"  Warning: trainer data file is malformed: {e}")
        _trainer_data = {}
        return {}


def get_trainers_for_game(game_slug: str, data: dict | None = None) -> dict:
    """
    Return the trainer dict for a given game slug.

    game_slug matches game_ctx["game_slug"] — e.g. "red-blue", "platinum".
    Returns {} when no data exists for that game.

    data — optional pre-loaded dict for testing; loads from file if None.
    """
    if data is None:
        data = load_trainer_data()
    return data.get(game_slug, {})


def list_trainer_names(game_slug: str, data: dict | None = None) -> list:
    """
    Return trainer names for a game, sorted by encounter order.

    Sort key: "order" field in the trainer entry (ascending), then
    alphabetical within the same order value.
    Returns [] when no data exists for that game.
    """
    trainers = get_trainers_for_game(game_slug, data)
    return sorted(
        trainers.keys(),
        key=lambda name: (trainers[name].get("order", 999), name)
    )


def get_trainer(game_slug: str, trainer_name: str,
                data: dict | None = None) -> dict | None:
    """
    Return the trainer entry for a specific game + name, or None if not found.
    """
    trainers = get_trainers_for_game(game_slug, data)
    return trainers.get(trainer_name)


# ── Validation helpers ────────────────────────────────────────────────────────

def validate_trainer_data(data: dict) -> list:
    """
    Validate the trainer data dict against known constraints.
    Returns a list of issue strings. Empty list = clean.

    Checks:
      - Every trainer has a "party" list with at least 1 Pokemon
      - Every party member has name, types (list), level (int > 0), moves (list)
      - Types must be valid era3 types (broadest set — catches unknown strings)
      - Move names must be non-empty strings
    """
    issues = []
    valid_types = set(calc.TYPES_ERA3)

    for game_slug, trainers in data.items():
        if game_slug.startswith("_"):
            continue
        if not isinstance(trainers, dict):
            issues.append(f"{game_slug}: not a dict")
            continue
        for trainer_name, entry in trainers.items():
            prefix = f"{game_slug}/{trainer_name}"
            party = entry.get("party", [])
            if not party:
                issues.append(f"{prefix}: empty party")
                continue
            for i, pkm in enumerate(party):
                p = f"{prefix}/party[{i}] {pkm.get('name', '?')}"
                if not pkm.get("name"):
                    issues.append(f"{p}: missing name")
                if not isinstance(pkm.get("types"), list) or not pkm["types"]:
                    issues.append(f"{p}: missing or empty types")
                else:
                    for t in pkm["types"]:
                        if t not in valid_types:
                            issues.append(f"{p}: unknown type '{t}'")
                if not isinstance(pkm.get("level"), int) or pkm["level"] <= 0:
                    issues.append(f"{p}: invalid level")
                if not isinstance(pkm.get("moves"), list) or not pkm["moves"]:
                    issues.append(f"{p}: missing or empty moves")
                else:
                    for m in pkm["moves"]:
                        if not isinstance(m, str) or not m.strip():
                            issues.append(f"{p}: invalid move entry {m!r}")
    return issues

# ── Iteration B — Pure matchup logic ──────────────────────────────────────────

def analyze_matchup(team_ctx, trainer, era_key):
    """
    Analyze how a player's team matches up against a trainer's party.
    
    For each trainer Pokemon, compute:
      - threats:  team members weak to it (multiplier > 1.0)
      - resists:  team members that resist it (multiplier < 1.0)
      - counters: team members hitting it SE via their types (multiplier >= 2.0)
    
    Args:
      team_ctx:  list of team member dicts with form_name, type1, type2
      trainer:   trainer entry dict with 'party' key (list of opponent Pokemon)
      era_key:   "era1", "era2", or "era3" (for type chart lookup)
    
    Returns:
      list[dict] — one result dict per trainer Pokemon:
        {
          "name":     str,           # opponent Pokemon name
          "types":    [str, str],    # [type1, type2]
          "level":    int,
          "threats":  [{
            "form_name": str,
            "multiplier": float      # > 1.0 means weak to this team member
          }, ...],
          "resists":  [{
            "form_name": str,
            "multiplier": float      # < 1.0 means resists this team member
          }, ...],
          "counters": [{
            "form_name": str,
            "types":    [str, ...]   # which of this member's types hit SE
          }, ...]
        }
    """
    results = []
    
    for opp_pkm in trainer.get("party", []):
        opp_name = opp_pkm.get("name", "?")
        opp_type1 = opp_pkm.get("types", ["None"])[0]
        opp_type2 = opp_pkm.get("types", ["None"])[1] if len(opp_pkm.get("types", [])) > 1 else "None"
        
        # Compute defensive matchup: how much damage does each team member do?
        threats = []
        resists = []
        counters = []
        
        for team_member in team_ctx:
            member_form = team_member.get("form_name", "?")
            member_t1 = team_member.get("type1", "None")
            member_t2 = team_member.get("type2", "None")
            
            # Each of the team member's types attacking the opponent
            hits_se = []
            for member_type in [member_t1, member_t2]:
                if member_type == "None":
                    continue
                mult = calc.get_multiplier(era_key, member_type, opp_type1)
                mult *= calc.get_multiplier(era_key, member_type, opp_type2) if opp_type2 != "None" else 1.0
                
                if mult >= 2.0:
                    hits_se.append(member_type)
            
            if hits_se:
                counters.append({
                    "form_name": member_form,
                    "types": hits_se
                })
            
            # Each of the opponent's types attacking the team member
            def_mult_t1 = calc.get_multiplier(era_key, opp_type1, member_t1)
            def_mult_t2 = calc.get_multiplier(era_key, opp_type1, member_t2) if member_t2 != "None" else 1.0
            combined_from_t1 = def_mult_t1 * def_mult_t2
            
            def_mult_t1_from_t2 = calc.get_multiplier(era_key, opp_type2, member_t1) if opp_type2 != "None" else 1.0
            def_mult_t2_from_t2 = calc.get_multiplier(era_key, opp_type2, member_t2) if opp_type2 != "None" else 1.0
            combined_from_t2 = def_mult_t1_from_t2 * def_mult_t2_from_t2
            
            total_mult = combined_from_t1 * combined_from_t2
            
            if total_mult > 1.0:
                threats.append({
                    "form_name": member_form,
                    "multiplier": total_mult
                })
            elif total_mult < 1.0:
                resists.append({
                    "form_name": member_form,
                    "multiplier": total_mult
                })
        
        results.append({
            "name": opp_name,
            "types": [opp_type1, opp_type2],
            "level": opp_pkm.get("level", 0),
            "threats": threats,
            "resists": resists,
            "counters": counters
        })
    
    return results


def uncovered_threats(matchup_results):
    """
    Filter matchup results to return only opponent Pokemon with zero counters.
    
    Args:
      matchup_results: list returned from analyze_matchup()
    
    Returns:
      list[dict] — subset of matchup_results where counters list is empty
    """
    return [r for r in matchup_results if not r["counters"]]


def recommended_leads(matchup_results, team_ctx):
    """
    Rank team members by how many opponent Pokemon they can hit SE.
    
    Args:
      matchup_results: list returned from analyze_matchup()
      team_ctx: player's team (to preserve order and get form_name)
    
    Returns:
      list[str] — team member form_names sorted by SE coverage (descending)
               then by team order (as they appear in team_ctx)
    """
    # Count how many opponent Pokemon each team member hits SE
    se_counts = {}
    for team_member in team_ctx:
        form_name = team_member.get("form_name", "?")
        se_counts[form_name] = 0
    
    for result in matchup_results:
        for counter in result["counters"]:
            form_name = counter["form_name"]
            if form_name in se_counts:
                se_counts[form_name] += 1
    
    # Sort by count descending, then by team order (index in team_ctx)
    team_order = {team_member.get("form_name", "?"): i for i, team_member in enumerate(team_ctx)}
    
    sorted_names = sorted(
        se_counts.keys(),
        key=lambda name: (-se_counts[name], team_order.get(name, 999))
    )
    
    return sorted_names

# ── Entry point stubs (Iterations B–D) ───────────────────────────────────────

def run(team_ctx: list, game_ctx: dict) -> None:
    """Called from pokemain (key X). Implemented in Iteration D."""
    print("\n  Team vs opponent — not yet fully implemented.")
    print("  (Iteration A complete: data loader ready)")
    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("╔══════════════════════════════════════════╗")
    print("║      Team vs In-Game Opponent            ║")
    print("╚══════════════════════════════════════════╝")
    print("\n  Feature in progress — Iteration A (data loader) complete.")
    print(f"  Trainer data file: {_TRAINERS_FILE}")
    data = load_trainer_data()
    if not data:
        print("  No trainer data loaded.")
        return
    print(f"\n  Games with trainer data ({len(data)}):")
    for slug in sorted(data.keys()):
        names = list_trainer_names(slug, data)
        print(f"    {slug:<30}  {len(names)} trainers")
    input("\n  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):  print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_opponent.py — self-test (Iteration A)\n")

    # ── Fixture ───────────────────────────────────────────────────────────────
    # All tests use this fixture dict — no file I/O in offline tests.

    _fixture = {
        "red-blue": {
            "Brock": {
                "title": "Gym Leader 1 — Rock",
                "order": 1,
                "party": [
                    {
                        "name": "Geodude",
                        "types": ["Rock", "Ground"],
                        "level": 12,
                        "moves": ["Tackle", "Defense Curl"]
                    },
                    {
                        "name": "Onix",
                        "types": ["Rock", "Ground"],
                        "level": 14,
                        "moves": ["Tackle", "Bind", "Screech"]
                    }
                ]
            },
            "Misty": {
                "title": "Gym Leader 2 — Water",
                "order": 2,
                "party": [
                    {
                        "name": "Staryu",
                        "types": ["Water"],
                        "level": 18,
                        "moves": ["Tackle", "Water Gun"]
                    },
                    {
                        "name": "Starmie",
                        "types": ["Water", "Psychic"],
                        "level": 21,
                        "moves": ["Water Gun", "Bubblebeam"]
                    }
                ]
            },
            "Blue": {
                "title": "Champion",
                "order": 13,
                "party": [
                    {
                        "name": "Pidgeot",
                        "types": ["Normal", "Flying"],
                        "level": 59,
                        "moves": ["Quick Attack", "Gust"]
                    },
                    {
                        "name": "Blastoise",
                        "types": ["Water"],
                        "level": 63,
                        "moves": ["Water Gun", "Bubble"]
                    }
                ]
            }
        },
        "platinum": {
            "Cynthia": {
                "title": "Champion",
                "order": 13,
                "party": [
                    {
                        "name": "Spiritomb",
                        "types": ["Ghost", "Dark"],
                        "level": 58,
                        "moves": ["Dark Pulse", "Shadow Ball"]
                    },
                    {
                        "name": "Garchomp",
                        "types": ["Dragon", "Ground"],
                        "level": 62,
                        "moves": ["Earthquake", "Dragon Rush"]
                    }
                ]
            }
        }
    }

    # ── get_trainers_for_game ─────────────────────────────────────────────────

    result = get_trainers_for_game("red-blue", _fixture)
    if set(result.keys()) == {"Brock", "Misty", "Blue"}:
        ok("get_trainers_for_game: returns correct trainers for red-blue")
    else:
        fail("get_trainers_for_game red-blue", str(set(result.keys())))

    result2 = get_trainers_for_game("platinum", _fixture)
    if "Cynthia" in result2 and len(result2) == 1:
        ok("get_trainers_for_game: returns correct trainers for platinum")
    else:
        fail("get_trainers_for_game platinum", str(result2))

    result3 = get_trainers_for_game("gold-silver", _fixture)
    if result3 == {}:
        ok("get_trainers_for_game: unknown game slug → {}")
    else:
        fail("get_trainers_for_game unknown", str(result3))

    # ── list_trainer_names ────────────────────────────────────────────────────

    names = list_trainer_names("red-blue", _fixture)
    if names == ["Brock", "Misty", "Blue"]:
        ok("list_trainer_names: sorted by order field (Brock=1, Misty=2, Blue=13)")
    else:
        fail("list_trainer_names order", str(names))

    names2 = list_trainer_names("platinum", _fixture)
    if names2 == ["Cynthia"]:
        ok("list_trainer_names: single entry returned correctly")
    else:
        fail("list_trainer_names single", str(names2))

    names3 = list_trainer_names("gold-silver", _fixture)
    if names3 == []:
        ok("list_trainer_names: unknown game → []")
    else:
        fail("list_trainer_names unknown", str(names3))

    # Alphabetical tiebreak for same order value
    _tie_fixture = {"test-game": {
        "Zelda": {"order": 1, "party": [{"name": "X", "types": ["Fire"], "level": 1, "moves": ["Tackle"]}]},
        "Aaron": {"order": 1, "party": [{"name": "X", "types": ["Fire"], "level": 1, "moves": ["Tackle"]}]},
        "Mike":  {"order": 1, "party": [{"name": "X", "types": ["Fire"], "level": 1, "moves": ["Tackle"]}]},
    }}
    tie_names = list_trainer_names("test-game", _tie_fixture)
    if tie_names == ["Aaron", "Mike", "Zelda"]:
        ok("list_trainer_names: alphabetical tiebreak within same order value")
    else:
        fail("list_trainer_names tiebreak", str(tie_names))

    # Trainers without order field fall back to 999 (appear last)
    _noorder = {"test": {
        "NoOrder":  {"party": [{"name": "X", "types": ["Fire"], "level": 1, "moves": ["T"]}]},
        "HasOrder": {"order": 1, "party": [{"name": "X", "types": ["Fire"], "level": 1, "moves": ["T"]}]},
    }}
    no_order_names = list_trainer_names("test", _noorder)
    if no_order_names[0] == "HasOrder" and no_order_names[1] == "NoOrder":
        ok("list_trainer_names: missing order field → falls back to 999 (last)")
    else:
        fail("list_trainer_names no order", str(no_order_names))

    # ── get_trainer ───────────────────────────────────────────────────────────

    brock = get_trainer("red-blue", "Brock", _fixture)
    if brock and brock["title"] == "Gym Leader 1 — Rock" and len(brock["party"]) == 2:
        ok("get_trainer: returns correct entry for Brock")
    else:
        fail("get_trainer Brock", str(brock))

    none_result = get_trainer("red-blue", "Cynthia", _fixture)
    if none_result is None:
        ok("get_trainer: unknown trainer name → None")
    else:
        fail("get_trainer unknown", str(none_result))

    none_game = get_trainer("gold-silver", "Brock", _fixture)
    if none_game is None:
        ok("get_trainer: unknown game → None")
    else:
        fail("get_trainer unknown game", str(none_game))

    # ── Party structure ───────────────────────────────────────────────────────

    brock_party = brock["party"]
    geodude = brock_party[0]
    if geodude["name"] == "Geodude" and geodude["types"] == ["Rock", "Ground"]:
        ok("party member: name and types correct")
    else:
        fail("party member types", str(geodude))

    if geodude["level"] == 12:
        ok("party member: level correct")
    else:
        fail("party member level", str(geodude["level"]))

    if "Tackle" in geodude["moves"] and "Defense Curl" in geodude["moves"]:
        ok("party member: moves list present and correct")
    else:
        fail("party member moves", str(geodude["moves"]))

    starmie = get_trainer("red-blue", "Misty", _fixture)["party"][1]
    if starmie["types"] == ["Water", "Psychic"]:
        ok("party member: dual type stored correctly")
    else:
        fail("party member dual type", str(starmie["types"]))

    # ── validate_trainer_data ─────────────────────────────────────────────────

    issues = validate_trainer_data(_fixture)
    if issues == []:
        ok("validate_trainer_data: clean fixture → no issues")
    else:
        fail("validate_trainer_data clean", str(issues))

    # Unknown type detected
    _bad_type = {"test": {"T": {"order": 1, "party": [
        {"name": "Fakemon", "types": ["Fire", "FakeType"], "level": 10, "moves": ["Tackle"]}
    ]}}}
    bad_issues = validate_trainer_data(_bad_type)
    if any("FakeType" in i for i in bad_issues):
        ok("validate_trainer_data: unknown type flagged")
    else:
        fail("validate_trainer_data bad type", str(bad_issues))

    # Empty party detected
    _empty_party = {"test": {"T": {"order": 1, "party": []}}}
    ep_issues = validate_trainer_data(_empty_party)
    if any("empty party" in i for i in ep_issues):
        ok("validate_trainer_data: empty party flagged")
    else:
        fail("validate_trainer_data empty party", str(ep_issues))

    # Invalid level detected
    _bad_level = {"test": {"T": {"order": 1, "party": [
        {"name": "X", "types": ["Fire"], "level": 0, "moves": ["Tackle"]}
    ]}}}
    lv_issues = validate_trainer_data(_bad_level)
    if any("invalid level" in i for i in lv_issues):
        ok("validate_trainer_data: invalid level flagged")
    else:
        fail("validate_trainer_data bad level", str(lv_issues))

    # Missing moves detected
    _no_moves = {"test": {"T": {"order": 1, "party": [
        {"name": "X", "types": ["Fire"], "level": 10, "moves": []}
    ]}}}
    mv_issues = validate_trainer_data(_no_moves)
    if any("moves" in i for i in mv_issues):
        ok("validate_trainer_data: missing moves flagged")
    else:
        fail("validate_trainer_data no moves", str(mv_issues))

    # Metadata key (_meta) is skipped
    _with_meta = {"_meta": {"version": 1}, "test": {"T": {"order": 1, "party": [
        {"name": "X", "types": ["Fire"], "level": 10, "moves": ["Tackle"]}
    ]}}}
    meta_issues = validate_trainer_data(_with_meta)
    if meta_issues == []:
        ok("validate_trainer_data: _meta key skipped cleanly")
    else:
        fail("validate_trainer_data meta", str(meta_issues))

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 22
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
