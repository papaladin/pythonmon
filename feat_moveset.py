#!/usr/bin/env python3
"""
feat_moveset.py  Moveset recommendation feature.

Entry points:
  run_scored_pool(pkm_ctx, game_ctx)   — option 3: full ranked pool (no combo)
  run(pkm_ctx, game_ctx, constraints)  — option 4: moveset recommendation
  main()                               — standalone entry point

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
    from feat_moveset_data import (
        build_candidate_pool, select_combo, rank_status_moves,
        TWO_TURN_MOVES, LOW_ACCURACY_THRESHOLD,
    )
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

def _print_combo(combo, label, game_gen, base_stats):
    """Print one 4-move combo block with header label."""
    print()
    hdr = f"  {label} "
    fill = max(0, 68 - len(hdr))
    print(hdr + "─" * fill)
    print(f"  {'Move':<22}{'Type':<12}{'Cat':<10}{'Pwr':>5}{'Acc':>6}  Notes")
    print("  " + "─" * 72)
    for row in combo:
        pwr = str(row["power"])    if row["power"]    is not None else "--"
        acc = str(row["accuracy"]) if row["accuracy"] is not None else "--"
        bd  = _breakdown(row, game_gen, base_stats)
        print(f"  {row['name']:<22}{row['type']:<12}{row['category']:<10}"
              f"{pwr:>5}{acc:>5}%  {bd}")
    if len(combo) < 4:
        empty = 4 - len(combo)
        slot_word = "slot" if empty == 1 else "slots"
        print(f"  ({'─' * 70})")
        print(f"  Only {len(combo)} move type(s) available — "
              f"{empty} {slot_word} left unfilled")


def _print_status(ranked, total_status):
    """Print ranked status move recommendations."""
    if not ranked:
        return
    print()
    print(f"  Recommended status moves  ({len(ranked)} of {total_status})")
    print("  " + "─" * 56)
    print(f"  {'Move':<22}{'Type':<12}{'Tier':<18}{'Quality':>7}")
    print("  " + "─" * 56)
    for row in ranked:
        print(f"  {row['name']:<22}{row['type']:<12}"
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


def _print_coverage(combo, era_key, weak_types=None, damage_pool=None):
    """
    Print type coverage summary and own-weakness coverage line.

    weak_types   — list of type strings the Pokemon is weak to (optional).
    damage_pool  — full scored move pool (list of dicts with counters_weaknesses).
                   When provided, uncovered weaknesses are annotated with
                   '(no move in pool)' if no pool move can cover them at all.
    """
    se_types, gap_types = _compute_coverage(combo, era_key)
    n_types = len(calc.CHARTS[era_key][1])  # total type count for the era

    print()
    print("  ── Type coverage " + "─" * 49)

    # SE hits
    se_str = "  ".join(se_types) if se_types else "—"
    print(f"  Hits SE  [{len(se_types):2d}/{n_types}]:  {se_str}")

    # Gaps (not shown if none)
    if gap_types:
        print(f"  Gaps     [{len(gap_types):2d}/{n_types}]:  " + "  ".join(gap_types))

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

        print(f"  Weakness coverage [{len(covered):2d}/{len(weak_types):2d}]:  " + "  ".join(parts))

# ── Pool header ───────────────────────────────────────────────────────────────

def _print_header(pkm_ctx, game_ctx, pool):
    defense    = calc.compute_defense(game_ctx["era_key"],
                                      pkm_ctx["type1"], pkm_ctx["type2"])
    weaknesses = sorted([t for t, m in defense.items() if m > 1.0],
                        key=lambda t: defense[t], reverse=True)
    types_str  = " / ".join(pkm_ctx["types"])
    stats      = pkm_ctx.get("base_stats", {})

    print()
    print(f"  {pkm_ctx['form_name']}  [{types_str}]  "
          f"Atk {stats.get('attack','?')}  SpA {stats.get('special-attack','?')}")
    print(f"  {game_ctx['game']}  (Gen {game_ctx['game_gen']})")
    if weaknesses:
        weak_str = "  ".join(f"{t} x{defense[t]:.0f}" for t in weaknesses)
        print(f"  Weak to: {weak_str}")
    d, s, sk = len(pool["damage"]), len(pool["status"]), pool["skipped"]
    skipped_note = f"  ({sk} skipped)" if sk else ""
    print(f"  Pool: {d} damage  |  {s} status{skipped_note}")


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

def _show_mode(mode, damage, status_ranked, total_status,
               weak_types, era_key, game_gen, base_stats, locked):
    combo = select_combo(damage, mode, weak_types, era_key, locked=locked)
    _print_combo(combo, _MODE_LABELS[mode], game_gen, base_stats)
    _print_coverage(combo, era_key, weak_types, damage_pool=damage)
    _print_status(status_ranked, total_status)


def _show_all(damage, status_ranked, total_status,
              weak_types, era_key, game_gen, base_stats, locked):
    modes = ("coverage", "counter", "stab")
    for i, mode in enumerate(modes):
        if i > 0:
            print()
            print()
        combo = select_combo(damage, mode, weak_types, era_key, locked=locked)
        _print_combo(combo, _MODE_LABELS[mode], game_gen, base_stats)
        _print_coverage(combo, era_key, weak_types, damage_pool=damage)
    print()
    _print_status(status_ranked, total_status)




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


def _display_filtered_scored_pool(damage: list, status_ranked: list,
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
    print(f"\n  [ filter: {_filter_summary(f)} ]")

    # Damage section
    print()
    hdr = "  ATTACK MOVES — ranked by score "
    print(hdr + "─" * max(0, 72 - len(hdr)))
    if filtered:
        print(f"  {'#':<4}{'Move':<22}{'Type':<12}{'Cat':<10}"
              f"{'Pwr':>5}{'Acc':>6}  {'Score':>7}  Notes")
        print("  " + "─" * 80)
        for rank, (_label, _name, row) in enumerate(filtered, start=1):
            pwr = str(row["power"])    if row["power"]    is not None else "--"
            acc = str(row["accuracy"]) if row["accuracy"] is not None else "--"
            bd  = _breakdown(row, game_gen, base_stats)
            print(f"  {rank:<4}{row['name']:<22}{row['type']:<12}{row['category']:<10}"
                  f"{pwr:>5}{acc:>5}%  {row['score']:>7.1f}  {bd}")
        print(f"\n  Showing {len(filtered)} of {total_d} attack moves (filtered)")
    else:
        print("  (no moves match filter)")

    # Status section — apply type filter only
    print()
    hdr = "  STATUS MOVES — ranked by tier & quality "
    print(hdr + "─" * max(0, 72 - len(hdr)))
    if status_ranked:
        type_filter = f.get("type")
        shown_status = [r for r in status_ranked
                        if not type_filter
                        or r.get("type", "").lower() == type_filter.lower()]
        if shown_status:
            print(f"  {'Move':<22}{'Type':<12}{'Tier':<20}{'Quality':>7}")
            print("  " + "─" * 62)
            for row in shown_status:
                print(f"  {row['name']:<22}{row['type']:<12}"
                      f"{row['tier_label']:<20}{row['quality']:>7}")
        else:
            print("  (no status moves match filter)")
    else:
        print("  (none)")


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

    Examples:
      ("flamethrower", {...})  → ("Flamethrower", "exact")
      ("flame", {...})         → ("Flamethrower", "prefix")   # if unambiguous
      ("fire", {...})          → (None, "ambiguous")           # Fire Blast + Fire Punch + ...
      ("xyz", {...})           → (None, "not_found")
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

def collect_constraints(pkm_ctx: dict, game_ctx: dict,
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
        print("  Could not load learnset — locked moves unavailable.")
        return list(existing or [])

    locked = list(existing or [])

    while True:
        remaining = MAX_CONSTRAINTS - len(locked)

        print()
        if locked:
            print(f"  Locked moves ({len(locked)}/{MAX_CONSTRAINTS}): "
                  f"{', '.join(locked)}")
        else:
            print(f"  No moves locked yet.")

        if remaining == 0:
            print("  Maximum of 4 locked moves reached.")
            break

        print(f"  Enter a move to lock ({remaining} slot(s) remaining),")
        print("  or press Enter / type 'done' to proceed to the recommendation.")
        if locked:
            print("  Type 'clear' to remove all locked moves.")

        raw = input("  Move: ").strip()

        # ── Exit conditions ────────────────────────────────────────────────────
        if raw.lower() in ("", "skip", "done", "q"):
            break

        if raw.lower() == "clear":
            locked = []
            print("  Locked moves cleared.")
            continue

        # ── Validate against learnset ──────────────────────────────────────────
        name, status = match_move(raw, learnable)

        if status == "not_found":
            print(f"  '{raw}' not found in {pkm_ctx['form_name']}'s learnset "
                  f"for {game_ctx['game']}.")
            print("  Try again or press Enter to skip.")
            continue

        if status == "ambiguous":
            candidates = sorted(n for n in learnable
                                if n.lower().startswith(raw.strip().lower()))
            print(f"  '{raw}' matches multiple moves: "
                  f"{', '.join(candidates[:6])}"
                  f"{'...' if len(candidates) > 6 else ''}")
            print("  Please be more specific.")
            continue

        # status is "exact" or "prefix" — name is resolved
        if status == "prefix":
            confirm = input(f"  Did you mean '{name}'? (y/n): ").strip().lower()
            if confirm != "y":
                continue

        # ── Duplicate check ────────────────────────────────────────────────────
        if name in locked:
            print(f"  '{name}' is already locked.")
            continue

        locked.append(name)
        print(f"  Locked: {name}")

    return locked

# ── Public entry point ────────────────────────────────────────────────────────


# ── Scored pool display ───────────────────────────────────────────────────────

def run_scored_pool(pkm_ctx, game_ctx):
    """
    Show the full scored move pool for a Pokemon + game.
    Called from pokemain.py option 3 ("Learnable move list scoring").

    Displays two sections:
      - All damage moves ranked by individual score (descending), with breakdown
      - All status moves ranked by tier + quality, with tier label

    No combo selection, no locked slots — pure ranked list.
    """
    print_session_header(pkm_ctx, game_ctx)
    print("\n  Building scored pool...")

    try:
        pool = build_candidate_pool(pkm_ctx, game_ctx)
    except (ConnectionError, ValueError) as e:
        print(f"\n  Could not build pool: {e}")
        input("  Press Enter to continue...")
        return

    damage = pool["damage"]
    status = pool["status"]
    skipped = pool["skipped"]

    if not damage and not status:
        print("\n  No moves found in pool.")
        input("  Press Enter to continue...")
        return

    variety_slug = pkm_ctx.get("variety_slug") or pkm_ctx["pokemon"]
    age = cache.get_learnset_age_days(variety_slug, game_ctx["game"])
    if age is not None and age > cache.LEARNSET_STALE_DAYS:
        print(f"  [ learnset cached {age} days ago — press R to refresh ]")

    game_gen   = game_ctx["game_gen"]
    base_stats = pkm_ctx.get("base_stats", {})

    _print_header(pkm_ctx, game_ctx, pool)

    # ── Damage moves ─────────────────────────────────────────────────────────
    print()
    hdr = "  ATTACK MOVES — ranked by score "
    print(hdr + "─" * max(0, 72 - len(hdr)))
    if damage:
        print(f"  {'#':<4}{'Move':<22}{'Type':<12}{'Cat':<10}"
              f"{'Pwr':>5}{'Acc':>6}  {'Score':>7}  Notes")
        print("  " + "─" * 80)
        for rank, row in enumerate(damage, start=1):
            pwr = str(row["power"])    if row["power"]    is not None else "--"
            acc = str(row["accuracy"]) if row["accuracy"] is not None else "--"
            bd  = _breakdown(row, game_gen, base_stats)
            print(f"  {rank:<4}{row['name']:<22}{row['type']:<12}{row['category']:<10}"
                  f"{pwr:>5}{acc:>5}%  {row['score']:>7.1f}  {bd}")
    else:
        print("  (none)")

    if skipped:
        print(f"\n({skipped} move(s) skipped — no data available for this game)")

    # ── Status moves ─────────────────────────────────────────────────────────
    print()
    hdr = "  STATUS MOVES — ranked by tier & quality "
    print(hdr + "─" * max(0, 72 - len(hdr)))
    if status:
        status_ranked = rank_status_moves(status, top_n=len(status))  # show all
        print(f"  {'Move':<22}{'Type':<12}{'Tier':<20}{'Quality':>7}")
        print("  " + "─" * 62)
        for row in status_ranked:
            print(f"  {row['name']:<22}{row['type']:<12}"
                  f"{row['tier_label']:<20}{row['quality']:>7}")
    else:
        print("  (none)")

    choice = input("\n  Filter? (f to filter, Enter to return): ").strip().lower()
    if choice == "f":
        from feat_movepool import _prompt_filter
        f = _prompt_filter()
        if any(v is not None for v in f.values()):
            _display_filtered_scored_pool(damage, status_ranked, f,
                                          game_gen, base_stats)
        else:
            print("  (no filter set)")
        input("\n  Press Enter to continue...")

def run(pkm_ctx, game_ctx, constraints=None):
    """
    Display moveset recommendation sub-menu.
    Called from pokemain.py with both contexts loaded.

    Flow:
      1. Build candidate pool (auto-fetches learnset + move details if needed)
      2. Prompt user for locked moves (collect_constraints)
      3. Display all three modes at once (Coverage / Counter / STAB)
    """
    print_session_header(pkm_ctx, game_ctx)
    print("\n  Building moveset pool...")

    try:
        pool = build_candidate_pool(pkm_ctx, game_ctx)
    except (ConnectionError, ValueError) as e:
        print(f"\n  Could not build pool: {e}")
        input("  Press Enter to continue...")
        return

    if not pool["damage"] and not pool["status"]:
        print("\n  No moves found in pool.")
        input("  Press Enter to continue...")
        return

    variety_slug = pkm_ctx.get("variety_slug") or pkm_ctx["pokemon"]
    age = cache.get_learnset_age_days(variety_slug, game_ctx["game"])
    if age is not None and age > cache.LEARNSET_STALE_DAYS:
        print(f"  [ learnset cached {age} days ago — press R to refresh ]")

    # ── Step 1: collect locked moves ─────────────────────────────────────────
    locked_names = collect_constraints(pkm_ctx, game_ctx, existing=[])
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
        print("\n  No scoreable damage moves found in pool.")
        input("  Press Enter to continue...")
        return

    _print_header(pkm_ctx, game_ctx, pool)

    if unmatched:
        print(f"  Note: locked moves not found in pool: {', '.join(unmatched)}")
    if locked:
        print(f"  Locked: {', '.join(r['name'] for r in locked)}")

    _show_all(damage, status_ranked, len(status),
              weak_types, era_key, game_gen, base_stats, locked)

    input("\n  Press Enter to continue...")


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

    run(pkm_ctx, game_ctx, constraints=[])



# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests(with_cache=False):
    import sys, os, tempfile
    import pkm_cache as _cache

    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_moveset.py — self-test\n")

    # ── _breakdown ───────────────────────────────────────────────────────────
    def base_row(**kw):
        return {"is_stab": False, "category": "Physical", "is_two_turn": False,
                "accuracy": 100, "low_accuracy": False, "priority": 0,
                "drain": 0, "effect_chance": 0, "ailment": "none",
                "counters_weaknesses": [], **kw}

    # No flags → dash
    r = _breakdown(base_row(name="Tackle"), 9, {"attack": 80, "special-attack": 80})
    if r == "-": ok("_breakdown no flags → dash")
    else: fail("_breakdown no flags", r)

    # STAB
    r = _breakdown(base_row(name="Tackle", is_stab=True), 9,
                   {"attack": 80, "special-attack": 80})
    if "STAB x1.5" in r: ok("_breakdown STAB present")
    else: fail("_breakdown STAB", r)

    # Stat weight (gen4+, physical, atk > spa)
    r = _breakdown(base_row(name="Tackle"), 4,
                   {"attack": 100, "special-attack": 50})
    if "Stat x2.00" in r: ok("_breakdown Stat weight gen4 physical")
    else: fail("_breakdown Stat weight gen4 physical", r)

    # No stat weight before gen4
    r = _breakdown(base_row(name="Tackle"), 3,
                   {"attack": 100, "special-attack": 50})
    if "Stat" not in r: ok("_breakdown no Stat weight gen3")
    else: fail("_breakdown no Stat weight gen3", r)

    # Negative priority
    r = _breakdown(base_row(name="Dragon Tail", priority=-6), 9,
                   {"attack": 80, "special-attack": 80})
    if "Prio -6" in r: ok("_breakdown negative priority")
    else: fail("_breakdown negative priority", r)

    # Recoil
    r = _breakdown(base_row(name="Double-Edge", drain=-33), 9,
                   {"attack": 80, "special-attack": 80})
    if "Recoil 33%" in r: ok("_breakdown recoil")
    else: fail("_breakdown recoil", r)

    # Effect chance with ailment
    r = _breakdown(base_row(name="Thunder", effect_chance=30, ailment="paralysis"), 9,
                   {"attack": 80, "special-attack": 80})
    if "30% paralysis" in r: ok("_breakdown effect/ailment")
    else: fail("_breakdown effect/ailment", r)

    # ── _compute_coverage ────────────────────────────────────────────────────
    # Fire + Ice + Electric + Ground vs era3 should hit most types
    combo4 = [{"type": t} for t in ("Fire", "Ice", "Electric", "Ground")]
    se, gaps = _compute_coverage(combo4, "era3")
    if len(se) >= 10: ok(f"_compute_coverage era3 broad coverage ({len(se)} SE)")
    else: fail("_compute_coverage era3 broad", f"only {len(se)} SE types")

    # Era2 has 17 types (no Fairy) — SE count must be <= 17
    se2, gaps2 = _compute_coverage(combo4, "era2")
    _, valid_era2, _ = calc.CHARTS["era2"]
    if len(se2) <= len(valid_era2) and "Fairy" not in se2:
        ok(f"_compute_coverage era2 bounded ({len(se2)} SE, no Fairy)")
    else: fail("_compute_coverage era2 bounded", f"se={se2}")

    # Single water move: gaps should include Fire, Ground, Rock (SE), not gaps
    water_combo = [{"type": "Water"}]
    se_w, gaps_w = _compute_coverage(water_combo, "era3")
    if "Fire" in se_w and "Water" not in se_w: ok("_compute_coverage Water SE/neutral correct")
    else: fail("_compute_coverage Water", f"se={se_w}")

    # Normal type hits nothing SE in era3
    normal_combo = [{"type": "Normal"}]
    se_n, gaps_n = _compute_coverage(normal_combo, "era3")
    if len(se_n) == 0: ok("_compute_coverage Normal hits 0 SE")
    else: fail("_compute_coverage Normal", f"got SE: {se_n}")

    # Ghost is immune to Normal → should appear in gaps
    if "Ghost" in gaps_n: ok("_compute_coverage Normal → Ghost in gaps")
    else: fail("_compute_coverage Normal gap Ghost", f"gaps={gaps_n}")

    # ── _print_combo: short-combo note ──────────────────────────────────────
    import io as _io2, sys as _sys2

    _short_combo = [
        {"name":"Thunderbolt","type":"Electric","category":"Special","power":95,
         "accuracy":100,"priority":0,"drain":0,"effect_chance":0,
         "counters_weaknesses":[],"is_stab":True,"score":1,"is_two_turn":False,
         "low_accuracy":False,"ailment":None},
        {"name":"Wing Attack","type":"Flying","category":"Physical","power":60,
         "accuracy":100,"priority":0,"drain":0,"effect_chance":0,
         "counters_weaknesses":[],"is_stab":True,"score":1,"is_two_turn":False,
         "low_accuracy":False,"ailment":None},
        {"name":"Hyper Beam","type":"Normal","category":"Special","power":150,
         "accuracy":90,"priority":0,"drain":0,"effect_chance":0,
         "counters_weaknesses":[],"is_stab":False,"score":1,"is_two_turn":True,
         "low_accuracy":False,"ailment":None},
    ]
    _buf_sc = _io2.StringIO()
    _sys2.stdout = _buf_sc
    _print_combo(_short_combo, "TEST", 1, {"attack": 90, "special-attack": 90})
    _sys2.stdout = _sys2.__stdout__
    _out_sc = _buf_sc.getvalue()

    if "Only 3 move type(s) available" in _out_sc and "1 slot left unfilled" in _out_sc:
        ok("_print_combo: short-combo note shown for 3-move combo")
    else:
        fail("_print_combo: short-combo note missing", _out_sc)

    # Full 4-move combo: no note
    _full_combo = _short_combo + [
        {"name":"Drill Peck","type":"Flying","category":"Physical","power":80,
         "accuracy":100,"priority":0,"drain":0,"effect_chance":0,
         "counters_weaknesses":[],"is_stab":True,"score":1,"is_two_turn":False,
         "low_accuracy":False,"ailment":None},
    ]
    _buf_fc = _io2.StringIO()
    _sys2.stdout = _buf_fc
    _print_combo(_full_combo, "TEST", 1, {"attack": 90, "special-attack": 90})
    _sys2.stdout = _sys2.__stdout__
    _out_fc = _buf_fc.getvalue()

    if "unfilled" not in _out_fc:
        ok("_print_combo: no short-combo note for full 4-move combo")
    else:
        fail("_print_combo: spurious note on 4-move combo", _out_fc)

    # ── _print_coverage: no-move-in-pool annotation ─────────────────────────
    # Simulate Lapras scenario: Electric weakness, no Ground move in pool
    import io as _io
    _combo = [
        {"type": "Ice",     "counters_weaknesses": ["Grass"]},
        {"type": "Water",   "counters_weaknesses": ["Rock"]},
        {"type": "Psychic", "counters_weaknesses": ["Fighting"]},
        {"type": "Fighting","counters_weaknesses": ["Rock"]},
    ]
    _pool = _combo   # no Ground move → Electric not coverable from pool
    _buf = _io.StringIO()
    import sys as _sys
    _sys.stdout = _buf
    _print_coverage(_combo, "era2",
                    weak_types=["Electric","Grass","Fighting","Rock"],
                    damage_pool=_pool)
    _sys.stdout = _sys.__stdout__
    _out = _buf.getvalue()
    if "✗ Electric (no move in pool)" in _out:
        ok("_print_coverage: truly uncoverable weakness annotated")
    else:
        fail("_print_coverage: missing no-move-in-pool annotation", _out)
    if "(no move in pool)" not in _out.replace("✗ Electric (no move in pool)", ""):
        ok("_print_coverage: coverable weaknesses NOT annotated")
    else:
        fail("_print_coverage: false annotation on coverable weakness", _out)

    # damage_pool=None: legacy behaviour — no annotation at all
    _buf2 = _io.StringIO()
    _sys.stdout = _buf2
    _print_coverage(_combo, "era2",
                    weak_types=["Electric","Grass"],
                    damage_pool=None)
    _sys.stdout = _sys.__stdout__
    _out2 = _buf2.getvalue()
    if "(no move in pool)" not in _out2:
        ok("_print_coverage: no annotation when damage_pool=None")
    else:
        fail("_print_coverage: unexpected annotation with damage_pool=None", _out2)

    # ── _resolve_locked ──────────────────────────────────────────────────────
    pool = [{"name": "Earthquake"}, {"name": "Dragon Claw"},
            {"name": "Flamethrower"}, {"name": "Flash Cannon"}]

    # Exact match (case-insensitive)
    locked, unmatched = _resolve_locked(["earthquake"], pool)
    if len(locked)==1 and locked[0]["name"]=="Earthquake": ok("_resolve_locked exact match")
    else: fail("_resolve_locked exact", f"{locked}")

    # Prefix match (unambiguous)
    locked, unmatched = _resolve_locked(["flam"], pool)
    if len(locked)==1 and locked[0]["name"]=="Flamethrower": ok("_resolve_locked prefix match")
    else: fail("_resolve_locked prefix", f"{locked}")

    # Ambiguous prefix → unmatched
    locked, unmatched = _resolve_locked(["fla"], pool)
    if len(locked)==0 and "fla" in unmatched: ok("_resolve_locked ambiguous → unmatched")
    else: fail("_resolve_locked ambiguous", f"locked={locked} unmatched={unmatched}")

    # Not found
    locked, unmatched = _resolve_locked(["Surf"], pool)
    if "Surf" in unmatched: ok("_resolve_locked not found → unmatched")
    else: fail("_resolve_locked not found", f"{unmatched}")

    # Empty constraints
    locked, unmatched = _resolve_locked([], pool)
    if locked == [] and unmatched == []: ok("_resolve_locked empty")
    else: fail("_resolve_locked empty", f"{locked}")

    # ── match_move ───────────────────────────────────────────────────────────
    names = {"Flamethrower", "Flash Cannon", "Fire Blast", "Scald", "Surf"}

    m, s = match_move("Flamethrower", names)
    if m=="Flamethrower" and s=="exact": ok("match_move exact")
    else: fail("match_move exact", f"{m}, {s}")

    m, s = match_move("flamethrower", names)
    if m=="Flamethrower" and s=="exact": ok("match_move exact case-insensitive")
    else: fail("match_move exact case", f"{m}, {s}")

    m, s = match_move("Sca", names)
    if m=="Scald" and s=="prefix": ok("match_move unambiguous prefix")
    else: fail("match_move prefix", f"{m}, {s}")

    m, s = match_move("Fla", names)
    if m is None and s=="ambiguous": ok("match_move ambiguous prefix")
    else: fail("match_move ambiguous", f"{m}, {s}")

    m, s = match_move("Earthquake", names)
    if m is None and s=="not_found": ok("match_move not found")
    else: fail("match_move not found", f"{m}, {s}")

    m, s = match_move("", names)
    if m is None and s=="not_found": ok("match_move empty string")
    else: fail("match_move empty", f"{m}, {s}")

    # ── get_learnable_names (requires cache) ─────────────────────────────────
    if with_cache:
        pkm_ctx  = {"pokemon": "charizard", "variety_slug": "charizard",
                    "form_name": "Charizard"}
        game_ctx = {"game": "Scarlet / Violet", "era_key": "era3", "game_gen": 9}
        names_set = get_learnable_names(pkm_ctx, game_ctx)
        if isinstance(names_set, set) and len(names_set) > 10:
            ok(f"get_learnable_names Charizard SV → {len(names_set)} moves")
        else:
            fail("get_learnable_names", f"got {names_set!r:.80}")

    # ── _adapt_pool_for_filter ────────────────────────────────────────────────

    def _row(name, typ, cat, pwr):
        return {"name": name, "type": typ, "category": cat, "power": pwr,
                "accuracy": 100, "score": float(pwr or 0)}

    pool_f = [
        _row("Flamethrower", "Fire",   "Special",  90),
        _row("Waterfall",    "Water",  "Physical", 80),
        _row("Swords Dance", "Normal", "Status",   None),
        _row("Ice Beam",     "Ice",    "Special",  90),
    ]

    adapted = _adapt_pool_for_filter(pool_f)
    if len(adapted) == 4 and all(len(t) == 3 for t in adapted):
        ok("_adapt_pool_for_filter: correct length and tuple shape")
    else:
        fail("_adapt_pool_for_filter shape", str(adapted))

    if adapted[0][1] == "Flamethrower" and adapted[0][2] is pool_f[0]:
        ok("_adapt_pool_for_filter: name and dict reference correct")
    else:
        fail("_adapt_pool_for_filter content", str(adapted[0]))

    if _adapt_pool_for_filter([]) == []:
        ok("_adapt_pool_for_filter: empty pool → []")
    else:
        fail("_adapt_pool_for_filter empty")

    from feat_movepool import _apply_filter
    f_fire = {"type": "Fire", "category": None, "min_power": 80}
    result = _apply_filter(_adapt_pool_for_filter(pool_f), f_fire)
    names_r = [t[1] for t in result]
    if names_r == ["Flamethrower"]:
        ok("_adapt_pool_for_filter + _apply_filter: Fire+pwr≥80 → Flamethrower only")
    else:
        fail("_adapt_pool_for_filter+_apply_filter fire filter", str(names_r))

    f_none = {"type": None, "category": None, "min_power": None}
    result_all = _apply_filter(_adapt_pool_for_filter(pool_f), f_none)
    if len(result_all) == 4:
        ok("_adapt_pool_for_filter + _apply_filter: all-None filter → all rows")
    else:
        fail("_adapt_pool_for_filter all-None filter", str(len(result_all)))

    # ── summary ──────────────────────────────────────────────────────────────
    print()
    n = len(errors)
    total = 33 + (1 if with_cache else 0)
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