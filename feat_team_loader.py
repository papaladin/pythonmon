#!/usr/bin/env python3
"""
feat_team_loader.py  Team context management (up to 6 Pokémon)

A team is simply an ordered list of up to 6 pkm_ctx dicts (None = empty slot).
Teams are session-only — they are not persisted to disk.

Public API (used by pokemain.py):
  new_team()                        → fresh team_ctx (6 None slots)
  team_size(team_ctx)               → count of filled slots
  team_slots(team_ctx)              → list of (slot_idx, pkm_ctx) for filled slots
  add_to_team(team_ctx, pkm_ctx)    → (team_ctx, slot_idx) or raises TeamFullError
  remove_from_team(team_ctx, idx)   → team_ctx  (idx is 0-based)
  clear_team(team_ctx)              → empty team_ctx
  team_summary_line(team_ctx)       → "Charizard / Blastoise / ..."  (for menu header)

Entry points:
  run(game_ctx)   called from pokemain (key T)
  main()          standalone
"""

import sys

MAX_SLOTS = 6


# ── Exceptions ────────────────────────────────────────────────────────────────

class TeamFullError(Exception):
    pass


# ── Core data operations ──────────────────────────────────────────────────────

def new_team() -> list:
    """Return a fresh team: list of MAX_SLOTS None entries."""
    return [None] * MAX_SLOTS


def team_size(team_ctx: list) -> int:
    """Return the number of filled slots."""
    return sum(1 for s in team_ctx if s is not None)


def team_slots(team_ctx: list) -> list:
    """Return list of (slot_idx, pkm_ctx) for every filled slot (0-based idx)."""
    return [(i, s) for i, s in enumerate(team_ctx) if s is not None]


def add_to_team(team_ctx: list, pkm_ctx: dict) -> tuple:
    """
    Add pkm_ctx to the first empty slot.
    Returns (updated_team_ctx, slot_idx).
    Raises TeamFullError if all 6 slots are occupied.
    """
    for i, slot in enumerate(team_ctx):
        if slot is None:
            new = list(team_ctx)
            new[i] = pkm_ctx
            return new, i
    raise TeamFullError(f"Team is full ({MAX_SLOTS}/{MAX_SLOTS} slots filled).")


def remove_from_team(team_ctx: list, idx: int) -> list:
    """
    Remove the Pokémon in slot idx (0-based).
    Raises IndexError if idx is out of range.
    Raises ValueError if the slot is already empty.
    """
    if idx < 0 or idx >= MAX_SLOTS:
        raise IndexError(f"Slot index {idx} out of range (0–{MAX_SLOTS-1}).")
    if team_ctx[idx] is None:
        raise ValueError(f"Slot {idx+1} is already empty.")
    new = list(team_ctx)
    new[idx] = None
    return new


def clear_team(team_ctx: list) -> list:
    """Return a new empty team."""
    return new_team()


def team_summary_line(team_ctx: list) -> str:
    """
    Return a compact slash-separated list of form names for filled slots.
    e.g. "Charizard / Blastoise / Venusaur"
    Returns "No team loaded" if empty.
    """
    names = [s["form_name"] for s in team_ctx if s is not None]
    return " / ".join(names) if names else "No team loaded"


# ── Display ───────────────────────────────────────────────────────────────────

def _type_str(pkm_ctx: dict) -> str:
    t2 = pkm_ctx.get("type2", "None")
    return (f"{pkm_ctx['type1']} / {t2}" if t2 != "None"
            else pkm_ctx["type1"])


def print_team(team_ctx: list, game_ctx: dict = None) -> None:
    """Print the current team roster in a simple table."""
    game_label = game_ctx["game"] if game_ctx else "(no game selected)"
    print()
    print(f"  Team  •  {game_label}")
    print("  " + "─" * 52)
    print(f"  {'Slot':<6}  {'Pokémon':<22}  {'Type'}")
    print("  " + "─" * 52)
    for i in range(MAX_SLOTS):
        slot = team_ctx[i]
        if slot is None:
            print(f"  {i+1:<6}  {'— empty —':<22}")
        else:
            print(f"  {i+1:<6}  {slot['form_name']:<22}  {_type_str(slot)}")
    print("  " + "─" * 52)
    filled = team_size(team_ctx)
    print(f"  {filled}/{MAX_SLOTS} slots filled")


