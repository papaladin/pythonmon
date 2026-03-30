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
  run(team_ctx, game_ctx, ui=None)   called from pokemain (key X)
  main()                    standalone

Public API:
  Iteration A (loader):
    load_trainer_data()                → dict
    get_trainers_for_game(slug)        → dict  (single version)
    get_trainers_for_versions(slugs)   → dict  (merged across versions)
    list_trainer_names(...)            → list[str]
    get_trainer(...)                   → dict | None

  Iteration B (pure matchup logic) → now in core_opponent
  Iteration C (UI + output) remains here.
"""

import json
import os
import sys

try:
    import pkm_cache as cache
    import matchup_calculator as calc
    import pkm_pokeapi as pokeapi
    from core_opponent import analyze_matchup, uncovered_threats, recommended_leads
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
    """Load trainers.json from the data/ directory."""
    global _trainer_data
    if _trainer_data is not None:
        return _trainer_data
    try:
        with open(_TRAINERS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _trainer_data = {k: v for k, v in raw.items() if not k.startswith("_")}
        return _trainer_data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  Warning: trainer data file error: {e}")
        _trainer_data = {}
        return {}


def get_trainers_for_game(game_slug: str, data: dict | None = None) -> dict:
    """Return trainer dict for a single game slug."""
    if data is None:
        data = load_trainer_data()
    return data.get(game_slug, {})


def list_trainer_names(game_slug: str, data: dict | None = None) -> list:
    """Return trainer names for a single game, sorted by encounter order."""
    trainers = get_trainers_for_game(game_slug, data)
    return sorted(
        trainers.keys(),
        key=lambda name: (trainers[name].get("order", 999), name)
    )


def get_trainer(game_slug: str, trainer_name: str,
                data: dict | None = None) -> dict | None:
    """Return trainer entry for a specific game + name."""
    trainers = get_trainers_for_game(game_slug, data)
    return trainers.get(trainer_name)


# ── Iteration A (extended): multi-version merging ─────────────────────────────

def _merge_trainer_dicts(trainer_dicts: dict) -> dict:
    """Merge multiple trainer dicts (each keyed by trainer name)."""
    merged = {}
    for slug, trainer_dict in trainer_dicts.items():
        for tname, entry in trainer_dict.items():
            if tname not in merged:
                new_entry = dict(entry)
                new_entry["games"] = [slug]
                merged[tname] = new_entry
            else:
                merged[tname].setdefault("games", []).append(slug)
    for entry in merged.values():
        if "games" in entry:
            entry["games"].sort()
    return merged


def get_trainers_for_versions(version_slugs: list, data: dict | None = None) -> dict:
    """Return merged trainer dict for a list of version slugs."""
    if data is None:
        data = load_trainer_data()
    version_dicts = {}
    for slug in version_slugs:
        version_dicts[slug] = get_trainers_for_game(slug, data)
    return _merge_trainer_dicts(version_dicts)


def list_trainer_names_for_versions(version_slugs: list, data: dict | None = None) -> list:
    """Return trainer names (merged) sorted by encounter order."""
    trainers = get_trainers_for_versions(version_slugs, data)
    if not trainers:
        return []
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
    """Return merged trainer entry for a trainer name, or None."""
    trainers = get_trainers_for_versions(version_slugs, data)
    return trainers.get(trainer_name)


# ── Validation helpers ────────────────────────────────────────────────────────

def validate_trainer_data(data: dict) -> list:
    """Validate trainer data against known constraints."""
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


# ── Move type resolution (I/O) ────────────────────────────────────────────────

def get_move_type(move_name: str, era_key: str = "era1") -> str | None:
    """
    Resolve a move name to its type using the cache.
    """
    try:
        move_entries = cache.get_move(move_name)
        if not move_entries:
            return None
        era_to_gen = {"era1": 1, "era2": 2, "era3": 9}
        game_gen = era_to_gen.get(era_key, 1)
        resolved = cache.resolve_move(
            {move_name: move_entries},
            move_name,
            "",  # game (not needed for type lookup)
            game_gen
        )
        return resolved.get("type") if resolved else None
    except Exception:
        return None


def get_opponent_move_types(opponent_pkm: dict, era_key: str = "era1") -> list:
    """Extract the types of all moves an opponent Pokemon knows."""
    move_types = []
    for move_name in opponent_pkm.get("moves", []):
        move_type = get_move_type(move_name, era_key)
        if move_type:
            move_types.append(move_type)
    return move_types


# ── Iteration C: Trainer picker & output display ──────────────────────────────

def _version_indicator(games: list) -> str:
    """Return a short suffix like "(R,B,Y)" from a list of version slugs."""
    if not games:
        return ""
    letters = [slug[0].upper() for slug in games]
    return " (" + ",".join(letters) + ")"


async def pick_trainer_interactive(ui, version_slugs: list, data: dict | None = None) -> str | None:
    """Interactive menu to pick a trainer from a list of version slugs."""
    if data is None:
        data = load_trainer_data()
    trainers = get_trainers_for_versions(version_slugs, data)
    if not trainers:
        await ui.print_output(f"\n  No trainers found for versions {version_slugs}.")
        return None
    names = list_trainer_names_for_versions(version_slugs, data)

    display_names = []
    for name in names:
        entry = trainers[name]
        games = entry.get("games", [])
        ind = _version_indicator(games)
        title = entry.get("title", "Unknown")
        display_names.append((name, ind, title))

    await ui.print_output(f"\n  Select opponent  |  {', '.join(version_slugs).upper()}")
    await ui.print_output("  " + "─" * 40)
    for i, (name, ind, title) in enumerate(display_names, 1):
        await ui.print_output(f"   {i:2d}. {name}{ind:<12}  ({title})")
    await ui.print_output("   0. Back")
    await ui.print_output("")

    while True:
        try:
            choice = await ui.input_prompt("  Enter choice: ")
            if choice == "0":
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(names):
                return names[idx]
            else:
                await ui.print_output("  Invalid choice. Try again.")
        except ValueError:
            await ui.print_output("  Invalid input. Enter a number.")


async def display_matchup_results(ui, results: list, trainer_name: str, team_ctx: list,
                                  version_slugs: list) -> None:
    """Display formatted matchup analysis results."""
    if not results:
        await ui.print_output("\n  No analysis available.")
        return

    slugs_str = ", ".join(version_slugs).upper()
    await ui.print_output("")
    await ui.print_output("╔" + "═" * 78 + "╗")
    await ui.print_output(f"║  {trainer_name.upper()} — {slugs_str:<70}║")
    await ui.print_output("╚" + "═" * 78 + "╝")

    for result in results:
        opp_name = result["name"]
        opp_types = ", ".join(result["types"])
        opp_level = result["level"]
        opp_moves = ", ".join(result.get("moves", [])) if "moves" in result else ""

        await ui.print_output(f"\n  {opp_name} (Lvl {opp_level})  |  {opp_types}")
        if opp_moves:
            await ui.print_output(f"     Moves: {opp_moves}")
        await ui.print_output("  " + "─" * 76)

        threats = result.get("threats", [])
        if threats:
            await ui.print_output("  ⚠️  WEAK TO (opponent's moves):")
            for threat in sorted(threats, key=lambda x: -x["multiplier"]):
                form_name = threat["form_name"]
                mult = threat["multiplier"]
                move_types = ", ".join(threat.get("move_types", []))
                mult_str = f"{mult:.1f}x"
                await ui.print_output(f"       • {form_name:<20}  {mult_str}  to {move_types}")
        else:
            await ui.print_output("  ✓  Team is not hit SE by your opponent's moves")

        resists = result.get("resists", [])
        if resists:
            await ui.print_output("  ✓  RESISTS (opponent's moves):")
            for resist in sorted(resists, key=lambda x: x["multiplier"]):
                form_name = resist["form_name"]
                mult = resist["multiplier"]
                move_types = ", ".join(resist.get("move_types", []))
                mult_str = f"{mult:.1f}x"
                await ui.print_output(f"       • {form_name:<20}  {mult_str} resistance  to {move_types}")

        counters = result.get("counters", [])
        if counters:
            await ui.print_output("  💥 HITS SE (your STAB moves):")
            for counter in counters:
                form_name = counter["form_name"]
                move_types = ", ".join(counter.get("move_types", []))
                await ui.print_output(f"       • {form_name:<20}  with {move_types}")
        else:
            await ui.print_output("  ❌ No STAB coverage against this opponent")

    await ui.print_output("")
    await ui.print_output("=" * 80)

    uncovered = uncovered_threats(results)
    if uncovered:
        await ui.print_output(f"\n  ❌ UNCOVERED THREATS ({len(uncovered)}/{len(results)}):")
        for threat in uncovered:
            await ui.print_output(f"     • {threat['name']} (Lvl {threat['level']})  {', '.join(threat['types'])}")
    else:
        await ui.print_output(f"\n  ✓ All opponents are hit SE by your STAB moves!")

    leads = recommended_leads(results, team_ctx)
    if leads:
        await ui.print_output(f"\n  💡 RECOMMENDED LEADS (by STAB coverage):")
        for i, lead in enumerate(leads, 1):
            coverage_count = sum(
                1 for result in results
                if any(c["form_name"] == lead for c in result.get("counters", []))
            )
            await ui.print_output(f"     {i}. {lead:<20}  (hits {coverage_count} opponent(s) SE with STAB)")
    else:
        await ui.print_output("\n  No recommended leads available.")

    await ui.print_output("")


# ── Entry point: run() for pokemain integration ────────────────────────────────

async def run(team_ctx: list, game_ctx: dict, ui=None) -> None:
    """
    Called from pokemain (key X).

    Interactive trainer picker + analysis display.
    """
    if ui is None:
        # Fallback dummy UI for standalone
        from ui_dummy import DummyUI
        ui = DummyUI()

    if not team_ctx:
        await ui.print_output("\n  No team loaded.")
        await ui.input_prompt("\n  Press Enter to continue...")
        return

    version_slugs = game_ctx.get("version_slugs", [])
    if not version_slugs:
        game_slug = game_ctx.get("game_slug", "")
        if not game_slug:
            await ui.print_output("\n  No game selected.")
            await ui.input_prompt("\n  Press Enter to continue...")
            return
        version_slugs = [game_slug]

    era_key = game_ctx.get("era_key", "era1")

    data = load_trainer_data()
    if not data:
        await ui.print_output("\n  Trainer data not available.")
        await ui.input_prompt("\n  Press Enter to continue...")
        return

    trainer_name = await pick_trainer_interactive(ui, version_slugs, data)
    if trainer_name is None:
        return

    trainer = get_trainer_for_versions(version_slugs, trainer_name, data)
    if not trainer:
        await ui.print_output(f"\n  Trainer '{trainer_name}' not found.")
        await ui.input_prompt("\n  Press Enter to continue...")
        return

    # Build opponent_team list with resolved move types
    opponent_team = []
    for pkm in trainer["party"]:
        opp_move_types = get_opponent_move_types(pkm, era_key)
        opponent_team.append({
            "name": pkm.get("name", "Unknown"),
            "types": pkm.get("types", []),
            "level": pkm.get("level", 1),
            "move_types": opp_move_types,
        })

    # Run analysis using pure function from core_opponent
    results = analyze_matchup(team_ctx, opponent_team, era_key)

    # Display results (display function still here)
    await display_matchup_results(ui, results, trainer_name, team_ctx, version_slugs)

    await ui.input_prompt("  Press Enter to continue...")


# ── Main menu (standalone) ────────────────────────────────────────────────────

def main() -> None:
    import asyncio

    # Dummy UI for standalone
    from ui_dummy import DummyUI
    ui = DummyUI()

    asyncio.run(ui.print_output(""))
    asyncio.run(ui.print_output("╔══════════════════════════════════════════╗"))
    asyncio.run(ui.print_output("║      Team vs In-Game Opponent            ║"))
    asyncio.run(ui.print_output("╚══════════════════════════════════════════╝"))

    data = load_trainer_data()
    if not data:
        asyncio.run(ui.print_output("\n  Trainer data not loaded."))
        asyncio.run(ui.input_prompt("\n  Press Enter to exit..."))
        return

    # Determine generation for each game slug (for sorting)
    gen_map = {slug: pokeapi.VERSION_GROUP_TO_GEN.get(slug, 99) for slug in data.keys()}
    games_sorted = sorted(data.keys(), key=lambda slug: (gen_map.get(slug, 99), slug))

    asyncio.run(ui.print_output(f"\n  Games with trainer data ({len(data)}):"))
    for i, game_slug in enumerate(games_sorted, 1):
        names = list_trainer_names(game_slug, data)
        asyncio.run(ui.print_output(f"    {i}. {game_slug:<30}  {len(names)} trainers"))

    asyncio.run(ui.print_output("\n  Select a game to browse trainers:"))
    while True:
        try:
            choice = asyncio.run(ui.input_prompt("  Enter choice (or 0 to exit): "))
            if choice == "0":
                return
            idx = int(choice) - 1
            if 0 <= idx < len(games_sorted):
                game_slug = games_sorted[idx]
                break
            else:
                asyncio.run(ui.print_output("  Invalid choice. Try again."))
        except ValueError:
            asyncio.run(ui.print_output("  Invalid input."))

    version_slugs = [game_slug]
    trainer_name = asyncio.run(pick_trainer_interactive(ui, version_slugs, data))
    if trainer_name is None:
        return

    trainer = get_trainer_for_versions(version_slugs, trainer_name, data)
    if not trainer:
        asyncio.run(ui.print_output(f"\n  Trainer not found."))
        return

    # For demo, use a sample team
    sample_team = [
        {"form_name": "Charizard", "type1": "Fire", "type2": "Flying"},
        {"form_name": "Blastoise", "type1": "Water", "type2": "None"},
        {"form_name": "Venusaur", "type1": "Grass", "type2": "Poison"},
    ]

    # Build opponent_team for demo
    opponent_team = []
    for pkm in trainer["party"]:
        opp_move_types = get_opponent_move_types(pkm, "era1")
        opponent_team.append({
            "name": pkm.get("name", "Unknown"),
            "types": pkm.get("types", []),
            "level": pkm.get("level", 1),
            "move_types": opp_move_types,
        })

    results = analyze_matchup(sample_team, opponent_team, "era1")
    asyncio.run(display_matchup_results(ui, results, trainer_name, sample_team, version_slugs))
    asyncio.run(ui.input_prompt("  Press Enter to exit..."))


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import io, contextlib
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

    print("\n  feat_opponent.py — self-test (wrapper only)\n")

    # Simple tests for the wrapper functions (loading, merging, display)
    # Most logic is now in core_opponent.

    # Fixture
    _fixture = {
        "red-blue": {
            "Brock": {"title": "Rock", "order": 1, "party": []},
            "Misty": {"title": "Water", "order": 2, "party": []},
            "Blue": {"title": "Champion", "order": 13, "party": []}
        },
        "yellow": {
            "Brock": {"title": "Rock", "order": 1, "party": []},
            "Misty": {"title": "Water", "order": 2, "party": []}
        }
    }

    # Test get_trainers_for_versions
    merged = get_trainers_for_versions(["red-blue", "yellow"], _fixture)
    if "Brock" in merged and merged["Brock"].get("games") == ["red-blue", "yellow"]:
        ok("get_trainers_for_versions: Brock merged")
    else:
        fail("get_trainers_for_versions", str(merged.get("Brock")))

    # Test list_trainer_names_for_versions
    names = list_trainer_names_for_versions(["red-blue", "yellow"], _fixture)
    if names == ["Brock", "Misty", "Blue"]:
        ok("list_trainer_names_for_versions: correct order")
    else:
        fail("list_trainer_names_for_versions", str(names))

    # Test pick_trainer_interactive (mock input)
    import builtins
    real_input = builtins.input
    builtins.input = lambda p="": "1"
    # Create dummy UI for test
    class DummyUI:
        async def print_output(self, text): print(text)
        async def input_prompt(self, prompt): return builtins.input(prompt)
        async def confirm(self, prompt): return False
    dummy = DummyUI()
    import asyncio
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        name = asyncio.run(pick_trainer_interactive(dummy, ["red-blue", "yellow"], _fixture))
    builtins.input = real_input
    if name == "Brock":
        ok("pick_trainer_interactive: returns correct name")
    else:
        fail("pick_trainer_interactive", str(name))

    # Test display_matchup_results (smoke)
    results = [{"name": "Geodude", "types": ["Rock","Ground"], "level": 12,
                "threats": [], "resists": [], "counters": []}]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        asyncio.run(display_matchup_results(dummy, results, "Brock", [], ["red-blue"]))
    out = buf.getvalue()
    if "BROCK" in out and "Geodude" in out:
        ok("display_matchup_results: renders trainer and opponent")
    else:
        fail("display_matchup_results smoke", out[:200])

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
        main()