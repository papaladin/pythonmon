# AI_WORKFLOW.md
# Implementation workflow for AI assistants

> This document defines a strict step-by-step workflow for implementing changes in this codebase.  
> It is written for an AI assistant working on this codebase.
> Follow these steps in order. Do not skip steps, even for small changes.

---

## 0. Restore context

- Read `TASKS.md` (current task), `ROADMAP.md` (big picture).
- Read relevant module docstrings and `ARCHITECTURE.md` if changes affect structure.
- Run `python run_tests.py --offline` – all tests must pass.
- If continuing a previous session, verify that docs match implementation. If not, produce a reconstruction summary and wait for user confirmation.

---


## 1. Understand the request

- Identify: output type (feature/fix/refactor), files involved, constraints (offline, no new deps, tests must pass).
- If ambiguous, ask one clarifying question.
- If >1 new file or >3 existing files, propose a breakdown and confirm.

---

## 2. Explore the code

Use tools to inspect relevant files:
- `grep -n "def \|class " <file>` – map API
- `sed -n 'N,Mp' <file>` – read sections
- `python3 -c "import mod; ..."` – probe live values

Answer: data flow, reusable functions, existing tests. Never assume – verify.

---

## 3. Plan (for non-trivial changes)

For changes touching >1 function or adding a new file:

- List files to create/modify.
- New functions: signature + one-line purpose.
- Test cases: what invariants to check.
- If multiple approaches, recommend one and wait for confirmation.

Skip planning for trivial changes (single function, display tweak) but narrate.

---

## 3.5 Design freeze (mandatory for architectural/roadmap work)

If the task involves **any** of the following, **stop and produce a Design Freeze**:

- Architectural decisions
- Feature design choices
- Breaking work into tasks
- Proposing new modules/screens
- Changing roadmap

**Design Freeze must contain**:
1. Design decisions (chosen approach, alternatives, rationale)
2. Architecture changes (new modules/data structures/dependencies)
3. Feature breakdown (list of tasks)
4. Documentation updates required (TASKS, ROADMAP, ARCHITECTURE, README)
5. Implementation scope (files to create/modify, tests)

Wait for user approval. After approval, update docs **before** writing code.

---

## 4. Write tests first (or alongside)

- Test pure logic only. Use inline fixtures. Offline tests only.
- Each test: one-line label (`<function>: what is asserted`).
- After writing tests for a new function, run them – they must fail initially.
- For display-only changes, tests can be written after.

---

## 5. Implement

Order:
1. Pure logic (no I/O)
2. Display helpers
3. Entry points (`run`, `main`)

Reuse existing helpers. Match code style. No new deps without approval.
After each logical unit, run `python <file>.py --autotest` and fix failures immediately.

---

## 6. Wire into pokemain (if applicable)

- Add import (inside try/except).
- Add menu line in `_build_menu_lines` with visibility condition.
- Add handler with context guards.
- Use `await ui.show_error()` for missing context.

Verify import: `python -c "import pokemain; print('OK')"`

---

## 7. Run full test suite

`python run_tests.py --offline` – zero failures required.

Verify each module’s `total = N` matches actual test count.

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

- Copy modified files to output directory.
- Present them using the file-present tool.
- Write a short summary: what changed, why, caveats.
- Do not explain line by line.

---

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
9. Final docs          README + ROADMAP + TASKS + HISTORY + ARCHITECTURE
10. Deliver            copy outputs, present files, short summary
```

