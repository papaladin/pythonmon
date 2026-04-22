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
  run_joint_team(team_ctx, game_ctx, ui)    joint optimisation (key J)
  main()                                    standalone
"""

import sys
import asyncio

try:
    import matchup_calculator as calc
    import pkm_cache as cache
    from feat_team_loader import team_slots, team_size
    from core_team import (team_offensive_gaps, team_defensive_gaps,
                           candidate_passes_filter, rank_candidates,
                           precompute_pokemon_data, team_fitness,
                           create_individual, crossover, mutate,
                           tournament_selection, run_ga)
    from core_evolution import is_pure_level_up_chain
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# -- helper function for pkm_ctx ---

def _build_pkm_ctx_from_cache(slug: str) -> dict | None:
    """Build a pkm_ctx dict from cache for use in batch team load."""
    import pkm_cache as cache
    data = cache.get_pokemon(slug)
    if not data or not data.get("forms"):
        return None
    form = data["forms"][0]
    types = form.get("types", [])
    if not types:
        return None
    return {
        "pokemon": slug,
        "variety_slug": form.get("variety_slug", slug),
        "form_name": form["name"],
        "types": types,
        "type1": types[0],
        "type2": types[1] if len(types) > 1 else "None",
        "species_gen": data.get("species_gen", 1),
        "form_gen": data.get("species_gen", 1),
        "base_stats": form.get("base_stats", {}),
        "abilities": form.get("abilities", []),
        "egg_groups": data.get("egg_groups", []),
        "evolution_chain_id": data.get("evolution_chain_id"),
    }



# ── Helper to filter Mega/Gigantamax forms ─────────────────────────────────────

def _is_mega_or_gmax(form_name: str) -> bool:
    """Return True if the form name indicates a Mega Evolution or Gigantamax form."""
    words = form_name.lower().split()
    return "mega" in words or "gigantamax" in words


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


async def fetch_needed_rosters(ui, relevant_types) -> int:
    """Ensure all relevant type rosters are in the local cache, showing progress in the UI."""
    import pkm_cache as cache
    needed = [t for t in sorted(relevant_types)
              if cache.get_type_roster(t) is None]
    total = len(needed)
    fetched = 0
    for i, t in enumerate(needed, 1):
        await ui.print_progress(f"  {i}/{total}  {t}...", end="\r", flush=True)
        cache.get_type_roster_or_fetch(t)
        fetched += 1
    if total > 0:
        await ui.print_progress("  Done.                          ")
    return fetched


async def build_suggestion_pool(team_ctx: list, game_ctx: dict,
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

    # ── Filter out Mega and Gigantamax forms entirely ─────────────────────────
    filtered_candidates_temp = []
    for c in candidates:
        if _is_mega_or_gmax(c["form_name"]):
            skipped_forms += 1
            continue
        filtered_candidates_temp.append(c)
    candidates = filtered_candidates_temp

    # ── Filter out lower‑stage pure level‑up evolutions ───────────────────────
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


async def _print_suggestion(ui, rank: int, result: dict, era_key: str,
                            all_scores: list) -> None:
    """Print one structured suggestion card."""
    name      = result["form_name"]
    types_str = " / ".join(result["types"])
    rating    = _dot_rating(result["score"], all_scores)
    dots      = _format_dots(rating)

    # Header line
    header = f"  {rank}. {name:<16} [{types_str}]"
    await ui.print_output(f"{header:<46}  {dots}")

    # Covers line
    if result.get("off_covered"):
        await ui.print_output(f"       ✓ Covers:  {'  '.join(result['off_covered'])}")

    # Resists line
    if result.get("def_covered"):
        await ui.print_output(f"       ✓ Resists: {'  '.join(result['def_covered'])}")

    # Weak-pair warning lines
    for pair_str in result.get("new_weak_pairs", []):
        await ui.print_output(f"       ✗ Adds pair: {pair_str}")

    # Lookahead line
    await ui.print_output(f"       {_format_lookahead(result.get('remaining_off_gaps', []), era_key)}")


async def display_team_builder(ui, team_ctx: list, game_ctx: dict,
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

    await ui.print_output(f"\n  Team builder  |  {game}")
    await ui.print_output(f"  Team: {summary}  ({filled}/6)")

    if filled < 3:
        await ui.print_output(f"  ⚠  Results are most meaningful with 2–3 Pokémon loaded."
                              f"  Add more via T.")

    # Gap summary
    await ui.print_output("")
    await ui.print_output("  Team gaps:")
    if off_gaps:
        await ui.print_output(f"    Offensive:  {'  '.join(off_gaps)}")
    else:
        await ui.print_output("    Offensive:  (none — full coverage)")
    if def_gaps:
        await ui.print_output(f"    Defensive:  {'  '.join(g + ' (critical)' for g in def_gaps)}")
    else:
        await ui.print_output("    Defensive:  (none — no critical gaps)")

    # Suggestions
    await ui.print_output("")
    await ui.print_output("  Top suggestions for the next slot:")
    await ui.print_output("  " + "═" * _BLOCK_SEP)

    if not results:
        await ui.print_output("  No matching Pokémon found for current gaps.")
    else:
        all_scores = [r["score"] for r in results]
        for i, result in enumerate(results, 1):
            if i > 1:
                await ui.print_output("")
            await _print_suggestion(ui, i, result, era_key, all_scores)

    await ui.print_output("  " + "═" * _BLOCK_SEP)

    if missing_rosters:
        await ui.print_output(f"\n  ⚠  Type data not yet cached for: {', '.join(missing_rosters)}")
        await ui.print_output("     Run with a network connection to fetch missing rosters.")


# ── Entry points ───────────────────────────────────────────────────────────────

async def run(team_ctx: list, game_ctx: dict, ui=None) -> None:
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
        from ui_dummy import DummyUI
        ui = DummyUI()

    from feat_team_loader import team_size as _team_size

    if _team_size(team_ctx) == 0:
        await ui.print_output("\n  Team is empty — load some Pokémon first (press T).")
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
            await ui.print_output(f"\n  Fetching {len(missing_before)} type roster(s)...")
            await fetch_needed_rosters(ui, relevant)

    # Build pool
    pool = await build_suggestion_pool(team_ctx, game_ctx, off_gaps, def_gaps)
    candidates = pool["candidates"]

    if not candidates:
        await ui.print_output("\n  No matching Pokémon found for current gaps.")
        if pool["missing_rosters"]:
            await ui.print_output(f"  Missing type data: {', '.join(pool['missing_rosters'])}")
        await ui.input_prompt("\n  Press Enter to continue...")
        return

    slots_remaining = 6 - team_size(team_ctx)
    results = rank_candidates(candidates, team_ctx, era_key,
                              off_gaps, def_gaps,
                              slots_remaining, top_n=6)

    await display_team_builder(ui, team_ctx, game_ctx, results,
                               off_gaps, def_gaps,
                               missing_rosters=pool["missing_rosters"] or None)

    await ui.input_prompt("\n  Press Enter to continue...")


# ──────────────────────────────────────────────────────────────────────────────
# Joint team optimisation (new)
# ──────────────────────────────────────────────────────────────────────────────

async def run_joint_team(team_ctx: list, game_ctx: dict, ui=None) -> None:
    if ui is None:
        from ui_dummy import DummyUI
        ui = DummyUI()

    if game_ctx is None:
        await ui.show_error("Select a game first (press G).")
        return

    # Locked slugs from current team (if any)
    locked_slugs = set()
    for slot in team_ctx:
        if slot is not None:
            locked_slugs.add(slot["pokemon"])

    if locked_slugs:
        await ui.print_output(f"\n  Locked Pokémon from team: {', '.join(locked_slugs)}")

    extra = await ui.input_prompt(
        "  Enter additional Pokémon to lock (comma‑separated, or Enter to continue): "
    )

    if extra.strip():
        index = cache.get_index()
        for name in extra.split(','):
            name = name.strip()
            if not name:
                continue
            from pkm_session import _index_search
            matches = _index_search(name, index)
            if matches:
                locked_slugs.add(matches[0])
            else:
                await ui.print_output(f"  Warning: '{name}' not found, skipping.")

    locked_slugs = frozenset(locked_slugs)

    if len(locked_slugs) > 6:
        await ui.show_error("Cannot lock more than 6 Pokémon.")
        return

    await ui.print_output("\n  Preparing candidate pool...")

    import asyncio

    # Helper to update progress from main thread
    def set_progress_main(percent: int, text: str):
        if hasattr(ui, "app"):
            ui.app.update_progress(percent, text)
        else:
            print(f"\r{text}", end="", flush=True)

    # Step 1: Build candidate pool in thread
    def build_candidate_pool():
        # This runs in thread; use call_from_thread for UI updates
        def update(percent, text):
            if hasattr(ui, "app"):
                ui.app.call_from_thread(ui.app.update_progress, percent, text)
        update(0, "Building candidate pool...")
        all_pokemon = []
        index = cache.get_index()
        slugs = list(index.keys())
        total = len(slugs)
        for i, slug in enumerate(slugs):
            if i % 20 == 0:
                percent = int((i / total) * 100)
                update(percent, f"Processing Pokémon {i}/{total}...")
            data = cache.get_pokemon(slug)
            if data and data.get("species_gen", 1) <= game_ctx["game_gen"]:
                pkm = _build_pkm_ctx_from_cache(slug)
                if pkm:
                    all_pokemon.append(pkm)
        update(100, "Filtering evolutions...")
        result = filter_pure_level_up_evolutions(all_pokemon, game_ctx["game_gen"])
        update(100, "Candidate pool ready.")
        return result

    loop = asyncio.get_event_loop()
    candidate_pool = await loop.run_in_executor(None, build_candidate_pool)
    # Clear progress bar from main thread
    if hasattr(ui, "app"):
        ui.app.update_progress(100, "")
        # Or clear: ui.app.update_progress(0, "")
    await ui.print_output(f"  Candidate pool size: {len(candidate_pool)}")

    candidate_slugs = [p["pokemon"] for p in candidate_pool]
    if len(candidate_slugs) < 6:
        await ui.show_error("Not enough Pokémon in pool.")
        return

    # Step 2: Precompute data (fast, can run in main thread or thread)
    await ui.print_output("  Precomputing Pokémon data...")
    # Precompute is CPU-bound but quick; run in thread to avoid any lag
    def precompute():
        return precompute_pokemon_data(candidate_pool, game_ctx["era_key"])
    precomputed = await loop.run_in_executor(None, precompute)
    await ui.print_output("  Precomputation complete.")

    # Step 3: Run GA in thread with progress
    await ui.print_output("  Running genetic algorithm...")
    set_progress_main(0, "GA starting...")

    def run_ga_thread():
        # We'll use a callback that calls call_from_thread
        def ga_progress(current, total, fitness):
            percent = int(current / total * 100)
            text = f"Gen {current}/{total} | best fitness {fitness:.1f}"
            if hasattr(ui, "app"):
                ui.app.call_from_thread(ui.app.update_progress, percent, text)
            else:
                print(f"\r{text}", end="", flush=True)
        return run_ga(
            candidate_slugs,
            locked_slugs,
            precomputed,
            game_ctx["era_key"],
            population_size=200,
            generations=200,
            mutation_rate=0.05,
            elitism_ratio=0.1,
            random_seed=None,
            progress_callback=ga_progress,
        )

    best_slugs, best_fitness = await loop.run_in_executor(None, run_ga_thread)
    if hasattr(ui, "app"):
        ui.app.update_progress(100, "")
    await ui.print_output(f"  GA complete. Best fitness: {best_fitness:.1f}")

    # Build team
    best_team = []
    for slug in best_slugs:
        pkm = next((p for p in candidate_pool if p["pokemon"] == slug), None)
        if pkm is None:
            pkm = _build_pkm_ctx_from_cache(slug)
        best_team.append(pkm)

    await display_joint_team_result(ui, best_team, best_fitness, game_ctx)

    # Ask user if they want to load this team
    load_choice = await ui.confirm("\n  Load this team into your current team slots?")
    if load_choice:
        # Clear existing team slots
        for i in range(len(team_ctx)):
            team_ctx[i] = None
        # Fill with new team (up to 6 slots)
        for i, pkm in enumerate(best_team[:6]):
            team_ctx[i] = pkm
        await ui.print_output("  Team loaded successfully.")
    else:
        await ui.print_output("  Team not loaded.")

    # In CLI mode, pause before returning; TUI handles via confirm modal
    if not hasattr(ui, "app"):
        await ui.input_prompt("\n  Press Enter to continue...")

#----------------------------------------------------------------------------------------------------------------

def filter_pure_level_up_evolutions(pokemon_list: list, game_gen: int) -> list:
    """
    Remove lower‑stage Pokémon that evolve purely by level‑up into a higher stage
    that is also in the candidate pool.
    """
    import pkm_cache as cache
    from core_evolution import is_pure_level_up_chain

    candidate_slugs = {p["pokemon"] for p in pokemon_list}
    slug_to_paths = {}

    for p in pokemon_list:
        slug = p["pokemon"]
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
    for p in pokemon_list:
        slug = p["pokemon"]
        paths = slug_to_paths.get(slug)
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

    return [p for p in pokemon_list if p["pokemon"] not in to_remove]


async def display_joint_team_result(ui, team: list, fitness: float, game_ctx: dict) -> None:
    """Show best team with per‑member cards and team coverage summary."""
    await ui.print_output(f"\n  Best team found (fitness: {fitness:.1f})")
    await ui.print_output("  " + "═" * _BLOCK_SEP)

    for i, pkm in enumerate(team, 1):
        types = " / ".join(pkm["types"])
        await ui.print_output(f"  {i}. {pkm['form_name']} [{types}]")
        # Optionally compute per‑member notes here.

    await ui.print_output("  " + "═" * _BLOCK_SEP)

    from core_team import build_offensive_coverage
    # Compute coverage from the team's types (no moves involved)
    coverage = build_offensive_coverage(
        [{"se_types": se_types_from_pokemon(pkm, game_ctx["era_key"])} for pkm in team],
        game_ctx["era_key"]
    )
    await ui.print_output(
        f"  Team coverage: {len(coverage['covered'])} / {coverage['total_types']} types hit SE"
    )
    if coverage.get("gaps"):
        await ui.print_output(f"  Gaps: {', '.join(coverage['gaps'])}")
    if coverage.get("overlap"):
        overlap_str = "  ".join(f"{t} ({n})" for t, n in coverage["overlap"])
        await ui.print_output(f"  Overlap: {overlap_str}")


def se_types_from_pokemon(pkm_ctx: dict, era_key: str) -> list:
    """Return types hit SE by this Pokémon's own types."""
    _, valid_types, _ = calc.CHARTS[era_key]
    se = []
    for def_type in valid_types:
        if calc.get_multiplier(era_key, pkm_ctx["type1"], def_type) >= 2.0:
            se.append(def_type)
        elif pkm_ctx["type2"] != "None" and calc.get_multiplier(era_key, pkm_ctx["type2"], def_type) >= 2.0:
            se.append(def_type)
    return se


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_builder.py — self-test\n")

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
    import io
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
        async def print_output(self, text):
            self.buf.write(text + "\n")
        async def input_prompt(self, prompt):
            return ""
        async def confirm(self, prompt):
            return False
    dummy = DummyUI()
    import asyncio
    asyncio.run(_print_suggestion(dummy, 1, fake_result, "era3", [80.0, 50.0, 30.0]))
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

    if "✗" not in out:
        ok("_print_suggestion: no ✗ line when new_weak_pairs is empty")
    else:
        fail("_print_suggestion no-pairs", out[:120])

    # ── display_team_builder (stdout capture) ─────────────────────────────────
    from feat_team_loader import new_team, add_to_team
    team_ctx = new_team()
    charizard = {"form_name": "Charizard", "type1": "Fire", "type2": "Flying"}
    team_ctx, _ = add_to_team(team_ctx, charizard)
    game_ctx_sv = {"era_key": "era3", "game_gen": 9, "game": "Scarlet / Violet"}

    buf2 = io.StringIO()
    dummy2 = DummyUI()
    dummy2.buf = buf2
    asyncio.run(display_team_builder(dummy2, team_ctx, game_ctx_sv,
                                     [fake_result], ["Normal"], [], []))
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
    asyncio.run(display_team_builder(dummy3, team3, game_ctx_sv,
                                     [fake_result], ["Normal"], [], []))
    out3 = dummy3.buf.getvalue()

    if "most meaningful" not in out3:
        ok("display_team_builder: small-team note absent for 3-member team")
    else:
        fail("display_team_builder 3-member no note", out3[:120])

    # Missing rosters note shown when list non-empty
    buf5 = io.StringIO()
    dummy5 = DummyUI()
    dummy5.buf = buf5
    asyncio.run(display_team_builder(dummy5, team_ctx, game_ctx_sv,
                                     [], ["Normal"], [], ["Dragon", "Ghost"]))
    out5 = dummy5.buf.getvalue()

    if "Dragon" in out5 and "Ghost" in out5 and "not yet cached" in out5:
        ok("display_team_builder: missing rosters note shown")
    else:
        fail("display_team_builder missing rosters", out5[:120])

    # ── Mega/Gigantamax filtering test ────────────────────────────────────────
    candidates_with_mega = [
        {"slug": "charizard-mega-x", "form_name": "Mega Charizard X", "types": ["Fire", "Dragon"]},
        {"slug": "charizard", "form_name": "Charizard", "types": ["Fire", "Flying"]},
    ]
    filtered = [c for c in candidates_with_mega if not _is_mega_or_gmax(c["form_name"])]
    if len(filtered) == 1 and filtered[0]["form_name"] == "Charizard":
        ok("Mega/Gigantamax filtering: Mega form removed")
    else:
        fail("Mega/Gigantamax filtering", f"got {[c['form_name'] for c in filtered]}")

    candidates_with_gmax = [
        {"slug": "charizard-gmax", "form_name": "Gigantamax Charizard", "types": ["Fire", "Flying"]},
        {"slug": "charizard", "form_name": "Charizard", "types": ["Fire", "Flying"]},
    ]
    filtered2 = [c for c in candidates_with_gmax if not _is_mega_or_gmax(c["form_name"])]
    if len(filtered2) == 1 and filtered2[0]["form_name"] == "Charizard":
        ok("Mega/Gigantamax filtering: Gigantamax form removed")
    else:
        fail("Mega/Gigantamax filtering gmax", f"got {[c['form_name'] for c in filtered2]}")

    # ── New tests for joint team optimisation helpers ─────────────────────────
    print("\n  --- Joint team optimisation helpers ---")

    # 1. _build_pkm_ctx_from_cache
    import tempfile
    import pkm_cache as cache
    import pkm_sqlite

    # Set up temporary cache
    orig_base = cache._BASE
    tmp_dir = tempfile.mkdtemp()
    cache._BASE = tmp_dir
    pkm_sqlite.set_base(tmp_dir)

    try:
        fake_data = {
            "pokemon": "charizard",
            "species_gen": 1,
            "egg_groups": ["monster", "dragon"],
            "evolution_chain_id": 1,
            "forms": [{
                "name": "Charizard",
                "variety_slug": "charizard",
                "types": ["Fire", "Flying"],
                "base_stats": {"hp": 78, "attack": 84, "defense": 78,
                               "special-attack": 109, "special-defense": 85, "speed": 100},
                "abilities": [{"slug": "blaze", "is_hidden": False}]
            }]
        }
        cache.save_pokemon("charizard", fake_data)

        pkm = _build_pkm_ctx_from_cache("charizard")
        expected_keys = {"pokemon", "variety_slug", "form_name", "types",
                         "type1", "type2", "species_gen", "form_gen",
                         "base_stats", "abilities", "egg_groups", "evolution_chain_id"}
        if pkm and expected_keys.issubset(pkm.keys()):
            ok("_build_pkm_ctx_from_cache: returns full pkm_ctx")
        else:
            fail("_build_pkm_ctx_from_cache", f"missing keys: {expected_keys - set(pkm.keys()) if pkm else 'None'}")

        if pkm and pkm["type1"] == "Fire" and pkm["type2"] == "Flying":
            ok("_build_pkm_ctx_from_cache: types correct")
        else:
            fail("_build_pkm_ctx_from_cache types", str(pkm))

        # Cache miss
        pkm_miss = _build_pkm_ctx_from_cache("pikachu")
        if pkm_miss is None:
            ok("_build_pkm_ctx_from_cache: cache miss → None")
        else:
            fail("_build_pkm_ctx_from_cache miss", str(pkm_miss))

    finally:
        # Restore original cache
        cache._BASE = orig_base
        pkm_sqlite.set_base(orig_base)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 2. se_types_from_pokemon
    charizard_ctx = {
        "type1": "Fire",
        "type2": "Flying",
        "types": ["Fire", "Flying"]
    }
    se = se_types_from_pokemon(charizard_ctx, "era3")
    # Fire hits Grass, Ice, Bug, Steel; Flying hits Fighting, Bug, Grass
    expected_se = {"Grass", "Ice", "Bug", "Steel", "Fighting"}
    if expected_se.issubset(set(se)):
        ok("se_types_from_pokemon: Charizard hits expected SE types")
    else:
        fail("se_types_from_pokemon", f"got {se}")

    # Single-type
    blastoise_ctx = {"type1": "Water", "type2": "None", "types": ["Water"]}
    se_water = se_types_from_pokemon(blastoise_ctx, "era3")
    if "Fire" in se_water and "Ground" in se_water and "Rock" in se_water:
        ok("se_types_from_pokemon: Blastoise SE types correct")
    else:
        fail("se_types_from_pokemon Blastoise", str(se_water))

    # 3. filter_pure_level_up_evolutions (requires evolution chain cache)
    # Mock the cache to return a pure level-up chain for Charmander->Charmeleon->Charizard
    # and a non-pure chain for Horsea->Seadra->Kingdra (trade item)
    import tempfile
    import pkm_cache as cache
    import pkm_sqlite

    tmp_dir2 = tempfile.mkdtemp()
    cache._BASE = tmp_dir2
    pkm_sqlite.set_base(tmp_dir2)

    try:
        # Mock Pokémon data for three stages
        charmander_data = {
            "pokemon": "charmander",
            "species_gen": 1,
            "egg_groups": ["monster", "dragon"],
            "evolution_chain_id": 2,
            "forms": [{"name": "Charmander", "variety_slug": "charmander", "types": ["Fire"]}]
        }
        charmeleon_data = {
            "pokemon": "charmeleon",
            "species_gen": 1,
            "egg_groups": ["monster", "dragon"],
            "evolution_chain_id": 2,
            "forms": [{"name": "Charmeleon", "variety_slug": "charmeleon", "types": ["Fire"]}]
        }
        charizard_data = {
            "pokemon": "charizard",
            "species_gen": 1,
            "egg_groups": ["monster", "dragon"],
            "evolution_chain_id": 2,
            "forms": [{"name": "Charizard", "variety_slug": "charizard", "types": ["Fire", "Flying"]}]
        }
        cache.save_pokemon("charmander", charmander_data)
        cache.save_pokemon("charmeleon", charmeleon_data)
        cache.save_pokemon("charizard", charizard_data)

        # Mock evolution chain (pure level-up)
        chain_pure = [
            [{"slug": "charmander", "trigger": ""},
             {"slug": "charmeleon", "trigger": "Level 16"},
             {"slug": "charizard", "trigger": "Level 36"}]
        ]
        cache.save_evolution_chain(2, chain_pure)

        # Create candidate pool with all three
        pool = [
            _build_pkm_ctx_from_cache("charmander"),
            _build_pkm_ctx_from_cache("charmeleon"),
            _build_pkm_ctx_from_cache("charizard")
        ]
        filtered = filter_pure_level_up_evolutions(pool, 9)
        filtered_slugs = [p["pokemon"] for p in filtered]
        # Only the highest stage should remain
        if filtered_slugs == ["charizard"]:
            ok("filter_pure_level_up_evolutions: pure chain keeps only final stage")
        else:
            fail("filter_pure_level_up_evolutions pure chain", str(filtered_slugs))

        # Mixed chain: Horsea (pure level-up to Seadra) -> Kingdra (trade item)
        # Mock Pokémon data
        horsea_data = {
            "pokemon": "horsea",
            "species_gen": 1,
            "egg_groups": ["water1", "dragon"],
            "evolution_chain_id": 3,
            "forms": [{"name": "Horsea", "variety_slug": "horsea", "types": ["Water"]}]
        }
        seadra_data = {
            "pokemon": "seadra",
            "species_gen": 1,
            "egg_groups": ["water1", "dragon"],
            "evolution_chain_id": 3,
            "forms": [{"name": "Seadra", "variety_slug": "seadra", "types": ["Water"]}]
        }
        kingdra_data = {
            "pokemon": "kingdra",
            "species_gen": 2,
            "egg_groups": ["water1", "dragon"],
            "evolution_chain_id": 3,
            "forms": [{"name": "Kingdra", "variety_slug": "kingdra", "types": ["Water", "Dragon"]}]
        }
        cache.save_pokemon("horsea", horsea_data)
        cache.save_pokemon("seadra", seadra_data)
        cache.save_pokemon("kingdra", kingdra_data)

        chain_mixed = [
            [{"slug": "horsea", "trigger": ""},
             {"slug": "seadra", "trigger": "Level 32"},
             {"slug": "kingdra", "trigger": "Trade holding Dragon Scale"}]
        ]
        cache.save_evolution_chain(3, chain_mixed)

        pool2 = [
            _build_pkm_ctx_from_cache("horsea"),
            _build_pkm_ctx_from_cache("seadra"),
            _build_pkm_ctx_from_cache("kingdra")
        ]
        filtered2 = filter_pure_level_up_evolutions(pool2, 9)
        filtered2_slugs = [p["pokemon"] for p in filtered2]
        # Seadra evolves to Kingdra via trade, so Seadra and Kingdra should both remain
        # Horsea is pure level-up to Seadra, so Horsea should be filtered out
        if set(filtered2_slugs) == {"seadra", "kingdra"}:
            ok("filter_pure_level_up_evolutions: mixed chain keeps both Seadra and Kingdra, removes Horsea")
        else:
            fail("filter_pure_level_up_evolutions mixed chain", str(filtered2_slugs))

    finally:
        cache._BASE = orig_base
        pkm_sqlite.set_base(orig_base)
        import shutil
        shutil.rmtree(tmp_dir2, ignore_errors=True)

    # 4. Smoke test for run_joint_team (mocked)
    # We'll mock cache, run_ga, etc. to ensure it doesn't crash.
    print("\n  --- run_joint_team smoke test ---")
    from unittest.mock import patch, AsyncMock, MagicMock
    import asyncio

    class MockUI:
        def __init__(self):
            self.output = []
            self.app = MagicMock()
            self.app.call_from_thread = MagicMock()
            self.app.update_progress = MagicMock()
            self.app.clear_progress = MagicMock()
        async def print_output(self, text):
            self.output.append(text)
        async def input_prompt(self, prompt):
            return ""
        async def show_error(self, msg):
            self.output.append(f"ERROR: {msg}")
        async def confirm(self, prompt):
            return False

    mock_ui = MockUI()
    mock_game_ctx = {"era_key": "era3", "game_gen": 9, "game": "Scarlet / Violet"}

    # Mock dependencies
    with patch('feat_team_builder.cache') as mock_cache, \
         patch('feat_team_builder.run_ga') as mock_run_ga, \
         patch('feat_team_builder.precompute_pokemon_data') as mock_precomp, \
         patch('feat_team_builder.filter_pure_level_up_evolutions') as mock_filter, \
         patch('feat_team_builder._build_pkm_ctx_from_cache') as mock_build:

        # Setup mock returns
        mock_cache.get_index.return_value = {"charizard": {}, "blastoise": {}}
        mock_cache.get_pokemon.return_value = {
            "species_gen": 1,
            "forms": [{"name": "Charizard", "variety_slug": "charizard", "types": ["Fire", "Flying"]}]
        }
        mock_build.return_value = {"pokemon": "charizard", "form_name": "Charizard", "types": ["Fire", "Flying"]}
        mock_filter.return_value = [mock_build.return_value] * 10  # 10 candidates
        mock_precomp.return_value = {"charizard": {"offensive_bitmask": 0, "defensive_bitmask": 0, "total_stats": 534, "role": "special"}}
        mock_run_ga.return_value = (frozenset(["charizard"] * 6), 95.0)

        # Also mock the team_ctx
        team_ctx = [None] * 6  # empty team

        # Run the function
        try:
            asyncio.run(run_joint_team(team_ctx, mock_game_ctx, ui=mock_ui))
            ok("run_joint_team: completes without exception")
        except Exception as e:
            fail("run_joint_team smoke test", str(e))

    print()
    total = 13 + 8  # original 13 + 8 new tests (adjust as needed)
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