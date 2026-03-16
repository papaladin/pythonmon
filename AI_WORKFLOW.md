# AI_WORKFLOW.md
# How to handle implementation requests in this project

> This document describes the exact workflow to follow when receiving a prompt
> asking for a new feature, a fix, a refactor, or a display change.
> It is written for an AI assistant working on this codebase.
> Follow these steps in order. Do not skip steps, even for small changes.

---

## 0. Before anything else — restore context

At the start of every session, or when picking up an unfinished task:

1. Read `TASKS.md` — understand what is in progress and what the next step is.
2. Read `ROADMAP.md` — understand where the current task fits in the bigger picture.
3. If the task involves a specific module, read that module's header docstring.
4. If the task is architecturally significant, read `ARCHITECTURE.md`.
5. Verify the working environment: `python run_tests.py --offline`
   All tests must pass before starting. If they do not, fix the environment first.
6. Session Resume Protocol (AI handoff safety). If the assistant is continuing work started in a previous session, it must verify that the **documentation state matches the implementation state** before writing any code : TASKS.md & ROADMAP.md aligns with codebase. If inconsistencies are detected: Produce a **reconstruction summary** describing how to repair documentation. Once the user confirms and the project state is clarified, you can proceed to next step.

---

## 1. Understand the request

- Read the request carefully. Identify:
  - What **output** the user wants (new feature, display change, bug fix, refactor, new file).
  - What **files** are likely involved (source + tests + docs).
  - What **constraints** apply (offline-only, no new deps, must not break existing tests).
- If the request is ambiguous, ask one focused clarifying question before proceeding.
- If the request is large (more than 1 new file, or touches more than 3 existing files),
  propose breaking it into smaller steps and confirm with the user before implementing.

---

## 2. Explore the relevant code

Before writing a single line, read the relevant sections of existing files.
Typical actions (visible in the assistant output as brief action lines):

    grep -n "def \|class " <file>          # map public API of a module
    sed -n 'N,Mp' <file>                   # read a specific section
    grep -n "keyword" <file>               # find where something is used
    python3 -c "import mod; ..."           # probe a live value or return shape

The goal is to answer:
- What data structures flow in and out of the area being changed?
- What functions/constants will be reused vs written from scratch?
- Are there existing tests that exercise the code being modified?

Do NOT assume what a function returns. Verify it by reading the code or probing it live.

---

## 3. Propose a plan (for non-trivial changes)

For any change that touches more than one function or adds a new file:

- State which files will be created or modified.
- List the new functions with their signature and one-line purpose.
- Identify the test cases that will be added (what invariant each one checks).
- If multiple implementation approaches exist, describe them and recommend one.
  Wait for user confirmation before proceeding.

For small changes (single function, display tweak, rename): skip the proposal
and go directly to implementation, but still narrate what you are doing.


---

## 3.5 Design Freeze (mandatory for architectural or roadmap work)

If the task involves **any of the following**, implementation MUST NOT begin immediately:

* architectural decisions
* feature design choices
* breaking work into tasks or substeps
* proposing a new module
* proposing a new menu screen or feature
* suggesting changes to the project roadmap
* identifying future work during exploration

Instead, the assistant must **produce a Design Freeze output first**.

### Design Freeze output must contain

1. **Design decisions**

   * Chosen approach
   * Alternatives considered
   * Rationale

2. **Architecture changes (if any)**

   * New modules
   * New data structures
   * New dependencies between modules

3. **Feature breakdown**

   * List of tasks or subtasks required for implementation
   * Any follow-up tasks discovered

4. **Documentation updates required**

   * `TASKS.md`
   * `ROADMAP.md`
   * `ARCHITECTURE.md`
   * `README.md` (if relevant)

5. **Implementation scope**

   * Files that will be created
   * Files that will be modified
   * Test suites that will be added or updated

### Important rule

The assistant must **stop after presenting the Design Freeze output** and wait for the user to approve or modify it.

No code should be written at this stage.

### After approval

Once the user confirms the plan:

1. Update the relevant documentation files **before implementation begins**:

   * `TASKS.md` — reflect the detailed task list
   * `ROADMAP.md` — update progress or next step
   * `ARCHITECTURE.md` — record architectural changes
   * `README.md` if the user-visible feature set changes

2. Only after documentation is updated may the assistant proceed to implementation.

### Reason for this rule

AI sessions can terminate unexpectedly.
Capturing decisions and future work **before implementation** ensures that another AI can resume work without losing design context.


---

## 4. Write tests first (or alongside implementation)

Tests live in the `_run_tests()` function at the bottom of each module,
invoked via `python <file>.py --autotest`.

