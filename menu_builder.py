#!/usr/bin/env python3
"""
menu_builder.py  Builds context and menu lines for the UI.

Separated from pokemain.py so both CLI and TUI can use the same logic.
"""

import sys

W = 52  # inner width of the menu box (must match the UI's box width)


def _format_stats(base_stats):
    """Return a compact stats string, or empty string if no stats."""
    if not base_stats:
        return ""
    hp = base_stats.get("hp", "?")
    atk = base_stats.get("attack", "?")
    def_ = base_stats.get("defense", "?")
    spa = base_stats.get("special-attack", "?")
    spd = base_stats.get("special-defense", "?")
    spe = base_stats.get("speed", "?")
    try:
        total = str(hp + atk + def_ + spa + spd + spe)
    except (TypeError, ValueError):
        total = "?"
    return f"HP{hp} Atk{atk} Def{def_} SpA{spa} SpD{spd} Spe{spe}  Total {total}"


def build_context_lines(pkm_ctx, game_ctx, team_ctx=None):
    """Build the list of context lines to display in the menu."""
    lines = []
    if pkm_ctx:
        dual = (f"{pkm_ctx['type1']} / {pkm_ctx['type2']}"
                if pkm_ctx["type2"] != "None" else pkm_ctx["type1"])
        lines.append(f"{pkm_ctx['form_name']}  •  {dual}")
        stats_line = _format_stats(pkm_ctx.get("base_stats", {}))
        if stats_line:
            lines.append(stats_line)
    if not pkm_ctx:
        lines.append("No Pokemon loaded")
    if game_ctx:
        lines.append(game_ctx["game"])
    elif not pkm_ctx:
        lines.append("No game selected")
    if team_ctx is not None:
        from feat_team_loader import team_size, team_summary_line
        filled = team_size(team_ctx)
        summary = team_summary_line(team_ctx)
        lines.append(f"Team ({filled}/6): {summary}")
    return lines


def build_menu_lines(pkm_ctx, game_ctx, team_ctx=None, pkm_features=None):
    """Build the list of menu lines (including context and options)."""
    has_pkm = pkm_ctx is not None
    has_game = game_ctx is not None
    both = has_pkm and has_game
    has_team = team_ctx is not None and (lambda t: sum(1 for s in t if s is not None))(team_ctx) > 0

    lines = []

    # Always‑visible core actions
    lines.append("G. Select game" if not has_game else "G. Change game")
    lines.append("P. Load a Pokemon" if not has_pkm else "P. Load a different Pokemon")
    lines.append("T. Manage team")
    lines.append("─" * (W + 2))

    # Features that need game only (or no context)
    if has_game:
        lines.append("M. Look up a move")
    lines.append("B. Browse Pokémon by type")
    lines.append("N. Nature & EV build advisor")
    lines.append("A. Ability browser")
    lines.append("")  # blank line for grouping

    # Features that need a Pokemon (and maybe game)
    if has_pkm:
        lines.append("E. Egg group browser")
    if both:
        lines.append("L. Compare learnsets  (pick a second Pokémon)")
    if has_pkm or both:
        lines.append("")

    # Numbered features (need both Pokemon and game)
    if both and pkm_features:
        for i, (label, _mod, _fn, np, ng, avail) in enumerate(pkm_features, start=1):
            if avail:
                lines.append(f"{i}. {label}")
            else:
                short = label[:W - 18]
                lines.append(f"   {short:<{W - 18}}  [coming soon]")
        lines.append("")

    # Team features (need team and game)
    if has_team and has_game:
        lines.append("V. Team defensive vulnerability analysis")
        lines.append("O. Team offensive coverage")
        lines.append("S. Team moveset synergy")
        lines.append("H. Team builder  (suggest next slot)")
        lines.append("J. Joint team optimisation (full 6‑member search)")
        lines.append("X. Team vs in-game opponent")
        lines.append("")

    # Cache utilities (always visible)
    lines.append("Y.    Pre-load move table  (stats for all ~920 moves)")
    lines.append("W.    Pre-load TM/HM table (TM numbers in move lists)")
    if has_pkm:
        lines.append("R. Refresh data for current Pokemon")
    lines.append("")
    lines.append("Q. Quit")

    # Remove duplicate empty lines while preserving order
    seen = set()
    result = []
    for ln in lines:
        if ln == "":
            if result and result[-1] == "":
                continue
            result.append(ln)
            continue
        if ln in seen:
            continue
        result.append(ln)
        seen.add(ln)
    return result


# ── Self‑tests ────────────────────────────────────────────────────────────────

