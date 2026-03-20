#!/usr/bin/env python3
"""
feat_team_builder.py  Team builder — slot suggestion

Suggests the best Pokémon to add to the next open team slot, based on
the current team's offensive coverage gaps and critical defensive gaps.

Accessible via menu key H (needs game + ≥1 team member).

Output for each suggestion: name, types, dot rating (●●●●●), offensive
gaps covered, defensive gaps resisted, new shared-weakness pairs introduced,
and a lookahead note showing what gaps would remain after the addition.

## Scoring formula

  intrinsic =   offensive_contribution  × 10
              + defensive_contribution  ×  8
              - shared_weakness_penalty ×  6
              + role_diversity_bonus    ×  4   (only when base_stats available)

  lookahead = patchability_after_addition
              / max(slots_remaining, 1)
              × (2 if slots_remaining ≤ 2 else 1)

  total_score = intrinsic + lookahead

Where:
  offensive_contribution  — off gap types hit SE by ≥1 candidate type
  defensive_contribution  — def gap types resisted/immune by candidate
  shared_weakness_penalty — existing members sharing ≥2 weaknesses w/ candidate
  role_diversity_bonus    — 1 if candidate role not already on team, else 0
  patchability_after      — patchability_score() of gaps remaining after adding

## Assumptions

ASSUMPTION (Option B): Scoring uses base_stats when the Pokémon is already in
the pokemon cache; type-only scoring otherwise. Upgradeable to full fetch
(Option C) by replacing `build_suggestion_pool`'s cache-only lookup with a
fetch call.

Public API:
  team_offensive_gaps(team_ctx, era_key)                   → list[str]
  team_defensive_gaps(team_ctx, era_key)                   → list[str]
  candidate_passes_filter(candidate_types, off_gaps,
                          def_gaps, era_key)               → bool
  patchability_score(remaining_off_gaps, era_key)          → float
  score_candidate(candidate_types, team_ctx, era_key,
                  off_gaps, def_gaps, slots_remaining,
                  base_stats=None)                         → float
  rank_candidates(candidates, team_ctx, era_key,
                  off_gaps, def_gaps, slots_remaining,
                  top_n=6)                                 → list[dict]

  collect_relevant_types(off_gaps, def_gaps, era_key)      → set[str]
  fetch_needed_rosters(relevant_types, progress_cb=None)   → int
  build_suggestion_pool(team_ctx, game_ctx,
                       off_gaps, def_gaps)                 → dict
"""

import sys

try:
    import matchup_calculator as calc
    from feat_team_loader import team_slots, team_size
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Scoring weights ────────────────────────────────────────────────────────────

_W_OFFENSIVE   = 10
_W_DEFENSIVE   =  8
_W_WEAK_PAIR   =  6
_W_ROLE        =  4
_LOOKAHEAD_END =  2   # multiplier applied when slots_remaining ≤ 2


# ── Gap analysis ───────────────────────────────────────────────────────────────

def team_offensive_gaps(team_ctx: list, era_key: str) -> list:
    """
    Return era types that no filled team member can hit SE using their own types.

    A type G is an offensive gap if no member has a type T where
    get_multiplier(era, T, G) >= 2.0.

    Empty team → all era types are gaps (nothing is covered).
    Returns sorted list of type strings.
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    slots = team_slots(team_ctx)

    if not slots:
        return sorted(valid_types)

    # Collect all types that the team can hit SE
    covered = set()
    for _, pkm in slots:
        for atk_type in [pkm["type1"]] + (
                [pkm["type2"]] if pkm["type2"] != "None" else []):
            for def_type in valid_types:
                if calc.get_multiplier(era_key, atk_type, def_type) >= 2.0:
                    covered.add(def_type)

    return sorted(t for t in valid_types if t not in covered)


def team_defensive_gaps(team_ctx: list, era_key: str) -> list:
    """
    Return types that are CRITICAL defensive gaps for the team.

    A type is critical when:
      - ≥2 team members are weak to it (multiplier > 1.0), AND
      - 0 team members resist or are immune to it (multiplier < 1.0)

    Single-member teams can never have a critical gap (threshold is 2).
    Returns sorted list of type strings.
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    slots = team_slots(team_ctx)
    gaps = []

    for atk_type in valid_types:
        weak_count   = 0
        cover_count  = 0
        for _, pkm in slots:
            defense = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
            m = defense.get(atk_type, 1.0)
            if m > 1.0:
                weak_count  += 1
            elif m < 1.0:
                cover_count += 1
        if weak_count >= 2 and cover_count == 0:
            gaps.append(atk_type)

    return sorted(gaps)


# ── Filter ─────────────────────────────────────────────────────────────────────

def candidate_passes_filter(candidate_types: list, off_gaps: list,
                             def_gaps: list, era_key: str) -> bool:
    """
    Return True if the candidate is relevant to the team's gaps.

    Passes if at least one candidate type:
      - hits ≥1 offensive gap type SE (get_multiplier ≥ 2.0), OR
      - resists or is immune to ≥1 critical defensive gap (get_multiplier ≤ 0.5)

    Always returns True when both off_gaps and def_gaps are empty (no gaps
    means any Pokémon could contribute).
    """
    if not off_gaps and not def_gaps:
        return True

    for ctype in candidate_types:
        for gap in off_gaps:
            if calc.get_multiplier(era_key, ctype, gap) >= 2.0:
                return True
        for gap in def_gaps:
            # gap_type attacking candidate_type: ≤0.5 means candidate resists/immune
            if calc.get_multiplier(era_key, gap, ctype) <= 0.5:
                return True

    return False


# ── Patchability ───────────────────────────────────────────────────────────────

def patchability_score(remaining_off_gaps: list, era_key: str) -> float:
    """
    Measure how easy the remaining offensive gaps are to fill.

    For each remaining gap type G: count era types T that hit G SE.
    Return the sum across all gaps. Higher = easier to patch remaining state.

    Empty gaps → 0.0 (no gaps left = perfect state, not "hard to patch").
    Normal gap → 1.0 (only Fighting hits Normal SE — hardest single gap).
    Water gap  → 2.0 (Electric + Grass hit Water SE).
    """
    if not remaining_off_gaps:
        return 0.0

    _, valid_types, _ = calc.CHARTS[era_key]
    total = 0.0
    for gap in remaining_off_gaps:
        count = sum(
            1 for t in valid_types
            if calc.get_multiplier(era_key, t, gap) >= 2.0
        )
        total += count
    return total


