#!/usr/bin/env python3
"""
feat_team_builder.py  Team builder — slot suggestion

Suggests the best Pokémon to add to the next open team slot, based on
the current team's offensive coverage gaps and critical defensive gaps.

Accessible via menu key H (needs game + ≥1 team member).

Output for each suggestion: name, types, dot rating (●●●●●), offensive
gaps covered, defensive gaps resisted, new shared-weakness pairs introduced,
and a lookahead note showing what gaps would remain after the addition.

Public API:
  run(team_ctx, game_ctx, ui=None)          called from pokemain (key H)
  main()                                    standalone

All pure logic is now in core_team. This file retains only I/O and display.
"""

import sys

try:
    import matchup_calculator as calc
    from feat_team_loader import team_slots, team_size
    from core_team import (team_offensive_gaps, team_defensive_gaps,
                           candidate_passes_filter, patchability_score,
                           shared_weakness_count, new_weak_pairs,
                           score_candidate, rank_candidates)
    from core_evolution import is_pure_level_up_chain
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Generation range table (duplicated from other files, kept for pool builder) ──
_GEN_RANGES = [
    (151,  1), (251,  2), (386,  3), (493,  4), (649,  5),
    (721,  6), (809,  7), (905,  8), (1025, 9),
]

def _id_to_gen(pokemon_id: int) -> int | None:
    """Return generation for a national-dex / variety ID, or None."""
    if pokemon_id > 10000:
        return None
    for max_id, gen in _GEN_RANGES:
        if pokemon_id <= max_id:
            return gen
    return None


# ── Candidate pool builder ─────────────────────────────────────────────────────

def collect_relevant_types(off_gaps: list, def_gaps: list, era_key: str) -> set:
    """Return set of type names whose rosters should be searched."""
    _, valid_types, _ = calc.CHARTS[era_key]
    relevant = set()
    for gap in off_gaps:
        for t in valid_types:
            if calc.get_multiplier(era_key, t, gap) >= 2.0:
                relevant.add(t)
    for gap in def_gaps:
        for t in valid_types:
            if calc.get_multiplier(era_key, gap, t) <= 0.5:
                relevant.add(t)
    return relevant


def fetch_needed_rosters(relevant_types, progress_cb=None) -> int:
    """Ensure all relevant type rosters are in the local cache."""
    import pkm_cache as cache
    needed = [t for t in sorted(relevant_types)
              if cache.get_type_roster(t) is None]
    total = len(needed)
    fetched = 0
    for i, t in enumerate(needed, 1):
        if progress_cb:
            progress_cb(i, total, t)
        cache.get_type_roster_or_fetch(t)
        fetched += 1
    return fetched


