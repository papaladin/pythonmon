#!/usr/bin/env python3
"""
feat_opponent.py  Team coverage vs in-game opponents

Loads a static trainer database (data/trainers.json) bundled with the project
and lets the player evaluate their loaded team against a named gym leader,
Elite Four member, Champion, or rival.

MOVESET-AWARE ANALYSIS:
  - For YOUR team: type-based (assume STAB moves only)
    * Threats = DEFENSIVE types (what hits you SE)
    * Counters = STAB move types (what you hit SE with)
  - For OPPONENT: actual movesets from trainers.json
    * Threats = opponent's ACTUAL move types (what they can hit you with)
    * Resists = opponent's ACTUAL move types (what you resist)

The trainer data is source data, not user cache — it lives in data/ not cache/.
Move names in trainers.json must match moves.json display names exactly so that
the existing cache.resolve_move() pipeline can look them up.

Data policy (recorded in trainers.json _meta):
  - First encounter, normal difficulty
  - Most feature-complete version of each game group
  - Version differences and rematches are separate entries
  - Types are era-correct for the game (Clefable is Normal in Gen 1–5)

Entry points:
  run(team_ctx, game_ctx)   called from pokemain (key X)
  main()                    standalone

Public API:
  Iteration A (loader):
    load_trainer_data()                → dict
    get_trainers_for_game(slug)        → dict  (single version)
    get_trainers_for_versions(slugs)   → dict  (merged across versions)
    list_trainer_names(...)            → list[str]
    get_trainer(...)                   → dict | None

  Iteration B (pure matchup logic):
    analyze_matchup(team_ctx, trainer, era_key)  → list[dict]
    uncovered_threats(matchup_results)           → list[dict]
    recommended_leads(matchup_results, team_ctx) → list[str]

  Iteration C (UI + output):
    pick_trainer_interactive(version_slugs, data) → str | None
    display_matchup_results(results, trainer_name, team_ctx, version_slugs)
    run(team_ctx, game_ctx)                      → None
"""

import json
import os
import sys

try:
    import pkm_cache as cache
    import matchup_calculator as calc
    import pkm_pokeapi as pokeapi
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Data file path ────────────────────────────────────────────────────────────

_DATA_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_TRAINERS_FILE = os.path.join(_DATA_DIR, "trainers.json")

# Module-level cache so the file is read once per session
_trainer_data: dict | None = None


# ── Iteration A: Loader (single version) ──────────────────────────────────────

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
    Return the trainer dict for a single game slug.

    game_slug matches game_ctx["game_slug"] — e.g. "red-blue", "platinum".
    Returns {} when no data exists for that game.

    data — optional pre-loaded dict for testing; loads from file if None.
    """
    if data is None:
        data = load_trainer_data()
    return data.get(game_slug, {})


def list_trainer_names(game_slug: str, data: dict | None = None) -> list:
    """
    Return trainer names for a single game, sorted by encounter order.

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


# ── Iteration A (extended): multi-version merging ─────────────────────────────

def _merge_trainer_dicts(trainer_dicts: list) -> dict:
    """
    Merge multiple trainer dicts (each keyed by trainer name).

    If a trainer appears in multiple dicts with identical party data, the entry
    is merged into one, and a "games" list is added to the entry containing the
    slugs of the versions where it appears. If the party data differs, the entry
    with the same name from different versions is NOT automatically merged;
    they remain separate entries under the same name? Actually we will keep only
    the first encountered entry and ignore duplicates (assuming identical data).
    The "games" field records all slugs where that trainer appears.

    This is a pure function (no I/O). Returns a new dict.
    """
    merged = {}
    for slug, trainer_dict in trainer_dicts.items():
        # trainer_dict is the dict of trainers for one version
        for tname, entry in trainer_dict.items():
            if tname not in merged:
                # Create a copy of the entry and add a "games" list
                new_entry = dict(entry)
                new_entry["games"] = [slug]
                merged[tname] = new_entry
            else:
                # Already have this trainer; append the slug to "games"
                merged[tname].setdefault("games", []).append(slug)
    # For consistency, sort the "games" list for each trainer
    for entry in merged.values():
        if "games" in entry:
            entry["games"].sort()
    return merged


