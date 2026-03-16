# TASKS.md

# Current active task and granular steps

> This file tracks only the task currently in progress.
> When a task completes, the outcome moves to HISTORY.md and this file is updated.
> For what comes next, see ROADMAP.md.

---

# Current task: Step 4 — Team moveset synergy

**Roadmap item:** Team features / Step 4
**Status:** Not started
**Goal:** Run moveset recommendation for each team member, then aggregate results into a team-level coverage summary.

This feature extends the existing **single-Pokémon moveset recommendation engine (Option 4)** to operate at the **team level**.

Design decisions already agreed:

* The **user selects a single mode** for the entire team (Coverage / Counter / STAB).
* The engine runs **fully automatically** (no locked-move prompting).
* Output is **compact**, optimized for viewing all six team members on one screen.
* Team summary includes **coverage gaps and overlap** (types covered by ≥3 members).
* Feature is accessible via **menu key `S`**.

---

# Task 4-1: Implement Team-Wide Moveset Recommendation Mode

**Description**
Extend moveset recommendations to operate at the team level while **reusing the existing single-Pokémon recommendation engine**.

The system should compute a recommended moveset for each member and display them compactly.

---

## Sub-tasks

### 1. Create new module for team movesets

**[TO BE DONE]**

Create a new module:

```
feat_team_moveset.py
```

Responsibilities of this module:

* Team-level moveset orchestration
* Aggregating results across team members
* Display logic for team-level output
* Team coverage analysis

This module must **not modify `feat_moveset.py`**, but reuse its logic.

---

### 2. Implement team moveset recommendation function

Add a function:

```
recommend_team_movesets(team_ctx, game_ctx, mode)
```

Responsibilities:

* Iterate through the 6 team slots
* Run the **same scoring engine used in Option 4**
* Select the best moveset for each Pokémon
* Return results for the entire team

Requirements:

* Reuse existing **scored move pool logic**
* Ensure behavior is consistent with individual recommendation mode
* Ensure each member returns **exactly 4 moves when possible**

Output format:

```
list[TeamMemberMoveset]
```

Each entry contains:

* Pokémon identifier
* recommended moves
* weakness summary
* super-effective coverage count

---

### 3. Explicit reuse of single-Pokémon moveset engine

**[TO BE DONE]**

The team feature must **reuse the existing engine from `feat_moveset.py`** rather than duplicating logic.

Implementation guideline:

* Use the same functions used by **Option 4** to:

  * build scored move pools
  * evaluate STAB / coverage / counter logic
  * select optimal move combinations

Team logic should only orchestrate **multiple engine runs**, not reimplement scoring.

---

### 4. Compact display format

Each team member should display:

```
[Pokemon Name]
Weakness: Fire / Rock / Electric
Move1      Move2
Move3      Move4
SE hits: X types
```

Requirements:

* **4 moves displayed**
* **2 moves per line layout**
* Show **weakness line**
* Show **individual SE coverage count**

**Weakness line and SE count must be included** in each block.

---

### 5. Mode selection UI

Prompt user for a mode before computing movesets:

```
(C)overage
co(U)nter
(S)TAB
```

Mode applies to **all 6 team members**.

---

### 6. Maintain compatibility with future locked moves

Although Step 4 runs **fully automatically**, the architecture must:

* allow future support for **locked/pinned moves**
* maintain compatibility with the existing Option 4 system

---

# Task 4-2: Implement Team Offensive Coverage Matrix

**Description**
Analyze how well the entire team covers all Pokémon types offensively.

---

## Sub-tasks

### 1. Implement coverage aggregation function

Create function:

```
build_offensive_coverage(team_ctx, game_ctx)
```

Responsibilities:

* Aggregate recommended moves across the team
* Compute **super-effective coverage vs all types**

Track:

* types hit by ≥1 member
* types not covered (coverage gaps)
* types covered by ≥3 members (overlap)

---

### 2. Produce team coverage summary

The summary should display:

```
Team coverage: X / 18 types hit SE
Gaps: Dragon, Electric, Poison
Overlap: Water (4), Ground (3)
```

Definitions:

* **Gap:** 0 or 1 member can hit the type SE
* **Overlap:** ≥3 members can hit the type SE

---

### 3. Coverage percentage score

Compute:

```
coverage_percent = covered_types / total_types
```

Include this in the summary.

---

### 4. Structured return format

Return a structured object containing:

* coverage percent
* list of gaps
* list of overlapping types
* per-type coverage counts

---

# Task 4-3: Integrate Team Moveset Feature into Main Menu

**Description**
Add a new menu option to access team moveset synergy.

---

## Sub-tasks

### 1. Add new menu key

Add new key to `pokemain.py`:

```
S — Team moveset synergy
```

Visibility conditions:

* team loaded
* game loaded

(same condition as **V** and **O** features)

---

### 2. Connect menu option to new module

`pokemain.py` must:

* import `feat_team_moveset`
* call the appropriate entry function
* prompt for mode selection

---

### 3. Ensure menu labeling is clear

Menu text must clearly describe the feature:

```
S — Team moveset synergy
```

---

# Task 4-4: Implement Test Infrastructure

**Description**
Ensure the entire team moveset system is fully testable **offline**.

---

## Sub-tasks

### 1. Add dependency injection for move pools

**[TO BE DONE]**

Introduce `_pool_fn` injection into:

```
build_member_result(...)
build_team_movesets(...)
```

Purpose:

* allow tests to inject **fake move pools**
* run the full algorithm **without network calls**
* make tests deterministic and fast

---

### 2. Create fake move pools for tests

**[TO BE DONE]**

Tests must include:

* move pools with **≥4 distinct move types**
* ensure coverage mode does not collapse to fewer moves due to type deduplication

---

### 3. Add new test suite

**[TO BE DONE]**

Create tests for:

* team moveset recommendation
* coverage aggregation
* edge cases (small move pools, missing types)

Test requirements:

* fully offline
* deterministic
* no API calls

---

### 4. Update `run_tests.py`

**[TO BE DONE]**

Integrate the new test suite into the project’s test runner.

Ensure:

* all suites execute correctly
* tests pass with and without cache mode

---

# Task 4-5: Update Documentation

**Description**
After Step 4 is implemented, update all project documentation.

---

## Sub-tasks

### 1. Update HISTORY.md

**[TO BE DONE]**

Add new entry describing:

* new team moveset synergy feature
* new module `feat_team_moveset.py`
* menu key `S`
* team coverage summary

---

### 2. Update ROADMAP.md

**[TO BE DONE]**

Mark **Step 4 as completed**.

Add next development step.

---

### 3. Update TASKS.md

**[TO BE DONE]**

After Step 4 completion:

* move Step 4 outcome to **HISTORY**
* update `TASKS.md` so **Step 5 becomes the current task**

---

### 4. Update ARCHITECTURE.md

**[TO BE DONE]**

Document:

* new module `feat_team_moveset.py`
* relationship with `feat_moveset.py`
* team coverage analysis system
* test architecture using `_pool_fn` injection

---

# Completion Criteria

Step 4 is complete when:

* team moveset recommendation works for all 6 members
* display format matches compact layout
* coverage summary correctly reports gaps and overlap
* menu key `S` works
* offline tests run successfully
* documentation files are updated

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