def build_suggestion_pool(team_ctx: list, game_ctx: dict,
                         off_gaps: list, def_gaps: list) -> dict:
    """
    Build the filtered candidate list from cached type rosters.

    Reads cached type rosters for all types in collect_relevant_types().
    Does NOT fetch — call fetch_needed_rosters() first.

    Returns:
      {
        "candidates"     : list[dict],  # {slug, form_name, types, base_stats}
        "missing_rosters": list[str],   # relevant types with no cached roster
        "skipped_forms"  : int,         # alt forms skipped (id > 10000, not cached)
        "skipped_gen"    : int,         # slugs filtered by generation
        "skipped_team"   : int,         # slugs already on team
      }
    """
    import pkm_cache as cache

    era_key  = game_ctx["era_key"]
    game_gen = game_ctx["game_gen"]

    relevant = collect_relevant_types(off_gaps, def_gaps, era_key)

    # Team variety slugs to exclude
    team_slugs = {pkm["variety_slug"] for _, pkm in team_slots(team_ctx)}

    # Pass 1: scan all relevant type rosters; accumulate slug → {types, id}
    slug_info       = {}   # slug → {"types": set(), "id": int}
    missing_rosters = []

    for t in sorted(relevant):
        roster = cache.get_type_roster(t)
        if roster is None:
            missing_rosters.append(t)
            continue
        for entry in roster:
            slug = entry["slug"]
            id_  = entry.get("id", 0)
            if slug not in slug_info:
                slug_info[slug] = {"types": set(), "id": id_}
            slug_info[slug]["types"].add(t)

    # Pass 2: filter and build candidate dicts
    candidates    = []
    skipped_forms = 0
    skipped_gen   = 0
    skipped_team  = 0

    for slug, info in slug_info.items():
        id_ = info["id"]

        # Filter 1: unknown alternate form
        if id_ > 10000 and cache.get_pokemon(slug) is None:
            skipped_forms += 1
            continue

        # Filter 2: generation
        pkm_data = cache.get_pokemon(slug)
        if pkm_data:
            species_gen = pkm_data.get("species_gen")
        else:
            species_gen = _id_to_gen(id_)
        if species_gen is not None and species_gen > game_gen:
            skipped_gen += 1
            continue

        # Filter 3: already on team
        if slug in team_slugs:
            skipped_team += 1
            continue

        # Determine types + form info
        if pkm_data:
            forms = pkm_data.get("forms", [])
            # Prefer the form matching this variety slug
            match = next((f for f in forms if f.get("variety_slug") == slug),
                         forms[0] if forms else None)
            types      = match["types"]      if match else sorted(info["types"])
            base_stats = match.get("base_stats") if match else None
            form_name  = match["name"]       if match else slug.replace("-", " ").title()
        else:
            types      = sorted(info["types"])   # approximation from rosters
            base_stats = None
            form_name  = slug.replace("-", " ").title()

        if not types:
            continue

        # Filter 4: must be relevant to at least one gap
        if not candidate_passes_filter(types, off_gaps, def_gaps, era_key):
            continue

        candidates.append({
            "slug"      : slug,
            "form_name" : form_name,
            "types"     : types,
            "base_stats": base_stats,
        })

    # ── Filter out lower‑stage pure level‑up evolutions ───────────────────────
    # Build a set of candidate slugs for quick lookup
    candidate_slugs = {c["slug"] for c in candidates}

    # Build a map: slug -> evolution chain paths (only for slugs we have in cache)
    slug_to_paths = {}
    for c in candidates:
        slug = c["slug"]
        if slug in slug_to_paths:
            continue
        data = cache.get_pokemon(slug)
        if data is None:
            continue
        chain_id = data.get("evolution_chain_id")
        if chain_id is None:
            continue
        paths = cache.get_evolution_chain(chain_id)
        if paths is None:
            continue
        slug_to_paths[slug] = paths

    to_remove = set()
    for c in candidates:
        slug = c["slug"]
        paths = slug_to_paths.get(slug)
        if paths is None:
            continue
        # For each path, see if this slug appears and if there is a higher stage
        for path in paths:
            for i, stage in enumerate(path):
                if stage["slug"] == slug:
                    # Check higher stages (indices > i)
                    for j in range(i+1, len(path)):
                        higher_slug = path[j]["slug"]
                        if higher_slug in candidate_slugs:
                            # If the path to higher_slug is pure level‑up, we can remove this slug
                            if is_pure_level_up_chain(paths, higher_slug):
                                to_remove.add(slug)
                            break  # once we find a higher candidate, stop for this path
                    break  # slug found, no need to continue searching this path

    # Remove filtered slugs
    filtered_candidates = [c for c in candidates if c["slug"] not in to_remove]

    return {
        "candidates"     : filtered_candidates,
        "missing_rosters": missing_rosters,
        "skipped_forms"  : skipped_forms,
        "skipped_gen"    : skipped_gen,
        "skipped_team"   : skipped_team,
    }


# ── Display helpers ────────────────────────────────────────────────────────────

_FILLED = "●"
_EMPTY  = "○"
_BLOCK_SEP = 56


def _format_dots(rating: int) -> str:
    """Return a 5-character dot string for a 1–5 rating."""
    rating = max(1, min(5, rating))
    return _FILLED * rating + _EMPTY * (5 - rating)


def _dot_rating(score: float, all_scores: list) -> int:
    """
    Convert a score to a 1–5 dot rating based on its percentile within all_scores.
    """
    if len(all_scores) <= 1:
        return 5
    if len(set(all_scores)) == 1:
        return 3
    sorted_scores = sorted(all_scores, reverse=True)
    rank = sorted_scores.index(score)   # 0 = highest
    pct  = rank / len(sorted_scores)    # 0.0 = top, approaching 1.0 = bottom
    if pct < 0.2:  return 5
    if pct < 0.4:  return 4
    if pct < 0.6:  return 3
    if pct < 0.8:  return 2
    return 1