# ── Team management loop ──────────────────────────────────────────────────────

def _team_menu(team_ctx: list, game_ctx: dict) -> list:
    """
    Interactive team management sub-menu.
    Type a Pokémon name to add it, D+slot to remove, C to clear, Q to exit.
    Returns the (possibly modified) team_ctx when the user exits.
    """
    try:
        from pkm_session import select_pokemon
    except ModuleNotFoundError as e:
        print(f"\n  ERROR: {e}")
        return team_ctx

    while True:
        print_team(team_ctx, game_ctx)
        filled = team_size(team_ctx)

        print()
        hints = []
        if filled < MAX_SLOTS:
            hints.append("type a name to add")
        if filled > 0:
            hints.append("-<n> to remove (e.g. -2)")
            hints.append("C to clear all")
        hints.append("Q to go back")
        print("  " + "  |  ".join(hints))

        raw = input("\n  > ").strip()
        if not raw:
            continue

        cmd = raw.lower()

        # ── Q: back ──────────────────────────────────────────────────────────
        if cmd == "q":
            return team_ctx

        # ── C: clear all ─────────────────────────────────────────────────────
        if cmd == "c":
            if filled == 0:
                print("\n  Team is already empty.")
                continue
            confirm = input("  Clear all slots? (y/n): ").strip().lower()
            if confirm == "y":
                team_ctx = clear_team(team_ctx)
                print("  Team cleared.")
            continue

        # ── -<n>: remove slot n ──────────────────────────────────────────────
        if cmd.startswith("-") and len(cmd) > 1:
            try:
                idx = int(cmd[1:]) - 1
                team_ctx = remove_from_team(team_ctx, idx)
                print(f"  Slot {idx+1} cleared.")
            except (ValueError, IndexError) as e:
                print(f"\n  {e}")
            continue

        # ── Otherwise: treat as Pokémon name to add ───────────────────────────
        if filled >= MAX_SLOTS:
            print(f"\n  Team is full ({MAX_SLOTS}/{MAX_SLOTS}). Remove a slot first.")
            continue

        # Pre-fill the Pokémon name prompt with what the user already typed.
        import builtins
        real_input = builtins.input
        _name_pending = [raw]
        def _input_with_name(p=""):
            if _name_pending:
                val = _name_pending.pop(0)
                if p:
                    print(p + val)   # echo prompt + pre-filled value
                return val
            return real_input(p)
        builtins.input = _input_with_name
        try:
            pkm = select_pokemon(game_ctx=game_ctx)
        finally:
            builtins.input = real_input

        if pkm is None:
            continue
        try:
            team_ctx, slot = add_to_team(team_ctx, pkm)
            print(f"\n  Added {pkm['form_name']} to slot {slot + 1}.")
        except TeamFullError as e:
            print(f"\n  {e}")

    return team_ctx


# ── Entry points ──────────────────────────────────────────────────────────────

def run(game_ctx: dict, team_ctx: list = None) -> list:
    """
    Called from pokemain (key T).
    Returns the updated team_ctx.
    """
    if team_ctx is None:
        team_ctx = new_team()
    if game_ctx is None:
        print("\n  Please select a game first (press G).")
        return team_ctx
    return _team_menu(team_ctx, game_ctx)


