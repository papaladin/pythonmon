#!/usr/bin/env python3
"""
core_team.py  Pure team‑related logic (no I/O, no display)

Contains functions for:
  - Defensive analysis (build_team_defense, build_unified_rows, gap_label, weakness pairs)
  - Offensive analysis (hitting_types, build_team_offense, build_offense_rows, coverage_gaps)
  - Moveset synergy (weakness_types, se_types, build_offensive_coverage, formatting helpers)
  - Team builder (offensive/defensive gaps, candidate scoring, ranking)
  - Joint team optimisation (precomputation, fitness, GA core)
"""

import sys
import random

try:
    import matchup_calculator as calc
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)

from core_stat import total_stats, infer_role

# ── Constants for display (used in formatting functions) ──────────────────────
_NAME_ABBREV = 4
_COL_TYPE = 10
_COL_CNT = 2
_COL_WNAMES = 30
_COL_RNAMES = 28
_COL_INAMES = 20
_GAP_WIDTH = 12

_COL_HITTERS = 70
_MOVE_NAME_LEN = 12

_COL_MOVE = 22
_BLOCK_SEP = 56

_W_OFFENSIVE   = 10
_W_DEFENSIVE   = 8
_W_WEAK_PAIR   = 6
_W_ROLE        = 4
_W_BST         = 5
_LOOKAHEAD_END = 2


# ── Defensive analysis ────────────────────────────────────────────────────────

def build_team_defense(team_ctx: list, era_key: str) -> dict:
    _, valid_types, _ = calc.CHARTS[era_key]
    result = {t: [] for t in valid_types}
    for pkm in team_ctx:
        if pkm is None:
            continue
        matchups = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
        for atk_type in valid_types:
            m = matchups.get(atk_type, 1.0)
            result[atk_type].append({
                "form_name": pkm["form_name"],
                "multiplier": m,
            })
    return result


def build_unified_rows(team_defense: dict, era_key: str) -> list:
    _, all_types, _ = calc.CHARTS[era_key]
    rows = []
    for t in all_types:
        members = team_defense.get(t, [])
        weak    = [(m["form_name"], m["multiplier"]) for m in members if m["multiplier"] >= 2.0]
        resist  = [(m["form_name"], m["multiplier"]) for m in members if 0.0 < m["multiplier"] < 1.0]
        immune  = [m["form_name"] for m in members if m["multiplier"] == 0.0]
        neutral = sum(1 for m in members if m["multiplier"] == 1.0)
        rows.append({
            "type": t,
            "weak_members": weak,
            "resist_members": resist,
            "immune_members": immune,
            "neutral_count": neutral,
        })
    rows.sort(key=lambda r: (-len(r["weak_members"]),
                             -(len(r["resist_members"]) + len(r["immune_members"])),
                             r["type"]))
    return rows


def gap_label(weak_count: int, cover_count: int) -> str:
    if weak_count >= 3 and cover_count == 0:
        return "!! CRITICAL"
    if weak_count >= 3 and cover_count <= 1:
        return "!  MAJOR"
    if weak_count == 2 and cover_count == 0:
        return ".  MINOR"
    return ""


def build_weakness_pairs(team_ctx: list, era_key: str) -> list:
    slots = [(i, pkm) for i, pkm in enumerate(team_ctx) if pkm is not None]
    pairs = []
    for ai, (_, pkm_a) in enumerate(slots):
        def_a = calc.compute_defense(era_key, pkm_a["type1"], pkm_a["type2"])
        weak_a = {t for t, m in def_a.items() if m > 1.0}
        for _, (_, pkm_b) in enumerate(slots[ai + 1:]):
            def_b = calc.compute_defense(era_key, pkm_b["type1"], pkm_b["type2"])
            weak_b = {t for t, m in def_b.items() if m > 1.0}
            shared = sorted(weak_a & weak_b)
            if len(shared) >= 2:
                pairs.append({
                    "name_a": pkm_a["form_name"],
                    "name_b": pkm_b["form_name"],
                    "shared_types": shared,
                    "shared_count": len(shared),
                })
    pairs.sort(key=lambda p: (-p["shared_count"], p["name_a"]))
    return pairs


def gap_pair_label(shared_count: int) -> str:
    return "!! CRITICAL" if shared_count >= 3 else ""


# ── Offensive analysis ────────────────────────────────────────────────────────

def hitting_types(era_key: str, type1: str, type2: str, target: str) -> list:
    letters = []
    if calc.get_multiplier(era_key, type1, target) >= 2.0:
        letters.append(type1[0])
    if type2 != "None" and calc.get_multiplier(era_key, type2, target) >= 2.0:
        letters.append(type2[0])
    return letters


def build_team_offense(team_ctx: list, era_key: str) -> dict:
    _, valid_types, _ = calc.CHARTS[era_key]
    result = {t: [] for t in valid_types}
    for pkm in team_ctx:
        if pkm is None:
            continue
        t1, t2 = pkm["type1"], pkm["type2"]
        for target in valid_types:
            letters = hitting_types(era_key, t1, t2, target)
            if letters:
                full_types = [
                    t for t in [t1, t2]
                    if t != "None" and calc.get_multiplier(era_key, t, target) >= 2.0
                ]
                result[target].append({
                    "form_name": pkm["form_name"],
                    "hitting_letters": letters,
                    "hitting_types": full_types,
                })
    return result