def _format_lookahead(remaining_off_gaps: list, era_key: str) -> str:
    """
    Format the "after adding this candidate" lookahead line.
    """
    if not remaining_off_gaps:
        return "→ After: full offensive coverage"

    _, valid_types, _ = calc.CHARTS[era_key]
    counts = []
    for gap in remaining_off_gaps:
        n = sum(1 for t in valid_types
                if calc.get_multiplier(era_key, t, gap) >= 2.0)
        counts.append(n)

    gap_str   = ", ".join(remaining_off_gaps)
    count_str = ", ".join(str(c) for c in counts)

    if len(remaining_off_gaps) == 1:
        return f"→ After: {gap_str} gap  ({count_str} types cover it)"
    return f"→ After: {gap_str} gaps  ({count_str} types cover each)"


def _print_suggestion(ui, rank: int, result: dict, era_key: str,
                      all_scores: list) -> None:
    """Print one structured suggestion card."""
    name      = result["form_name"]
    types_str = " / ".join(result["types"])
    rating    = _dot_rating(result["score"], all_scores)
    dots      = _format_dots(rating)

    # Header line
    header = f"  {rank}. {name:<16} [{types_str}]"
    ui.print_output(f"{header:<46}  {dots}")

    # Covers line
    if result.get("off_covered"):
        ui.print_output(f"       ✓ Covers:  {'  '.join(result['off_covered'])}")

    # Resists line
    if result.get("def_covered"):
        ui.print_output(f"       ✓ Resists: {'  '.join(result['def_covered'])}")

    # Weak-pair warning lines
    for pair_str in result.get("new_weak_pairs", []):
        ui.print_output(f"       ✗ Adds pair: {pair_str}")

    # Lookahead line
    ui.print_output(f"       {_format_lookahead(result.get('remaining_off_gaps', []), era_key)}")


def display_team_builder(ui, team_ctx: list, game_ctx: dict,
                         results: list, off_gaps: list, def_gaps: list,
                         missing_rosters: list = None) -> None:
    """
    Print the full team builder suggestion screen.
    """
    era_key  = game_ctx["era_key"]
    game     = game_ctx["game"]
    filled   = team_size(team_ctx)

    from feat_team_loader import team_summary_line
    summary = team_summary_line(team_ctx)

    ui.print_output(f"\n  Team builder  |  {game}")
    ui.print_output(f"  Team: {summary}  ({filled}/6)")

    if filled < 3:
        ui.print_output(f"  ⚠  Results are most meaningful with 2–3 Pokémon loaded."
                        f"  Add more via T.")

    # Gap summary
    ui.print_output("")
    ui.print_output("  Team gaps:")
    if off_gaps:
        ui.print_output(f"    Offensive:  {'  '.join(off_gaps)}")
    else:
        ui.print_output("    Offensive:  (none — full coverage)")
    if def_gaps:
        ui.print_output(f"    Defensive:  {'  '.join(g + ' (critical)' for g in def_gaps)}")
    else:
        ui.print_output("    Defensive:  (none — no critical gaps)")

    # Suggestions
    ui.print_output("")
    ui.print_output("  Top suggestions for the next slot:")
    ui.print_output("  " + "═" * _BLOCK_SEP)

    if not results:
        ui.print_output("  No matching Pokémon found for current gaps.")
    else:
        all_scores = [r["score"] for r in results]
        for i, result in enumerate(results, 1):
            if i > 1:
                ui.print_output("")
            _print_suggestion(ui, i, result, era_key, all_scores)

    ui.print_output("  " + "═" * _BLOCK_SEP)

    if missing_rosters:
        ui.print_output(f"\n  ⚠  Type data not yet cached for: {', '.join(missing_rosters)}")
        ui.print_output("     Run with a network connection to fetch missing rosters.")


# ── Entry points ───────────────────────────────────────────────────────────────