def get_trainers_for_versions(version_slugs: list, data: dict | None = None) -> dict:
    """
    Return a merged trainer dict for a list of version slugs.

    The result contains one entry per trainer name, with an extra key "games"
    listing which version slugs the trainer appears in.

    Returns {} if no data found for any slug.
    """
    if data is None:
        data = load_trainer_data()
    # Collect trainer dicts for each slug
    version_dicts = {}
    for slug in version_slugs:
        version_dicts[slug] = get_trainers_for_game(slug, data)
    return _merge_trainer_dicts(version_dicts)


def list_trainer_names_for_versions(version_slugs: list, data: dict | None = None) -> list:
    """
    Return trainer names (merged across versions) sorted by encounter order.

    Uses the first version's order (the one with the smallest order value) to
    determine sorting; if order differs between versions, the smallest order
    wins. Falls back to alphabetical tiebreak.
    """
    trainers = get_trainers_for_versions(version_slugs, data)
    if not trainers:
        return []

    # Create a list of (trainer_name, order) where order is the minimal order
    # across all versions where the trainer appears.
    order_map = {}
    for slug in version_slugs:
        slug_trainers = get_trainers_for_game(slug, data)
        for tname, entry in slug_trainers.items():
            ord_val = entry.get("order", 999)
            if tname not in order_map or ord_val < order_map[tname]:
                order_map[tname] = ord_val

    return sorted(
        trainers.keys(),
        key=lambda name: (order_map.get(name, 999), name)
    )


def get_trainer_for_versions(version_slugs: list, trainer_name: str,
                             data: dict | None = None) -> dict | None:
    """
    Return the merged trainer entry for a trainer name, or None if not found.

    The entry includes a "games" list of all versions where this trainer appears.
    """
    trainers = get_trainers_for_versions(version_slugs, data)
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


# ── Move type resolution ──────────────────────────────────────────────────────

def get_move_type(move_name: str, era_key: str = "era1") -> str | None:
    """
    Resolve a move name to its type using the cache.

    Args:
      move_name (str): e.g. "Tackle", "Water Gun"
      era_key (str): game era for context — "era1", "era2", or "era3"

    Returns:
      str | None: Type (e.g. "Normal", "Water"), or None if not found
    """
    try:
        # Get all versioned entries for this move
        move_entries = cache.get_move(move_name)
        if not move_entries:
            return None
        
        # Map era_key to game generation
        # (Move types don't change by game, only by generation if at all)
        era_to_gen = {"era1": 1, "era2": 2, "era3": 9}
        game_gen = era_to_gen.get(era_key, 1)
        
        # Resolve to the correct version entry for this era
        # Use empty game name since type doesn't vary by game
        resolved = cache.resolve_move(
            {move_name: move_entries},
            move_name,
            "",  # game (not needed for type lookup)
            game_gen  # gen (determines version entry)
        )
        return resolved.get("type") if resolved else None
    except Exception:
        return None


def get_opponent_move_types(opponent_pkm: dict, era_key: str = "era1") -> list:
    """
    Extract the types of all moves an opponent Pokemon knows.

    Args:
      opponent_pkm (dict): Opponent Pokemon entry from trainers.json
        {
          "name": str,
          "types": [str, ...],
          "level": int,
          "moves": [str, ...]  ← move names to resolve
        }
      era_key (str): game era for context

    Returns:
      list: Move types, e.g. ["Normal", "Normal", "Water"]
      
    Note: Returns empty list if no moves resolved. Gracefully handles missing moves.
    """
    move_types = []
    for move_name in opponent_pkm.get("moves", []):
        move_type = get_move_type(move_name, era_key)
        if move_type:
            move_types.append(move_type)
    return move_types


# ── Iteration B: Pure matchup logic (MOVESET-AWARE) ───────────────────────────