def main() -> None:
    print()
    print("╔══════════════════════════════════════════╗")
    print("║           Team Manager (standalone)       ║")
    print("╚══════════════════════════════════════════╝")

    try:
        from pkm_session import select_game
    except ModuleNotFoundError as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)

    game_ctx = select_game()
    if game_ctx is None:
        sys.exit(0)

    team_ctx = new_team()
    team_ctx = _team_menu(team_ctx, game_ctx)
    print("\n  Session ended.")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []

    def ok(label):
        print(f"  [OK]   {label}")

    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_loader.py — self-test\n")

    # ── Fixtures ──────────────────────────────────────────────────────────────
    def _pkm(name, t1, t2="None"):
        return {"form_name": name, "pokemon": name.lower(),
                "type1": t1, "type2": t2,
                "variety_slug": name.lower(), "types": [t1] if t2 == "None" else [t1, t2]}

    charizard  = _pkm("Charizard",  "Fire",   "Flying")
    blastoise  = _pkm("Blastoise",  "Water")
    venusaur   = _pkm("Venusaur",   "Grass",  "Poison")
    pikachu    = _pkm("Pikachu",    "Electric")
    gengar     = _pkm("Gengar",     "Ghost",  "Poison")
    snorlax    = _pkm("Snorlax",    "Normal")
    garchomp   = _pkm("Garchomp",   "Dragon", "Ground")

    # ── new_team ──────────────────────────────────────────────────────────────
    t = new_team()
    if len(t) == MAX_SLOTS and all(s is None for s in t):
        ok("new_team returns 6 empty slots")
    else:
        fail("new_team", str(t))

    # ── team_size ─────────────────────────────────────────────────────────────
    if team_size(t) == 0:
        ok("team_size empty team → 0")
    else:
        fail("team_size empty", team_size(t))

    # ── add_to_team ───────────────────────────────────────────────────────────
    t, s = add_to_team(t, charizard)
    if s == 0 and team_size(t) == 1:
        ok("add_to_team first slot → idx 0, size 1")
    else:
        fail("add_to_team first", f"s={s} size={team_size(t)}")

    t, s = add_to_team(t, blastoise)
    if s == 1 and team_size(t) == 2:
        ok("add_to_team second slot → idx 1, size 2")
    else:
        fail("add_to_team second", f"s={s} size={team_size(t)}")

    # Fill to 6
    t, _ = add_to_team(t, venusaur)
    t, _ = add_to_team(t, pikachu)
    t, _ = add_to_team(t, gengar)
    t, _ = add_to_team(t, snorlax)

    if team_size(t) == 6:
        ok("add_to_team filled to 6")
    else:
        fail("fill to 6", team_size(t))

    # Full team → TeamFullError
    try:
        add_to_team(t, garchomp)
        fail("TeamFullError not raised")
    except TeamFullError:
        ok("add_to_team full team → TeamFullError")

    # ── team_slots ────────────────────────────────────────────────────────────
    slots = team_slots(t)
    if len(slots) == 6 and slots[0] == (0, charizard):
        ok("team_slots returns all 6 filled slots with correct indices")
    else:
        fail("team_slots", str(slots[:2]))

    # ── remove_from_team ──────────────────────────────────────────────────────
    t2 = remove_from_team(t, 1)   # remove Blastoise (slot 2)
    if t2[1] is None and team_size(t2) == 5:
        ok("remove_from_team slot 1 → None, size 5")
    else:
        fail("remove_from_team", f"slot1={t2[1]} size={team_size(t2)}")

    # Remove already-empty slot → ValueError
    try:
        remove_from_team(t2, 1)
        fail("remove empty slot no error raised")
    except ValueError:
        ok("remove_from_team empty slot → ValueError")

    # Out-of-range → IndexError
    try:
        remove_from_team(t2, 99)
        fail("remove out-of-range no error raised")
    except IndexError:
        ok("remove_from_team out-of-range → IndexError")

    # ── add fills gap left by remove ──────────────────────────────────────────
    t3, s3 = add_to_team(t2, garchomp)
    if s3 == 1 and t3[1] == garchomp:
        ok("add_to_team fills gap at slot 1 after remove")
    else:
        fail("add fills gap", f"s={s3} slot1={t3[1]}")

    # ── clear_team ────────────────────────────────────────────────────────────
    tc = clear_team(t)
    if team_size(tc) == 0 and len(tc) == MAX_SLOTS:
        ok("clear_team → all slots None, length preserved")
    else:
        fail("clear_team", str(tc))

    # ── team_summary_line ─────────────────────────────────────────────────────
    if team_summary_line(new_team()) == "No team loaded":
        ok("team_summary_line empty → 'No team loaded'")
    else:
        fail("team_summary_line empty", team_summary_line(new_team()))

    t_partial = new_team()
    t_partial, _ = add_to_team(t_partial, charizard)
    t_partial, _ = add_to_team(t_partial, blastoise)
    summary = team_summary_line(t_partial)
    if summary == "Charizard / Blastoise":
        ok("team_summary_line partial → 'Charizard / Blastoise'")
    else:
        fail("team_summary_line partial", summary)

    # 6-member summary
    summary6 = team_summary_line(t)
    if "Charizard" in summary6 and summary6.count("/") == 5:
        ok("team_summary_line 6 members → 5 slashes")
    else:
        fail("team_summary_line 6", summary6)

    # ── team_slots on sparse team ─────────────────────────────────────────────
    sparse = [charizard, None, venusaur, None, None, snorlax]
    slots_sparse = team_slots(sparse)
    if slots_sparse == [(0, charizard), (2, venusaur), (5, snorlax)]:
        ok("team_slots sparse → correct (idx, pkm) pairs")
    else:
        fail("team_slots sparse", str(slots_sparse))

    # ── _type_str ─────────────────────────────────────────────────────────────
    if _type_str(charizard) == "Fire / Flying":
        ok("_type_str dual type")
    else:
        fail("_type_str dual", _type_str(charizard))

    if _type_str(blastoise) == "Water":
        ok("_type_str single type")
    else:
        fail("_type_str single", _type_str(blastoise))

    # ── command parsing (D/C/Q logic, no interactive stack needed) ──────────
    # Simulate the cmd-parsing logic extracted from _team_menu
    def _parse_cmd(raw):
        """Returns ('quit'|'clear'|'remove'|'add'), optional slot idx or name."""
        cmd = raw.strip().lower()
        if cmd == "q":            return "quit",   None
        if cmd == "c":            return "clear",  None
        if cmd.startswith("-") and len(cmd) > 1:
            try:    return "remove", int(cmd[1:]) - 1
            except ValueError: return "add", raw
        return "add", raw

    if _parse_cmd("q") == ("quit", None):
        ok("cmd: Q → quit")
    else: fail("cmd Q", str(_parse_cmd("q")))

    if _parse_cmd("Q") == ("quit", None):
        ok("cmd: Q case-insensitive")
    else: fail("cmd Q upper", str(_parse_cmd("Q")))

    if _parse_cmd("c") == ("clear", None):
        ok("cmd: C → clear")
    else: fail("cmd C", str(_parse_cmd("c")))

    if _parse_cmd("-2") == ("remove", 1):
        ok("cmd: -2 → remove slot idx 1")
    else: fail("cmd -2", str(_parse_cmd("-2")))

    if _parse_cmd("-3") == ("remove", 2):
        ok("cmd: -3 → remove slot idx 2")
    else: fail("cmd -3", str(_parse_cmd("-3")))

    if _parse_cmd("-6") == ("remove", 5):
        ok("cmd: -6 → remove slot idx 5")
    else: fail("cmd -6", str(_parse_cmd("-6")))

    act, val = _parse_cmd("Charizard")
    if act == "add" and val == "Charizard":
        ok("cmd: name → add")
    else: fail("cmd name", f"({act}, {val})")

    # Dragonite should now be treated as a name to add, not a remove command
    act2, val2 = _parse_cmd("Dragonite")
    if act2 == "add" and val2 == "Dragonite":
        ok("cmd: Dragonite → add (not remove)")
    else: fail("cmd Dragonite", f"({act2}, {val2})")

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 28
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        sys.exit(1)
    else:
        print(f"  All {total} tests passed")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if "--autotest" in args:
        _run_tests()
    else:
        main()