def run(team_ctx: list, game_ctx: dict, ui=None) -> None:
    """
    Full team builder pipeline. Called from pokemain (key H).

    1. Guard: empty team → message + return
    2. Compute offensive and defensive gaps
    3. Collect relevant type names
    4. Fetch any missing rosters (with per-type progress indicator)
    5. Build candidate pool from cached rosters
    6. If pool empty → message + return
    7. Rank top 6 candidates
    8. Display suggestion screen
    9. Wait for Enter
    """
    if ui is None:
        # Fallback dummy UI for standalone
        import builtins
        class DummyUI:
            def print_output(self, text): builtins.print(text)
            def print_progress(self, text, end="\n", flush=False): builtins.print(text, end=end, flush=flush)
            def input_prompt(self, prompt): return builtins.input(prompt)
            def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
        ui = DummyUI()

    from feat_team_loader import team_size as _team_size

    if _team_size(team_ctx) == 0:
        ui.print_output("\n  Team is empty — load some Pokémon first (press T).")
        return

    era_key = game_ctx["era_key"]

    off_gaps = team_offensive_gaps(team_ctx, era_key)
    def_gaps = team_defensive_gaps(team_ctx, era_key)

    relevant = collect_relevant_types(off_gaps, def_gaps, era_key)

    # Fetch missing rosters
    if relevant:
        import pkm_cache as cache
        missing_before = [t for t in sorted(relevant)
                          if cache.get_type_roster(t) is None]
        if missing_before:
            total = len(missing_before)
            ui.print_output(f"\n  Fetching {total} type roster(s)...")

            def _progress(cur, tot, tname):
                ui.print_progress(f"  {cur}/{tot}  {tname}...", end="\r", flush=True)

            fetch_needed_rosters(relevant, progress_cb=_progress)
            ui.print_progress(f"  Done.                          ")

    # Build pool
    pool = build_suggestion_pool(team_ctx, game_ctx, off_gaps, def_gaps)
    candidates = pool["candidates"]

    if not candidates:
        ui.print_output("\n  No matching Pokémon found for current gaps.")
        if pool["missing_rosters"]:
            ui.print_output(f"  Missing type data: {', '.join(pool['missing_rosters'])}")
        ui.input_prompt("\n  Press Enter to continue...")
        return

    slots_remaining = 6 - team_size(team_ctx)
    results = rank_candidates(candidates, team_ctx, era_key,
                              off_gaps, def_gaps,
                              slots_remaining, top_n=6)

    display_team_builder(ui, team_ctx, game_ctx, results,
                         off_gaps, def_gaps,
                         missing_rosters=pool["missing_rosters"] or None)

    ui.input_prompt("\n  Press Enter to continue...")


