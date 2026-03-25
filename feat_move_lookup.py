#!/usr/bin/env python3
"""
feat_move_lookup.py  Move characteristics lookup — lazy cache

Move data is fetched from PokeAPI on first lookup and cached in moves.json.
Subsequent lookups are instant (cache hit). The optional T menu option
pre-warms the full table if you want zero-latency for all moves up front.

Entry points:
  run(game_ctx, ui=None)   called from pokemain when a game is loaded
  main()                   standalone: prompts for game then enters the lookup loop
"""

import sys

try:
    from pkm_session import select_game
    import matchup_calculator as calc
    import pkm_cache as cache
    import pkm_pokeapi as pokeapi
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Move fetch (lazy, with cache) ─────────────────────────────────────────────

def _fetch_move_cached(name: str, ui) -> tuple:
    """
    Return (canonical_name, entries) for a move, using cache when available.

    Flow:
      1. Check moves.json for exact or case-insensitive match → return if found
      2. Cache miss → fetch from PokeAPI → upsert into moves.json → return

    Returns (None, suggestions) if the move is not found anywhere.
    suggestions is a list of cached move names starting with the query.
    """
    # Step 1: check cache
    moves_data = cache.get_moves() or {}

    # Try exact match in cache
    lower = name.lower().strip()
    canonical = None
    for k in moves_data:
        if k.lower() == lower:
            canonical = k
            break

    if canonical:
        return canonical, moves_data[canonical]

    # Startswith suggestions from cache
    suggestions = [k for k in moves_data if k.lower().startswith(lower)
                   and not k.startswith("_")]

    if suggestions:
        # Partial query or known prefix — return suggestions from cache immediately.
        # Only go to PokeAPI when there are zero cache hits at all, meaning the
        # user typed something that doesn't match anything cached yet.
        return None, suggestions

    # Step 2: nothing in cache — try PokeAPI (full name the user typed exactly)
    try:
        ui.print_output(f"  Fetching '{name}' from PokeAPI...", end=" ", flush=True)
        entries = pokeapi.fetch_move(name)
        # fetch_move returns list of versioned entries; get display name from API
        # The canonical name comes back via the English name lookup inside fetch_move.
        # We re-fetch just the display name cleanly:
        slug = pokeapi._name_to_slug(name)
        data = pokeapi._get(f"move/{slug}")
        canonical = pokeapi._en_name(data.get("names", []), None)
        if not canonical:
            canonical = slug.replace("-", " ").title()
        cache.upsert_move(canonical, entries)
        ui.print_output("cached.")
        return canonical, entries
    except ValueError:
        ui.print_output("not found.")
        return None, suggestions
    except ConnectionError as e:
        ui.print_output(f"connection error: {e}")
        return None, suggestions


# ── Type coverage ─────────────────────────────────────────────────────────────

def _attacking_coverage(move_type: str, era_key: str):
    """Return (super_effective, resisted, immune) lists for an attacking type."""
    _, valid_types, _ = calc.CHARTS[era_key]
    se, resisted, immune = [], [], []
    for def_type in valid_types:
        m = calc.get_multiplier(era_key, move_type, def_type)
        if m >= 2.0:      se.append(def_type)
        elif m == 0.0:    immune.append(def_type)
        elif m < 1.0:     resisted.append(def_type)
    return se, resisted, immune


# ── Display ───────────────────────────────────────────────────────────────────

def _fmt(v, suffix=""):
    return f"{v}{suffix}" if v is not None else "--"

def _acc_fmt(v):
    """Format accuracy: show 'always hits' for null accuracy moves."""
    if v is None:
        return "(always hits)"
    return f"{v}%"

def _pp_fmt(v):
    """Format PP."""
    if v is None:
        return "--"
    return str(v)