Rules:
- Test **pure logic** (data transformations, calculations, sorting, string
  formatting helpers). Do not test print output beyond presence of key strings.
- Use inline fixtures (small dicts/lists defined inside `_run_tests()`).
  Do not rely on live cache or network in offline tests.
- Each test has a one-line label passed to `ok()` or `fail()`.
  Labels must be specific enough to diagnose the failure without reading the code.
  Example: "weakness_summary: Rock sorted first (x4 priority)"
  Not: "sort test 3"
- After writing tests for a new function, run them — they should fail before
  the function exists. If they pass, the test is wrong.

Exception: display-only changes (column renames, spacing) — write tests after,
since the "before" state has no meaningful invariant to assert.

---

## 5. Implement the feature

Implementation order:
1. Pure logic functions first (no I/O, no print statements).
2. Display / formatting helpers second.
3. Entry points (`run()`, `main()`) last.

During implementation:
- Reuse existing helpers rather than reimplementing them.
  Key shared utilities: `_abbrev()`, `_names_cell()`, `calc.compute_defense()`,
  `team_slots()`, `team_size()`, `select_pokemon()`, `select_game()`. If an existing function performs ≥70% of the required behavior, reuse or extend it instead of writing a new one.
- Match the style of surrounding code (indentation, comment style, docstring format).
- Do not add new pip dependencies without explicit user approval.
- If a function grows beyond ~50 lines, consider splitting it. The exception is
  display functions that build a single visual output — these can be longer.

After each logical unit (pure logic done, display done), run the tests:
    python <file>.py --autotest
Fix failures before continuing. Do not accumulate failures across steps.

---

## 6. Wire into pokemain.py (if applicable)

If the feature is a new screen reachable from the main menu:
- Add the import at the top of `pokemain.py` (inside the try/except block).
- Add the menu line in `_print_menu()`, conditional on required context.
  Examples: show V only when team is loaded; show options 1-4 only when Pokemon selected.
- Add the `elif choice == "x":` handler in the main loop.
- Guard against missing context with a clear error message, never a crash.

Verify the import compiles cleanly:
    python -c "import pokemain; print('OK')"

---

## 7. Run the full test suite

    python run_tests.py --offline

All tests must pass. Zero failures is the only acceptable result before delivery.
If a pre-existing test breaks, fix it — do not leave known failures in the suite.

Also verify: the `total = N` constant at the bottom of each module's `_run_tests()`
must match the actual number of `ok()` / `fail()` calls in that function.

---

## 8. Update documentation

Update all of the following. None are optional.

| Document      | What to update |
|---|---|
| `README.md`   | File table (new file?), key table (new key?), test table (new count?), limitations |
| `ROADMAP.md`  | Mark completed item as done; update status of related items |
| `TASKS.md`    | Check off completed steps; add follow-up steps if discovered |
| `HISTORY.md`  | Append a new section (format below) |
| `ARCHITECTURE.md` | Update only if a new module was added, a data structure changed, or a key dependency changed |

### HISTORY.md entry format

    ## §N — Short descriptive title

    ### What changed
    - New file: `feat_xyz.py` — one-line description
    - Modified: `pokemain.py` — what was added or changed
    - Modified: `run_tests.py` — new suite added

    ### Why
    One paragraph: the user request or motivation.

    ### Key decisions
    - Why this approach over the alternative(s).

    ### Bugs found during testing
    Any incorrect assumptions caught by tests, and how they were fixed.

    ### Test count
    N tests in this module. Full suite: X offline tests, 0 failures.

---

## 9. Deliver outputs

- Copy all modified files to the output directory.
- Present the files to the user using the file-present tool.
- Write a short summary: what was changed, which files to replace, anything to watch out for.
- Do NOT explain line by line what the code does. The user can read it.
  Focus on: what changed, why, and any caveats.

---

## Quick reference — full workflow

## Quick reference — full workflow

```
0. Restore context     read TASKS.md, run tests --offline, verify all pass
1. Understand          clarify if ambiguous; propose breakdown if large
2. Explore             grep/sed/probe the relevant code — never assume
3. Plan                list files, functions, tests
3.5 Design Freeze      document decisions, architecture, tasks — WAIT for approval
4. Update docs         TASKS / ROADMAP / ARCHITECTURE updated before coding
5. Tests               inline fixtures, offline only, specific labels
6. Implement           logic first, display second, entry point last
7. Wire pokemain       import, menu line, handler, context guard
8. Full suite          run_tests.py --offline — zero failures
9. Final docs          README + ROADMAP + TASKS + HISTORY
10. Deliver            copy outputs, present files, short summary
```