def main() -> None:
    # Dummy UI for standalone
    import builtins
    class DummyUI:
        def print_output(self, text): builtins.print(text)
        def print_progress(self, text, end="\n", flush=False): builtins.print(text, end=end, flush=flush)
        def input_prompt(self, prompt): return builtins.input(prompt)
        def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
    ui = DummyUI()

    ui.print_output("")
    ui.print_output("  This module is not usable standalone.")
    ui.print_output("  Launch from pokemain.py instead.")
    ui.print_output("")
    ui.input_prompt("  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_builder.py — self-test\n")

    # Most logic is now in core_team; we keep only display tests and pool builder tests.

    # ── _format_dots ──────────────────────────────────────────────────────────
    if _format_dots(5) == "●●●●●":
        ok("_format_dots: 5 → ●●●●●")
    else:
        fail("_format_dots 5", repr(_format_dots(5)))

    if _format_dots(3) == "●●●○○":
        ok("_format_dots: 3 → ●●●○○")
    else:
        fail("_format_dots 3", repr(_format_dots(3)))

    if _format_dots(1) == "●○○○○":
        ok("_format_dots: 1 → ●○○○○")
    else:
        fail("_format_dots 1", repr(_format_dots(1)))

    # ── _dot_rating ───────────────────────────────────────────────────────────
    if _dot_rating(100.0, [100.0]) == 5:
        ok("_dot_rating: single score → 5")
    else:
        fail("_dot_rating single", str(_dot_rating(100.0, [100.0])))

    scores5 = [100.0, 80.0, 60.0, 40.0, 20.0]
    if _dot_rating(100.0, scores5) == 5:
        ok("_dot_rating: top score in set of 5 → 5")
    else:
        fail("_dot_rating top", str(_dot_rating(100.0, scores5)))

    if _dot_rating(20.0, scores5) == 1:
        ok("_dot_rating: bottom score in set of 5 → 1")
    else:
        fail("_dot_rating bottom", str(_dot_rating(20.0, scores5)))

    if _dot_rating(60.0, scores5) == 3:
        ok("_dot_rating: middle score → 3")
    else:
        fail("_dot_rating middle", str(_dot_rating(60.0, scores5)))

    # ── _print_suggestion (stdout capture) ────────────────────────────────────
    import io, contextlib
    fake_result = {
        "form_name"         : "Garchomp",
        "types"             : ["Dragon", "Ground"],
        "score"             : 80.0,
        "off_covered"       : ["Normal", "Rock"],
        "def_covered"       : ["Electric"],
        "new_weak_pairs"    : [],
        "remaining_off_gaps": ["Dragon"],
    }

    class DummyUI:
        def __init__(self):
            self.buf = io.StringIO()
        def print_output(self, text):
            self.buf.write(text + "\n")
        def print_progress(self, text, end="\n", flush=False):
            self.buf.write(text + end)
        def input_prompt(self, prompt):
            return ""
        def confirm(self, prompt):
            return False
    dummy = DummyUI()
    _print_suggestion(dummy, 1, fake_result, "era3", [80.0, 50.0, 30.0])
    out = dummy.buf.getvalue()

    if "Garchomp" in out and "Dragon" in out and "Ground" in out:
        ok("_print_suggestion: name and types present")
    else:
        fail("_print_suggestion name/types", out[:80])

    if "✓ Covers" in out and "Normal" in out:
        ok("_print_suggestion: covers line present when off_covered non-empty")
    else:
        fail("_print_suggestion covers", out[:120])

    if "→ After" in out:
        ok("_print_suggestion: lookahead line present")
    else:
        fail("_print_suggestion lookahead", out[:120])

    # No ✗ line when new_weak_pairs is empty
    if "✗" not in out:
        ok("_print_suggestion: no ✗ line when new_weak_pairs is empty")
    else:
        fail("_print_suggestion no-pairs", out[:120])

    # ── display_team_builder (stdout capture) ─────────────────────────────────
    # 1-member team → small-team note shown
    from feat_team_loader import new_team, add_to_team
    team_ctx = new_team()
    charizard = {"form_name": "Charizard", "type1": "Fire", "type2": "Flying"}
    team_ctx, _ = add_to_team(team_ctx, charizard)
    game_ctx_sv = {"era_key": "era3", "game_gen": 9, "game": "Scarlet / Violet"}

    buf2 = io.StringIO()
    dummy2 = DummyUI()
    # Override print_output to capture
    dummy2.buf = buf2
    display_team_builder(dummy2, team_ctx, game_ctx_sv,
                         [fake_result], ["Normal"], [], [])
    out2 = dummy2.buf.getvalue()

    if "most meaningful with 2" in out2:
        ok("display_team_builder: small-team note shown for 1-member team")
    else:
        fail("display_team_builder small-team note", out2[:120])

    # 3-member team → no small-team note
    team3 = new_team()
    team3, _ = add_to_team(team3, charizard)
    team3, _ = add_to_team(team3, {"form_name": "Blastoise", "type1": "Water", "type2": "None"})
    team3, _ = add_to_team(team3, {"form_name": "Venusaur", "type1": "Grass", "type2": "Poison"})
    buf3 = io.StringIO()
    dummy3 = DummyUI()
    dummy3.buf = buf3
    display_team_builder(dummy3, team3, game_ctx_sv,
                         [fake_result], ["Normal"], [], [])
    out3 = dummy3.buf.getvalue()

    if "most meaningful" not in out3:
        ok("display_team_builder: small-team note absent for 3-member team")
    else:
        fail("display_team_builder 3-member no note", out3[:120])

    # Missing rosters note shown when list non-empty
    buf5 = io.StringIO()
    dummy5 = DummyUI()
    dummy5.buf = buf5
    display_team_builder(dummy5, team_ctx, game_ctx_sv,
                         [], ["Normal"], [], ["Dragon", "Ghost"])
    out5 = dummy5.buf.getvalue()

    if "Dragon" in out5 and "Ghost" in out5 and "not yet cached" in out5:
        ok("display_team_builder: missing rosters note shown")
    else:
        fail("display_team_builder missing rosters", out5[:120])

    # ── evolution filtering test ──────────────────────────────────────────────
    import pkm_cache as cache
    from core_evolution import is_pure_level_up_chain

    # Mock cache functions
    def _mock_get_pokemon(slug):
        if slug in ("dratini", "dragonair", "dragonite"):
            return {"evolution_chain_id": 123, "forms": [{"variety_slug": slug}]}
        return None

    def _mock_get_evolution_chain(chain_id):
        if chain_id == 123:
            return [[
                {"slug": "dratini", "trigger": ""},
                {"slug": "dragonair", "trigger": "Level 30"},
                {"slug": "dragonite", "trigger": "Level 55"}
            ]]
        return None

    orig_get_pokemon = cache.get_pokemon
    orig_get_chain = cache.get_evolution_chain
    cache.get_pokemon = _mock_get_pokemon
    cache.get_evolution_chain = _mock_get_evolution_chain

    # Simulate candidates
    candidates = [
        {"slug": "dratini", "form_name": "Dratini", "types": ["Dragon"]},
        {"slug": "dragonair", "form_name": "Dragonair", "types": ["Dragon"]},
        {"slug": "dragonite", "form_name": "Dragonite", "types": ["Dragon", "Flying"]},
    ]
    candidate_slugs = {c["slug"] for c in candidates}
    slug_to_paths = {c["slug"]: _mock_get_evolution_chain(123) for c in candidates}
    to_remove = set()
    for c in candidates:
        slug = c["slug"]
        paths = slug_to_paths[slug]
        if paths is None:
            continue
        for path in paths:
            for i, stage in enumerate(path):
                if stage["slug"] == slug:
                    for j in range(i+1, len(path)):
                        higher_slug = path[j]["slug"]
                        if higher_slug in candidate_slugs:
                            if is_pure_level_up_chain(paths, higher_slug):
                                to_remove.add(slug)
                            break
                    break
    filtered_slugs = [c["slug"] for c in candidates if c["slug"] not in to_remove]
    if filtered_slugs == ["dragonite"]:
        ok("evolution filtering: lower stages removed, only highest stage remains")
    else:
        fail("evolution filtering", f"got {filtered_slugs}")

    # Mixed chain: Seadra and Kingdra – both should remain because Kingdra not pure
    def _mock_get_pokemon2(slug):
        if slug in ("horsea", "seadra", "kingdra"):
            return {"evolution_chain_id": 124, "forms": [{"variety_slug": slug}]}
        return None
    def _mock_get_evolution_chain2(chain_id):
        if chain_id == 124:
            return [[
                {"slug": "horsea", "trigger": ""},
                {"slug": "seadra", "trigger": "Level 32"},
                {"slug": "kingdra", "trigger": "Trade holding Dragon Scale"}
            ]]
        return None

    cache.get_pokemon = _mock_get_pokemon2
    cache.get_evolution_chain = _mock_get_evolution_chain2

    candidates2 = [
        {"slug": "horsea", "form_name": "Horsea", "types": ["Water"]},
        {"slug": "seadra", "form_name": "Seadra", "types": ["Water"]},
        {"slug": "kingdra", "form_name": "Kingdra", "types": ["Water", "Dragon"]},
    ]
    candidate_slugs2 = {c["slug"] for c in candidates2}
    slug_to_paths2 = {c["slug"]: _mock_get_evolution_chain2(124) for c in candidates2}
    to_remove2 = set()
    for c in candidates2:
        slug = c["slug"]
        paths = slug_to_paths2[slug]
        if paths is None:
            continue
        for path in paths:
            for i, stage in enumerate(path):
                if stage["slug"] == slug:
                    for j in range(i+1, len(path)):
                        higher_slug = path[j]["slug"]
                        if higher_slug in candidate_slugs2:
                            if is_pure_level_up_chain(paths, higher_slug):
                                to_remove2.add(slug)
                            break
                    break
    filtered_slugs2 = [c["slug"] for c in candidates2 if c["slug"] not in to_remove2]
    if filtered_slugs2 == ["seadra", "kingdra"]:
        ok("evolution filtering: mixed chain keeps Seadra and Kingdra (Horsea removed as redundant)")
    else:
        fail("evolution filtering mixed", f"got {filtered_slugs2}")

    # Restore original functions
    cache.get_pokemon = orig_get_pokemon
    cache.get_evolution_chain = orig_get_chain

    print()
    total = 13  # original 11 + 2 new evolution tests
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