def build_offense_rows(team_offense: dict, era_key: str) -> list:
    _, valid_types, _ = calc.CHARTS[era_key]
    rows = []
    for t in valid_types:
        hitters = team_offense.get(t, [])
        rows.append({"type": t, "hitters": hitters})
    rows.sort(key=lambda r: (-len(r["hitters"]), r["type"]))
    return rows


def coverage_gaps(rows: list) -> list:
    return [r["type"] for r in rows if not r["hitters"]]


# ── Moveset synergy ───────────────────────────────────────────────────────────

def weakness_types(pkm_ctx: dict, era_key: str) -> list:
    defense = calc.compute_defense(era_key, pkm_ctx["type1"], pkm_ctx["type2"])
    return [t for t, m in defense.items() if m > 1.0]


def se_types(combo: list, era_key: str) -> list:
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


def build_offensive_coverage(member_results: list, era_key: str) -> dict:
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
        "counts": counts,
        "covered": covered,
        "gaps": gaps,
        "overlap": overlap,
        "total_types": len(valid_types),
    }


def empty_member_result(form_name: str) -> dict:
    return {
        "form_name": form_name,
        "types": [],
        "moves": [],
        "weakness_types": [],
        "se_types": [],
    }


def format_weak_line(weakness_types: list) -> str:
    if not weakness_types:
        return "Weak:  —"
    return "Weak:  " + "  ".join(weakness_types)


def format_move_pair(left: str | None, right: str | None) -> str:
    l = left  if left  is not None else "—"
    r = right if right is not None else "—"
    return f"{l:<{_COL_MOVE}}  {r}"


def format_se_line(se_types: list, era_key: str) -> str:
    _, valid_types, _ = calc.CHARTS[era_key]
    return f"SE: {len(se_types)} / {len(valid_types)} types"


# ── Team builder ──────────────────────────────────────────────────────────────

def team_offensive_gaps(team_ctx: list, era_key: str) -> list:
    _, valid_types, _ = calc.CHARTS[era_key]
    slots = [(i, pkm) for i, pkm in enumerate(team_ctx) if pkm is not None]
    if not slots:
        return sorted(valid_types)
    covered = set()
    for _, pkm in slots:
        for atk_type in [pkm["type1"]] + ([pkm["type2"]] if pkm["type2"] != "None" else []):
            for def_type in valid_types:
                if calc.get_multiplier(era_key, atk_type, def_type) >= 2.0:
                    covered.add(def_type)
    return sorted(t for t in valid_types if t not in covered)


def team_defensive_gaps(team_ctx: list, era_key: str) -> list:
    _, valid_types, _ = calc.CHARTS[era_key]
    slots = [(i, pkm) for i, pkm in enumerate(team_ctx) if pkm is not None]
    gaps = []
    for atk_type in valid_types:
        weak_count = cover_count = 0
        for _, pkm in slots:
            defense = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
            m = defense.get(atk_type, 1.0)
            if m > 1.0:
                weak_count += 1
            elif m < 1.0:
                cover_count += 1
        if weak_count >= 2 and cover_count == 0:
            gaps.append(atk_type)
    return sorted(gaps)


def candidate_passes_filter(candidate_types: list, off_gaps: list,
                            def_gaps: list, era_key: str) -> bool:
    if not off_gaps and not def_gaps:
        return True
    for ctype in candidate_types:
        for gap in off_gaps:
            if calc.get_multiplier(era_key, ctype, gap) >= 2.0:
                return True
        for gap in def_gaps:
            if calc.get_multiplier(era_key, gap, ctype) <= 0.5:
                return True
    return False


def patchability_score(remaining_off_gaps: list, era_key: str) -> float:
    if not remaining_off_gaps:
        return 0.0
    _, valid_types, _ = calc.CHARTS[era_key]
    total = 0.0
    for gap in remaining_off_gaps:
        count = sum(1 for t in valid_types if calc.get_multiplier(era_key, t, gap) >= 2.0)
        total += count
    return total


def shared_weakness_count(candidate_types: list, team_ctx: list, era_key: str) -> int:
    ctype1 = candidate_types[0]
    ctype2 = candidate_types[1] if len(candidate_types) > 1 else "None"
    cand_defense = calc.compute_defense(era_key, ctype1, ctype2)
    cand_weak = {t for t, m in cand_defense.items() if m > 1.0}
    count = 0
    for pkm in team_ctx:
        if pkm is None:
            continue
        member_defense = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
        member_weak = {t for t, m in member_defense.items() if m > 1.0}
        if len(cand_weak & member_weak) >= 2:
            count += 1
    return count