# ── Scoring ────────────────────────────────────────────────────────────────────

def _shared_weakness_count(candidate_types: list, team_ctx: list,
                            era_key: str) -> int:
    """
    Count existing team members that would share ≥2 weakness types with
    the candidate if added. Same logic as build_weakness_pairs but inline
    to avoid a cross-feature import at the same layer.
    """
    ctype1 = candidate_types[0]
    ctype2 = candidate_types[1] if len(candidate_types) > 1 else "None"
    cand_defense = calc.compute_defense(era_key, ctype1, ctype2)
    cand_weak = {t for t, m in cand_defense.items() if m > 1.0}

    count = 0
    for _, pkm in team_slots(team_ctx):
        member_defense = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
        member_weak = {t for t, m in member_defense.items() if m > 1.0}
        if len(cand_weak & member_weak) >= 2:
            count += 1
    return count


def _new_weak_pairs(candidate_types: list, team_ctx: list,
                    era_key: str) -> list:
    """
    Return human-readable strings describing new shared-weakness pairs.
    e.g. ["Charizard + Candidate share: Ice  Electric"]
    """
    ctype1 = candidate_types[0]
    ctype2 = candidate_types[1] if len(candidate_types) > 1 else "None"
    cand_defense = calc.compute_defense(era_key, ctype1, ctype2)
    cand_weak = {t for t, m in cand_defense.items() if m > 1.0}

    pairs = []
    for _, pkm in team_slots(team_ctx):
        member_defense = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
        member_weak = {t for t, m in member_defense.items() if m > 1.0}
        shared = sorted(cand_weak & member_weak)
        if len(shared) >= 2:
            pairs.append(f"{pkm['form_name']} shares: {'  '.join(shared)}")
    return pairs


def score_candidate(candidate_types: list, team_ctx: list, era_key: str,
                    off_gaps: list, def_gaps: list,
                    slots_remaining: int,
                    base_stats: dict = None) -> float:
    """
    Compute the composite score for a candidate Pokémon.

    candidate_types — list of 1–2 type strings  e.g. ["Dragon", "Ground"]
    team_ctx        — current team (used for shared-weakness + role checks)
    era_key         — "era1" | "era2" | "era3"
    off_gaps        — team's current offensive gap types
    def_gaps        — team's current critical defensive gap types
    slots_remaining — empty slots left after adding this candidate
    base_stats      — dict from pokemon cache, or None for type-only scoring

    Returns float. Higher is better.
    """
    # ── Offensive contribution ────────────────────────────────────────────────
    off_covered = [
        g for g in off_gaps
        if any(calc.get_multiplier(era_key, ct, g) >= 2.0
               for ct in candidate_types)
    ]
    offensive_contribution = len(off_covered)

    # ── Defensive contribution ────────────────────────────────────────────────
    def_covered = [
        g for g in def_gaps
        if any(calc.get_multiplier(era_key, g, ct) <= 0.5
               for ct in candidate_types)
    ]
    defensive_contribution = len(def_covered)

    # ── Shared weakness penalty ───────────────────────────────────────────────
    shared_penalty = _shared_weakness_count(candidate_types, team_ctx, era_key)

    # ── Role diversity bonus ──────────────────────────────────────────────────
    role_bonus = 0
    if base_stats and isinstance(base_stats, dict):
        try:
            from feat_stat_compare import infer_role
            candidate_role = infer_role(base_stats)
            team_roles = set()
            for _, pkm in team_slots(team_ctx):
                bs = pkm.get("base_stats", {})
                if bs:
                    team_roles.add(infer_role(bs))
            if candidate_role not in team_roles:
                role_bonus = 1
        except (ImportError, Exception):
            pass

    # ── Intrinsic score ───────────────────────────────────────────────────────
    intrinsic = (
        offensive_contribution  * _W_OFFENSIVE
        + defensive_contribution  * _W_DEFENSIVE
        - shared_penalty          * _W_WEAK_PAIR
        + role_bonus              * _W_ROLE
    )

    # ── Lookahead score ───────────────────────────────────────────────────────
    # Gaps that remain after hypothetically adding this candidate
    remaining_off_gaps = [g for g in off_gaps if g not in off_covered]
    patch = patchability_score(remaining_off_gaps, era_key)

    weight = _LOOKAHEAD_END if slots_remaining <= 2 else 1
    lookahead = patch / max(slots_remaining, 1) * weight

    return intrinsic + lookahead


def rank_candidates(candidates: list, team_ctx: list, era_key: str,
                    off_gaps: list, def_gaps: list,
                    slots_remaining: int,
                    top_n: int = 6) -> list:
    """
    Score all candidates and return the top_n sorted by score descending.

    Each candidate dict in:
      { slug, form_name, types, base_stats (or None) }

    Each result dict out:
      {
        slug, form_name, types, score,
        off_covered        — offensive gaps this candidate covers
        def_covered        — defensive gaps resisted/immune
        new_weak_pairs     — list of warning strings for shared weakness pairs
        remaining_off_gaps — offensive gaps still open after adding this
        role               — str or None
        speed_tier         — str or None
      }

    Returns [] when candidates is empty.
    """
    if not candidates:
        return []

    scored = []
    for c in candidates:
        ctypes     = c["types"]
        base_stats = c.get("base_stats")

        s = score_candidate(ctypes, team_ctx, era_key,
                            off_gaps, def_gaps,
                            slots_remaining, base_stats)

        # Build result annotation fields
        off_covered = [
            g for g in off_gaps
            if any(calc.get_multiplier(era_key, ct, g) >= 2.0
                   for ct in ctypes)
        ]
        def_covered = [
            g for g in def_gaps
            if any(calc.get_multiplier(era_key, g, ct) <= 0.5
                   for ct in ctypes)
        ]
        remaining   = [g for g in off_gaps if g not in off_covered]
        pairs       = _new_weak_pairs(ctypes, team_ctx, era_key)

        role       = None
        speed_tier = None
        if base_stats and isinstance(base_stats, dict):
            try:
                from feat_stat_compare import infer_role, infer_speed_tier
                role       = infer_role(base_stats)
                speed_tier = infer_speed_tier(base_stats)
            except (ImportError, Exception):
                pass

        scored.append({
            "slug"              : c["slug"],
            "form_name"         : c["form_name"],
            "types"             : ctypes,
            "score"             : s,
            "off_covered"       : off_covered,
            "def_covered"       : def_covered,
            "new_weak_pairs"    : pairs,
            "remaining_off_gaps": remaining,
            "role"              : role,
            "speed_tier"        : speed_tier,
        })

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_n]


