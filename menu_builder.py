#!/usr/bin/env python3
"""
menu_builder.py  Builds context and menu lines for the UI.

Separated from pokemain.py so both CLI and TUI can use the same logic.
"""

W = 52  # inner width of the menu box (must match the UI's box width)

def _format_stats(base_stats):
    """Return a compact stats string, or empty string if no stats."""
    if not base_stats:
        return ""
    hp   = base_stats.get("hp", "?")
    atk  = base_stats.get("attack", "?")
    def_ = base_stats.get("defense", "?")
    spa  = base_stats.get("special-attack", "?")
    spd  = base_stats.get("special-defense", "?")
    spe  = base_stats.get("speed", "?")
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
    has_pkm  = pkm_ctx is not None
    has_game = game_ctx is not None
    both     = has_pkm and has_game
    has_team = team_ctx is not None and (lambda t: sum(1 for s in t if s is not None))(team_ctx) > 0

    lines = []

    # ── Always‑visible core actions ─────────────────────────────────────────
    lines.append("G. Select game" if not has_game else "G. Change game")
    lines.append("P. Load a Pokemon" if not has_pkm else "P. Load a different Pokemon")
    lines.append("T. Manage team")
    lines.append("─" * (W+2))

    # ── Features that need game only (or no context) ────────────────────────
    if has_game:
        lines.append("M. Look up a move")
    lines.append("B. Browse Pokémon by type")
    lines.append("N. Nature & EV build advisor")
    lines.append("A. Ability browser")
    lines.append("")  # blank line for grouping

    # ── Features that need a Pokemon (and maybe game) ───────────────────────
    if has_pkm:
        lines.append("E. Egg group browser")
    if both:
        lines.append("L. Compare learnsets  (pick a second Pokémon)")
    if has_pkm or both:
        lines.append("")

    # ── Numbered features (need both Pokemon and game) ──────────────────────
    if both and pkm_features:
        for i, (label, _mod, _fn, np, ng, avail) in enumerate(pkm_features, start=1):
            if avail:
                lines.append(f"{i}. {label}")
            else:
                short = label[:W-18]
                lines.append(f"   {short:<{W-18}}  [coming soon]")
        lines.append("")

    # ── Team features (need team and game) ──────────────────────────────────
    if has_team and has_game:
        lines.append("V. Team defensive vulnerability analysis")
        lines.append("O. Team offensive coverage")
        lines.append("S. Team moveset synergy")
        lines.append("H. Team builder  (suggest next slot)")
        lines.append("X. Team vs in-game opponent")
        lines.append("")

    # ── Cache utilities (always visible) ────────────────────────────────────
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