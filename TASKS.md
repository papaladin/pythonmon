# TASKS.md

# STEP 4 — Team moveset synergy

**Roadmap item:** Team features / Step 4
**Status:** ✅ COMPLETE — all steps done (§66–§71)

Goal:

Reuse the **single-Pokémon moveset recommendation engine (Option 4)** so it can compute
recommended movesets for all team members and produce a **team-level offensive coverage summary**.

---

# Design decisions (already approved)

These decisions must **not be revisited during implementation**.

* The **user selects one mode** for the entire team.
* Modes available:

  * Coverage
  * Counter
  * STAB
* The engine runs **fully automatically** (no locked moves prompting).
* Output is **compact**, allowing all 6 members to fit on one screen.
* The screen includes a **team coverage summary**.
* Coverage summary must report:

  * types hit SE by ≥1 member
  * coverage gaps
  * overlap (types covered by ≥3 members)
* Feature is accessible via **menu key `S`**.

---

# Implementation tasks

Each implementation step must include:

1. implementation
2. local `_run_tests()` additions in the module
3. integration into `run_tests.py`
4. documentation updates (`TASKS`, `HISTORY`, `ARCHITECTURE`, `README` if needed)

No step is considered complete until **tests pass and documentation is updated**.

---

# 4.1 Create team moveset module

Status: ✅ COMPLETE (§66)

Created module `feat_team_moveset.py` with:

* `_MODES` constant mapping key letters to mode strings
* `_empty_member_result(form_name)` defining the agreed result structure
* `recommend_team_movesets(team_ctx, game_ctx, mode)` — stub returning shaped dicts
* `_mode_prompt()` — interactive `(C)overage / co(U)nter / (S)TAB` selector
* `run(team_ctx, game_ctx)` — entry point with empty-team guard
* 14 offline tests; all pass

`feat_moveset.py` was not modified.

**Note:** `pokemain.py` wiring (import, menu key `S`, handler, context guards)
was added ahead of schedule. This covers the integration work planned for step 4.5.
Verify before closing 4.5.

---

# 4.2 Implement team moveset recommendation

Status: ✅ COMPLETE (§67)

Added to `feat_team_moveset.py`:

* `_weakness_types(pkm_ctx, era_key) → list[str]`
* `_se_types(combo, era_key) → list[str]`
* `recommend_team_movesets` — real engine calling `build_candidate_pool` +
  `select_combo` per slot; graceful degradation on empty pool

36 offline tests; all pass. `feat_moveset.py` was not modified.

---

# 4.3 Implement compact team display

Status: ✅ COMPLETE (§68)

Added to `feat_team_moveset.py`:

* `_format_weak_line(weakness_types) → str`
* `_format_move_pair(left, right) → str`  left col 22 chars; `"—"` for None
* `_format_se_line(se_types, era_key) → str`
* `_display_member_block(result, era_key)`  5-line block per member
* `display_team_movesets(results, game_ctx, mode)`  full screen
* `run()` updated to call `display_team_movesets`
* `"types"` field added to member result dict

45 offline tests; all pass.

---

# 4.4 Implement team offensive coverage analysis

Status: ✅ COMPLETE (§70)

Added to `feat_team_moveset.py`:

* `build_offensive_coverage(member_results, era_key) → dict`
  Aggregates `se_types` from each member result. Returns `covered`, `gaps`,
  `overlap` (≥3 members), `counts`, `total_types`. Does not recompute movesets.
* `_display_coverage_summary(coverage)` — Covered / Gaps / Overlap block
* `display_team_movesets` updated to call both; stub footer removed

61 offline tests; all pass.

---

# 4.5 Add menu integration

Status: ✅ COMPLETE (§71)

`pokemain.py` wiring was added ahead of schedule in §65 and verified complete
during the 4.5 closure pass (§71). All four checkpoints confirmed:

1. `feat_team_moveset` import inside the `try/except ModuleNotFoundError` block
2. Menu line `S. Team moveset synergy` gated behind `team_size > 0` (same
   condition as V and O)
3. Handler guards: `game_ctx is None` → "Select a game first";
   empty team → "Load a team first"
4. `feat_team_moveset.run(team_ctx, game_ctx)` called in the happy path

No code changes required.

---

# Completion criteria

Step 4 is complete when:

* team movesets compute for all 6 members
* compact display works
* coverage summary works
* menu key `S` works
* all offline tests pass
* documentation is fully updated

---

# Additional Notes

* Implementation must remain **fast and overview-focused**.
* Users can still run **Option 4** for detailed single-Pokémon moveset tuning.
* Step 4 is meant to provide **team-level synergy insights**, not replace individual analysis.

---

## Recently completed

| Task                                        | Outcome                                                                 | History |
| ------------------------------------------- | ----------------------------------------------------------------------- | ------- |
| Step 4.5: menu integration verified + docs  | `pokemain.py` confirmed; `README/ROADMAP/TASKS/HISTORY` closed          | §71     |
| Step 4.4: team offensive coverage summary   | `feat_team_moveset.py` extended, 61 tests                               | §70     |
| Step 4.3: compact team display              | `feat_team_moveset.py` extended, 45 tests                               | §68     |
| Step 4.2: team moveset engine               | `feat_team_moveset.py` extended, 36 tests                               | §67     |
| Step 4.1: module stub created               | `feat_team_moveset.py` created, 14 tests                                | §66     |
| Bugfix: move cache key mismatch             | `feat_moveset_data.py` fixed, 2 regression tests                        | §69     |
| Step 3b: best scored move inline in O table | `feat_team_offense.py` extended, 50 tests                               | §63     |
| Step 3a: team offensive coverage by type    | `feat_team_offense.py`, O key, 38 tests                                 | §62     |
| Step 2: team defensive analysis             | `feat_team_analysis.py`, V key, 58 tests                                | §60–§61 |
| Documentation restructure                   | README/ARCHITECTURE/ROADMAP/TASKS/HISTORY/AI_WORKFLOW/DEVELOPMENT_RULES | §62     |