def _display_move(ui, name: str, entry: dict, game_ctx: dict, all_entries: list = None):
    era_key   = game_ctx["era_key"]
    game      = game_ctx["game"]
    game_gen  = game_ctx["game_gen"]
    move_type = entry.get("type", "--")
    category  = entry.get("category", "--")

    ui.print_output("")
    ui.print_output("  " + "─" * 46)
    ui.print_output(f"  {name}  [{game}]")
    ui.print_output("  " + "─" * 46)
    ui.print_output(f"  Type      : {move_type}")
    ui.print_output(f"  Category  : {category}")
    ui.print_output(f"  Power     : {_fmt(entry.get('power'))}")
    ui.print_output(f"  Accuracy  : {_acc_fmt(entry.get('accuracy'))}")
    ui.print_output(f"  PP        : {_pp_fmt(entry.get('pp'))}")

    effect = entry.get("effect", "")
    if effect:
        ui.print_output(f"  Effect    : {effect}")

    # Version history — show how stats changed across generations
    if all_entries and len(all_entries) > 1:
        ui.print_output("")
        ui.print_output("  Version history:")
        for e in all_entries:
            apps = e.get("applies_to_games")
            if apps:
                gen_range = f"  {', '.join(apps)}"
            else:
                fg = e.get("from_gen")
                tg = e.get("to_gen")
                if fg is None:
                    continue
                gen_range = f"  Gen {fg}–{tg if tg else 'now'}"
                if fg == tg:
                    gen_range = f"  Gen {fg}"
            active = " ◄" if e is entry else ""
            pwr = _fmt(e.get("power"))
            acc = _acc_fmt(e.get("accuracy"))
            pp  = _pp_fmt(e.get("pp"))
            cat = e.get("category", "--")
            ui.print_output(f"  {gen_range:<18}  {cat:<10}  Pwr {pwr:<5}  Acc {acc:<16}  PP {pp}{active}")

    # Coverage only for damaging moves whose type exists in this era
    _, valid_types, _ = calc.CHARTS[era_key]
    if category in ("Physical", "Special") and move_type in valid_types:
        se, resisted, immune = _attacking_coverage(move_type, era_key)
        ui.print_output("")
        if se:       ui.print_output(f"  Super-effective vs : {', '.join(se)}")
        if resisted: ui.print_output(f"  Resisted by        : {', '.join(resisted)}")
        if immune:   ui.print_output(f"  No effect on       : {', '.join(immune)}")

    ui.print_output("  " + "─" * 46)


# ── Core loop ─────────────────────────────────────────────────────────────────

def _lookup_loop(ui, game_ctx: dict):
    """Interactive move lookup loop. Returns on blank input."""
    ui.print_output(f"\n  Move lookup  •  {game_ctx['game']}")
    ui.print_output("  Enter a move name, or blank to return.\n")

    while True:
        raw = ui.input_prompt("  Move name: ")
        if not raw:
            return

        canonical, result = _fetch_move_cached(raw, ui)

        if canonical is None:
            if result:
                ui.print_output(f"  Not found. Did you mean: {', '.join(result[:6])}?")
            else:
                ui.print_output("  Move not found.")
            continue

        entry = cache.resolve_move(
            {canonical: result}, canonical,
            game_ctx["game"], game_ctx["game_gen"]
        )
        if entry is None:
            ui.print_output(f"  '{canonical}' did not exist in {game_ctx['game']}.")
        else:
            _display_move(ui, canonical, entry, game_ctx, all_entries=result)


# ── Entry points ──────────────────────────────────────────────────────────────

def run(game_ctx: dict, ui=None) -> None:
    """Called from pokemain with game already loaded."""
    if ui is None:
        # Fallback for standalone
        import builtins
        class DummyUI:
            def print_output(self, text): builtins.print(text)
            def input_prompt(self, prompt): return builtins.input(prompt)
        ui = DummyUI()
    _lookup_loop(ui, game_ctx)