def new_weak_pairs(candidate_types: list, team_ctx: list, era_key: str) -> list:
    ctype1 = candidate_types[0]
    ctype2 = candidate_types[1] if len(candidate_types) > 1 else "None"
    cand_defense = calc.compute_defense(era_key, ctype1, ctype2)
    cand_weak = {t for t, m in cand_defense.items() if m > 1.0}
    pairs = []
    for pkm in team_ctx:
        if pkm is None:
            continue
        member_defense = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
        member_weak = {t for t, m in member_defense.items() if m > 1.0}
        shared = sorted(cand_weak & member_weak)
        if len(shared) >= 2:
            pairs.append(f"{pkm['form_name']} shares: {'  '.join(shared)}")
    return pairs


def score_candidate(candidate_types: list, team_ctx: list, era_key: str,
                    off_gaps: list, def_gaps: list, slots_remaining: int,
                    base_stats: dict = None) -> float:
    off_covered = [g for g in off_gaps if any(calc.get_multiplier(era_key, ct, g) >= 2.0 for ct in candidate_types)]
    offensive_contribution = len(off_covered)
    def_covered = [g for g in def_gaps if any(calc.get_multiplier(era_key, g, ct) <= 0.5 for ct in candidate_types)]
    defensive_contribution = len(def_covered)
    shared_penalty = shared_weakness_count(candidate_types, team_ctx, era_key)
    role_bonus = 0
    if base_stats and isinstance(base_stats, dict):
        try:
            candidate_role = infer_role(base_stats)
            team_roles = set()
            for pkm in team_ctx:
                if pkm is None:
                    continue
                bs = pkm.get("base_stats", {})
                if bs:
                    team_roles.add(infer_role(bs))
            if candidate_role not in team_roles:
                role_bonus = 1
        except Exception:
            pass
    intrinsic = (offensive_contribution * _W_OFFENSIVE +
                 defensive_contribution * _W_DEFENSIVE -
                 shared_penalty * _W_WEAK_PAIR +
                 role_bonus * _W_ROLE)
    bst_bonus = 0
    if base_stats and isinstance(base_stats, dict):
        total = total_stats(base_stats)
        bst_bonus = (total / 720) * _W_BST
    total_intrinsic = intrinsic + bst_bonus
    remaining_off_gaps = [g for g in off_gaps if g not in off_covered]
    patch = patchability_score(remaining_off_gaps, era_key)
    weight = _LOOKAHEAD_END if slots_remaining <= 2 else 1
    lookahead = patch / max(slots_remaining, 1) * weight
    return total_intrinsic + lookahead


