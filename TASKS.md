# TASKS.md
# Current active task and granular steps

> This file tracks only the task currently in progress.
> When a task completes, the outcome moves to HISTORY.md and this file is updated.
> For what comes next, see ROADMAP.md.

---

## Current task: Step 3b — Team offensive coverage by learnable moves

**Roadmap item:** Team features / Step 3b
**Status:** Not started
**Goal:** Extend step 3a — instead of only using member types, check actual learnable
moves in cache to find which specific moves can hit each type SE.
This gives richer information: "can hit Electric SE, but only Blastoise with Thunderbolt."

### Context / constraints
- Builds on `feat_team_offense.py` — extends the same table with move-level detail
- Requires each member's learnset to be cached (may trigger network fetch on first run)
- A member with a Water-type move can hit Fire SE even if their own type isn't Water
- Must show progress if fetching multiple learnsets (up to 6 API calls)
- Still needs to work per era (move type charts are era-aware)

### Relevant files
- `feat_team_offense.py` — base logic to extend
- `pkm_cache.py` — `get_learnset(variety_slug, game_slug)` for move pool
- `pkm_pokeapi.py` — fallback fetch if learnset not cached
- `matchup_calculator.py` — `get_multiplier` for move type vs target type

### Steps

- [ ] **3b-1** Clarify scope with user
  Key question: does 3b *replace* the type-based table or *extend* it?
  Options: (A) separate screen, (B) same O screen with a toggle, (C) extra columns.

- [ ] **3b-2** Design the output
  Show per-member which moves hit each type SE, not just which types.
  Propose layout and confirm before implementing.

- [ ] **3b-3** Write learnset-to-offense logic
  For each member: fetch learnset, iterate moves, check move type vs target type.
  Filter to moves the member can actually learn in the selected game.

- [ ] **3b-4** Write tests (cache-dependent, --withcache flag)

- [ ] **3b-5** Implement + wire into pokemain (new key or extend O)

- [ ] **3b-6** Full test suite, zero failures

- [ ] **3b-7** Update README, ROADMAP, TASKS, HISTORY

---

## Recently completed

| Task | Outcome | History |
|---|---|---|
| Step 3a: team offensive coverage by type | `feat_team_offense.py`, O key, 38 tests | §62 |
| Step 2: team defensive analysis | `feat_team_analysis.py`, V key, 58 tests | §60–§61 |
| Documentation restructure | README/ARCHITECTURE/ROADMAP/TASKS/HISTORY/AI_WORKFLOW/DEVELOPMENT_RULES | §62 |
