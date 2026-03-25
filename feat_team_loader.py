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

# ── Batch team load helpers ───────────────────────────────────────────────────

def _resolve_batch_name(raw: str, index: dict) -> str | None:
    """
    Resolve a raw name string to a pokemon slug via the local cache index.
    Returns the slug, or None if unresolvable.
    Ambiguous matches: picks first alphabetically and prints a warning.
    """
    from pkm_session import _index_search
    needle  = raw.strip().lower()
    matches = _index_search(needle, index)
    if not matches:
        return None
    if len(matches) > 1:
        print(f"  ?  '{raw}': multiple matches — using '{matches[0]}'.")
    return matches[0]


def _build_pkm_ctx_from_cache(slug: str) -> dict | None:
    """
    Build a pkm_ctx dict from cache for use in batch team load.
    Uses the first (default) form. Returns None if not cached or incomplete.
    """
    import pkm_cache as cache
    data = cache.get_pokemon(slug)
    if not data or not data.get("forms"):
        return None
    form  = data["forms"][0]
    types = form.get("types", [])
    if not types:
        return None
    return {
        "pokemon"           : slug,
        "variety_slug"      : form.get("variety_slug", slug),
        "form_name"         : form["name"],
        "types"             : types,
        "type1"             : types[0],
        "type2"             : types[1] if len(types) > 1 else "None",
        "species_gen"       : data.get("species_gen", 1),
        "form_gen"          : data.get("species_gen", 1),
        "base_stats"        : form.get("base_stats", {}),
        "abilities"         : form.get("abilities", []),
        "egg_groups"        : data.get("egg_groups", []),
        "evolution_chain_id": data.get("evolution_chain_id"),
    }


def _fetch_and_build(slug: str) -> dict | None:
    """
    Fetch a Pokémon from PokeAPI, save to cache, and return a pkm_ctx dict.
    Uses the default form. Returns None on network failure or unknown slug.
    Separated as a module-level function so tests can patch it.
    """
    try:
        import pkm_pokeapi as pokeapi
        import pkm_cache as cache
        data = pokeapi.fetch_pokemon(slug)
        cache.save_pokemon(data["pokemon"], data)
        return _build_pkm_ctx_from_cache(data["pokemon"])
    except (ValueError, ConnectionError):
        return None