def _run_tests():
    import sys
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  menu_builder.py — self-test\n")

    # ── Fixtures ──────────────────────────────────────────────────────────────
    def _pkm(name, t1, t2="None", base_stats=None):
        return {
            "form_name": name,
            "type1": t1,
            "type2": t2,
            "base_stats": base_stats or {},
        }

    def _game(name):
        return {"game": name}

    def _team(names):
        # Creates a team_ctx of 6 slots with given names filled in order
        ctx = [None] * 6
        for i, n in enumerate(names):
            if i < 6:
                ctx[i] = {"form_name": n}
        return ctx

    # ── _format_stats ────────────────────────────────────────────────────────
    stats1 = {"hp": 78, "attack": 84, "defense": 78,
              "special-attack": 109, "special-defense": 85, "speed": 100}
    s = _format_stats(stats1)
    if "HP78" in s and "Atk84" in s and "Total 534" in s:
        ok("_format_stats: returns correct string")
    else:
        fail("_format_stats", f"got {s!r}")

    s_empty = _format_stats({})
    if s_empty == "":
        ok("_format_stats: empty dict -> ''")
    else:
        fail("_format_stats empty", f"got {s_empty!r}")

    # ── build_context_lines ──────────────────────────────────────────────────
    # No contexts
    lines = build_context_lines(None, None)
    expected = ["No Pokemon loaded", "No game selected"]
    if lines == expected:
        ok("build_context_lines: no contexts -> no Pokemon, no game")
    else:
        fail("build_context_lines no context", str(lines))

    # Pokemon only
    p = _pkm("Charizard", "Fire", "Flying", stats1)
    lines = build_context_lines(p, None)
    # Should have form/type and stats lines, but no "No game selected"
    if lines == ["Charizard  •  Fire / Flying", "HP78 Atk84 Def78 SpA109 SpD85 Spe100  Total 534"]:
        ok("build_context_lines: Pokemon only -> form/type + stats")
    else:
        fail("build_context_lines Pokemon only", str(lines))

    # Game only
    g = _game("Scarlet / Violet")
    lines = build_context_lines(None, g)
    if lines == ["No Pokemon loaded", "Scarlet / Violet"]:
        ok("build_context_lines: game only -> no Pokemon + game")
    else:
        fail("build_context_lines game only", str(lines))

    # Both Pokemon and game
    lines = build_context_lines(p, g)
    if lines == ["Charizard  •  Fire / Flying", "HP78 Atk84 Def78 SpA109 SpD85 Spe100  Total 534", "Scarlet / Violet"]:
        ok("build_context_lines: both -> form/type, stats, game")
    else:
        fail("build_context_lines both", str(lines))

    # Team context (mock team_loader)
    team_ctx = _team(["Charizard", "Blastoise", "Venusaur"])
    lines = build_context_lines(p, g, team_ctx)
    # Last line should contain team summary
    if len(lines) == 4 and lines[3].startswith("Team (3/6): "):
        ok("build_context_lines: with team -> adds team line")
    else:
        fail("build_context_lines with team", str(lines))

    # ── build_menu_lines ─────────────────────────────────────────────────────
    # No contexts
    menu = build_menu_lines(None, None)
    # Should have core actions, then features, etc.
    if "G. Select game" in menu and "P. Load a Pokemon" in menu and "T. Manage team" in menu:
        ok("build_menu_lines: no contexts -> core actions present")
    else:
        fail("build_menu_lines no contexts", str(menu[:5]))

    # Game only
    menu = build_menu_lines(None, g)
    # Should have M (move lookup) anywhere
    if any("M. Look up a move" in line for line in menu):
        ok("build_menu_lines: game only -> M appears")
    else:
        fail("build_menu_lines game only", str(menu))

    # Pokemon only
    menu = build_menu_lines(p, None)
    # Should have E (egg group)
    if any("E. Egg group browser" in line for line in menu):
        ok("build_menu_lines: Pokemon only -> E appears")
    else:
        fail("build_menu_lines Pokemon only", str(menu))

    # Both
    menu = build_menu_lines(p, g)
    # Should have L (learnset compare) anywhere
    if any("L. Compare learnsets" in line for line in menu):
        ok("build_menu_lines: both -> L appears")
    else:
        fail("build_menu_lines both", str(menu))

    # Team features (with team)
    team_ctx = _team(["Charizard"])
    menu = build_menu_lines(p, g, team_ctx)
    # Should have V, O, S, H, X
    for key in ("V.", "O.", "S.", "H.", "X."):
        if not any(key in line for line in menu):
            fail(f"build_menu_lines with team missing {key}", str(menu))
            break
    else:
        ok("build_menu_lines: team features present")

    # Cache utilities always present
    menu = build_menu_lines(None, None)
    if any("Y." in line for line in menu) and any("W." in line for line in menu):
        ok("build_menu_lines: cache utilities present")
    else:
        fail("build_menu_lines cache utilities", str(menu))

    # Duplicate empty line removal
    # build_menu_lines intentionally inserts blank lines for grouping. Ensure we don't have double blanks.
    menu = build_menu_lines(None, None)
    # Scan for consecutive empty strings
    has_double_empty = any(menu[i] == "" and menu[i+1] == "" for i in range(len(menu)-1))
    if not has_double_empty:
        ok("build_menu_lines: no consecutive empty lines")
    else:
        fail("build_menu_lines double empty", str(menu))

    print()
    total = 11
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
    else:
        # Not meant to be run standalone; print usage
        print("This module is not meant to be run directly. Use --autotest to run self-tests.")