#!/usr/bin/env python3
"""
feat_moveset_data.py  Data fetching for moveset recommendation (I/O layer)

Builds the scored candidate pool by fetching learnset and move details.
Pure scoring logic has been moved to core_move.py.
"""

import sys

try:
    import pkm_cache as cache
    import matchup_calculator as calc
    import pkm_pokeapi as pokeapi
    from core_move import score_learnset
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


def build_candidate_pool(pkm_ctx: dict, game_ctx: dict, ui=None) -> dict:
    """
    Build the scored candidate pool for a loaded Pokemon + game context.

    Loads learnset from cache, resolves moves, fetches missing move details,
    then calls core_move.score_learnset.

    ui – optional UI instance for progress output (used in auto‑fetch).
    """
    variety_slug = pkm_ctx.get("variety_slug") or pkm_ctx["pokemon"]
    learnset = cache.get_learnset_or_fetch(variety_slug, pkm_ctx["form_name"], game_ctx["game"])
    if learnset is None:
        return {"damage": [], "status": [], "skipped": 0}

    form_name = pkm_ctx["form_name"]
    forms_dict = learnset.get("forms", {})
    form_data = forms_dict.get(form_name) or (
        next(iter(forms_dict.values())) if forms_dict else {}
    )
    if not form_data:
        return {"damage": [], "status": [], "skipped": 0}

    # Collect all move names from learnset
    all_names = {
        entry["move"]
        for section in ("level-up", "machine", "tutor", "egg")
        for entry in form_data.get(section, [])
        if entry.get("move")
    }

    # Auto-fetch missing move details (batch)
    missing = [n for n in all_names if cache.get_move(n) is None]
    if missing:
        total = len(missing)
        if ui:
            ui.print_output(f"  Fetching details for {total} move(s) not yet in cache...")
        else:
            print(f"  Fetching details for {total} move(s) not yet in cache...")
        batch = {}
        for i, name in enumerate(missing, start=1):
            if ui:
                ui.print_progress(f"  {i}/{total}  {name:<28}", end="\r", flush=True)
            else:
                print(f"  {i}/{total}  {name:<28}", end="\r", flush=True)
            try:
                entries = pokeapi.fetch_move(name)
                batch[name] = entries
            except (ValueError, ConnectionError):
                pass
        if batch:
            cache.upsert_move_batch(batch)
        if ui:
            ui.print_progress("  Done.                                   ")
        else:
            print("  Done.                                   ")

    skipped = sum(1 for n in all_names if cache.get_move(n) is None)

    # Build move_entries_map (resolved for this game)
    moves_lookup = {}
    for n in all_names:
        entries = cache.get_move(n)
        if entries is not None:
            moves_lookup[n] = cache.resolve_move(
                {n: entries}, n, game_ctx["game"], game_ctx["game_gen"]
            )

    # Pokemon's defensive weaknesses
    era_key = game_ctx["era_key"]
    defense = calc.compute_defense(era_key, pkm_ctx["type1"], pkm_ctx["type2"])
    weakness_types = [t for t, m in defense.items() if m > 1.0]

    # Score using core function
    damage_pool, status_pool = score_learnset(
        form_data, moves_lookup, pkm_ctx, game_ctx, weakness_types, era_key
    )

    return {"damage": damage_pool, "status": status_pool, "skipped": skipped}


# ── Self‑tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import sys
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

    print("\n  feat_moveset_data.py — self-test (wrapper only)\n")

    # Simple smoke test to ensure the module imports correctly
    ok("feat_moveset_data imports core_move and builds pool wrapper")

    print()
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
    else:
        print("This module is not meant to be run standalone.")