def main() -> None:
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║          Move Characteristics Lookup         ║")
    print("╚══════════════════════════════════════════════╝")
    game_ctx = select_game()
    if game_ctx is None:
        sys.exit(0)
    # Create a dummy UI for standalone (since we don't have a real UI)
    import builtins
    class DummyUI:
        def print_output(self, text): builtins.print(text)
        def input_prompt(self, prompt): return builtins.input(prompt)
    ui = DummyUI()
    _lookup_loop(ui, game_ctx)


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests(with_cache=False):
    import sys
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_move_lookup.py — self-test\n")

    # ── _fmt ─────────────────────────────────────────────────────────────────
    if _fmt(100) == "100":          ok("_fmt integer")
    else: fail("_fmt integer", _fmt(100))

    if _fmt(80, "%") == "80%":      ok("_fmt with suffix")
    else: fail("_fmt suffix", _fmt(80, "%"))

    if _fmt(None) == "--":          ok("_fmt None → --")
    else: fail("_fmt None", _fmt(None))

    if _fmt(None, "%") == "--":     ok("_fmt None ignores suffix")
    else: fail("_fmt None+suffix", _fmt(None, "%"))

    # ── _attacking_coverage ───────────────────────────────────────────────────
    # Fire era3: SE vs Grass, Ice, Bug, Steel; immune: none; resisted: Fire, Water, Rock, Dragon
    se, resisted, immune = _attacking_coverage("Fire", "era3")
    if "Grass" in se and "Ice" in se and "Bug" in se and "Steel" in se:
        ok(f"_attacking_coverage Fire era3 SE ({len(se)} types)")
    else: fail("_attacking_coverage Fire era3 SE", str(se))

    if "Water" in resisted and "Rock" in resisted:
        ok("_attacking_coverage Fire era3 resisted")
    else: fail("_attacking_coverage Fire era3 resisted", str(resisted))

    if immune == []:
        ok("_attacking_coverage Fire era3 no immunities")
    else: fail("_attacking_coverage Fire era3 immune", str(immune))

    # Normal: no SE, immune = Ghost
    se_n, res_n, imm_n = _attacking_coverage("Normal", "era3")
    if se_n == []:                  ok("_attacking_coverage Normal no SE")
    else: fail("_attacking_coverage Normal SE", str(se_n))

    if "Ghost" in imm_n:            ok("_attacking_coverage Normal Ghost immune")
    else: fail("_attacking_coverage Normal immune", str(imm_n))

    # Ghost era3: SE vs Ghost + Psychic; immune: Normal + Fighting
    se_g, _, imm_g = _attacking_coverage("Ghost", "era3")
    if "Ghost" in se_g and "Psychic" in se_g:
        ok("_attacking_coverage Ghost era3 SE")
    else: fail("_attacking_coverage Ghost era3 SE", str(se_g))

    if "Normal" in imm_g and "Fighting" not in imm_g:
        ok("_attacking_coverage Ghost era3 immune (Normal only)")
    else: fail("_attacking_coverage Ghost era3 immune", str(imm_g))

    # Era2: Ghost is NOT immune to Normal (era1/2 quirk — test era3 vs era2 differ)
    # Actually in era2 Ghost→Normal is ×0 (immune). Check Bug→Poison is 2x in era1
    se_bug1, _, _ = _attacking_coverage("Bug", "era1")
    if "Poison" in se_bug1:
        ok("_attacking_coverage Bug era1 → Poison SE (era1 quirk)")
    else: fail("_attacking_coverage Bug era1 Poison", str(se_bug1))

    # era1: Ghost→Psychic is ×0 immune
    _, _, imm_ghost1 = _attacking_coverage("Ghost", "era1")
    if "Psychic" in imm_ghost1:
        ok("_attacking_coverage Ghost era1 → Psychic immune (era1 quirk)")
    else: fail("_attacking_coverage Ghost era1 Psychic", str(imm_ghost1))

    # ── _display_move effect line ─────────────────────────────────────────────
    import io, contextlib

    game_ctx_fake = {"game": "Scarlet / Violet", "era_key": "era3", "game_gen": 9}

    entry_with_effect = {
        "type": "Fire", "category": "Special", "power": 90,
        "accuracy": 100, "pp": 15, "effect": "Inflicts regular damage. Has a 10% chance to burn the target."
    }
    class DummyUI:
        def __init__(self):
            self.buf = io.StringIO()
        def print_output(self, text):
            self.buf.write(text + "\n")
        def input_prompt(self, prompt):
            return ""
    dummy = DummyUI()
    _display_move(dummy, "Flamethrower", entry_with_effect, game_ctx_fake)
    out = dummy.buf.getvalue()
    if "Effect" in out and "burn" in out:
        ok("_display_move: Effect line shown when entry has effect text")
    else:
        fail("_display_move effect present", out[:120])

    entry_no_effect = {
        "type": "Normal", "category": "Physical", "power": 40,
        "accuracy": 100, "pp": 35, "effect": ""
    }
    dummy2 = DummyUI()
    _display_move(dummy2, "Tackle", entry_no_effect, game_ctx_fake)
    out2 = dummy2.buf.getvalue()
    if "Effect" not in out2:
        ok("_display_move: no Effect line when effect is empty string")
    else:
        fail("_display_move effect absent", out2[:120])

    # ── with_cache: _fetch_move_cached ───────────────────────────────────────
    if with_cache:
        # _fetch_move_cached returns (canonical_name, versioned_entries_list)
        # versioned_entries_list is a list of dicts, each with from_gen/to_gen + move fields
        dummy3 = DummyUI()
        name_ft, entries_ft = _fetch_move_cached("Flamethrower", dummy3)
        if name_ft and any(e.get("type") == "Fire" for e in entries_ft):
            ok(f"_fetch_move_cached Flamethrower → name={name_ft!r}, type=Fire in entries")
        else:
            fail("_fetch_move_cached Flamethrower", f"name={name_ft!r} entries={str(entries_ft)[:60]}")

        name_eq, entries_eq = _fetch_move_cached("Earthquake", dummy3)
        if name_eq and any(e.get("category") == "Physical" for e in entries_eq):
            ok("_fetch_move_cached Earthquake → Physical in entries")
        else:
            fail("_fetch_move_cached Earthquake", f"name={name_eq!r} entries={str(entries_eq)[:60]}")

    # ── summary ──────────────────────────────────────────────────────────────
    print()
    total = 14 + (2 if with_cache else 0)
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
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