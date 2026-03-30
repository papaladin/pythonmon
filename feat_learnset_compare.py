#!/usr/bin/env python3
"""
feat_learnset_compare.py  Side-by-side learnset comparison

Compares the full learnable move pools of two Pokemon in the same game,
grouped into three sections:
  - Unique to Pokemon A
  - Unique to Pokemon B
  - Shared by both

A brief stat comparison header (from core_stat) is shown above the
learnset sections for context.

Entry points:
  run(pkm_ctx, game_ctx, ui=None)   called from pokemain (key L)
  main()                   standalone
"""

import sys

try:
    import pkm_cache as cache
    from pkm_session import select_game, select_pokemon
    from core_stat import compare_stats, total_stats, infer_role, infer_speed_tier
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Pure logic ────────────────────────────────────────────────────────────────

def _flat_moves(learnset: dict, form_name: str) -> set:
    """
    Return the flat set of all move names learnable by a form across all
    learn methods (level-up, machine, tutor, egg).
    Falls back to first form if form_name is not found.
    """
    forms_dict = learnset.get("forms", {})
    form_data  = forms_dict.get(form_name) or (
        next(iter(forms_dict.values())) if forms_dict else {}
    )
    names = set()
    for section in ("level-up", "machine", "tutor", "egg"):
        for entry in form_data.get(section, []):
            move = entry.get("move")
            if move:
                names.add(move)
    return names


def compare_learnsets(moves_a: set, moves_b: set) -> dict:
    """
    Compare two flat move sets.

    Returns:
      {
        "only_a": set[str],   -- moves learnable only by A
        "only_b": set[str],   -- moves learnable only by B
        "shared": set[str],   -- moves learnable by both
      }
    """
    return {
        "only_a": moves_a - moves_b,
        "only_b": moves_b - moves_a,
        "shared": moves_a & moves_b,
    }


def _build_move_rows(names: set, game_ctx: dict) -> list:
    """
    Resolve move details for a set of move names.
    Returns a list of dicts sorted alphabetically by name.
    Moves not in cache get "?" fields -- graceful fallback.
    """
    rows = []
    for name in sorted(names):
        entries = cache.get_move(name)
        entry   = cache.resolve_move(
            {name: entries}, name,
            game_ctx["game"], game_ctx["game_gen"]
        ) if entries else None

        rows.append({
            "name"    : name,
            "type"    : entry.get("type", "?")       if entry else "?",
            "category": entry.get("category", "?")   if entry else "?",
            "power"   : entry.get("power")            if entry else None,
            "accuracy": entry.get("accuracy")         if entry else None,
        })
    return rows


# ── Display helpers ───────────────────────────────────────────────────────────

_COL_NAME = 22
_COL_TYPE = 10
_COL_CAT  = 10
_COL_PWR  =  5
_COL_ACC  =  6
_SEP_W    = _COL_NAME + _COL_TYPE + _COL_CAT + _COL_PWR + _COL_ACC + 8
_STAT_W   = 60


def _fmt_row(r: dict) -> str:
    pwr = str(r["power"])    if r["power"]    is not None else "--"
    acc = str(r["accuracy"]) if r["accuracy"] is not None else "--"
    return (f"  {r['name']:<{_COL_NAME}}"
            f"  {r['type']:<{_COL_TYPE}}"
            f"  {r['category']:<{_COL_CAT}}"
            f"  {pwr:>{_COL_PWR}}"
            f"  {acc+'%':>{_COL_ACC}}")


async def _print_col_headers(ui) -> None:
    await ui.print_output(f"  {'Move':<{_COL_NAME}}"
                    f"  {'Type':<{_COL_TYPE}}"
                    f"  {'Category':<{_COL_CAT}}"
                    f"  {'Pwr':>{_COL_PWR}}"
                    f"  {'Acc':>{_COL_ACC}}")
    await ui.print_output("  " + "-" * _SEP_W)


async def _print_section(ui, title: str, rows: list) -> None:
    fill = max(0, _SEP_W - len(title) - 12)
    await ui.print_output(f"\n  -- {title} ({len(rows)} moves) " + "-" * fill)
    if not rows:
        await ui.print_output("  (none)")
        return
    await _print_col_headers(ui)
    for r in rows:
        await ui.print_output(_fmt_row(r))


def _type_str(pkm: dict) -> str:
    t2 = pkm.get("type2", "None")
    return f"{pkm['type1']} / {t2}" if t2 != "None" else pkm["type1"]


