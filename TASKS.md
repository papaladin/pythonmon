# TASKS.md

# STEP 4 — Team moveset synergy

**Roadmap item:** Team features / Step 4
**Status:** NOT STARTED

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

Status: IN PROGRESS

Create new module:

```
feat_team_moveset.py
```

Responsibilities when all steps are done:

* orchestrate team-level moveset recommendations
* aggregate per-member results
* compute team coverage
* format team display

Constraint:

```
feat_moveset.py must NOT be modified
```

Prompt user for a mode before computing movesets:

```
(C)overage
co(U)nter
(S)TAB
```

Mode applies to **all 6 team members**.


After mode choice, the new module will **reuse the engine of feat_moveset.py**.
But that is mainly foreseen to be done in the next tasks steps, for now a stub will do.


### Tests

Add `_run_tests()` to the module.

Initial tests should verify:

* module imports correctly
* minimal team context can be processed
* placeholder structures for member results work

Tests must be **fully offline**.

### Test runner integration

Update:

```
run_tests.py
```

Add the new module test suite.

Verify the global test count.

### Documentation updates

Update:

* `ARCHITECTURE.md`
  Add the new module and its role.

* `HISTORY.md`
  Record module creation.

* `TASKS.md`
  Mark 4.1 as completed when done.



---

# 4.2 Implement team moveset recommendation

Status: TO DO

Add function:

```
recommend_team_movesets(team_ctx, game_ctx, mode) in feat_team_moveset.py
```

Behavior:

* iterate over all team slots
* run the same scoring engine used in Option 4
* compute the best moveset for each member
* return all results

Return type:

```
list[TeamMemberMoveset]
```

Each result must contain:

* Pokémon identifier
* recommended moves
* weakness summary
* super-effective coverage count

Constraint:

Team logic must **reuse the existing engine** from `feat_moveset.py`.
It must **not duplicate scoring logic**.

### Tests

Add tests verifying:

* moveset generation for a fake team
* each member returns ≤4 moves
* coverage modes behave consistently

Use **fake move pools** to avoid network calls.

Ensure test fixtures include **≥4 move types** to avoid coverage deduplication.

### Test runner integration

If necessary, update `run_tests.py` with new tests.

Verify:

```
python run_tests.py --offline
```

All tests pass.

### Documentation updates

Update:

* `ARCHITECTURE.md`
  Document interaction between `feat_team_moveset` and `feat_moveset`.

* `HISTORY.md`
  Record implementation of team moveset engine.

* `TASKS.md`
  Mark step 4.2 complete.

---

# 4.3 Implement compact team display

Status: TO DO

Each member block must display:

```
[Pokemon Name]
Weakness: Fire / Rock / Electric
Move1      Move2
Move3      Move4
SE hits: X
```

Rules:

* Maximum **4 moves**
* **2-per-line layout**
* show weakness line
* show individual SE coverage count

### Tests

Add tests verifying:

* formatting helpers
* move layout structure
* weakness summary formatting

Tests should verify **data structure and formatting logic**, not exact print spacing.

### Test runner integration

Update `run_tests.py` if necessary

Verify the full test suite passes.

### Documentation updates

Update:

* `README.md`
  Describe the new team display feature.

* `HISTORY.md`
  Record display implementation.

* `TASKS.md`
  Mark step 4.3 complete.

---

# 4.4 Implement team offensive coverage analysis

Status: TO DO

Add function:

```
build_offensive_coverage(team_ctx, game_ctx)
```
Input:
  result list returned by recommend_team_movesets() as performed in step 4.2

Must NOT recompute movesets.
Must only aggregate coverage from member_results.

Responsibilities:

* aggregate recommended moves from all members
* compute super-effective coverage across all types

Track:

* types hit SE by >1 member
* coverage gaps (0–1 coverage)
* overlap (≥3 members coverage)

Coverage score:

```
coverage_percent = covered_types / total_types
```

Example output:

```
Team coverage: 14 / 18 types hit SE
Gaps: Dragon, Electric
Overlap: Water (4), Ground (3)
```

### Tests

Add tests verifying:

* coverage aggregation
* correct gap detection
* overlap detection

Edge cases:

* empty team
* single-type coverage

### Test runner integration

Update `run_tests.py`.

Run full offline suite.

### Documentation updates

Update:

* `ARCHITECTURE.md`
  Document team coverage analysis logic.

* `HISTORY.md`
  Record coverage analysis feature.

* `TASKS.md`
  Mark step 4.4 complete.

---

# 4.5 Add menu integration

Status: TO DO

Modify:

```
pokemain.py
```

Add menu key:

```
S — Team moveset synergy
```

Conditions:

* team loaded
* game loaded

Handler must:

1. prompt for mode

```
(C)overage
co(U)nter
(S)TAB
```

2. run team recommendation
3. display results
4. show team coverage summary

### Tests

Add minimal integration tests verifying:

* module imports correctly
* menu key is registered
* handler executes without crash

### Test runner integration

Update `run_tests.py`.

Run full suite.

### Documentation updates

Update:

* `README.md`
  Document new menu key.

* `ROADMAP.md`
  Mark Step 4 completed.

* `HISTORY.md`
  Record final integration.

* `TASKS.md`
  Replace this file with **Step 5** after completion.

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
| Step 3b: best scored move inline in O table | `feat_team_offense.py` extended, 50 tests                               | §63     |
| Step 3a: team offensive coverage by type    | `feat_team_offense.py`, O key, 38 tests                                 | §62     |
| Step 2: team defensive analysis             | `feat_team_analysis.py`, V key, 58 tests                                | §60–§61 |
| Documentation restructure                   | README/ARCHITECTURE/ROADMAP/TASKS/HISTORY/AI_WORKFLOW/DEVELOPMENT_RULES | §62     |