def _load_batch(raw: str, team_ctx: list) -> list:
    """
    Process a comma-separated name string, adding matched Pokémon to the team.

    Resolution order for each name:
      1. Local cache index (instant, no network)
      2. PokeAPI fetch + cache on miss (lazy, with loading indicator)

    Names that cannot be resolved even via PokeAPI are skipped with a note.
    Always uses the default form for batch-loaded Pokémon.
    """
    import pkm_cache as cache
    names = [n.strip() for n in raw.split(",") if n.strip()]
    if not names:
        return team_ctx
    index = cache.get_index()
    print(f"\n  Resolving {len(names)} Pokémon...")
    for i, name in enumerate(names):
        if team_size(team_ctx) >= MAX_SLOTS:
            remaining = names[i:]
            print(f"  —  Team full. Skipping: {', '.join(remaining)}.")
            break

        # Step 1: try local index + cache
        slug = _resolve_batch_name(name, index)
        pkm  = _build_pkm_ctx_from_cache(slug) if slug else None

        # Step 2: fall back to PokeAPI on any miss
        if pkm is None:
            fetch_slug = slug or name.strip().lower()
            print(f"  …  '{name}': not cached — fetching...", end=" ", flush=True)
            pkm = _fetch_and_build(fetch_slug)
            if pkm is None:
                print("not found.")
                continue
            print(f"found ({pkm['form_name']}).")

        try:
            team_ctx, slot = add_to_team(team_ctx, pkm)
            print(f"  ✓  {pkm['form_name']:<20} → slot {slot + 1}")
        except TeamFullError:
            remaining = names[i:]
            print(f"  —  Team full. Skipping: {', '.join(remaining)}.")
            break
    return team_ctx


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
            hints.append("name to add  |  name1, name2 to batch-add")
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

        # ── Comma: batch load ────────────────────────────────────────────────
        if "," in raw:
            team_ctx = _load_batch(raw, team_ctx)
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
    passed = 0

    def ok(label):
        nonlocal passed
        passed += 1
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
    def _parse_cmd(raw):
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

    act2, val2 = _parse_cmd("Dragonite")
    if act2 == "add" and val2 == "Dragonite":
        ok("cmd: Dragonite → add (not remove)")
    else: fail("cmd Dragonite", f"({act2}, {val2})")

    # ── _resolve_batch_name ───────────────────────────────────────────────────
    # Use a temporary SQLite database for cache operations
    import tempfile
    import pkm_cache as _cache
    import pkm_sqlite

    tmp_dir = tempfile.mkdtemp()
    _cache._BASE = tmp_dir
    pkm_sqlite.set_base(tmp_dir)

    # Save some Pokémon to the cache so index exists
    _cache.save_pokemon("charizard", {
        "pokemon": "charizard", "species_gen": 1,
        "egg_groups": ["monster", "dragon"], "evolution_chain_id": 1,
        "forms": [{"name": "Charizard", "variety_slug": "charizard",
                   "types": ["Fire","Flying"], "base_stats": {"hp":78},
                   "abilities": [{"slug":"blaze","is_hidden":False}]}]
    })
    _cache.save_pokemon("charmander", {
        "pokemon": "charmander", "species_gen": 1,
        "egg_groups": ["monster", "dragon"], "evolution_chain_id": 1,
        "forms": [{"name": "Charmander", "variety_slug": "charmander",
                   "types": ["Fire"], "base_stats": {"hp":39},
                   "abilities": [{"slug":"blaze","is_hidden":False}]}]
    })
    _cache.save_pokemon("blastoise", {
        "pokemon": "blastoise", "species_gen": 1,
        "egg_groups": ["monster", "water1"], "evolution_chain_id": 1,
        "forms": [{"name": "Blastoise", "variety_slug": "blastoise",
                   "types": ["Water"], "base_stats": {"hp":79},
                   "abilities": [{"slug":"torrent","is_hidden":False}]}]
    })
    _cache.save_pokemon("gengar", {
        "pokemon": "gengar", "species_gen": 1,
        "egg_groups": ["indeterminate"], "evolution_chain_id": 1,
        "forms": [{"name": "Gengar", "variety_slug": "gengar",
                   "types": ["Ghost","Poison"], "base_stats": {"hp":60},
                   "abilities": [{"slug":"cursed-body","is_hidden":False}]}]
    })
    _cache.save_pokemon("rotom-wash", {
        "pokemon": "rotom-wash", "species_gen": 4,
        "egg_groups": ["indeterminate"], "evolution_chain_id": 1,
        "forms": [{"name": "Rotom-Wash", "variety_slug": "rotom-wash",
                   "types": ["Water","Electric"], "base_stats": {"hp":50},
                   "abilities": [{"slug":"levitate","is_hidden":False}]}]
    })
    _cache.save_pokemon("rotom-heat", {
        "pokemon": "rotom-heat", "species_gen": 4,
        "egg_groups": ["indeterminate"], "evolution_chain_id": 1,
        "forms": [{"name": "Rotom-Heat", "variety_slug": "rotom-heat",
                   "types": ["Fire","Electric"], "base_stats": {"hp":50},
                   "abilities": [{"slug":"levitate","is_hidden":False}]}]
    })

    batch_index = _cache.get_index()  # get index after saves

    r = _resolve_batch_name("charizard", batch_index)
    if r == "charizard":
        ok("_resolve_batch_name: exact match → slug")
    else: fail("_resolve_batch_name exact", str(r))

    r = _resolve_batch_name("char", batch_index)
    if r == "charizard":
        ok("_resolve_batch_name: prefix match → first alpha result")
    else: fail("_resolve_batch_name prefix", str(r))

    r = _resolve_batch_name("xyz", batch_index)
    if r is None:
        ok("_resolve_batch_name: no match → None")
    else: fail("_resolve_batch_name no match", str(r))

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = _resolve_batch_name("rotom", batch_index)
    if r == "rotom-heat" and "multiple matches" in buf.getvalue():
        ok("_resolve_batch_name: ambiguous → first alpha + warning printed")
    else: fail("_resolve_batch_name ambiguous", f"r={r} out={buf.getvalue()[:60]}")

    # ── _build_pkm_ctx_from_cache ─────────────────────────────────────────────
    ctx = _build_pkm_ctx_from_cache("charizard")
    required = {"pokemon","variety_slug","form_name","types","type1","type2",
                "species_gen","form_gen","base_stats","abilities",
                "egg_groups","evolution_chain_id"}
    if ctx is not None and required <= set(ctx.keys()):
        ok("_build_pkm_ctx_from_cache: valid cache → all required keys")
    else: fail("_build_pkm_ctx_from_cache valid", str(ctx))

    if ctx and ctx["type1"] == "Fire" and ctx["type2"] == "Flying":
        ok("_build_pkm_ctx_from_cache: types populated correctly")
    else: fail("_build_pkm_ctx_from_cache types", str(ctx))

    ctx_miss = _build_pkm_ctx_from_cache("pikachu")
    if ctx_miss is None:
        ok("_build_pkm_ctx_from_cache: missing cache → None")
    else: fail("_build_pkm_ctx_from_cache miss", str(ctx_miss))

    # ── _load_batch ───────────────────────────────────────────────────────────
    # 2 valid names → team_size == 2
    t_empty = new_team()
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        t_result = _load_batch("charizard, blastoise", t_empty)
    if team_size(t_result) == 2:
        ok("_load_batch: 2 valid names → team_size == 2")
    else: fail("_load_batch 2 names", f"size={team_size(t_result)}")

    # 1 unresolvable + 1 valid → adds 1, skips 1
    # Patch _fetch_and_build to simulate network failure (pikachu not cached)
    import sys as _sys2
    _self = _sys2.modules[__name__]
    _orig_fab = _self._fetch_and_build
    _self._fetch_and_build = lambda slug: None  # network always fails

    t_empty2 = new_team()
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        t_result2 = _load_batch("pikachu, charizard", t_empty2)
    _self._fetch_and_build = _orig_fab

    if team_size(t_result2) == 1:
        ok("_load_batch: 1 miss + 1 hit (API fail) → team_size == 1")
    else: fail("_load_batch miss+hit", f"size={team_size(t_result2)}")

    # PokeAPI fallback: name not in index → _fetch_and_build called and succeeds
    _pikachu_ctx = {
        "pokemon": "pikachu", "variety_slug": "pikachu",
        "form_name": "Pikachu", "types": ["Electric"],
        "type1": "Electric", "type2": "None",
        "species_gen": 1, "form_gen": 1,
        "base_stats": {"hp": 35}, "abilities": [],
        "egg_groups": [], "evolution_chain_id": None,
    }
    _fetch_calls = []
    def _mock_fab(slug):
        _fetch_calls.append(slug)
        return _pikachu_ctx if slug == "pikachu" else None

    _self._fetch_and_build = _mock_fab
    t_empty3 = new_team()
    buf_fab = io.StringIO()
    with contextlib.redirect_stdout(buf_fab):
        t_result_fab = _load_batch("pikachu", t_empty3)
    _self._fetch_and_build = _orig_fab

    if team_size(t_result_fab) == 1 and len(_fetch_calls) == 1:
        ok("_load_batch: PokeAPI fallback called on cache miss, Pokémon added")
    else: fail("_load_batch PokeAPI fallback", f"size={team_size(t_result_fab)} calls={_fetch_calls}")

    if "fetching" in buf_fab.getvalue():
        ok("_load_batch: 'fetching' loading indicator shown during API call")
    else: fail("_load_batch fetching indicator", buf_fab.getvalue()[:80])

    # Full team (5/6) + 2 names → adds 1, reports remaining skipped
    t_full5 = new_team()
    for _ in range(5):
        t_full5, _ = add_to_team(t_full5, _build_pkm_ctx_from_cache("charizard"))
    buf4 = io.StringIO()
    with contextlib.redirect_stdout(buf4):
        t_result3 = _load_batch("blastoise, charizard", t_full5)
    if team_size(t_result3) == 6:
        ok("_load_batch: 5/6 team + 2 names → fills to 6")
    else: fail("_load_batch 5/6 team", f"size={team_size(t_result3)}")

    # Full team → adds 0
    buf5 = io.StringIO()
    with contextlib.redirect_stdout(buf5):
        t_result4 = _load_batch("charizard", t_result3)
    if team_size(t_result4) == 6 and "full" in buf5.getvalue().lower():
        ok("_load_batch: full team → 0 added, team-full note shown")
    else: fail("_load_batch full team", f"size={team_size(t_result4)}")

    # Clean up temp directory
    import shutil
    shutil.rmtree(tmp_dir)

    print()
    total = passed + len(errors)
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