async def _print_stat_header(ui, pkm_a: dict, pkm_b: dict) -> None:
    """Brief stat comparison header shown above the learnset sections."""
    bs_a  = pkm_a.get("base_stats", {})
    bs_b  = pkm_b.get("base_stats", {})

    # Guard: base_stats must be a non-empty dict.  Old cache entries could store
    # it as a list of PokeAPI stat objects, or pkm_ctx could arrive with an empty
    # dict when the cache was read before the pokemon file was fully written
    # (timing edge case on first load).  In either case, fall back to re-reading
    # directly from the pokemon cache by form name.
    def _ensure_stats(pkm: dict, bs: dict) -> dict:
        if isinstance(bs, dict) and bs:
            return bs
        try:
            data = cache.get_pokemon(pkm.get("pokemon", ""))
            if data:
                form_name = pkm.get("form_name", "")
                form = next((f for f in data.get("forms", [])
                             if f["name"] == form_name), None)
                if form and isinstance(form.get("base_stats"), dict):
                    return form["base_stats"]
        except Exception:
            pass
        return {}

    bs_a = _ensure_stats(pkm_a, bs_a)
    bs_b = _ensure_stats(pkm_b, bs_b)
    tot_a = total_stats(bs_a)
    tot_b = total_stats(bs_b)
    role_a = f"{infer_role(bs_a).capitalize()} / {infer_speed_tier(bs_a).capitalize()}"
    role_b = f"{infer_role(bs_b).capitalize()} / {infer_speed_tier(bs_b).capitalize()}"
    mark_a = "★" if tot_a > tot_b else ("•" if tot_a == tot_b else " ")
    mark_b = "★" if tot_b > tot_a else ("•" if tot_a == tot_b else " ")

    _LABELS = {"hp": "HP", "attack": "Atk", "defense": "Def",
               "special-attack": "SpA", "special-defense": "SpD", "speed": "Spe"}
    rows = compare_stats(bs_a, bs_b)

    _left_w = 26
    name_a  = f"{pkm_a['form_name']}  [{_type_str(pkm_a)}]"
    name_b  = f"{pkm_b['form_name']}  [{_type_str(pkm_b)}]"
    await ui.print_output(f"  {'':8}  {name_a:<{_left_w}}  {name_b}")
    await ui.print_output("  " + "=" * _STAT_W)
    for r in rows:
        ma = "★" if r["winner"] == "a" else ("•" if r["winner"] == "tie" else " ")
        mb = "★" if r["winner"] == "b" else ("•" if r["winner"] == "tie" else " ")
        left_val = f"{r['val_a']:>3} {ma}"
        await ui.print_output(f"  {_LABELS.get(r['key'], r['key']):<8}  {left_val:<{_left_w}}  {r['val_b']:>3} {mb}")
    await ui.print_output("  " + "-" * _STAT_W)
    left_total = f"{tot_a:>3} {mark_a}"
    await ui.print_output(f"  {'Total':<8}  {left_total:<{_left_w}}  {tot_b:>3} {mark_b}")
    await ui.print_output(f"  {'Role':<8}  {role_a:<{_left_w}}  {role_b}")
    await ui.print_output("  " + "=" * _STAT_W)


async def display_learnset_comparison(ui, pkm_a: dict, pkm_b: dict, game_ctx: dict) -> None:
    """Full learnset comparison screen."""
    name_a = pkm_a["form_name"]
    name_b = pkm_b["form_name"]
    game   = game_ctx["game"]

    await ui.print_output(f"\n  Learnset comparison  |  {game}")
    await ui.print_output(f"  {name_a}  vs  {name_b}")

    await _print_stat_header(ui, pkm_a, pkm_b)

    def _load(pkm):
        slug = pkm.get("variety_slug") or pkm["pokemon"]
        return cache.get_learnset_or_fetch(slug, pkm["form_name"], game)

    ls_a = _load(pkm_a)
    ls_b = _load(pkm_b)

    if ls_a is None:
        await ui.print_output(f"  Could not load learnset for {name_a}.")
        return
    if ls_b is None:
        await ui.print_output(f"  Could not load learnset for {name_b}.")
        return

    moves_a = _flat_moves(ls_a, name_a)
    moves_b = _flat_moves(ls_b, name_b)
    diff    = compare_learnsets(moves_a, moves_b)

    rows_only_a = _build_move_rows(diff["only_a"], game_ctx)
    rows_only_b = _build_move_rows(diff["only_b"], game_ctx)
    rows_shared = _build_move_rows(diff["shared"],  game_ctx)

    await _print_section(ui, f"Unique to {name_a}", rows_only_a)
    await _print_section(ui, f"Unique to {name_b}", rows_only_b)
    await _print_section(ui, "Shared by both",      rows_shared)

    await ui.print_output(f"\n  Total: {name_a} {len(moves_a)} moves  |  "
                    f"{name_b} {len(moves_b)} moves  |  "
                    f"{len(diff['shared'])} shared")


# ── Entry points ──────────────────────────────────────────────────────────────