def rank_candidates(candidates: list, team_ctx: list, era_key: str,
                    off_gaps: list, def_gaps: list, slots_remaining: int,
                    top_n: int = 6) -> list:
    if not candidates:
        return []
    scored = []
    for c in candidates:
        ctypes = c["types"]
        base_stats = c.get("base_stats")
        s = score_candidate(ctypes, team_ctx, era_key, off_gaps, def_gaps, slots_remaining, base_stats)
        off_covered = [g for g in off_gaps if any(calc.get_multiplier(era_key, ct, g) >= 2.0 for ct in ctypes)]
        def_covered = [g for g in def_gaps if any(calc.get_multiplier(era_key, g, ct) <= 0.5 for ct in ctypes)]
        remaining = [g for g in off_gaps if g not in off_covered]
        pairs = new_weak_pairs(ctypes, team_ctx, era_key)
        role = speed_tier = None
        if base_stats and isinstance(base_stats, dict):
            try:
                from core_stat import infer_speed_tier
                role = infer_role(base_stats)
                speed_tier = infer_speed_tier(base_stats)
            except Exception:
                pass
        scored.append({
            "slug": c["slug"],
            "form_name": c["form_name"],
            "types": ctypes,
            "score": s,
            "off_covered": off_covered,
            "def_covered": def_covered,
            "new_weak_pairs": pairs,
            "remaining_off_gaps": remaining,
            "role": role,
            "speed_tier": speed_tier,
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_n]


# ──────────────────────────────────────────────────────────────────────────────
# Joint team optimisation — Genetic Algorithm helpers
# ──────────────────────────────────────────────────────────────────────────────

def precompute_pokemon_data(pkm_ctx_list: list, era_key: str) -> dict:
    _, valid_types, _ = calc.CHARTS[era_key]
    _TYPE_TO_BIT = {t: 1 << i for i, t in enumerate(valid_types)}
    result = {}
    for pkm in pkm_ctx_list:
        slug = pkm["pokemon"]
        types = pkm.get("types", [])
        if not types:
            t1 = pkm.get("type1")
            t2 = pkm.get("type2")
            types = [t1] if t2 == "None" else [t1, t2]
        off_mask = 0
        for t in types:
            for def_type in valid_types:
                if calc.get_multiplier(era_key, t, def_type) >= 2.0:
                    off_mask |= _TYPE_TO_BIT[def_type]
        def_mask = 0
        defense_multipliers = {}
        for atk_type in valid_types:
            mult = calc.get_multiplier(era_key, atk_type, types[0])
            if len(types) > 1:
                mult *= calc.get_multiplier(era_key, atk_type, types[1])
            defense_multipliers[atk_type] = mult
            if mult > 1.0:
                def_mask |= _TYPE_TO_BIT[atk_type]
        base_stats = pkm.get("base_stats", {})
        role = infer_role(base_stats)
        total = total_stats(base_stats)
        result[slug] = {
            "types": types,
            "offensive_bitmask": off_mask,
            "defensive_bitmask": def_mask,
            "defense_multipliers": defense_multipliers,
            "base_stats": base_stats,
            "total_stats": total,
            "role": role,
            "form_name": pkm.get("form_name", slug.replace("-", " ").title()),
            "slug": slug,
        }
    return result


def team_fitness(team_slugs: frozenset, precomputed: dict, era_key: str,
                 locked_slugs: frozenset | None = None) -> float:
    members = [precomputed[s] for s in team_slugs if s in precomputed]
    if len(members) != 6:
        return 0.0
    _, valid_types, _ = calc.CHARTS[era_key]
    combined_off_mask = 0
    for m in members:
        combined_off_mask |= m["offensive_bitmask"]
    covered_types = bin(combined_off_mask).count("1")
    offensive_score = (covered_types / len(valid_types)) * 40
    weak_counts = [0] * len(valid_types)
    resist_counts = [0] * len(valid_types)
    immune_counts = [0] * len(valid_types)
    for m in members:
        mults = m["defense_multipliers"]
        for i, atk_type in enumerate(valid_types):
            mult = mults[atk_type]
            if mult >= 2.0:
                weak_counts[i] += 1
            elif 0.0 < mult < 1.0:
                resist_counts[i] += 1
            elif mult == 0.0:
                immune_counts[i] += 1
    critical_gaps = sum(1 for i in range(len(valid_types))
                        if weak_counts[i] >= 3 and (resist_counts[i] + immune_counts[i]) <= 1)
    defensive_score = ((len(valid_types) - critical_gaps) / len(valid_types)) * 30
    roles = [m["role"] for m in members]
    distinct_roles = len(set(roles))
    role_score = (distinct_roles / 3) * 15
    individual_sum = sum(min(m["total_stats"] / 720, 1.0) * 100 for m in members)
    individual_score = (individual_sum / 600) * 15
    pair_penalty = 0
    members_list = list(members)
    for i in range(5):
        for j in range(i + 1, 6):
            overlap = members_list[i]["defensive_bitmask"] & members_list[j]["defensive_bitmask"]
            if bin(overlap).count("1") >= 2:
                pair_penalty += 5
    pair_penalty = min(pair_penalty, 15)
    total = offensive_score + defensive_score + role_score + individual_score - pair_penalty
    return max(0.0, total)


# ── GA Core Functions ─────────────────────────────────────────────────────────

def create_individual(pool_slugs: list, locked_slugs: frozenset, rng: random.Random) -> frozenset:
    available = [s for s in pool_slugs if s not in locked_slugs]
    needed = 6 - len(locked_slugs)
    chosen = set(rng.sample(available, needed))
    return frozenset(locked_slugs.union(chosen))


def crossover(parent1: frozenset, parent2: frozenset, locked_slugs: frozenset,
              pool_slugs: list, rng: random.Random) -> frozenset:
    union = parent1.union(parent2)
    candidates = [s for s in union if s not in locked_slugs]
    needed = 6 - len(locked_slugs)
    if len(candidates) >= needed:
        chosen = set(rng.sample(candidates, needed))
    else:
        extra_pool = [s for s in pool_slugs if s not in locked_slugs and s not in parent1 and s not in parent2]
        chosen = set(candidates) | set(rng.sample(extra_pool, needed - len(candidates)))
    return frozenset(locked_slugs.union(chosen))


def mutate(individual: frozenset, locked_slugs: frozenset, pool_slugs: list,
           rng: random.Random, mutation_rate: float = 0.05) -> frozenset:
    if rng.random() > mutation_rate:
        return individual
    non_locked = [s for s in individual if s not in locked_slugs]
    if not non_locked:
        return individual
    to_replace = rng.choice(non_locked)
    available = [s for s in pool_slugs if s not in individual and s not in locked_slugs]
    if not available:
        return individual
    replacement = rng.choice(available)
    new_set = set(individual)
    new_set.remove(to_replace)
    new_set.add(replacement)
    return frozenset(new_set)


def tournament_selection(population: list, fitnesses: list, k: int, rng: random.Random):
    participants = rng.sample(list(zip(population, fitnesses)), k)
    best = max(participants, key=lambda x: x[1])
    return best[0]


def run_ga(pool_slugs: list, locked_slugs: frozenset, precomputed: dict, era_key: str,
           population_size: int = 200, generations: int = 200, mutation_rate: float = 0.05,
           elitism_ratio: float = 0.1, random_seed=None, progress_callback=None) -> tuple:
    rng = random.Random(random_seed)
    population = [create_individual(pool_slugs, locked_slugs, rng) for _ in range(population_size)]
    best_individual = None
    best_fitness = -1.0
    no_improve_count = 0
    current_mutation_rate = mutation_rate
    for gen in range(generations):
        fitnesses = [team_fitness(ind, precomputed, era_key, locked_slugs) for ind in population]
        gen_best_ind, gen_best_fit = max(zip(population, fitnesses), key=lambda x: x[1])
        if gen_best_fit > best_fitness:
            best_fitness = gen_best_fit
            best_individual = gen_best_ind
            no_improve_count = 0
            current_mutation_rate = max(0.02, current_mutation_rate - 0.01)
        else:
            no_improve_count += 1
            if no_improve_count >= 5:
                current_mutation_rate = min(0.3, current_mutation_rate + 0.02)
        if no_improve_count >= 20:
            break
        elite_count = int(population_size * elitism_ratio)
        sorted_pop = sorted(zip(population, fitnesses), key=lambda x: -x[1])
        new_population = [ind for ind, _ in sorted_pop[:elite_count]]
        while len(new_population) < population_size:
            p1 = tournament_selection(population, fitnesses, 3, rng)
            p2 = tournament_selection(population, fitnesses, 3, rng)
            child = crossover(p1, p2, locked_slugs, pool_slugs, rng)
            child = mutate(child, locked_slugs, pool_slugs, rng, current_mutation_rate)
            new_population.append(child)
        population = new_population
        if progress_callback:
            progress_callback(gen + 1, generations, best_fitness)
    return best_individual, best_fitness


# ── Self‑tests ────────────────────────────────────────────────────────────────

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

    print("\n  core_team.py — self-test\n")

    # Fixtures
    def _pkm(name, t1, t2="None"):
        return {"form_name": name, "type1": t1, "type2": t2}

    charizard = _pkm("Charizard", "Fire", "Flying")
    blastoise = _pkm("Blastoise", "Water")
    team1 = [charizard, None, None, None, None, None]
    team2 = [charizard, blastoise, None, None, None, None]
    team_cc = [charizard, charizard, None, None, None, None]

    ERA = "era3"
    _, valid_types, _ = calc.CHARTS[ERA]
    type_to_bit = {t: 1 << i for i, t in enumerate(valid_types)}

    # ── build_team_defense ───────────────────────────────────────────────────
    td = build_team_defense(team1, ERA)
    if td["Rock"][0]["multiplier"] == 4.0:
        ok("build_team_defense: Charizard Rock x4")
    else:
        fail("build_team_defense Rock", str(td["Rock"][0]["multiplier"]))

    # ── build_unified_rows ───────────────────────────────────────────────────
    rows = build_unified_rows(td, ERA)
    rock_row = next(r for r in rows if r["type"] == "Rock")
    if rock_row["weak_members"] == [("Charizard", 4.0)]:
        ok("build_unified_rows: Rock row correct")
    else:
        fail("build_unified_rows Rock", str(rock_row))

    # ── gap_label ────────────────────────────────────────────────────────────
    if gap_label(3, 0) == "!! CRITICAL":
        ok("gap_label: CRITICAL")
    else:
        fail("gap_label CRITICAL", gap_label(3, 0))
    if gap_label(3, 1) == "!  MAJOR":
        ok("gap_label: MAJOR")
    else:
        fail("gap_label MAJOR", gap_label(3, 1))
    if gap_label(2, 0) == ".  MINOR":
        ok("gap_label: MINOR")
    else:
        fail("gap_label MINOR", gap_label(2, 0))

    # ── build_weakness_pairs ─────────────────────────────────────────────────
    pairs = build_weakness_pairs(team_cc, ERA)
    if len(pairs) == 1 and pairs[0]["shared_count"] == 3:
        ok("build_weakness_pairs: two Charizard share 3 weaknesses")
    else:
        fail("build_weakness_pairs two Charizard", str(pairs))

    # ── hitting_types ────────────────────────────────────────────────────────
    if hitting_types(ERA, "Fire", "Flying", "Grass") == ["F", "F"]:
        ok("hitting_types: Charizard vs Grass -> [F,F]")
    else:
        fail("hitting_types Charizard/Grass", str(hitting_types(ERA, "Fire", "Flying", "Grass")))

    # ── build_team_offense ───────────────────────────────────────────────────
    to = build_team_offense(team1, ERA)
    grass_hitters = to["Grass"]
    if len(grass_hitters) == 1 and grass_hitters[0]["form_name"] == "Charizard":
        ok("build_team_offense: Charizard hits Grass SE")
    else:
        fail("build_team_offense Grass", str(grass_hitters))

    # ── build_offense_rows ───────────────────────────────────────────────────
    rows_off = build_offense_rows(to, ERA)
    if len(rows_off) == len(calc.TYPES_ERA3) and rows_off[0]["hitters"]:
        ok("build_offense_rows: correct length and sorted")
    else:
        fail("build_offense_rows", f"len={len(rows_off)} first hitters={rows_off[0]['hitters']}")

    # ── coverage_gaps ────────────────────────────────────────────────────────
    gaps = coverage_gaps(rows_off)
    if "Normal" in gaps:
        ok("coverage_gaps: Normal is a gap for Charizard")
    else:
        fail("coverage_gaps", str(gaps))

    # ── weakness_types ───────────────────────────────────────────────────────
    weak = weakness_types(charizard, ERA)
    if "Rock" in weak and "Water" in weak and "Electric" in weak:
        ok("weakness_types: Charizard weak to Rock, Water, Electric")
    else:
        fail("weakness_types", str(weak))

    # ── se_types ─────────────────────────────────────────────────────────────
    combo = [{"type": "Fire"}, {"type": "Water"}]
    se = se_types(combo, ERA)
    if "Grass" in se and "Fire" in se:
        ok("se_types: Fire+Water hits Grass and Fire SE")
    else:
        fail("se_types", str(se))

    # ── build_offensive_coverage ─────────────────────────────────────────────
    member_res = [{"se_types": ["Fire", "Water"]}, {"se_types": ["Grass"]}]
    cov = build_offensive_coverage(member_res, ERA)
    if "Fire" in cov["covered"] and "Grass" in cov["covered"] and "Electric" not in cov["covered"]:
        ok("build_offensive_coverage: correct coverage")
    else:
        fail("build_offensive_coverage", str(cov))

    # ── empty_member_result ─────────────────────────────────────────────────
    emp = empty_member_result("Test")
    if emp["form_name"] == "Test" and emp["moves"] == [] and emp["weakness_types"] == []:
        ok("empty_member_result: correct shape")
    else:
        fail("empty_member_result", str(emp))

    # ── format_weak_line ────────────────────────────────────────────────────
    if format_weak_line(["Rock", "Water"]) == "Weak:  Rock  Water":
        ok("format_weak_line: correct")
    else:
        fail("format_weak_line", format_weak_line(["Rock", "Water"]))

    # ── format_move_pair ────────────────────────────────────────────────────
    if "Flamethrower" in format_move_pair("Flamethrower", "Air Slash"):
        ok("format_move_pair: basic")
    else:
        fail("format_move_pair", format_move_pair("Flamethrower", "Air Slash"))

    # ── format_se_line ──────────────────────────────────────────────────────
    if format_se_line(["Fire", "Water"], ERA).startswith("SE: 2 / 18"):
        ok("format_se_line: correct format")
    else:
        fail("format_se_line", format_se_line(["Fire", "Water"], ERA))

    # ── team_offensive_gaps ─────────────────────────────────────────────────
    gaps_off = team_offensive_gaps(team1, ERA)
    if "Normal" in gaps_off:
        ok("team_offensive_gaps: Normal gap for Charizard")
    else:
        fail("team_offensive_gaps", str(gaps_off))

    # ── team_defensive_gaps ─────────────────────────────────────────────────
    # Two Charizard → Rock should be a gap
    gaps_def_cc = team_defensive_gaps(team_cc, ERA)
    if "Rock" in gaps_def_cc:
        ok("team_defensive_gaps: two Charizard -> Rock critical")
    else:
        fail("team_defensive_gaps two Charizard", str(gaps_def_cc))

    # Charizard + Blastoise → Rock not critical (only 1 weak)
    gaps_def_cb = team_defensive_gaps(team2, ERA)
    if "Rock" not in gaps_def_cb:
        ok("team_defensive_gaps: Charizard+Blastoise -> Rock not critical")
    else:
        fail("team_defensive_gaps Char+Blas", str(gaps_def_cb))

    # ── candidate_passes_filter ─────────────────────────────────────────────
    if candidate_passes_filter(["Ground"], ["Electric"], ["Electric"], ERA):
        ok("candidate_passes_filter: Ground passes")
    else:
        fail("candidate_passes_filter")

    # ── patchability_score ──────────────────────────────────────────────────
    if patchability_score(["Normal"], ERA) == 1.0:
        ok("patchability_score: Normal = 1")
    else:
        fail("patchability_score", str(patchability_score(["Normal"], ERA)))

    # ── shared_weakness_count ───────────────────────────────────────────────
    # Candidate not in team -> should be 0
    cnt = shared_weakness_count(["Water"], team1, ERA)
    if cnt == 0:
        ok("shared_weakness_count: candidate not in team -> 0")
    else:
        fail("shared_weakness_count", str(cnt))

    # ── new_weak_pairs ──────────────────────────────────────────────────────
    pairs_new = new_weak_pairs(["Water"], team1, ERA)
    if pairs_new == []:
        ok("new_weak_pairs: candidate not in team -> []")
    else:
        fail("new_weak_pairs", str(pairs_new))

    # ── score_candidate ─────────────────────────────────────────────────────
    score = score_candidate(["Ground"], team1, ERA, ["Electric"], ["Electric"], 5)
    if score > 0:
        ok("score_candidate: returns number")
    else:
        fail("score_candidate", str(score))

    # ── rank_candidates ─────────────────────────────────────────────────────
    candidates = [{"slug": "garchomp", "form_name": "Garchomp", "types": ["Dragon","Ground"], "base_stats": None}]
    ranked = rank_candidates(candidates, team1, ERA, ["Electric"], [], 5)
    if len(ranked) == 1 and ranked[0]["slug"] == "garchomp":
        ok("rank_candidates: basic")
    else:
        fail("rank_candidates", str(ranked))

    # ──────────────────────────────────────────────────────────────────────────
    # Tests for precompute_pokemon_data and team_fitness
    # ──────────────────────────────────────────────────────────────────────────
    print("\n  --- precompute_pokemon_data tests ---")
    # Create minimal mock Pokémon contexts
    mock_pkm_list = [
        {
            "pokemon": "charizard",
            "form_name": "Charizard",
            "types": ["Fire", "Flying"],
            "type1": "Fire",
            "type2": "Flying",
            "base_stats": {"hp": 78, "attack": 84, "defense": 78,
                           "special-attack": 109, "special-defense": 85, "speed": 100},
        },
        {
            "pokemon": "blastoise",
            "form_name": "Blastoise",
            "types": ["Water"],
            "type1": "Water",
            "type2": "None",
            "base_stats": {"hp": 79, "attack": 83, "defense": 100,
                           "special-attack": 85, "special-defense": 105, "speed": 78},
        },
        {
            "pokemon": "gengar",
            "form_name": "Gengar",
            "types": ["Ghost", "Poison"],
            "type1": "Ghost",
            "type2": "Poison",
            "base_stats": {"hp": 60, "attack": 65, "defense": 60,
                           "special-attack": 130, "special-defense": 75, "speed": 110},
        },
    ]

    precomp = precompute_pokemon_data(mock_pkm_list, "era3")

    # Check keys exist
    if set(precomp.keys()) == {"charizard", "blastoise", "gengar"}:
        ok("precompute_pokemon_data: all three slugs present")
    else:
        fail("precompute_pokemon_data keys", str(precomp.keys()))

    # Check Charizard
    cz = precomp["charizard"]
    if cz["form_name"] == "Charizard" and cz["role"] == "special" and cz["total_stats"] == 534:
        ok("precompute_pokemon_data: Charizard basic fields")
    else:
        fail("precompute_pokemon_data Charizard fields", f"role={cz['role']}, total={cz['total_stats']}")

    # Offensive bitmask check: Fire hits Grass, Ice, Bug, Steel SE (at least)
    if cz["offensive_bitmask"] != 0:
        ok("precompute_pokemon_data: Charizard offensive bitmask non-zero")
    else:
        fail("precompute_pokemon_data Charizard off_mask zero")

    # Defensive bitmask: Charizard weak to Rock, Water, Electric (among others)
    if cz["defensive_bitmask"] != 0:
        ok("precompute_pokemon_data: Charizard defensive bitmask non-zero")
    else:
        fail("precompute_pokemon_data Charizard def_mask zero")

    # Defense multipliers: should have all 18 types
    if len(cz["defense_multipliers"]) == 18:
        ok("precompute_pokemon_data: defense_multipliers has 18 entries")
    else:
        fail("precompute_pokemon_data defense_multipliers length", str(len(cz["defense_multipliers"])))

    # Check one known multiplier: Rock vs Charizard = 4.0
    if cz["defense_multipliers"].get("Rock") == 4.0:
        ok("precompute_pokemon_data: Charizard Rock multiplier 4.0")
    else:
        fail("precompute_pokemon_data Rock multiplier", str(cz["defense_multipliers"].get("Rock")))

    # Blastoise (single type)
    bl = precomp["blastoise"]
    # Blastoise has Atk 83, SpA 85 → mixed attacker
    if bl["role"] == "mixed" and bl["defense_multipliers"].get("Electric") == 2.0:
        ok("precompute_pokemon_data: Blastoise basic")
    else:
        fail("precompute_pokemon_data Blastoise", f"role={bl['role']}, Elec={bl['defense_multipliers'].get('Electric')}")

    # Gengar (Ghost/Poison)
    ga = precomp["gengar"]
    if ga["defense_multipliers"].get("Normal") == 0.0:
        ok("precompute_pokemon_data: Gengar Normal immunity")
    else:
        fail("precompute_pokemon_data Gengar Normal", str(ga["defense_multipliers"].get("Normal")))

    print("\n  --- team_fitness tests ---")
    # Create a 6-member team from our mock Pokémon (duplicates allowed for testing)
    team_slugs = frozenset(["charizard", "blastoise", "gengar", "charizard", "blastoise", "gengar"])
    fitness = team_fitness(team_slugs, precomp, "era3")
    if 0 <= fitness <= 100:
        ok("team_fitness: returns value in range 0-100")
    else:
        fail("team_fitness range", f"got {fitness}")

    # Test with incomplete team (<6)
    incomplete = frozenset(["charizard", "blastoise"])
    fit_incomplete = team_fitness(incomplete, precomp, "era3")
    if fit_incomplete == 0.0:
        ok("team_fitness: incomplete team returns 0")
    else:
        fail("team_fitness incomplete", f"got {fit_incomplete}")

    # Test with perfect offensive coverage (create a team covering all types)
    # We'll manually craft a precomputed dict where all Pokémon have full off_mask
    all_types_mask = (1 << len(valid_types)) - 1
    perfect_precomp = {}
    for i in range(6):
        slug = f"perfect{i}"
        perfect_precomp[slug] = {
            "offensive_bitmask": all_types_mask,
            "defensive_bitmask": 0,
            "defense_multipliers": {t: 1.0 for t in valid_types},
            "role": "special",
            "total_stats": 720,
        }
    perfect_team = frozenset(perfect_precomp.keys())
    fit_perfect = team_fitness(perfect_team, perfect_precomp, "era3")
    # Offensive: 40, Defensive: 30 (no weaknesses), Role: 5 (one role), Individual: 15, Penalty: 0
    # Role: distinct_roles=1 -> (1/3)*15 = 5
    # Individual: each total=720 -> indiv=100, sum=600 -> (600/600)*15 = 15
    expected_perfect = 40 + 30 + 5 + 15 - 0
    if abs(fit_perfect - expected_perfect) < 0.01:
        ok("team_fitness: perfect team scores 90.0")
    else:
        fail("team_fitness perfect team", f"expected {expected_perfect}, got {fit_perfect}")

    # Test defensive critical gaps (using Fire, which definitely exists)
    fire_bit = type_to_bit["Fire"]
    weak_precomp = {}
    for i in range(6):
        slug = f"weak{i}"
        weak_precomp[slug] = {
            "offensive_bitmask": 0,
            "defensive_bitmask": fire_bit,
            "defense_multipliers": {t: (2.0 if t == "Fire" else 1.0) for t in valid_types},
            "role": "physical",
            "total_stats": 500,
        }
    weak_team = frozenset(weak_precomp.keys())
    fit_weak = team_fitness(weak_team, weak_precomp, "era3")
    expected_defensive = ((len(valid_types) - 1) / len(valid_types)) * 30
    expected = expected_defensive + 5 + 10.416  # role=5, indiv=10.416
    if abs(fit_weak - expected) < 0.1:
        ok("team_fitness: defensive critical gap reduces score")
    else:
        fail("team_fitness defensive gap", f"expected ~{expected}, got {fit_weak}")

    # Test weakness overlap penalty (using Fire and Water)
    fire_bit = type_to_bit["Fire"]
    water_bit = type_to_bit["Water"]
    mask = fire_bit | water_bit
    overlap_precomp = {}
    for i in range(6):
        slug = f"overlap{i}"
        overlap_precomp[slug] = {
            "offensive_bitmask": 0,
            "defensive_bitmask": mask,
            "defense_multipliers": {t: (2.0 if t in ("Fire", "Water") else 1.0) for t in valid_types},
            "role": "mixed",
            "total_stats": 500,
        }
    overlap_team = frozenset(overlap_precomp.keys())
    fit_overlap = team_fitness(overlap_team, overlap_precomp, "era3")
    # 2 critical gaps (Fire and Water) -> defensive = ((18-2)/18)*30 ≈ 26.666
    expected_overlap = 26.666 + 5 + 10.416 - 15  # penalty 15
    if abs(fit_overlap - expected_overlap) < 0.1:
        ok("team_fitness: weakness overlap penalty applied")
    else:
        fail("team_fitness overlap penalty", f"expected ~{expected_overlap}, got {fit_overlap}")

    print("\n  --- GA core functions tests ---")
    try:
        rng = random.Random(42)
        pool_slugs = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
        locked = frozenset()
        precomputed_ga = {
            s: {
                "defense_multipliers": {t: 1.0 for t in valid_types},
                "offensive_bitmask": 0,
                "defensive_bitmask": 0,
                "total_stats": 500,
                "role": "physical",
                "base_stats": {},
            }
            for s in pool_slugs
        }
        ind = create_individual(pool_slugs, locked, rng)
        ok("create_individual: returns 6-element frozenset") if len(ind) == 6 else fail("create_individual", str(ind))
        parent1 = frozenset(["a", "b", "c", "d", "e", "f"])
        parent2 = frozenset(["a", "g", "h", "i", "j", "b"])
        child = crossover(parent1, parent2, locked, pool_slugs, rng)
        ok("crossover: returns 6-element frozenset") if len(child) == 6 else fail("crossover", str(child))
        mutated = mutate(parent1, locked, pool_slugs, rng)
        ok("mutate: returns 6-element frozenset") if len(mutated) == 6 else fail("mutate", str(mutated))
        pop = [frozenset(["a"]), frozenset(["b"]), frozenset(["c"])]
        fits = [0.5, 0.9, 0.2]
        selected = tournament_selection(pop, fits, 2, rng)
        # With seed 42, sample is ["a", "c"] → best is "a"
        if selected == frozenset(["a"]):
            ok("tournament_selection: picks best from sample (seed 42)")
        else:
            fail("tournament_selection", f"expected frozenset(['a']), got {selected}")
        best, fit = run_ga(pool_slugs, locked, precomputed_ga, ERA, population_size=10, generations=5, random_seed=42)
        ok("run_ga: completes") if len(best) == 6 and 0 <= fit <= 100 else fail("run_ga", f"best={best}, fit={fit}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        fail("GA core functions tests", f"unhandled exception: {e}")

    print()
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        try:
            _run_tests()
        except Exception as e:
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        print("This module is a library; run with --autotest to test.")