# ── Candidate pool builder ─────────────────────────────────────────────────────

# Generation ranges — same table as feat_type_browser._id_to_gen.
# Defined locally to avoid cross-feature imports at the same layer.
_GEN_RANGES = [
    (151,  1), (251,  2), (386,  3), (493,  4), (649,  5),
    (721,  6), (809,  7), (905,  8), (1025, 9),
]


def _id_to_gen(pokemon_id: int) -> int | None:
    """
    Return the generation for a national-dex / variety ID, or None.

    IDs > 10000 are alternate forms (Mega, Gigantamax, regional) and always
    return None — the pokemon cache is consulted separately for those.
    IDs 1–1025 are mapped to gen 1–9 via boundary ranges.
    IDs beyond 1025 (hypothetical future entries) return None.
    """
    if pokemon_id > 10000:
        return None
    for max_id, gen in _GEN_RANGES:
        if pokemon_id <= max_id:
            return gen
    return None


def collect_relevant_types(off_gaps: list, def_gaps: list,
                            era_key: str) -> set:
    """
    Return the set of type names whose rosters should be searched.

    For each offensive gap G: include every era type T where
      get_multiplier(era, T, G) >= 2.0  (T can hit the gap SE)

    For each defensive gap D: include every era type T where
      get_multiplier(era, D, T) <= 0.5  (D has reduced effect on T —
      i.e. T resists or is immune to the attacking type D)

    Empty gaps → empty set.
    Overlap between off and def contributions is deduplicated automatically
    (set union).
    """
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
    """
    Ensure all relevant type rosters are in the local cache.

    For each type in relevant_types that is not already cached, fetches
    from PokeAPI via pkm_cache.get_type_roster_or_fetch().

    progress_cb — optional callable invoked before each fetch with
      (current: int, total: int, type_name: str)

    Returns the count of rosters actually fetched (0 if all already cached).
    """
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

    Filter order:
      1. Skip if id > 10000 AND not in pokemon cache (unknown alt form)
      2. Skip if species_gen > game_gen (use cache species_gen if available,
         else _id_to_gen(id), else assume valid — never over-filter)
      3. Skip if variety_slug already on team
      4. Apply candidate_passes_filter (must hit ≥1 off gap SE or resist
         ≥1 def gap)
    Step 5: for each survivor, read base_stats from cache if available.

    Type resolution:
      - Pokemon in cache: full types from the matching form entry
      - Pokemon not in cache: the subset of types that appeared in
        searched rosters (approximation; avoids API calls)

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

    return {
        "candidates"     : candidates,
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
    """
    Return a 5-character dot string for a 1–5 rating.
    e.g. 5 → "●●●●●", 3 → "●●●○○", 1 → "●○○○○"
    """
    rating = max(1, min(5, rating))
    return _FILLED * rating + _EMPTY * (5 - rating)


def _dot_rating(score: float, all_scores: list) -> int:
    """
    Convert a score to a 1–5 dot rating based on its percentile within
    all_scores.

    Percentile bands (higher = better):
      top 20%       → 5
      20% – 40%     → 4
      40% – 60%     → 3
      60% – 80%     → 2
      bottom 20%    → 1

    Single result → 5.
    All scores equal → 3.
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

    No remaining gaps  → "→ After: full offensive coverage"
    1 gap              → "→ After: Dragon gap  (3 types cover it)"
    2+ gaps            → "→ After: Dragon, Normal gaps  (3, 1 types cover each)"
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


def _print_suggestion(rank: int, result: dict, era_key: str,
                      all_scores: list) -> None:
    """
    Print one structured suggestion card.

    Format:
      1. Garchomp      [Dragon / Ground]   ●●●●●
         ✓ Covers: Normal  Rock  Electric
         ✓ Resists: Rock
         ✗ Adds pair: Charizard shares: Ice  Electric
         → After: Dragon gap  (3 types cover it)

    Lines with no content are suppressed (e.g. no ✗ line when no new pairs).
    """
    name      = result["form_name"]
    types_str = " / ".join(result["types"])
    rating    = _dot_rating(result["score"], all_scores)
    dots      = _format_dots(rating)

    # Header line
    header = f"  {rank}. {name:<16} [{types_str}]"
    print(f"{header:<46}  {dots}")

    # Covers line
    if result.get("off_covered"):
        print(f"       ✓ Covers:  {'  '.join(result['off_covered'])}")

    # Resists line
    if result.get("def_covered"):
        print(f"       ✓ Resists: {'  '.join(result['def_covered'])}")

    # Weak-pair warning lines
    for pair_str in result.get("new_weak_pairs", []):
        print(f"       ✗ Adds pair: {pair_str}")

    # Lookahead line
    print(f"       {_format_lookahead(result.get('remaining_off_gaps', []), era_key)}")


def display_team_builder(team_ctx: list, game_ctx: dict,
                         results: list, off_gaps: list, def_gaps: list,
                         missing_rosters: list = None) -> None:
    """
    Print the full team builder suggestion screen.

    Shows:
      - Header with game name and current team summary
      - Small-team note when < 3 members
      - Offensive and defensive gap summary
      - Ranked suggestion cards (one per result)
      - Missing roster note if applicable
    """
    era_key  = game_ctx["era_key"]
    game     = game_ctx["game"]
    filled   = team_size(team_ctx)

    from feat_team_loader import team_summary_line
    summary = team_summary_line(team_ctx)

    print(f"\n  Team builder  |  {game}")
    print(f"  Team: {summary}  ({filled}/6)")

    if filled < 3:
        print(f"  ⚠  Results are most meaningful with 2–3 Pokémon loaded."
              f"  Add more via T.")

    # Gap summary
    print()
    print("  Team gaps:")
    if off_gaps:
        print(f"    Offensive:  {'  '.join(off_gaps)}")
    else:
        print("    Offensive:  (none — full coverage)")
    if def_gaps:
        print(f"    Defensive:  {'  '.join(g + ' (critical)' for g in def_gaps)}")
    else:
        print("    Defensive:  (none — no critical gaps)")

    # Suggestions
    print()
    print("  Top suggestions for the next slot:")
    print("  " + "═" * _BLOCK_SEP)

    if not results:
        print("  No matching Pokémon found for current gaps.")
    else:
        all_scores = [r["score"] for r in results]
        for i, result in enumerate(results, 1):
            if i > 1:
                print()
            _print_suggestion(i, result, era_key, all_scores)

    print("  " + "═" * _BLOCK_SEP)

    if missing_rosters:
        print(f"\n  ⚠  Type data not yet cached for: {', '.join(missing_rosters)}")
        print("     Run with a network connection to fetch missing rosters.")


# ── Entry points ───────────────────────────────────────────────────────────────

def run(team_ctx: list, game_ctx: dict) -> None:
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
    from feat_team_loader import team_size as _team_size

    if _team_size(team_ctx) == 0:
        print("\n  Team is empty — load some Pokémon first (press T).")
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
            print(f"\n  Fetching {total} type roster(s)...")

            def _progress(cur, tot, tname):
                print(f"  {cur}/{tot}  {tname}...", end="\r", flush=True)

            fetch_needed_rosters(relevant, progress_cb=_progress)
            print(f"  Done.                          ")

    # Build pool
    pool = build_suggestion_pool(team_ctx, game_ctx, off_gaps, def_gaps)
    candidates = pool["candidates"]

    if not candidates:
        print("\n  No matching Pokémon found for current gaps.")
        if pool["missing_rosters"]:
            print(f"  Missing type data: {', '.join(pool['missing_rosters'])}")
        input("\n  Press Enter to continue...")
        return

    slots_remaining = 6 - team_size(team_ctx)
    results = rank_candidates(candidates, team_ctx, era_key,
                              off_gaps, def_gaps,
                              slots_remaining, top_n=6)

    display_team_builder(team_ctx, game_ctx, results,
                         off_gaps, def_gaps,
                         missing_rosters=pool["missing_rosters"] or None)

    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("  This module is not usable standalone.")
    print("  Launch from pokemain.py instead.")
    print()
    input("  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_builder.py — Iterations A + B + C self-test\n")

    # ── Fixtures ──────────────────────────────────────────────────────────────
    def _pkm(name, t1, t2="None", bs=None):
        types = [t1] if t2 == "None" else [t1, t2]
        return {
            "form_name"   : name,
            "pokemon"     : name.lower(),
            "type1"       : t1,
            "type2"       : t2,
            "types"       : types,
            "variety_slug": name.lower(),
            "base_stats"  : bs or {},
        }

    charizard  = _pkm("Charizard",  "Fire",    "Flying",
                      {"hp":78,"attack":84,"defense":78,
                       "special-attack":109,"special-defense":85,"speed":100})
    blastoise  = _pkm("Blastoise",  "Water",   bs={
                       "hp":79,"attack":83,"defense":100,
                       "special-attack":85,"special-defense":105,"speed":78})
    garchomp   = _pkm("Garchomp",   "Dragon",  "Ground",
                      {"hp":108,"attack":130,"defense":95,
                       "special-attack":80,"special-defense":85,"speed":102})
    machamp    = _pkm("Machamp",    "Fighting",
                      bs={"hp":90,"attack":130,"defense":80,
                          "special-attack":65,"special-defense":85,"speed":55})
    alakazam   = _pkm("Alakazam",   "Psychic",
                      bs={"hp":55,"attack":50,"defense":45,
                          "special-attack":135,"special-defense":95,"speed":120})

    team_empty  = [None] * 6
    team1       = [charizard, None, None, None, None, None]
    team2_char  = [charizard, charizard, None, None, None, None]  # 2 Charizard
    team2_cb    = [charizard, blastoise, None, None, None, None]
    team3       = [charizard, blastoise, garchomp, None, None, None]

    ERA = "era3"
    _, ERA3_TYPES, _ = calc.CHARTS[ERA]

    # ── team_offensive_gaps ───────────────────────────────────────────────────

    gaps_empty = team_offensive_gaps(team_empty, ERA)
    if set(gaps_empty) == set(ERA3_TYPES):
        ok("team_offensive_gaps: empty team → all era3 types")
    else:
        fail("team_offensive_gaps empty", str(gaps_empty))

    gaps1 = team_offensive_gaps(team1, ERA)
    # Charizard Fire/Flying hits: Grass,Ice,Bug,Steel (Fire) + Grass,Fighting,Bug (Flying)
    # Normal should be a gap (only Fighting hits it, Charizard has no Fighting)
    if "Normal" in gaps1:
        ok("team_offensive_gaps: Normal in Charizard's gaps (no Fighting type)")
    else:
        fail("team_offensive_gaps Charizard Normal", str(gaps1))

    if "Grass" not in gaps1:
        ok("team_offensive_gaps: Grass NOT a gap for Charizard (Fire hits it SE)")
    else:
        fail("team_offensive_gaps Charizard Grass", str(gaps1))

    gaps3 = team_offensive_gaps(team3, ERA)
    # Charizard+Blastoise+Garchomp cover a lot — gaps should be fewer
    if len(gaps3) < len(gaps1):
        ok(f"team_offensive_gaps: 3-member team has fewer gaps ({len(gaps3)}) than 1-member ({len(gaps1)})")
    else:
        fail("team_offensive_gaps 3-member", f"gaps3={len(gaps3)} gaps1={len(gaps1)}")

    # ── team_defensive_gaps ───────────────────────────────────────────────────

    # Single Charizard — Rock: only 1 weak, threshold is 2 → NOT critical
    def_gaps1 = team_defensive_gaps(team1, ERA)
    if "Rock" not in def_gaps1:
        ok("team_defensive_gaps: single Charizard → Rock NOT critical (only 1 member weak)")
    else:
        fail("team_defensive_gaps single Char Rock", str(def_gaps1))

    # Two Charizard — Rock: 2 weak, 0 resist → IS critical
    def_gaps2 = team_defensive_gaps(team2_char, ERA)
    if "Rock" in def_gaps2:
        ok("team_defensive_gaps: two Charizard → Rock IS critical (2 weak, 0 resist)")
    else:
        fail("team_defensive_gaps two Char Rock", str(def_gaps2))

    if "Electric" in def_gaps2 and "Water" in def_gaps2:
        ok("team_defensive_gaps: two Charizard → Electric and Water also critical")
    else:
        fail("team_defensive_gaps two Char others", str(def_gaps2))

    # Charizard + Blastoise — Water: Char weak, Blas resists → NOT critical
    def_gaps_cb = team_defensive_gaps(team2_cb, ERA)
    if "Water" not in def_gaps_cb:
        ok("team_defensive_gaps: Char+Blas → Water NOT critical (Blastoise resists)")
    else:
        fail("team_defensive_gaps Char+Blas Water", str(def_gaps_cb))

    # ── candidate_passes_filter ───────────────────────────────────────────────

    # Ground candidate vs Electric defensive gap → immune to Electric → passes
    if candidate_passes_filter(["Ground"], [], ["Electric"], ERA):
        ok("candidate_passes_filter: Ground candidate vs Electric def gap → passes (immune)")
    else:
        fail("candidate_passes_filter Ground vs Electric")

    # Fire candidate vs Grass offensive gap → hits Grass SE → passes
    if candidate_passes_filter(["Fire"], ["Grass"], [], ERA):
        ok("candidate_passes_filter: Fire candidate vs Grass off gap → passes")
    else:
        fail("candidate_passes_filter Fire vs Grass off gap")

    # Normal-type vs Electric/Dragon gaps → doesn't hit either SE, doesn't resist → fails
    if not candidate_passes_filter(["Normal"], ["Dragon"], ["Electric"], ERA):
        ok("candidate_passes_filter: Normal vs Dragon/Electric → fails both")
    else:
        fail("candidate_passes_filter Normal fails")

    # Dual-type passing via second type only: Water/Ice vs Grass off gap
    # Water doesn't hit Grass SE, but Ice does → should pass
    if candidate_passes_filter(["Water", "Ice"], ["Grass"], [], ERA):
        ok("candidate_passes_filter: Water/Ice vs Grass off gap → passes via Ice")
    else:
        fail("candidate_passes_filter dual-type via second type")

    # Empty gaps → always passes
    if candidate_passes_filter(["Normal"], [], [], ERA):
        ok("candidate_passes_filter: empty gaps → always passes")
    else:
        fail("candidate_passes_filter empty gaps")

    # ── patchability_score ────────────────────────────────────────────────────

    # Empty gaps → 0.0
    if patchability_score([], ERA) == 0.0:
        ok("patchability_score: empty gaps → 0.0")
    else:
        fail("patchability_score empty", str(patchability_score([], ERA)))

    # Normal gap: only Fighting hits Normal SE → count = 1
    ps_normal = patchability_score(["Normal"], ERA)
    if ps_normal == 1.0:
        ok("patchability_score: Normal gap → 1.0 (only Fighting hits it SE)")
    else:
        fail("patchability_score Normal", str(ps_normal))

    # Water gap: Electric + Grass hit Water SE → count = 2
    ps_water = patchability_score(["Water"], ERA)
    if ps_water == 2.0:
        ok("patchability_score: Water gap → 2.0 (Electric + Grass)")
    else:
        fail("patchability_score Water", str(ps_water))

    # Dragon gap: Ice + Dragon + Fairy → count = 3
    ps_dragon = patchability_score(["Dragon"], ERA)
    if ps_dragon == 3.0:
        ok("patchability_score: Dragon gap → 3.0 (Ice + Dragon + Fairy)")
    else:
        fail("patchability_score Dragon", str(ps_dragon))

    # Multiple gaps: Normal + Water = 1 + 2 = 3
    ps_multi = patchability_score(["Normal", "Water"], ERA)
    if ps_multi == 3.0:
        ok("patchability_score: Normal+Water gaps → 3.0 (sum of individual)")
    else:
        fail("patchability_score multi", str(ps_multi))

    # ── score_candidate ───────────────────────────────────────────────────────

    # Ground-type covers Electric off gap AND is immune to Electric def gap
    # → higher score than Fire-type that only covers Grass
    off_g  = ["Grass", "Electric"]
    def_g  = ["Electric"]

    score_ground = score_candidate(["Ground"], team1, ERA,
                                   off_g, def_g, 3)
    score_fire   = score_candidate(["Fire"],   team1, ERA,
                                   off_g, def_g, 3)
    if score_ground > score_fire:
        ok("score_candidate: Ground (covers Electric off+def) > Fire (covers Grass only)")
    else:
        fail("score_candidate ground>fire", f"ground={score_ground:.1f} fire={score_fire:.1f}")

    # Shared weakness penalty reduces score:
    # Both Ice/Flying and Fairy cover the Dragon off gap.
    # Ice/Flying shares Rock + Electric with Charizard (≥2) → penalty fires.
    # Fairy shares nothing with Charizard → no penalty.
    # Fairy should therefore score higher despite equal offensive contribution.
    score_ice_fly = score_candidate(["Ice","Flying"], team1, ERA,
                                    ["Dragon"], [], 3)
    score_fairy   = score_candidate(["Fairy"],         team1, ERA,
                                    ["Dragon"], [], 3)
    if score_fairy > score_ice_fly:
        ok("score_candidate: shared weakness penalty: Fairy > Ice/Flying (both cover Dragon, Ice/Flying penalised)")
    else:
        fail("score_candidate penalty",
             f"fairy={score_fairy:.1f} ice/flying={score_ice_fly:.1f}")

    # Lookahead weight: slots_remaining=1 gives stronger weight than 4
    score_sr1 = score_candidate(["Ground"], team1, ERA,
                                ["Normal", "Electric"], ["Electric"], 1)
    score_sr4 = score_candidate(["Ground"], team1, ERA,
                                ["Normal", "Electric"], ["Electric"], 4)
    if score_sr1 != score_sr4:
        ok("score_candidate: slots_remaining affects lookahead weight (sr=1 ≠ sr=4)")
    else:
        fail("score_candidate lookahead weight", f"sr1={score_sr1:.1f} sr4={score_sr4:.1f}")

    # base_stats=None → no crash, returns valid float
    try:
        s = score_candidate(["Ground"], team1, ERA, ["Electric"], [], 3,
                            base_stats=None)
        if isinstance(s, float):
            ok("score_candidate: base_stats=None → no crash, returns float")
        else:
            fail("score_candidate base_stats=None type", str(type(s)))
    except Exception as e:
        fail("score_candidate base_stats=None crash", str(e))

    # ── rank_candidates ───────────────────────────────────────────────────────

    # Build a small candidate list
    candidates = [
        {"slug": "garchomp",  "form_name": "Garchomp",
         "types": ["Dragon","Ground"],  "base_stats": garchomp["base_stats"]},
        {"slug": "blastoise", "form_name": "Blastoise",
         "types": ["Water"],            "base_stats": blastoise["base_stats"]},
        {"slug": "machamp",   "form_name": "Machamp",
         "types": ["Fighting"],         "base_stats": machamp["base_stats"]},
        {"slug": "alakazam",  "form_name": "Alakazam",
         "types": ["Psychic"],          "base_stats": alakazam["base_stats"]},
    ]

    team_for_rank = [charizard, None, None, None, None, None]
    off_gaps_r = team_offensive_gaps(team_for_rank, ERA)
    def_gaps_r = team_defensive_gaps(team_for_rank, ERA)

    results = rank_candidates(candidates, team_for_rank, ERA,
                              off_gaps_r, def_gaps_r, 5, top_n=6)

    if len(results) <= 6:
        ok("rank_candidates: returns at most top_n results")
    else:
        fail("rank_candidates top_n", str(len(results)))

    scores = [r["score"] for r in results]
    if scores == sorted(scores, reverse=True):
        ok("rank_candidates: sorted by score descending")
    else:
        fail("rank_candidates sort", str(scores))

    required = {"slug","form_name","types","score","off_covered","def_covered",
                "new_weak_pairs","remaining_off_gaps","role","speed_tier"}
    if all(required <= set(r.keys()) for r in results):
        ok("rank_candidates: all required keys present in each result dict")
    else:
        missing = [required - set(r.keys()) for r in results if required - set(r.keys())]
        fail("rank_candidates keys", str(missing))

    # Empty candidates → []
    if rank_candidates([], team_for_rank, ERA, off_gaps_r, def_gaps_r, 5) == []:
        ok("rank_candidates: empty candidates → []")
    else:
        fail("rank_candidates empty")

    # off_covered and remaining_off_gaps are complementary subsets of off_gaps
    for r in results:
        union = set(r["off_covered"]) | set(r["remaining_off_gaps"])
        # Every covered gap must be in the original gaps
        if all(g in off_gaps_r for g in r["off_covered"]):
            ok(f"rank_candidates: {r['form_name']} off_covered ⊆ original off_gaps")
        else:
            fail(f"rank_candidates {r['form_name']} off_covered subset",
                 str(r["off_covered"]))
        break  # test once is enough

    # ── _id_to_gen ────────────────────────────────────────────────────────────

    cases_gen = [
        (151,   1), (152,   2), (386,   3), (493,   4),
        (649,   5), (721,   6), (1025,  9), (10034, None),
    ]
    for id_, expected in cases_gen:
        result = _id_to_gen(id_)
        if result == expected:
            ok(f"_id_to_gen: id={id_} → gen {expected}")
        else:
            fail(f"_id_to_gen id={id_}", f"expected {expected} got {result}")

    # ── collect_relevant_types ────────────────────────────────────────────────

    # Electric off gap → Ground hits Electric SE (Ground is the only type)
    rel_electric = collect_relevant_types(["Electric"], [], ERA)
    if "Ground" in rel_electric:
        ok("collect_relevant_types: Electric off gap → Ground included")
    else:
        fail("collect_relevant_types Electric off gap", str(rel_electric))

    # Rock def gap → Fighting/Ground/Steel resist Rock (Rock hits them ≤ 0.5)
    rel_rock = collect_relevant_types([], ["Rock"], ERA)
    if "Fighting" in rel_rock and "Ground" in rel_rock and "Steel" in rel_rock:
        ok("collect_relevant_types: Rock def gap → Fighting/Ground/Steel included")
    else:
        fail("collect_relevant_types Rock def gap", str(rel_rock))

    # Empty gaps → empty set
    rel_empty = collect_relevant_types([], [], ERA)
    if rel_empty == set():
        ok("collect_relevant_types: empty gaps → empty set")
    else:
        fail("collect_relevant_types empty", str(rel_empty))

    # Overlap deduplicated: Ground appears for both Electric off gap AND
    # Rock def gap (Ground resists Rock). Should appear only once in result set.
    rel_both = collect_relevant_types(["Electric"], ["Rock"], ERA)
    if "Ground" in rel_both and len([x for x in rel_both if x == "Ground"]) == 1:
        ok("collect_relevant_types: overlap deduplicated (Ground in set once)")
    else:
        fail("collect_relevant_types overlap", str(rel_both))

    # ── build_suggestion_pool (mocked cache) ───────────────────────────────────

    import sys as _sys
    import pkm_cache as _real_cache

    # Roster: two Pokemon of type Ground
    #   - garchomp   id=445 gen4  types=[Dragon,Ground]  cached
    #   - landorus   id=645 gen5  types=[Ground,Flying]  not cached
    #   - altform    id=10200     types=[Ground]          not cached → skip
    #   - charizard  id=6         on team                → skip

    _fake_rosters = {
        "Ground": [
            {"slug": "garchomp",  "slot": 1, "id": 445},
            {"slug": "landorus",  "slot": 1, "id": 645},
            {"slug": "altform",   "slot": 1, "id": 10200},
            {"slug": "charizard", "slot": 2, "id": 6},
        ]
    }
    _fake_pokemon = {
        "garchomp": {
            "pokemon": "garchomp", "species_gen": 4,
            "egg_groups": [], "evolution_chain_id": 1,
            "forms": [{"name": "Garchomp", "variety_slug": "garchomp",
                       "types": ["Dragon", "Ground"],
                       "base_stats": {"hp": 108, "attack": 130, "defense": 95,
                                      "special-attack": 80, "special-defense": 85,
                                      "speed": 102}}]
        }
    }

    class _MockCache:
        def get_type_roster(self, t):
            return _fake_rosters.get(t)
        def get_pokemon(self, slug):
            return _fake_pokemon.get(slug)
        def get_abilities_index(self):
            return None

    _real_mod = _sys.modules.get("pkm_cache")
    _sys.modules["pkm_cache"] = _MockCache()

    try:
        # Team has Charizard (variety_slug "charizard")
        team_pool = [charizard, None, None, None, None, None]
        game_gen5 = {"era_key": "era3", "game_gen": 5}
        game_gen3 = {"era_key": "era3", "game_gen": 3}

        # Gen 5 game: Garchomp (gen4 ≤ 5) → included; Landorus (gen5 ≤ 5) → included
        # Charizard → skipped_team; altform → skipped_forms
        pool5 = build_suggestion_pool(team_pool, game_gen5, ["Electric"], [])
        slug5 = {c["slug"] for c in pool5["candidates"]}

        if "garchomp" in slug5:
            ok("build_candidate_pool: gen4 pokemon included in gen5 game")
        else:
            fail("build_candidate_pool gen4 included", str(slug5))

        if pool5["skipped_team"] >= 1:
            ok("build_candidate_pool: team member (Charizard) skipped")
        else:
            fail("build_candidate_pool team skip", str(pool5["skipped_team"]))

        if pool5["skipped_forms"] >= 1:
            ok("build_candidate_pool: alt form (id>10000) skipped when not cached")
        else:
            fail("build_candidate_pool alt form skip", str(pool5["skipped_forms"]))

        # Gen 3 game: Garchomp (gen4 > 3) → skipped_gen
        pool3 = build_suggestion_pool(team_pool, game_gen3, ["Electric"], [])
        if pool3["skipped_gen"] >= 1:
            ok("build_candidate_pool: post-game gen pokemon excluded")
        else:
            fail("build_candidate_pool gen filter", str(pool3["skipped_gen"]))

        # base_stats populated from cache for Garchomp, None for uncached
        cached_cand = next((c for c in pool5["candidates"] if c["slug"] == "garchomp"), None)
        if cached_cand and isinstance(cached_cand.get("base_stats"), dict):
            ok("build_candidate_pool: base_stats populated from cache")
        else:
            fail("build_candidate_pool base_stats", str(cached_cand))

        uncached_cand = next((c for c in pool5["candidates"] if c["slug"] == "landorus"), None)
        if uncached_cand and uncached_cand.get("base_stats") is None:
            ok("build_candidate_pool: base_stats is None for uncached pokemon")
        else:
            fail("build_candidate_pool uncached base_stats", str(uncached_cand))

    finally:
        if _real_mod is not None:
            _sys.modules["pkm_cache"] = _real_mod
        else:
            del _sys.modules["pkm_cache"]

    # ── fetch_needed_rosters (mocked cache) ──────────────────────────────────

    _fetched_calls = []

    class _MockCacheRosters:
        def __init__(self, already_cached):
            self._cached = set(already_cached)
        def get_type_roster(self, t):
            return [{"slug": "dummy", "id": 1}] if t in self._cached else None
        def get_type_roster_or_fetch(self, t):
            _fetched_calls.append(t)
            self._cached.add(t)
            return [{"slug": "dummy", "id": 1}]

    _real_mod2 = _sys.modules.get("pkm_cache")
    _sys.modules["pkm_cache"] = _MockCacheRosters({"Fire"})  # Fire already cached

    try:
        _fetched_calls.clear()
        n = fetch_needed_rosters({"Fire", "Ground"})
        if n == 1 and "Ground" in _fetched_calls and "Fire" not in _fetched_calls:
            ok("fetch_needed_rosters: cached roster not re-fetched, missing roster fetched")
        else:
            fail("fetch_needed_rosters count/calls",
                 f"n={n} calls={_fetched_calls}")

        # progress_cb called correctly
        cb_calls = []
        _fetched_calls.clear()
        _sys.modules["pkm_cache"] = _MockCacheRosters(set())  # nothing cached
        fetch_needed_rosters({"Water", "Ice"},
                             progress_cb=lambda cur, tot, t: cb_calls.append((cur, tot, t)))
        if len(cb_calls) == 2 and cb_calls[0][1] == 2:
            ok("fetch_needed_rosters: progress_cb called with (current, total, type_name)")
        else:
            fail("fetch_needed_rosters progress_cb", str(cb_calls))

    finally:
        if _real_mod2 is not None:
            _sys.modules["pkm_cache"] = _real_mod2
        else:
            del _sys.modules["pkm_cache"]

    # ── Iteration C display tests ─────────────────────────────────────────────
    import io, contextlib

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

    fake_result = {
        "form_name"         : "Garchomp",
        "types"             : ["Dragon", "Ground"],
        "score"             : 80.0,
        "off_covered"       : ["Normal", "Rock"],
        "def_covered"       : ["Electric"],
        "new_weak_pairs"    : [],
        "remaining_off_gaps": ["Dragon"],
    }

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_suggestion(1, fake_result, ERA, [80.0, 50.0, 30.0])
    out = buf.getvalue()

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

    # ── display_team_builder (stdout capture) ──────────────────────────────────

    game_ctx_sv = {"era_key": "era3", "game_gen": 9, "game": "Scarlet / Violet"}

    # 1-member team → small-team note shown
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        display_team_builder(team1, game_ctx_sv,
                             [fake_result], ["Normal"], [], [])
    out2 = buf2.getvalue()

    if "most meaningful with 2" in out2:
        ok("display_team_builder: small-team note shown for 1-member team")
    else:
        fail("display_team_builder small-team note", out2[:120])

    # 3-member team → no small-team note
    team3 = [charizard, blastoise, garchomp, None, None, None]
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        display_team_builder(team3, game_ctx_sv,
                             [fake_result], ["Normal"], [], [])
    out3 = buf3.getvalue()

    if "most meaningful" not in out3:
        ok("display_team_builder: small-team note absent for 3-member team")
    else:
        fail("display_team_builder 3-member no note", out3[:120])

    # All suggestion names present
    results_multi = [
        {**fake_result, "form_name": "Garchomp", "score": 80.0},
        {**fake_result, "form_name": "Machamp",  "score": 50.0,
         "types": ["Fighting"], "off_covered": ["Normal"]},
    ]
    buf4 = io.StringIO()
    with contextlib.redirect_stdout(buf4):
        display_team_builder(team1, game_ctx_sv,
                             results_multi, ["Normal", "Rock"], [], [])
    out4 = buf4.getvalue()

    if "Garchomp" in out4 and "Machamp" in out4:
        ok("display_team_builder: all suggestion names present")
    else:
        fail("display_team_builder names", out4[:120])

    # Missing rosters note shown when list non-empty
    buf5 = io.StringIO()
    with contextlib.redirect_stdout(buf5):
        display_team_builder(team1, game_ctx_sv,
                             [], ["Normal"], [], ["Dragon", "Ghost"])
    out5 = buf5.getvalue()

    if "Dragon" in out5 and "Ghost" in out5 and "not yet cached" in out5:
        ok("display_team_builder: missing rosters note shown")
    else:
        fail("display_team_builder missing rosters", out5[:120])

    # Gap summary shows off and def gaps
    buf6 = io.StringIO()
    with contextlib.redirect_stdout(buf6):
        display_team_builder(team1, game_ctx_sv,
                             [], ["Normal", "Dragon"], ["Rock"], [])
    out6 = buf6.getvalue()

    if "Normal" in out6 and "Dragon" in out6 and "Rock (critical)" in out6:
        ok("display_team_builder: gap summary shows off and def gaps")
    else:
        fail("display_team_builder gap summary", out6[:200])

    # ── Iteration D — run() guards ────────────────────────────────────────────

    game_ctx_sv = {"era_key": "era3", "game_gen": 9, "game": "Scarlet / Violet"}

    # Empty team → message printed, no crash
    buf_d1 = io.StringIO()
    with contextlib.redirect_stdout(buf_d1):
        # run() calls input() at the end — we need to mock it
        import builtins as _bi
        _real_input = _bi.input
        _bi.input = lambda p="": ""
        try:
            run([None]*6, game_ctx_sv)
        finally:
            _bi.input = _real_input
    out_d1 = buf_d1.getvalue()
    if "empty" in out_d1.lower() or "load" in out_d1.lower():
        ok("run(): empty team → message printed, no crash")
    else:
        fail("run() empty team", out_d1[:80])

    # 1-member team → small-team note visible (needs mocked pool)
    import sys as _sys2

    class _MockCacheD:
        def get_type_roster(self, t): return [{"slug": "garchomp", "id": 445}]
        def get_type_roster_or_fetch(self, t): return [{"slug": "garchomp", "id": 445}]
        def get_pokemon(self, slug):
            if slug == "garchomp":
                return {
                    "pokemon": "garchomp", "species_gen": 4,
                    "egg_groups": [], "evolution_chain_id": 1,
                    "forms": [{"name": "Garchomp", "variety_slug": "garchomp",
                               "types": ["Dragon", "Ground"],
                               "base_stats": {"hp":108,"attack":130,"defense":95,
                                              "special-attack":80,"special-defense":85,"speed":102}}]
                }
            return None

    _real_mod_d = _sys2.modules.get("pkm_cache")
    _sys2.modules["pkm_cache"] = _MockCacheD()
    _real_input2 = _bi.input
    _bi.input = lambda p="": ""
    try:
        buf_d2 = io.StringIO()
        with contextlib.redirect_stdout(buf_d2):
            run(team1, game_ctx_sv)
        out_d2 = buf_d2.getvalue()
        if "most meaningful with 2" in out_d2:
            ok("run(): 1-member team → small-team note shown")
        else:
            fail("run() small-team note", out_d2[:120])
    finally:
        _bi.input = _real_input2
        if _real_mod_d is not None:
            _sys2.modules["pkm_cache"] = _real_mod_d
        else:
            del _sys2.modules["pkm_cache"]

    # Pool empty → "No matching" message
    class _MockCacheEmpty:
        def get_type_roster(self, t): return []
        def get_type_roster_or_fetch(self, t): return []
        def get_pokemon(self, slug): return None

    _real_mod_e = _sys2.modules.get("pkm_cache")
    _sys2.modules["pkm_cache"] = _MockCacheEmpty()
    _real_input3 = _bi.input
    _bi.input = lambda p="": ""
    try:
        buf_d3 = io.StringIO()
        with contextlib.redirect_stdout(buf_d3):
            run(team1, game_ctx_sv)
        out_d3 = buf_d3.getvalue()
        if "No matching" in out_d3:
            ok("run(): empty pool → 'No matching Pokémon' message")
        else:
            fail("run() empty pool", out_d3[:120])
    finally:
        _bi.input = _real_input3
        if _real_mod_e is not None:
            _sys2.modules["pkm_cache"] = _real_mod_e
        else:
            del _sys2.modules["pkm_cache"]

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 57
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
