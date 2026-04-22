# Joint Team Optimisation — Genetic Algorithm Implementation Guide

> **STATUS:** Baseline GA (Phases 0–7) is **COMPLETE** and integrated as menu key `J`.
> The sections below describe the optional enhancement levels that can be added incrementally.

---

## ✅ Completed Baseline (Phases 0–7)

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Pre‑computation (`precompute_pokemon_data`) | ✅ Done |
| 1 | Fitness function (`team_fitness`) | ✅ Done |
| 2 | GA core functions (`create_individual`, `crossover`, `mutate`, `tournament_selection`, `run_ga`) | ✅ Done |
| 3–4 | Integration: `run_joint_team` in `feat_team_builder.py`, menu key `J` in CLI/TUI | ✅ Done |
| 5 | Candidate pool filtering (`filter_pure_level_up_evolutions`) | ✅ Done |
| 6 | Display (`display_joint_team_result`) | ✅ Done |
| 7 | Tests in `core_team.py` and `feat_team_builder.py` | ✅ Done |

**Current behavior:**
- Population: 200, Generations: 200
- Fitness weights: Offensive 40%, Defensive 30%, Role 15%, Individual 15%
- Selection: Tournament (size 3), Crossover: Uniform set, Mutation: 5%, Elitism: 10%
- Early stopping: 20 generations no improvement
- Candidate pool: all Pokémon in game (filtered by generation, excluding pure level‑up evolutions and Mega/Gigantamax)
- Output: best team with fitness score and type coverage summary

---

## 🔮 Optional Enhancements (Levels 1–4)

These levels build on the baseline GA to improve team quality and performance.

### Level 1 – Improved Fitness Function

**Goal:** Add move‑based synergy, type core bonuses, and speed tier analysis.

**Tasks:**
1. Extend `precompute_pokemon_data` to include presence of entry hazards, setup moves, priority moves.
2. In `team_fitness`, add bonuses:
   - +2 for entry hazard, +3 for setup sweeper, +1 for priority move.
   - +3 for type cores (Fire/Water/Grass, Dragon/Steel/Fairy, etc.).
   - Penalise all‑same speed tier (-5), reward balanced spread (+5).
3. Update tests.

**Files:** `core_team.py`  
**Estimated lines:** +100

---

### Level 2 – Adaptive GA Parameters

**Goal:** Dynamically adjust mutation rate, population size, and add early stopping (already present).

**Tasks:**
1. Mutation rate adapts based on improvement (already implemented in `run_ga`).
2. Increase population size if diversity drops (measured via fitness std dev).
3. Log statistics if verbose mode.

**Files:** `core_team.py`  
**Estimated lines:** +50

---

### Level 3 – Surrogate Model (Random Forest)

**Goal:** Use a lightweight surrogate model to prescreen individuals, reducing exact fitness evaluations.

**Tasks:**
1. Add `scikit-learn` to `requirements.txt`.
2. Extract team features (one‑hot roles, bitmasks, total stats) → fixed‑length vector.
3. Train `RandomForestRegressor` every 10 generations on evaluated teams.
4. Prescreen: only evaluate exactly if predicted fitness is in top 30%.
5. Measure speedup (target >3×).

**Files:** `core_team.py`, `requirements.txt`  
**New dependency:** `scikit-learn`  
**Estimated lines:** +150

---

### Level 4 – Memetic Algorithm (GA + Local Search)

**Goal:** Apply greedy local search to elite individuals each generation to polish solutions.

**Tasks:**
1. Implement `local_search(team_slugs, ...)` that tries single‑member replacements.
2. Restrict search to same‑role replacements to reduce attempts.
3. Apply to top 10% individuals every 5 generations, or when stagnation occurs.
4. Integrate with surrogate model if active.

**Files:** `core_team.py`  
**Estimated lines:** +120

---

## 📋 Summary of Dependencies and Order

| Level | Requires previous level | New dependencies | Expected speed impact |
|-------|------------------------|------------------|----------------------|
| 1 | 0 (baseline) | None | Negligible |
| 2 | 1 | None | Slightly faster |
| 3 | 2 | scikit-learn | 3–5× faster |
| 4 | 3 | None | Slower per generation, better quality |

**Recommended order:** Implement Level 1 → 2 → 3 → 4 incrementally, testing after each.