async def run(pkm_ctx: dict, game_ctx: dict, ui=None) -> None:
    """Called from pokemain (key L)."""
    if ui is None:
        # Fallback dummy UI for standalone
        from ui_dummy import DummyUI
        ui = DummyUI()

    await ui.print_output(f"\n  Comparing {pkm_ctx['form_name']}'s learnset with...")
    pkm_b = await ui.select_pokemon(game_ctx=game_ctx)
    if pkm_b is None:
        await ui.print_output("  No Pokemon selected.")
        return
    await display_learnset_comparison(ui, pkm_ctx, pkm_b, game_ctx)
    await ui.input_prompt("\n  Press Enter to continue...")


def main() -> None:
    # Dummy UI for standalone
    import asyncio

    from ui_dummy import DummyUI
    ui = DummyUI()

    asyncio.run(ui.print_output(""))
    asyncio.run(ui.print_output("╔══════════════════════════════════════════╗"))
    asyncio.run(ui.print_output("║         Learnset Comparison              ║"))
    asyncio.run(ui.print_output("╚══════════════════════════════════════════╝"))
    game_ctx = select_game()
    if game_ctx is None:
        sys.exit(0)
    asyncio.run(ui.print_output("\n  First Pokemon:"))
    pkm_a = select_pokemon(game_ctx=game_ctx)
    if pkm_a is None:
        sys.exit(0)
    asyncio.run(ui.print_output("\n  Second Pokemon:"))
    pkm_b = select_pokemon(game_ctx=game_ctx)
    if pkm_b is None:
        sys.exit(0)
    asyncio.run(display_learnset_comparison(ui, pkm_a, pkm_b, game_ctx))
    asyncio.run(ui.input_prompt("\n  Press Enter to exit..."))