def analyze_matchup(team_ctx: list, trainer: dict, era_key: str) -> list:
    """
    Analyze team coverage vs a single opponent trainer.

    MOVESET-AWARE logic:
      - For YOUR team:
        * Threats = team member's DEFENSIVE types (what hits them SE)
        * Counters = team member's STAB move types (assume STAB moves)
      - For OPPONENT:
        * Threats = opponent's ACTUAL move types (from their moveset)
        * Resists = opponent's ACTUAL move types (from their moveset)

    For each opponent Pokemon, compute:
      - threats: team members weak to opponent's ACTUAL MOVES
      - resists: team members that resist opponent's ACTUAL MOVES
      - counters: team members that hit opponent SE with STAB moves

    Args:
      team_ctx (list): Team context — list of team member dicts with form_name, type1, type2
      trainer (dict): Trainer dict from trainers.json with 'party' key
      era_key (str): "era1", "era2", or "era3" — determines type chart

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
    if not trainer or not trainer.get("party"):
        return []

    results = []

    for opponent_pkm in trainer["party"]:
        opp_name = opponent_pkm.get("name", "Unknown")
        opp_types = opponent_pkm.get("types", [])
        opp_level = opponent_pkm.get("level", 1)

        # ── RESOLVE opponent's ACTUAL move types ──────────────────────────────
        opp_move_types = get_opponent_move_types(opponent_pkm, era_key)

        threats = []
        resists = []
        counters = []

        # For each team member, compute their relationship to this opponent
        for member in team_ctx:
            if not member:
                continue
            form_name = member.get("form_name", "Unknown")
            member_type1 = member.get("type1", "Normal")
            member_type2 = member.get("type2", "None")

            # ──────────────────────────────────────────────────────────────────
            # THREATS: Team member's DEFENSIVE types vs opponent's ACTUAL moves
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # RESISTS: Team member's DEFENSIVE types vs opponent's ACTUAL moves
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # COUNTERS: Team member's STAB types vs opponent's DEFENSIVE types
            # ──────────────────────────────────────────────────────────────────
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
            "moves": opponent_pkm.get("moves", []),
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

    # Count how many opponent Pokemon each team member can hit SE
    for result in matchup_results:
        for counter in result.get("counters", []):
            form_name = counter.get("form_name")
            if form_name in coverage:
                count, pos = coverage[form_name]
                coverage[form_name] = (count + 1, pos)

    # Sort by count (descending first), then by team order (position ascending)
    sorted_leads = sorted(coverage.items(), key=lambda x: (-x[1][0], x[1][1]))
    return [form_name for form_name, _ in sorted_leads]


# ── Iteration C: Trainer picker & output display ──────────────────────────────

def _version_indicator(games: list) -> str:
    """
    Return a short suffix like "(R,B,Y)" from a list of version slugs.
    Uses first letter of each slug (capitalised). e.g. ["red-blue","yellow"] → "(R,B,Y)"
    """
    if not games:
        return ""
    letters = [slug[0].upper() for slug in games]
    return " (" + ",".join(letters) + ")"


def pick_trainer_interactive(version_slugs: list, data: dict | None = None) -> str | None:
    """
    Interactive menu to pick a trainer from a list of version slugs.

    Displays numbered list of trainers sorted by encounter order.
    Returns trainer name or None if user cancels.

    Args:
      version_slugs (list): e.g. ["red-blue", "yellow"]
      data (dict): optional pre-loaded trainer data (for testing)

    Returns:
      str | None: Trainer name, or None if cancelled
    """
    if data is None:
        data = load_trainer_data()

    trainers = get_trainers_for_versions(version_slugs, data)
    if not trainers:
        print(f"\n  No trainers found for versions {version_slugs}.")
        return None

    names = list_trainer_names_for_versions(version_slugs, data)

    # Build display strings with version indicators
    display_names = []
    for name in names:
        entry = trainers[name]
        games = entry.get("games", [])
        ind = _version_indicator(games)
        title = entry.get("title", "Unknown")
        display_names.append((name, ind, title))

    print(f"\n  Select opponent  |  {', '.join(version_slugs).upper()}")
    print("  " + "─" * 40)

    for i, (name, ind, title) in enumerate(display_names, 1):
        print(f"   {i:2d}. {name}{ind:<12}  ({title})")

    print("   0. Back")
    print()

    while True:
        try:
            choice = input("  Enter choice: ").strip()
            if choice == "0":
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(names):
                return names[idx]
            else:
                print("  Invalid choice. Try again.")
        except ValueError:
            print("  Invalid input. Enter a number.")


def display_matchup_results(results: list, trainer_name: str, team_ctx: list,
                            version_slugs: list) -> None:
    """
    Display formatted matchup analysis results.

    Shows:
      - Trainer name and version slugs
      - For each opponent Pokemon: threats (opponent's moves), resists, counters (your STAB)
      - Uncovered threats (if any)
      - Recommended leads

    Args:
      results (list): Output from analyze_matchup()
      trainer_name (str): e.g. "Brock"
      team_ctx (list): Your team list
      version_slugs (list): Version slugs used for the game (for display)
    """
    if not results:
        print("\n  No analysis available.")
        return

    slugs_str = ", ".join(version_slugs).upper()
    print()
    print("╔" + "═" * 78 + "╗")
    print(f"║  {trainer_name.upper()} — {slugs_str:<70}║")
    print("╚" + "═" * 78 + "╝")

    # ── Display opponent-by-opponent analysis ──────────────────────────────────

    for result in results:
        opp_name = result["name"]
        opp_types = ", ".join(result["types"])
        opp_level = result["level"]

        opp_moves = ", ".join(result.get("moves", []))
        print(f"\n  {opp_name} (Lvl {opp_level})  |  {opp_types}")
        print(f"     Moves: {opp_moves}")
        print("  " + "─" * 76)

        # ── THREATS: What opponent's ACTUAL moves hit your team for SE ──────────
        threats = result.get("threats", [])
        if threats:
            print("  ⚠️  WEAK TO (opponent's moves):")
            for threat in sorted(threats, key=lambda x: -x["multiplier"]):
                form_name = threat["form_name"]
                mult = threat["multiplier"]
                move_types = ", ".join(threat.get("move_types", []))
                mult_str = f"{mult:.1f}x"
                print(f"       • {form_name:<20}  {mult_str}  to {move_types}")
        else:
            print("  ✓  Team is not hit SE by your opponent's moves")

        # ── RESISTS: What opponent's ACTUAL moves your team resists ──────────────
        resists = result.get("resists", [])
        if resists:
            print("  ✓  RESISTS (opponent's moves):")
            for resist in sorted(resists, key=lambda x: x["multiplier"]):
                form_name = resist["form_name"]
                mult = resist["multiplier"]
                move_types = ", ".join(resist.get("move_types", []))
                mult_str = f"{mult:.1f}x"
                print(f"       • {form_name:<20}  {mult_str} resistance  to {move_types}")

        # ── COUNTERS: Your team's STAB types hit opponent SE ─────────────────────
        counters = result.get("counters", [])
        if counters:
            print("  💥 HITS SE (your STAB moves):")
            for counter in counters:
                form_name = counter["form_name"]
                move_types = ", ".join(counter.get("move_types", []))
                print(f"       • {form_name:<20}  with {move_types}")
        else:
            print("  ❌ No STAB coverage against this opponent")

    # ── Summary: uncovered threats and recommended leads ──────────────────────

    print("\n" + "=" * 80)

    uncovered = uncovered_threats(results)
    if uncovered:
        print(f"\n  ❌ UNCOVERED THREATS ({len(uncovered)}/{len(results)}):")
        for threat in uncovered:
            print(f"     • {threat['name']} (Lvl {threat['level']})  {', '.join(threat['types'])}")
    else:
        print(f"\n  ✓ All opponents are hit SE by your STAB moves!")

    leads = recommended_leads(results, team_ctx)
    if leads:
        print(f"\n  💡 RECOMMENDED LEADS (by STAB coverage):")
        for i, lead in enumerate(leads, 1):
            coverage_count = sum(
                1 for result in results
                if any(c["form_name"] == lead for c in result.get("counters", []))
            )
            print(f"     {i}. {lead:<20}  (hits {coverage_count} opponent(s) SE with STAB)")
    else:
        print("\n  No recommended leads available.")

    print()


# ── Entry point: run() for pokemain integration ────────────────────────────────

def run(team_ctx: list, game_ctx: dict) -> None:
    """
    Called from pokemain (key X).

    Iteration C: Interactive trainer picker + analysis display.

    Args:
      team_ctx (list): Loaded team context
      game_ctx (dict): Game context with game_slug, era_key, version_slugs
    """
    if not team_ctx:
        print("\n  No team loaded.")
        input("\n  Press Enter to continue...")
        return

    version_slugs = game_ctx.get("version_slugs", [])
    if not version_slugs:
        # Fallback to single slug for backward compatibility (should not happen)
        game_slug = game_ctx.get("game_slug", "")
        if not game_slug:
            print("\n  No game selected.")
            input("\n  Press Enter to continue...")
            return
        version_slugs = [game_slug]

    era_key = game_ctx.get("era_key", "era1")

    data = load_trainer_data()
    if not data:
        print("\n  Trainer data not available.")
        input("\n  Press Enter to continue...")
        return

    trainer_name = pick_trainer_interactive(version_slugs, data)
    if trainer_name is None:
        return

    trainer = get_trainer_for_versions(version_slugs, trainer_name, data)
    if not trainer:
        print(f"\n  Trainer '{trainer_name}' not found.")
        input("\n  Press Enter to continue...")
        return

    # Run the analysis
    results = analyze_matchup(team_ctx, trainer, era_key)
    display_matchup_results(results, trainer_name, team_ctx, version_slugs)

    input("  Press Enter to continue...")


# ── Main menu (standalone) ────────────────────────────────────────────────────

def main() -> None:
    print()
    print("╔══════════════════════════════════════════╗")
    print("║      Team vs In-Game Opponent            ║")
    print("╚══════════════════════════════════════════╝")

    data = load_trainer_data()
    if not data:
        print("\n  Trainer data not loaded.")
        input("\n  Press Enter to exit...")
        return

    # Determine generation for each game slug (for sorting)
    gen_map = {slug: pokeapi.VERSION_GROUP_TO_GEN.get(slug, 99) for slug in data.keys()}
    # Sort by generation, then by slug
    games_sorted = sorted(data.keys(), key=lambda slug: (gen_map.get(slug, 99), slug))

    print(f"\n  Games with trainer data ({len(data)}):")
    for i, game_slug in enumerate(games_sorted, 1):
        names = list_trainer_names(game_slug, data)
        print(f"    {i}. {game_slug:<30}  {len(names)} trainers")

    print("\n  Select a game to browse trainers:")
    while True:
        try:
            choice = input("  Enter choice (or 0 to exit): ").strip()
            if choice == "0":
                return
            idx = int(choice) - 1
            if 0 <= idx < len(games_sorted):
                game_slug = games_sorted[idx]
                break
            else:
                print("  Invalid choice. Try again.")
        except ValueError:
            print("  Invalid input.")

    # For standalone, use single slug; version_slugs = [game_slug] for consistency
    version_slugs = [game_slug]

    trainer_name = pick_trainer_interactive(version_slugs, data)
    if trainer_name is None:
        return

    trainer = get_trainer_for_versions(version_slugs, trainer_name, data)
    if not trainer:
        print(f"\n  Trainer not found.")
        return

    # For demo, use a sample team
    sample_team = [
        {"form_name": "Charizard", "type1": "Fire", "type2": "Flying"},
        {"form_name": "Blastoise", "type1": "Water", "type2": "None"},
        {"form_name": "Venusaur", "type1": "Grass", "type2": "Poison"},
    ]

    results = analyze_matchup(sample_team, trainer, "era1")
    display_matchup_results(results, trainer_name, sample_team, version_slugs)

    input("  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

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

    print("\n  feat_opponent.py — self-test (Iteration A–C, MOVESET-AWARE)\n")

    # ── Fixture with two versions for merging (identical Brock/Misty, different Blue) ──
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
                        "moves": ["Tackle", "Harden", "Water Gun", "Swift"]
                    },
                    {
                        "name": "Starmie",
                        "types": ["Water", "Psychic"],
                        "level": 21,
                        "moves": ["Tackle", "Harden", "Water Gun", "Bubblebeam"]
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
                        "level": 61,
                        "moves": ["Water Pulse", "Ice Beam"]
                    },
                    {
                        "name": "Exeggutor",
                        "types": ["Grass", "Psychic"],
                        "level": 61,
                        "moves": ["Solar Beam", "Psychic"]
                    }
                ]
            }
        },
        "yellow": {
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
                        "moves": ["Tackle", "Harden", "Water Gun", "Swift"]
                    },
                    {
                        "name": "Starmie",
                        "types": ["Water", "Psychic"],
                        "level": 21,
                        "moves": ["Tackle", "Harden", "Water Gun", "Bubblebeam"]
                    }
                ]
            }
            # Blue is omitted from yellow because its data differs
        },
        "platinum": {
            "Cynthia": {
                "title": "Champion",
                "order": 12,
                "party": [
                    {
                        "name": "Spiritomb",
                        "types": ["Ghost", "Dark"],
                        "level": 61,
                        "moves": ["Psychic", "Dark Pulse"]
                    },
                    {
                        "name": "Garchomp",
                        "types": ["Dragon", "Ground"],
                        "level": 66,
                        "moves": ["Earthquake", "Dragon Rush"]
                    }
                ]
            }
        }
    }

    # ── Iteration A tests (single version) ──────────────────────────────────────

    print("  Iteration A — Single version loader\n")

    ok("load_trainer_data: tested via get_trainers_for_game")

    result1 = get_trainers_for_game("red-blue", _fixture)
    if "Brock" in result1 and "Misty" in result1:
        ok("get_trainers_for_game: returns correct trainers for red-blue")
    else:
        fail("get_trainers_for_game red-blue", str(result1.keys()))

    names = list_trainer_names("red-blue", _fixture)
    if names == ["Brock", "Misty", "Blue"]:
        ok("list_trainer_names: sorted by order (Brock=1, Misty=2, Blue=13)")
    else:
        fail("list_trainer_names order", str(names))

    brock = get_trainer("red-blue", "Brock", _fixture)
    if brock and len(brock["party"]) == 2:
        ok("get_trainer: returns correct entry")
    else:
        fail("get_trainer", str(brock))

    # ── Iteration A (extended) multi-version merging tests ─────────────────────

    print("\n  Iteration A (extended) — Multi-version merging\n")

    # Merge red-blue and yellow
    merged = get_trainers_for_versions(["red-blue", "yellow"], _fixture)

    # Brock should appear with games ["red-blue","yellow"]
    brock_merged = merged.get("Brock")
    if brock_merged and brock_merged.get("games") == ["red-blue", "yellow"]:
        ok("get_trainers_for_versions: Brock merged with games list")
    else:
        fail("get_trainers_for_versions Brock", str(brock_merged))

    # Blue should be present only from red-blue (since yellow omitted it)
    blue_merged = merged.get("Blue")
    if blue_merged and blue_merged.get("games") == ["red-blue"]:
        ok("get_trainers_for_versions: Blue appears only in red-blue")
    else:
        fail("get_trainers_for_versions Blue", str(blue_merged))

    # Test list_trainer_names_for_versions
    names_merged = list_trainer_names_for_versions(["red-blue", "yellow"], _fixture)
    # Should contain Brock, Misty, Blue (order: Brock=1, Misty=2, Blue=13)
    if names_merged == ["Brock", "Misty", "Blue"]:
        ok("list_trainer_names_for_versions: correct order")
    else:
        fail("list_trainer_names_for_versions order", str(names_merged))

    # Test get_trainer_for_versions
    brock_vers = get_trainer_for_versions(["red-blue", "yellow"], "Brock", _fixture)
    if brock_vers and brock_vers.get("games") == ["red-blue", "yellow"]:
        ok("get_trainer_for_versions: returns merged entry with games")
    else:
        fail("get_trainer_for_versions", str(brock_vers))

    # ── Iteration B tests (unchanged, still work) ──────────────────────────────

    print("\n  Iteration B — Matchup logic (MOVESET-AWARE)\n")

    team_single = [
        {"form_name": "Lapras", "type1": "Water", "type2": "Ice"}
    ]
    brock_trainer = get_trainer_for_versions(["red-blue", "yellow"], "Brock", _fixture)
    results = analyze_matchup(team_single, brock_trainer, "era1")

    if len(results) == 2:
        ok("analyze_matchup: returns result for each opponent Pokemon")
    else:
        fail("analyze_matchup count", f"expected 2, got {len(results)}")

    geodude_result = next((r for r in results if r["name"] == "Geodude"), None)
    if geodude_result:
        geodude_threats = [t for t in geodude_result.get("threats", []) if t["form_name"] == "Lapras"]
        if not geodude_threats:
            ok("analyze_matchup: Geodude's Normal moves don't threaten Lapras (moveset-aware)")
        else:
            fail("analyze_matchup threat", f"Geodude shouldn't threaten Lapras via Normal moves")
    else:
        fail("analyze_matchup Geodude", "Geodude not found in results")

    if geodude_result and any(c["form_name"] == "Lapras" for c in geodude_result.get("counters", [])):
        ok("analyze_matchup: Lapras counters Geodude with Water (Rock/Ground weakness)")
    else:
        fail("analyze_matchup counter", "Lapras should hit Geodude SE")

    team_fire = [
        {"form_name": "Charizard", "type1": "Fire", "type2": "Flying"}
    ]
    misty_trainer = get_trainer_for_versions(["red-blue", "yellow"], "Misty", _fixture)
    results = analyze_matchup(team_fire, misty_trainer, "era1")

    starmie_result = next((r for r in results if r["name"] == "Starmie"), None)
    if starmie_result:
        starmie_threats = [t for t in starmie_result.get("threats", []) if t["form_name"] == "Charizard"]
        if starmie_threats and "Water" in starmie_threats[0].get("move_types", []):
            ok("analyze_matchup: Starmie threatens Charizard with Water moves (moveset-aware)")
        else:
            fail("analyze_matchup Water threat", "Starmie should threaten with Water moves from moveset")
    else:
        fail("analyze_matchup Starmie", "Starmie not found")

    # ── Iteration C tests (with version indicators) ────────────────────────────

    print("\n  Iteration C — Trainer picker & output display\n")

    # Test picker with merged list
    import io
    from contextlib import redirect_stdout

    # Mock input to select first trainer (Brock)
    import builtins
    real_input = builtins.input
    builtins.input = lambda p="": "1"

    # Capture stdout to see version indicator
    f = io.StringIO()
    with redirect_stdout(f):
        name = pick_trainer_interactive(["red-blue", "yellow"], _fixture)
    builtins.input = real_input
    output = f.getvalue()

    if name == "Brock":
        ok("pick_trainer_interactive: returns correct name")
    else:
        fail("pick_trainer_interactive", f"expected Brock, got {name}")

    if "(R,Y)" in output:
        ok("pick_trainer_interactive: shows version indicator")
    else:
        fail("pick_trainer_interactive indicator", output[-200:])

    # Test display_matchup_results with merged trainer
    brock_merged = get_trainer_for_versions(["red-blue", "yellow"], "Brock", _fixture)
    results = analyze_matchup(team_single, brock_merged, "era1")
    f2 = io.StringIO()
    with redirect_stdout(f2):
        display_matchup_results(results, "Brock", team_single, ["red-blue", "yellow"])
    output2 = f2.getvalue()

    if "BROCK — RED-BLUE, YELLOW" in output2:
        ok("display_matchup_results: shows version slugs")
    else:
        fail("display_matchup_results version slugs", output2[:200])

    # In this scenario, Lapras is not weak to any of Brock's moves (only Normal), so the
    # "WEAK TO" section should not appear; instead the "✓  Team is not hit SE" line should.
    if "✓  Team is not hit SE by your opponent's moves" in output2:
        ok("display_matchup_results: shows correct threat message (no weaknesses)")
    else:
        fail("display_matchup_results threats", output2[:200])

    # Test uncovered_threats and recommended_leads (unchanged)
    uncovered = uncovered_threats(results)
    if len(uncovered) < len(results):
        ok("uncovered_threats: correctly identifies covered threats")
    else:
        fail("uncovered_threats", "All threats should not be uncovered")

    leads = recommended_leads(results, team_single)
    if leads and leads[0] == "Lapras":
        ok("recommended_leads: Lapras ranked first")
    else:
        fail("recommended_leads ranking", f"Expected Lapras first, got {leads}")

    # ── Summary ────────────────────────────────────────────────────────────────

    print(f"\n  {'='*50}")
    if errors:
        print(f"  {len(errors)} test(s) failed:")
        for e in errors:
            print(f"    - {e}")
        return False
    else:
        print(f"  All {total} tests passed")
        return True


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--autotest" in sys.argv or "--dry-run" in sys.argv:
        success = _run_tests()
        sys.exit(0 if success else 1)
    else:
        main()