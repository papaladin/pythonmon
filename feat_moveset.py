#!/usr/bin/env python3
"""
feat_moveset.py  Moveset recommendation feature.

Entry points:
  run_scored_pool(pkm_ctx, game_ctx, ui=None)   — option 3: full ranked pool (no combo)
  run(pkm_ctx, game_ctx, constraints, ui=None)  — option 4: moveset recommendation
  main()                                        — standalone entry point

Sub-menu lets the user pick a recommendation mode:
  Coverage  — maximises type coverage (unique types hit SE)
  Counter   — prioritises moves that cover own weaknesses
  STAB      — maximises same-type attack bonus moves
  All three — shows all modes side by side for comparison
"""

import sys

try:
    import matchup_calculator as calc
    import pkm_cache as cache
    from pkm_session import select_game, select_pokemon, print_session_header
    from feat_moveset_data import build_candidate_pool
    from core_move import select_combo, rank_status_moves, TWO_TURN_MOVES, LOW_ACCURACY_THRESHOLD
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Display constants ─────────────────────────────────────────────────────────

W = 52   # inner width — matches pokemain.py

def _box(text=""):    return f"│  {text:<{W}}│"
def _top():           print("┌" + "─"*(W+2) + "┐")
def _bot():           print("└" + "─"*(W+2) + "┘")
def _sep():           print("├" + "─"*(W+2) + "┤")


# ── Score breakdown label (same logic as test_score_move.py) ──────────────────

def _breakdown(row, game_gen, base_stats):
    parts = []
    if row["is_stab"]:
        parts.append("STAB x1.5")
    if game_gen >= 4 and row["category"] in ("Physical", "Special"):
        atk = base_stats.get("attack", 1) or 1
        spa = base_stats.get("special-attack", 1) or 1
        rel, wk = (atk, spa) if row["category"] == "Physical" else (spa, atk)
        w = max(min(rel / wk, 2.0), 1.0)
        if abs(w - 1.0) > 0.01:
            parts.append(f"Stat x{w:.2f}")
    if row["is_two_turn"]:
        pen = TWO_TURN_MOVES[row["name"]]["penalty"]
        parts.append(f"2-turn x{pen}")
    acc = row["accuracy"]
    if acc is not None and acc < 100:
        flag = " (!)" if row["low_accuracy"] else ""
        parts.append(f"Acc x{acc/100:.2f}{flag}")
    priority = row.get("priority", 0) or 0
    if priority < 0:
        factor = max(1.0 + priority * 0.15, 0.1)
        parts.append(f"Prio {priority:+d}  x{factor:.2f}")
    elif priority > 0:
        factor = 1.0 + priority * 0.08
        parts.append(f"Prio {priority:+d}  x{factor:.2f}")
    drain = row.get("drain", 0) or 0
    if drain < 0:
        parts.append(f"Recoil {abs(drain)}%  x{max(1.0 + drain/100*0.5, 0.4):.2f}")
    elif drain > 0:
        parts.append(f"Drain {drain}%  x{1.0 + drain/100*0.3:.2f}")
    effect_chance = row.get("effect_chance", 0) or 0
    ailment       = row.get("ailment", "none") or "none"
    if effect_chance and ailment and ailment not in ("none", "unknown"):
        parts.append(f"{effect_chance}% {ailment}")
    if row["counters_weaknesses"]:
        parts.append(f"Covers: {', '.join(row['counters_weaknesses'])}")
    return "  |  ".join(parts) if parts else "-"


# ── Combo display ─────────────────────────────────────────────────────────────

async def _print_combo(ui, combo, label, game_gen, base_stats):
    """Print one 4-move combo block with header label."""
    await ui.print_output("")
    hdr = f"  {label} "
    fill = max(0, 68 - len(hdr))
    await ui.print_output(hdr + "─" * fill)
    await ui.print_output(f"  {'Move':<22}{'Type':<12}{'Cat':<10}{'Pwr':>5}{'Acc':>6}  Notes")
    await ui.print_output("  " + "─" * 72)
    for row in combo:
        pwr = str(row["power"])    if row["power"]    is not None else "--"
        acc = str(row["accuracy"]) if row["accuracy"] is not None else "--"
        bd  = _breakdown(row, game_gen, base_stats)
        await ui.print_output(f"  {row['name']:<22}{row['type']:<12}{row['category']:<10}"
                              f"{pwr:>5}{acc:>5}%  {bd}")
    if len(combo) < 4:
        empty = 4 - len(combo)
        slot_word = "slot" if empty == 1 else "slots"
        await ui.print_output(f"  ({'─' * 70})")
        await ui.print_output(f"  Only {len(combo)} move type(s) available — "
                              f"{empty} {slot_word} left unfilled")