# ── Self‑tests (synchronous) ─────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):  print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_learnset_compare.py -- self-test\n")

    # ── _flat_moves ───────────────────────────────────────────────────────────

    _ls_a = {"forms": {"Charizard": {
        "level-up": [{"move": "Flamethrower", "level": 30},
                     {"move": "Dragon Claw",  "level": 45}],
        "machine" : [{"move": "Earthquake", "tm": "TM41"}],
        "tutor"   : [{"move": "Air Slash"}],
        "egg"     : [{"move": "Dragon Dance"}],
    }}}

    moves = _flat_moves(_ls_a, "Charizard")
    if moves == {"Flamethrower", "Dragon Claw", "Earthquake", "Air Slash", "Dragon Dance"}:
        ok("_flat_moves: all 4 sections collected correctly")
    else:
        fail("_flat_moves all sections", str(moves))

    # Duplicate across sections: still one entry
    _ls_dup = {"forms": {"Test": {
        "level-up": [{"move": "Tackle", "level": 1}],
        "machine" : [{"move": "Tackle", "tm": "TM01"}],
    }}}
    if _flat_moves(_ls_dup, "Test") == {"Tackle"}:
        ok("_flat_moves: duplicate across sections -> single entry")
    else:
        fail("_flat_moves dedup")

    # Form fallback: unknown form name -> uses first form
    _ls_fb = {"forms": {"WrongName": {
        "level-up": [{"move": "Surf", "level": 1}],
    }}}
    if _flat_moves(_ls_fb, "Charizard") == {"Surf"}:
        ok("_flat_moves: unknown form name -> falls back to first form")
    else:
        fail("_flat_moves fallback", str(_flat_moves(_ls_fb, "Charizard")))

    # Empty learnset -> empty set
    if _flat_moves({}, "Charizard") == set():
        ok("_flat_moves: empty learnset -> empty set")
    else:
        fail("_flat_moves empty")

    # ── compare_learnsets ─────────────────────────────────────────────────────

    set_a = {"Flamethrower", "Dragon Claw", "Earthquake", "Air Slash"}
    set_b = {"Surf", "Earthquake", "Air Slash", "Ice Beam"}
    diff  = compare_learnsets(set_a, set_b)

    if diff["only_a"] == {"Flamethrower", "Dragon Claw"}:
        ok("compare_learnsets: only_a correct")
    else:
        fail("compare_learnsets only_a", str(diff["only_a"]))

    if diff["only_b"] == {"Surf", "Ice Beam"}:
        ok("compare_learnsets: only_b correct")
    else:
        fail("compare_learnsets only_b", str(diff["only_b"]))

    if diff["shared"] == {"Earthquake", "Air Slash"}:
        ok("compare_learnsets: shared correct")
    else:
        fail("compare_learnsets shared", str(diff["shared"]))

    # Identical sets -> all shared, nothing unique
    diff2 = compare_learnsets(set_a, set_a)
    if diff2["only_a"] == set() and diff2["only_b"] == set() and diff2["shared"] == set_a:
        ok("compare_learnsets: identical sets -> all shared, nothing unique")
    else:
        fail("compare_learnsets identical")

    # Disjoint sets -> nothing shared
    diff3 = compare_learnsets({"A", "B"}, {"C", "D"})
    if diff3["shared"] == set() and diff3["only_a"] == {"A", "B"}:
        ok("compare_learnsets: disjoint sets -> nothing shared")
    else:
        fail("compare_learnsets disjoint")

    # Empty set_b -> everything unique to A
    diff4 = compare_learnsets({"Surf", "Tackle"}, set())
    if diff4["only_a"] == {"Surf", "Tackle"} and diff4["shared"] == set():
        ok("compare_learnsets: empty set_b -> all unique to A")
    else:
        fail("compare_learnsets empty b")

    # ── _build_move_rows ──────────────────────────────────────────────────────

    game_ctx_fake = {"game": "Scarlet / Violet", "game_gen": 9}

    # Unknown move -> graceful ? fallback
    rows_unk = _build_move_rows({"ZZZUnknownMove999"}, game_ctx_fake)
    if len(rows_unk) == 1 and rows_unk[0]["type"] == "?":
        ok("_build_move_rows: unknown move -> graceful ? fallback")
    else:
        fail("_build_move_rows unknown", str(rows_unk))

    # Sorted alphabetically
    rows_sorted = _build_move_rows({"Surf", "Earthquake", "Air Slash"}, game_ctx_fake)
    names = [r["name"] for r in rows_sorted]
    if names == sorted(names):
        ok("_build_move_rows: results sorted alphabetically")
    else:
        fail("_build_move_rows sort", str(names))

    # Empty set -> empty list
    if _build_move_rows(set(), game_ctx_fake) == []:
        ok("_build_move_rows: empty set -> []")
    else:
        fail("_build_move_rows empty")

    # ── display smoke test (mock learnset fetch) ──────────────────────────────
    import io, contextlib

    _pkm_a = {
        "form_name": "Charizard", "pokemon": "charizard",
        "variety_slug": "charizard", "type1": "Fire", "type2": "Flying",
        "base_stats": {"hp": 78, "attack": 84, "defense": 78,
                       "special-attack": 109, "special-defense": 85, "speed": 100},
    }
    _pkm_b = {
        "form_name": "Blastoise", "pokemon": "blastoise",
        "variety_slug": "blastoise", "type1": "Water", "type2": "None",
        "base_stats": {"hp": 79, "attack": 83, "defense": 100,
                       "special-attack": 85, "special-defense": 105, "speed": 78},
    }
    _ls_char = {"forms": {"Charizard": {
        "level-up": [{"move": "Flamethrower", "level": 30}],
        "machine":  [{"move": "Earthquake",   "tm": "TM41"}],
    }}}
    _ls_blas = {"forms": {"Blastoise": {
        "level-up": [{"move": "Surf",       "level": 28}],
        "machine":  [{"move": "Earthquake", "tm": "TM41"}],
    }}}

    _orig_fetch = cache.get_learnset_or_fetch
    def _mock_fetch(slug, form_name, game):
        if slug == "charizard": return _ls_char
        if slug == "blastoise": return _ls_blas
        return None
    cache.get_learnset_or_fetch = _mock_fetch

    # Dummy UI for test (async but we'll run synchronously)
    class DummyUI:
        def __init__(self):
            self.buf = io.StringIO()
        async def print_output(self, text):
            self.buf.write(text + "\n")
        async def input_prompt(self, prompt):
            return ""
        async def confirm(self, prompt):
            return False
        async def select_pokemon(self, game_ctx=None):
            return None
    dummy = DummyUI()
    import asyncio
    asyncio.run(display_learnset_comparison(dummy, _pkm_a, _pkm_b, game_ctx_fake))
    out = dummy.buf.getvalue()
    cache.get_learnset_or_fetch = _orig_fetch

    if "Charizard" in out and "Blastoise" in out:
        ok("display: both Pokemon names present")
    else:
        fail("display names", out[:80])

    if "Unique to Charizard" in out and "Unique to Blastoise" in out:
        ok("display: unique sections shown")
    else:
        fail("display unique sections", out[:200])

    if "Shared by both" in out:
        ok("display: shared section shown")
    else:
        fail("display shared section", out[:200])

    if "Flamethrower" in out and "Surf" in out:
        ok("display: unique moves appear in output")
    else:
        fail("display unique moves", out[:300])

    if "Earthquake" in out:
        ok("display: shared move appears in output")
    else:
        fail("display shared move", out[:300])

    if "Total" in out and "Role" in out:
        ok("display: stat header rows present")
    else:
        fail("display stat header", out[:200])

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 19
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
    else:
        main()