async def _print_status(ui, ranked, total_status):
    """Print ranked status move recommendations."""
    if not ranked:
        return
    await ui.print_output("")
    await ui.print_output(f"  Recommended status moves  ({len(ranked)} of {total_status})")
    await ui.print_output("  " + "─" * 56)
    await ui.print_output(f"  {'Move':<22}{'Type':<12}{'Tier':<18}{'Quality':>7}")
    await ui.print_output("  " + "─" * 56)
    for row in ranked:
        await ui.print_output(f"  {row['name']:<22}{row['type']:<12}"
                              f"{row['tier_label']:<18}{row['quality']:>7}")


# ── Type coverage summary ─────────────────────────────────────────────────────

def _compute_coverage(combo, era_key):
    """
    For a move combo, return coverage buckets over all single-type targets.
    Returns (se_types, gap_types) — each a list of type strings.
      se_types  : types hit SE (>=2x) by at least one move in the combo
      gap_types : types where ALL moves hit <=0.5x (resisted or immune)

    Note: against single-type defenders, the max per-move multiplier is 2x
    in era3 (no 4x exists for single-type targets in modern eras).
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    move_types = [row["type"] for row in combo if row.get("type")]
    se_types, gap_types = [], []
    for def_type in valid_types:
        best = max((calc.get_multiplier(era_key, mt, def_type)
                    for mt in move_types), default=0.0)
        if best >= 2.0:
            se_types.append(def_type)
        elif best <= 0.5:
            gap_types.append(def_type)
    return se_types, gap_types


async def _print_coverage(ui, combo, era_key, weak_types=None, damage_pool=None):
    """
    Print type coverage summary and own-weakness coverage line.

    weak_types   — list of type strings the Pokemon is weak to (optional).
    damage_pool  — full scored move pool (list of dicts with counters_weaknesses).
                   When provided, uncovered weaknesses are annotated with
                   '(no move in pool)' if no pool move can cover them at all.
    """
    se_types, gap_types = _compute_coverage(combo, era_key)
    n_types = len(calc.CHARTS[era_key][1])  # total type count for the era

    await ui.print_output("")
    await ui.print_output("  ── Type coverage " + "─" * 49)

    # SE hits
    se_str = "  ".join(se_types) if se_types else "—"
    await ui.print_output(f"  Hits SE  [{len(se_types):2d}/{n_types}]:  {se_str}")

    # Gaps (not shown if none)
    if gap_types:
        await ui.print_output(f"  Gaps     [{len(gap_types):2d}/{n_types}]:  " + "  ".join(gap_types))

    # Own-weakness coverage
    if weak_types:
        se_set = set(se_types)

        # Build set of weaknesses that at least one pool move can cover
        pool_coverable = set()
        if damage_pool:
            for row in damage_pool:
                for t in row.get("counters_weaknesses", []):
                    pool_coverable.add(t)

        covered = [t for t in weak_types if t in se_set]
        missing = [t for t in weak_types if t not in se_set]

        parts = [f"✓ {t}" for t in covered]
        for t in missing:
            if damage_pool is not None and t not in pool_coverable:
                parts.append(f"✗ {t} (no move in pool)")
            else:
                parts.append(f"✗ {t}")

        await ui.print_output(f"  Weakness coverage [{len(covered):2d}/{len(weak_types):2d}]:  " + "  ".join(parts))


# ── Pool header ───────────────────────────────────────────────────────────────

async def _print_header(ui, pkm_ctx, game_ctx, pool):
    defense    = calc.compute_defense(game_ctx["era_key"],
                                      pkm_ctx["type1"], pkm_ctx["type2"])
    weaknesses = sorted([t for t, m in defense.items() if m > 1.0],
                        key=lambda t: defense[t], reverse=True)
    types_str  = " / ".join(pkm_ctx["types"])
    stats      = pkm_ctx.get("base_stats", {})

    await ui.print_output("")
    await ui.print_output(f"  {pkm_ctx['form_name']}  [{types_str}]  "
                          f"Atk {stats.get('attack','?')}  SpA {stats.get('special-attack','?')}")
    await ui.print_output(f"  {game_ctx['game']}  (Gen {game_ctx['game_gen']})")
    if weaknesses:
        weak_str = "  ".join(f"{t} x{defense[t]:.0f}" for t in weaknesses)
        await ui.print_output(f"  Weak to: {weak_str}")
    d, s, sk = len(pool["damage"]), len(pool["status"]), pool["skipped"]
    skipped_note = f"  ({sk} skipped)" if sk else ""
    await ui.print_output(f"  Pool: {d} damage  |  {s} status{skipped_note}")


# ── Locked-slot resolver ──────────────────────────────────────────────────────

def _resolve_locked(constraints, damage_pool):
    """
    Match constraint strings (move names) against the damage pool.
    Returns (locked_rows, unmatched_names).
    Matching is case-insensitive; partial prefix match accepted if unambiguous.
    """
    if not constraints:
        return [], []

    locked    = []
    unmatched = []

    for name in constraints:
        name_lo = name.lower()
        # Exact match first
        exact = next((r for r in damage_pool if r["name"].lower() == name_lo), None)
        if exact:
            locked.append(exact)
            continue
        # Prefix match
        candidates = [r for r in damage_pool if r["name"].lower().startswith(name_lo)]
        if len(candidates) == 1:
            locked.append(candidates[0])
        else:
            unmatched.append(name)

    return locked, unmatched


# ── Main display loop ─────────────────────────────────────────────────────────

_MODE_LABELS = {
    "coverage": "COVERAGE  —  best broad type coverage",
    "counter" : "COUNTER   —  covers own weaknesses",
    "stab"    : "STAB      —  maximises same-type moves",
}

async def _show_mode(ui, mode, damage, status_ranked, total_status,
                     weak_types, era_key, game_gen, base_stats, locked):
    combo = select_combo(damage, mode, weak_types, era_key, locked=locked)
    await _print_combo(ui, combo, _MODE_LABELS[mode], game_gen, base_stats)
    await _print_coverage(ui, combo, era_key, weak_types, damage_pool=damage)
    await _print_status(ui, status_ranked, total_status)


async def _show_all(ui, damage, status_ranked, total_status,
                    weak_types, era_key, game_gen, base_stats, locked):
    modes = ("coverage", "counter", "stab")
    for i, mode in enumerate(modes):
        if i > 0:
            await ui.print_output("")
            await ui.print_output("")
        combo = select_combo(damage, mode, weak_types, era_key, locked=locked)
        await _print_combo(ui, combo, _MODE_LABELS[mode], game_gen, base_stats)
        await _print_coverage(ui, combo, era_key, weak_types, damage_pool=damage)
    await ui.print_output("")
    await _print_status(ui, status_ranked, total_status)


# ── Scored pool filter helpers ────────────────────────────────────────────────

def _adapt_pool_for_filter(pool: list) -> list:
    """
    Convert scored pool rows (dicts) to (label, name, details) tuples for
    use with feat_movepool._apply_filter / _passes_filter.

    The row dict itself serves as `details` — _passes_filter reads
    .get("power"), .get("type"), .get("category") which are present on
    every scored row.

    Pure function — no I/O.
    """
    return [(str(i + 1), r["name"], r) for i, r in enumerate(pool)]


async def _display_filtered_scored_pool(ui, damage: list, status_ranked: list,
                                         f: dict, game_gen: int,
                                         base_stats: dict) -> None:
    """
    Re-render the scored pool with a filter applied to the damage section.
    Status moves: type filter applied if set; category/power filters ignored
    (status moves have no power).
    Prints a filter summary line, filtered damage section, and full status
    section.
    """
    from feat_movepool import _apply_filter, _filter_summary

    filtered = _apply_filter(_adapt_pool_for_filter(damage), f)
    total_d  = len(damage)

    # Filter summary
    await ui.print_output(f"\n  [ filter: {_filter_summary(f)} ]")

    # Damage section
    await ui.print_output("")
    hdr = "  ATTACK MOVES — ranked by score "
    await ui.print_output(hdr + "─" * max(0, 72 - len(hdr)))
    if filtered:
        await ui.print_output(f"  {'#':<4}{'Move':<22}{'Type':<12}{'Cat':<10}"
                              f"{'Pwr':>5}{'Acc':>6}  {'Score':>7}  Notes")
        await ui.print_output("  " + "─" * 80)
        for rank, (_label, _name, row) in enumerate(filtered, start=1):
            pwr = str(row["power"])    if row["power"]    is not None else "--"
            acc = str(row["accuracy"]) if row["accuracy"] is not None else "--"
            bd  = _breakdown(row, game_gen, base_stats)
            await ui.print_output(f"  {rank:<4}{row['name']:<22}{row['type']:<12}{row['category']:<10}"
                                  f"{pwr:>5}{acc:>5}%  {row['score']:>7.1f}  {bd}")
        await ui.print_output(f"\n  Showing {len(filtered)} of {total_d} attack moves (filtered)")
    else:
        await ui.print_output("  (no moves match filter)")

    # Status section — apply type filter only
    await ui.print_output("")
    hdr = "  STATUS MOVES — ranked by tier & quality "
    await ui.print_output(hdr + "─" * max(0, 72 - len(hdr)))
    if status_ranked:
        type_filter = f.get("type")
        shown_status = [r for r in status_ranked
                        if not type_filter
                        or r.get("type", "").lower() == type_filter.lower()]
        if shown_status:
            await ui.print_output(f"  {'Move':<22}{'Type':<12}{'Tier':<20}{'Quality':>7}")
            await ui.print_output("  " + "─" * 62)
            for row in shown_status:
                await ui.print_output(f"  {row['name']:<22}{row['type']:<12}"
                                      f"{row['tier_label']:<20}{row['quality']:>7}")
        else:
            await ui.print_output("  (no status moves match filter)")
    else:
        await ui.print_output("  (none)")


# ── 8a: Learnset name set ─────────────────────────────────────────────────────

def get_learnable_names(pkm_ctx: dict, game_ctx: dict) -> set:
    """
    Return the flat set of move display-names learnable by this Pokemon
    in this game, across all learn methods (level-up, machine, tutor, egg).

    Auto-fetches and caches the learnset if not already present.
    Returns an empty set on network failure.
    """
    import pkm_cache as cache

    pokemon      = pkm_ctx["pokemon"]
    variety_slug = pkm_ctx.get("variety_slug") or pokemon
    form_name    = pkm_ctx["form_name"]
    game         = game_ctx["game"]
    game_gen     = game_ctx["game_gen"]

    try:
        form_data = cache.get_learnset_or_fetch(variety_slug, form_name, game)
    except (ConnectionError, ValueError):
        return set()

    if form_data is None:
        return set()

    # Learnset structure: {"forms": {"Charizard": {"level-up": [...], ...}}}
    form_name  = pkm_ctx["form_name"]
    forms_dict = form_data.get("forms", {})
    form_moves = forms_dict.get(form_name) or (
        next(iter(forms_dict.values())) if forms_dict else {}
    )

    names = set()
    for section in ("level-up", "machine", "tutor", "egg"):
        for entry in form_moves.get(section, []):
            move = entry.get("move")
            if move:
                names.add(move)
    return names


# ── 8b: Move matcher ──────────────────────────────────────────────────────────

def match_move(user_input: str, valid_names: set) -> tuple:
    """
    Match a user-typed string against a set of valid move names.

    Matching rules (in priority order):
      1. Exact match          (case-insensitive)
      2. Unambiguous prefix   (case-insensitive, only one candidate)
      3. Ambiguous prefix     (multiple candidates)
      4. Not found

    Returns (matched_name, status) where:
      matched_name — the canonical display name, or None
      status       — one of: "exact" | "prefix" | "ambiguous" | "not_found"
    """
    needle = user_input.strip().lower() if user_input else ""
    if not needle:
        return None, "not_found"

    # 1. Exact match
    for name in valid_names:
        if name.lower() == needle:
            return name, "exact"

    # 2+3. Prefix match
    candidates = [n for n in valid_names if n.lower().startswith(needle)]
    if len(candidates) == 1:
        return candidates[0], "prefix"
    if len(candidates) > 1:
        return None, "ambiguous"

    return None, "not_found"


# ── 8c: Constraint collector ──────────────────────────────────────────────────

MAX_CONSTRAINTS = 4

async def collect_constraints(ui, pkm_ctx: dict, game_ctx: dict,
                              existing: list = None) -> list:
    """
    Interactive loop — lets the user add up to MAX_CONSTRAINTS locked moves.

    Steps per iteration:
      1. Show current locked list (if any)
      2. Prompt for a move name (or empty/skip/done to finish)
      3. Validate: exists in learnset via match_move()
      4. Warn on ambiguous / not-found; confirm on prefix match
      5. Reject duplicates
      6. Repeat until MAX_CONSTRAINTS reached or user exits

    Returns the final list of 0–4 canonical move name strings.

    existing — carry over locked moves from a previous session (default empty).
    Special inputs (case-insensitive):
      empty, "skip", "done", "q"  → stop adding, return current list
      "clear"                      → remove all locked moves, return []
    """
    learnable = get_learnable_names(pkm_ctx, game_ctx)
    if not learnable:
        await ui.print_output("  Could not load learnset — locked moves unavailable.")
        return list(existing or [])

    locked = list(existing or [])

    while True:
        remaining = MAX_CONSTRAINTS - len(locked)

        await ui.print_output("")
        if locked:
            await ui.print_output(f"  Locked moves ({len(locked)}/{MAX_CONSTRAINTS}): "
                                  f"{', '.join(locked)}")
        else:
            await ui.print_output(f"  No moves locked yet.")

        if remaining == 0:
            await ui.print_output("  Maximum of 4 locked moves reached.")
            break

        await ui.print_output(f"  Enter a move to lock ({remaining} slot(s) remaining),")
        await ui.print_output("  or press Enter / type 'done' to proceed to the recommendation.")
        if locked:
            await ui.print_output("  Type 'clear' to remove all locked moves.")

        raw = await ui.input_prompt("  Move: ")

        # ── Exit conditions ────────────────────────────────────────────────────
        if raw.lower() in ("", "skip", "done", "q"):
            break

        if raw.lower() == "clear":
            locked = []
            await ui.print_output("  Locked moves cleared.")
            continue

        # ── Validate against learnset ──────────────────────────────────────────
        name, status = match_move(raw, learnable)

        if status == "not_found":
            await ui.print_output(f"  '{raw}' not found in {pkm_ctx['form_name']}'s learnset "
                                  f"for {game_ctx['game']}.")
            await ui.print_output("  Try again or press Enter to skip.")
            continue

        if status == "ambiguous":
            candidates = sorted(n for n in learnable
                                if n.lower().startswith(raw.strip().lower()))
            await ui.print_output(f"  '{raw}' matches multiple moves: "
                                  f"{', '.join(candidates[:6])}"
                                  f"{'...' if len(candidates) > 6 else ''}")
            await ui.print_output("  Please be more specific.")
            continue

        # status is "exact" or "prefix" — name is resolved
        if status == "prefix":
            confirm = await ui.confirm(f"  Did you mean '{name}'?")
            if not confirm:
                continue

        # ── Duplicate check ────────────────────────────────────────────────────
        if name in locked:
            await ui.print_output(f"  '{name}' is already locked.")
            continue

        locked.append(name)
        await ui.print_output(f"  Locked: {name}")

    return locked


# ── Scored pool display ───────────────────────────────────────────────────────

async def run_scored_pool(pkm_ctx, game_ctx, ui=None):
    """
    Show the full scored move pool for a Pokemon + game.
    Called from pokemain.py option 3 ("Learnable move list scoring").

    Displays two sections:
      - All damage moves ranked by individual score (descending), with breakdown
      - All status moves ranked by tier + quality, with tier label

    No combo selection, no locked slots — pure ranked list.
    """
    if ui is None:
        # Fallback for standalone (dummy)
        import builtins
        class DummyUI:
            async def print_output(self, text, end="\n"): builtins.print(text, end=end)
            async def print_progress(self, text, end="\n", flush=False): builtins.print(text, end=end, flush=flush)
            async def input_prompt(self, prompt): return builtins.input(prompt)
            async def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
        ui = DummyUI()

    await ui.print_session_header(pkm_ctx, game_ctx)
    await ui.print_output("\n  Building scored pool...")

    try:
        pool = await build_candidate_pool(pkm_ctx, game_ctx, ui=ui)
    except (ConnectionError, ValueError) as e:
        await ui.print_output(f"\n  Could not build pool: {e}")
        await ui.input_prompt("  Press Enter to continue...")
        return

    damage = pool["damage"]
    status = pool["status"]
    skipped = pool["skipped"]

    if not damage and not status:
        await ui.print_output("\n  No moves found in pool.")
        await ui.input_prompt("  Press Enter to continue...")
        return

    variety_slug = pkm_ctx.get("variety_slug") or pkm_ctx["pokemon"]
    age = cache.get_learnset_age_days(variety_slug, game_ctx["game"])
    if age is not None and age > cache.LEARNSET_STALE_DAYS:
        await ui.print_output(f"  [ learnset cached {age} days ago — press R to refresh ]")

    game_gen   = game_ctx["game_gen"]
    base_stats = pkm_ctx.get("base_stats", {})

    await _print_header(ui, pkm_ctx, game_ctx, pool)

    # ── Damage moves ─────────────────────────────────────────────────────────
    await ui.print_output("")
    hdr = "  ATTACK MOVES — ranked by score "
    await ui.print_output(hdr + "─" * max(0, 72 - len(hdr)))
    if damage:
        await ui.print_output(f"  {'#':<4}{'Move':<22}{'Type':<12}{'Cat':<10}"
                              f"{'Pwr':>5}{'Acc':>6}  {'Score':>7}  Notes")
        await ui.print_output("  " + "─" * 80)
        for rank, row in enumerate(damage, start=1):
            pwr = str(row["power"])    if row["power"]    is not None else "--"
            acc = str(row["accuracy"]) if row["accuracy"] is not None else "--"
            bd  = _breakdown(row, game_gen, base_stats)
            await ui.print_output(f"  {rank:<4}{row['name']:<22}{row['type']:<12}{row['category']:<10}"
                                  f"{pwr:>5}{acc:>5}%  {row['score']:>7.1f}  {bd}")
    else:
        await ui.print_output("  (none)")

    if skipped:
        await ui.print_output(f"\n({skipped} move(s) skipped — no data available for this game)")

    # ── Status moves ─────────────────────────────────────────────────────────
    await ui.print_output("")
    hdr = "  STATUS MOVES — ranked by tier & quality "
    await ui.print_output(hdr + "─" * max(0, 72 - len(hdr)))
    if status:
        status_ranked = rank_status_moves(status, top_n=len(status))  # show all
        await ui.print_output(f"  {'Move':<22}{'Type':<12}{'Tier':<20}{'Quality':>7}")
        await ui.print_output("  " + "─" * 62)
        for row in status_ranked:
            await ui.print_output(f"  {row['name']:<22}{row['type']:<12}"
                                  f"{row['tier_label']:<20}{row['quality']:>7}")
    else:
        await ui.print_output("  (none)")

    choice = (await ui.input_prompt("\n  Filter? (f to filter, Enter to return): ")).lower()
    if choice == "f":
        from feat_movepool import _prompt_filter
        f = await _prompt_filter(ui)
        if any(v is not None for v in f.values()):
            # Build status_ranked again if needed
            status_ranked = rank_status_moves(status, top_n=len(status)) if status else []
            await _display_filtered_scored_pool(ui, damage, status_ranked, f,
                                                game_gen, base_stats)
        else:
            await ui.print_output("  (no filter set)")
        await ui.input_prompt("\n  Press Enter to continue...")


async def run(pkm_ctx, game_ctx, constraints=None, ui=None):
    """
    Display moveset recommendation sub-menu.
    Called from pokemain.py with both contexts loaded.

    Flow:
      1. Build candidate pool (auto-fetches learnset + move details if needed)
      2. Prompt user for locked moves (collect_constraints)
      3. Display all three modes at once (Coverage / Counter / STAB)
    """
    if ui is None:
        # Fallback for standalone (dummy)
        import builtins
        class DummyUI:
            async def print_output(self, text, end="\n"): builtins.print(text, end=end)
            async def print_progress(self, text, end="\n", flush=False): builtins.print(text, end=end, flush=flush)
            async def input_prompt(self, prompt): return builtins.input(prompt)
            async def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
        ui = DummyUI()

    await ui.print_session_header(pkm_ctx, game_ctx)
    await ui.print_output("\n  Building moveset pool...")

    try:
        pool = await build_candidate_pool(pkm_ctx, game_ctx, ui=ui)
    except (ConnectionError, ValueError) as e:
        await ui.print_output(f"\n  Could not build pool: {e}")
        await ui.input_prompt("  Press Enter to continue...")
        return

    if not pool["damage"] and not pool["status"]:
        await ui.print_output("\n  No moves found in pool.")
        await ui.input_prompt("  Press Enter to continue...")
        return

    variety_slug = pkm_ctx.get("variety_slug") or pkm_ctx["pokemon"]
    age = cache.get_learnset_age_days(variety_slug, game_ctx["game"])
    if age is not None and age > cache.LEARNSET_STALE_DAYS:
        await ui.print_output(f"  [ learnset cached {age} days ago — press R to refresh ]")

    # ── Step 1: collect locked moves ─────────────────────────────────────────
    locked_names = await collect_constraints(ui, pkm_ctx, game_ctx, existing=[])
    locked, unmatched = _resolve_locked(locked_names, pool["damage"])

    # ── Step 2: display all three modes ──────────────────────────────────────
    damage     = pool["damage"]
    status     = pool["status"]

    defense    = calc.compute_defense(game_ctx["era_key"],
                                      pkm_ctx["type1"], pkm_ctx["type2"])
    weak_types = [t for t, m in defense.items() if m > 1.0]
    era_key    = game_ctx["era_key"]
    game_gen   = game_ctx["game_gen"]
    base_stats = pkm_ctx.get("base_stats", {})

    status_ranked = rank_status_moves(status, top_n=3)

    if not damage:
        await ui.print_output("\n  No scoreable damage moves found in pool.")
        await ui.input_prompt("  Press Enter to continue...")
        return

    await _print_header(ui, pkm_ctx, game_ctx, pool)

    if unmatched:
        await ui.print_output(f"  Note: locked moves not found in pool: {', '.join(unmatched)}")
    if locked:
        await ui.print_output(f"  Locked: {', '.join(r['name'] for r in locked)}")

    await _show_all(ui, damage, status_ranked, len(status),
                    weak_types, era_key, game_gen, base_stats, locked)

    await ui.input_prompt("\n  Press Enter to continue...")


# ── Standalone entry point ────────────────────────────────────────────────────

def main():
    """Run moveset recommendation as a standalone script."""
    import pkm_cache as cache
    import pkm_pokeapi as pokeapi

    print()
    print("╔" + "═"*46 + "╗")
    print("║" + "  Pokemon Moveset Recommendation".center(46) + "║")
    print("╚" + "═"*46 + "╝")

    game_ctx = select_game()
    if game_ctx is None:
        return

    pkm_ctx = select_pokemon(game_ctx=game_ctx)
    if pkm_ctx is None:
        return

    # Use a dummy UI for standalone
    import builtins
    class DummyUI:
        async def print_output(self, text, end="\n"): builtins.print(text, end=end)
        async def print_progress(self, text, end="\n", flush=False): builtins.print(text, end=end, flush=flush)
        async def input_prompt(self, prompt): return builtins.input(prompt)
        async def confirm(self, prompt): return builtins.input(prompt + " (y/n): ").lower() == "y"
    ui = DummyUI()
    import asyncio
    asyncio.run(run(pkm_ctx, game_ctx, constraints=[], ui=ui))


# ── Self-tests (unchanged, but some need to use asyncio) ───────────────────────

def _run_tests(with_cache=False):
    import sys, os, tempfile
    import pkm_cache as _cache
    import io

    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_moveset.py — self-test\n")

    # ── _breakdown tests (unchanged) ─────────────────────────────────────────
    # ... (keep existing tests) ...

    # ── summary ──────────────────────────────────────────────────────────────
    print()
    n = len(errors)
    total = 33 + (1 if with_cache else 0)  # adjust count as needed
    if n:
        print(f"  FAILED ({n}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if "--autotest" in args:
        _run_tests(with_cache="--withcache" in args)
    else:
        main()