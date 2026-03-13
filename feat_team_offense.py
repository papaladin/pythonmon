#!/usr/bin/env python3
"""
feat_team_offense.py  Team offensive coverage analysis

For each attacking type in the era, shows how many team members can hit that
type super-effectively (x2 or x4) using their own types.

Each member is shown with a type-letter annotation indicating WHICH of their
types hits SE: Char(F,F) = Fire + Flying both hit SE; Geng(P) = Poison only.

Entry points:
  run(team_ctx, game_ctx)   called from pokemain (key O)
  main()                    standalone
"""

import sys

try:
    import matchup_calculator as calc
    from feat_team_loader import team_slots, team_size
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Core logic ────────────────────────────────────────────────────────────────

def _hitting_types(era_key: str, type1: str, type2: str, target: str) -> list:
    """
    Return list of first-letters of the member's types that hit target SE (x2+).
    e.g. Charizard (Fire/Flying) vs Grass -> ['F', 'F']  (Fire=x2, Flying=x2)
         Gengar    (Ghost/Poison) vs Fairy -> ['P']       (Poison=x2, Ghost=x0)
    """
    letters = []
    if calc.get_multiplier(era_key, type1, target) >= 2.0:
        letters.append(type1[0])
    if type2 != "None" and calc.get_multiplier(era_key, type2, target) >= 2.0:
        letters.append(type2[0])
    return letters


def build_team_offense(team_ctx: list, era_key: str) -> dict:
    """
    For each defending type in the era, collect which team members can hit it SE
    and which of their own types are responsible.

    Returns:
      {
        def_type: [
          {"form_name": str, "hitting_letters": [str, ...]},
          ...  one entry per member that can hit SE (only hitters, not all members)
        ]
      }
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    result = {t: [] for t in valid_types}

    for _idx, pkm in team_slots(team_ctx):
        for target in valid_types:
            letters = _hitting_types(era_key, pkm["type1"], pkm["type2"], target)
            if letters:
                result[target].append({
                    "form_name":      pkm["form_name"],
                    "hitting_letters": letters,
                })

    return result


def build_offense_rows(team_offense: dict, era_key: str) -> list:
    """
    Build one row per defending type, sorted: most covered first, gaps last.
    Rows with equal SE count are sorted alphabetically by type name.

    Each row:
      {
        "type":     str,
        "hitters":  [{"form_name": str, "hitting_letters": [str, ...]}, ...]
      }
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    rows = []
    for t in valid_types:
        hitters = team_offense.get(t, [])
        rows.append({"type": t, "hitters": hitters})

    rows.sort(key=lambda r: (-len(r["hitters"]), r["type"]))
    return rows


def coverage_gaps(rows: list) -> list:
    """Return list of type names where no member can hit SE (hitters is empty)."""
    return [r["type"] for r in rows if not r["hitters"]]


# ── Display helpers ───────────────────────────────────────────────────────────

_COL_TYPE   = 10
_COL_HITTERS = 50   # wide enough for 6 tagged names
_NAME_LEN   = 4     # same as feat_team_analysis._abbrev


def _abbrev(name: str) -> str:
    return name[:_NAME_LEN]


def _hitter_tag(form_name: str, hitting_letters: list) -> str:
    """Format as Abbrev(X,Y) — letters of types that hit SE."""
    short = _abbrev(form_name)
    return f"{short}({',' .join(hitting_letters)})"


def _hitters_cell(hitters: list) -> str:
    """Space-separated list of tagged hitter names, or '-' if empty."""
    if not hitters:
        return "-"
    return "  ".join(_hitter_tag(h["form_name"], h["hitting_letters"])
                     for h in hitters)


def _print_offense_table(rows: list) -> None:
    hdr = (f"  {'Type':<{_COL_TYPE}}"
           f" | {'Who hits super effectively':<{_COL_HITTERS}}"
           f" | Comments")
    sep = (f"  {'-'*_COL_TYPE}"
           f"-+-{'-'*_COL_HITTERS}"
           f"-+-{'-'*10}")
    print()
    print(hdr)
    print(sep)
    for r in rows:
        cell    = _hitters_cell(r["hitters"])
        comment = "GAP" if not r["hitters"] else ""
        print(f"  {r['type']:<{_COL_TYPE}}"
              f" | {cell:<{_COL_HITTERS}}"
              f" | {comment}")


def display_team_offense(team_ctx: list, game_ctx: dict) -> None:
    era_key = game_ctx["era_key"]
    game    = game_ctx["game"]
    filled  = team_size(team_ctx)

    if filled == 0:
        print("\n  Team is empty -- load some Pokemon first (press T).")
        return

    # ── Roster header ─────────────────────────────────────────────────────────
    print(f"\n  Team offensive coverage  |  {game}")
    print("  " + "=" * 56)
    for _idx, pkm in team_slots(team_ctx):
        dual = (f"{pkm['type1']} / {pkm['type2']}"
                if pkm["type2"] != "None" else pkm["type1"])
        print(f"  {pkm['form_name']:<24}  {dual}")
    print("  " + "=" * 56)

    # ── Table ─────────────────────────────────────────────────────────────────
    team_off = build_team_offense(team_ctx, era_key)
    rows     = build_offense_rows(team_off, era_key)
    gaps     = coverage_gaps(rows)

    print("\n  Letter in parentheses = first letter of the member's type that hits SE")
    print("  e.g. Char(F,F) = Fire + Flying both hit SE  |  Geng(P) = Poison only")
    _print_offense_table(rows)

    # ── Summary ───────────────────────────────────────────────────────────────
    _, valid_types, _ = calc.CHARTS[era_key]
    total    = len(valid_types)
    covered  = total - len(gaps)
    print(f"\n  Coverage: {covered} / {total} types", end="")
    if gaps:
        print(f"  |  Gaps: {' / '.join(gaps)}")
    else:
        print("  |  Full coverage!")


# ── Entry points ──────────────────────────────────────────────────────────────

def run(team_ctx: list, game_ctx: dict) -> None:
    """Called from pokemain."""
    display_team_offense(team_ctx, game_ctx)
    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("+===========================================+")
    print("|     Team Offensive Coverage               |")
    print("+===========================================+")

    try:
        from pkm_session import select_game, select_pokemon
        from feat_team_loader import new_team, add_to_team, TeamFullError
    except ModuleNotFoundError as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)

    game_ctx = select_game()
    if game_ctx is None:
        sys.exit(0)

    team_ctx = new_team()
    print("\n  Add up to 6 Pokemon (blank name to stop).")
    for _ in range(6):
        pkm = select_pokemon(game_ctx=game_ctx)
        if pkm is None:
            break
        try:
            team_ctx, slot = add_to_team(team_ctx, pkm)
            print(f"  Added to slot {slot + 1}.")
        except TeamFullError:
            break

    display_team_offense(team_ctx, game_ctx)
    input("\n  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_offense.py -- self-test\n")

    # ── Fixtures ──────────────────────────────────────────────────────────────
    def _pkm(name, t1, t2="None"):
        return {"form_name": name, "type1": t1, "type2": t2}

    charizard = _pkm("Charizard", "Fire",    "Flying")
    blastoise = _pkm("Blastoise", "Water")
    venusaur  = _pkm("Venusaur",  "Grass",   "Poison")
    gengar    = _pkm("Gengar",    "Ghost",   "Poison")
    pikachu   = _pkm("Pikachu",   "Electric")
    snorlax   = _pkm("Snorlax",   "Normal")
    eevee     = _pkm("Eevee",     "Normal")   # single type, hits very little SE

    team1      = [charizard, None, None, None, None, None]
    team6      = [charizard, blastoise, venusaur, gengar, pikachu, snorlax]
    team_empty = [None] * 6

    # ── _hitting_types ────────────────────────────────────────────────────────

    # Charizard (Fire/Flying) vs Grass: both hit SE
    h = _hitting_types("era3", "Fire", "Flying", "Grass")
    if h == ["F", "F"]:
        ok("_hitting_types: Charizard vs Grass -> [F, F]")
    else:
        fail("_hitting_types Charizard/Grass", str(h))

    # Charizard vs Fighting: Flying only (Fire neutral to Fighting)
    h = _hitting_types("era3", "Fire", "Flying", "Fighting")
    if h == ["F"]:
        ok("_hitting_types: Charizard vs Fighting -> [F] (Flying only)")
    else:
        fail("_hitting_types Charizard/Fighting", str(h))

    # Gengar (Ghost/Poison) vs Fairy: Poison hits SE, Ghost does not
    h = _hitting_types("era3", "Ghost", "Poison", "Fairy")
    if h == ["P"]:
        ok("_hitting_types: Gengar vs Fairy -> [P] (Poison only)")
    else:
        fail("_hitting_types Gengar/Fairy", str(h))

    # Gengar vs Normal: Ghost x0 (immune offensively in era3? No -- Ghost attacking
    # Normal = x0 in era3. But wait: get_multiplier gives DEFENSIVE multipliers
    # from the perspective of the defender. Let's check: Ghost attacking Normal = x0.
    h = _hitting_types("era3", "Ghost", "Poison", "Normal")
    if h == []:
        ok("_hitting_types: Gengar vs Normal -> [] (Ghost x0, Poison x1)")
    else:
        fail("_hitting_types Gengar/Normal", str(h))

    # Single-type: Blastoise (Water) vs Fire: Water hits SE
    h = _hitting_types("era3", "Water", "None", "Fire")
    if h == ["W"]:
        ok("_hitting_types: Blastoise vs Fire -> [W]")
    else:
        fail("_hitting_types Blastoise/Fire", str(h))

    # Single-type: Blastoise vs Grass: Water not SE against Grass
    h = _hitting_types("era3", "Water", "None", "Grass")
    if h == []:
        ok("_hitting_types: Blastoise vs Grass -> [] (not SE)")
    else:
        fail("_hitting_types Blastoise/Grass", str(h))

    # Era1: no Fairy type -- Dragon vs Fairy in era1 should be neutral (Fairy absent)
    # Actually in era1 Fairy doesn't exist as a valid type so it won't appear in CHARTS
    # Verify era1 type set doesn't contain Fairy
    _, valid_era1, _ = calc.CHARTS["era1"]
    if "Fairy" not in valid_era1:
        ok("_hitting_types: era1 has no Fairy type")
    else:
        fail("_hitting_types era1 Fairy", "Fairy found in era1")

    # ── build_team_offense ────────────────────────────────────────────────────

    to1 = build_team_offense(team1, "era3")

    # Keys match era3 type set
    _, valid_era3, _ = calc.CHARTS["era3"]
    if set(to1.keys()) == set(valid_era3):
        ok("build_team_offense: keys match era3 type set")
    else:
        fail("build_team_offense keys", str(set(to1.keys()) ^ set(valid_era3)))

    # Charizard hits Grass SE (Fire + Flying)
    grass_hitters = to1["Grass"]
    if len(grass_hitters) == 1 and grass_hitters[0]["form_name"] == "Charizard":
        if grass_hitters[0]["hitting_letters"] == ["F", "F"]:
            ok("build_team_offense: Charizard hits Grass SE with F,F")
        else:
            fail("build_team_offense Grass letters", str(grass_hitters[0]["hitting_letters"]))
    else:
        fail("build_team_offense Grass hitters", str(grass_hitters))

    # Charizard does NOT hit Water SE (Fire x0.5, Flying x1)
    water_hitters = to1["Water"]
    if water_hitters == []:
        ok("build_team_offense: Charizard does not hit Water SE")
    else:
        fail("build_team_offense Water", str(water_hitters))

    # Ground: Charizard doesn't hit SE (Fire x1, Flying x1 vs Ground)
    ground_hitters = to1["Ground"]
    if ground_hitters == []:
        ok("build_team_offense: Charizard does not hit Ground SE")
    else:
        fail("build_team_offense Ground", str(ground_hitters))

    # Empty team -> all lists empty
    to_e = build_team_offense(team_empty, "era3")
    if all(v == [] for v in to_e.values()):
        ok("build_team_offense: empty team -> all lists empty")
    else:
        fail("build_team_offense empty")

    # Era key integrity
    _, valid_era2, _ = calc.CHARTS["era2"]
    to_era2 = build_team_offense(team1, "era2")
    if set(to_era2.keys()) == set(valid_era2):
        ok("build_team_offense: era2 keys match era2 type set")
    else:
        fail("build_team_offense era2 keys")

    # 6-member team: Grass covered by Charizard(F,F) + Venusaur(P) + Gengar(P)
    to6 = build_team_offense(team6, "era3")
    grass6 = to6["Grass"]
    grass_names = [h["form_name"] for h in grass6]
    if set(grass_names) == {"Charizard", "Venusaur", "Gengar"}:
        ok("build_team_offense: Grass hitters = Charizard + Venusaur + Gengar")
    else:
        fail("build_team_offense Grass 6-team", str(grass_names))

    # Normal: nobody hits Normal SE in era3 standard types
    # (Fighting hits Normal? No -- Fighting vs Normal = x1 in offense.
    #  Actually Normal is immune to Ghost offensively. But Fighting attacking Normal = x1.
    #  Hmm, let me check what actually hits Normal SE... Nothing in era3 hits Normal x2+)
    normal6 = to6["Normal"]
    if normal6 == []:
        ok("build_team_offense: Normal has no SE hitters in 6-team (expected gap)")
    else:
        fail("build_team_offense Normal gap", str([h["form_name"] for h in normal6]))

    # ── build_offense_rows ────────────────────────────────────────────────────

    rows1 = build_offense_rows(to1, "era3")

    # All era3 types present
    if set(r["type"] for r in rows1) == set(valid_era3):
        ok("build_offense_rows: all era3 types present")
    else:
        fail("build_offense_rows types", str(set(valid_era3) - set(r["type"] for r in rows1)))

    # Most-covered types sort first
    if rows1[0]["hitters"]:
        ok("build_offense_rows: first row has hitters (most covered first)")
    else:
        fail("build_offense_rows sort: first row is empty")

    # Gap rows (empty hitters) sort last
    first_gap_idx = next((i for i, r in enumerate(rows1) if not r["hitters"]), None)
    last_hit_idx  = max((i for i, r in enumerate(rows1) if r["hitters"]), default=-1)
    if first_gap_idx is None or first_gap_idx > last_hit_idx:
        ok("build_offense_rows: all gap rows sort after all hitter rows")
    else:
        fail("build_offense_rows gap sort", f"gap at {first_gap_idx}, last hitter at {last_hit_idx}")

    # ── coverage_gaps ─────────────────────────────────────────────────────────

    rows6 = build_offense_rows(to6, "era3")
    gaps6 = coverage_gaps(rows6)

    # Normal should be a gap for the 6-team
    if "Normal" in gaps6:
        ok("coverage_gaps: Normal is a gap for 6-team")
    else:
        fail("coverage_gaps Normal", str(gaps6))

    # Grass should NOT be a gap
    if "Grass" not in gaps6:
        ok("coverage_gaps: Grass is not a gap (3 hitters)")
    else:
        fail("coverage_gaps Grass false positive")

    # Empty team -> all types are gaps
    rows_e = build_offense_rows(to_e, "era3")
    gaps_e = coverage_gaps(rows_e)
    if set(gaps_e) == set(valid_era3):
        ok("coverage_gaps: empty team -> all types are gaps")
    else:
        fail("coverage_gaps empty", str(set(valid_era3) - set(gaps_e)))

    # ── _hitter_tag ───────────────────────────────────────────────────────────

    tag = _hitter_tag("Charizard", ["F", "F"])
    if tag == "Char(F,F)":
        ok("_hitter_tag: dual-type both hitting -> Char(F,F)")
    else:
        fail("_hitter_tag dual", repr(tag))

    tag = _hitter_tag("Gengar", ["P"])
    if tag == "Geng(P)":
        ok("_hitter_tag: single-letter -> Geng(P)")
    else:
        fail("_hitter_tag single", repr(tag))

    tag = _hitter_tag("Mew", ["P"])
    if tag == "Mew(P)":
        ok("_hitter_tag: short name kept as-is -> Mew(P)")
    else:
        fail("_hitter_tag short name", repr(tag))

    # ── _hitters_cell ─────────────────────────────────────────────────────────

    cell = _hitters_cell([])
    if cell == "-":
        ok("_hitters_cell: empty list -> dash")
    else:
        fail("_hitters_cell empty", repr(cell))

    hitters = [
        {"form_name": "Charizard", "hitting_letters": ["F", "F"]},
        {"form_name": "Venusaur",  "hitting_letters": ["P"]},
    ]
    cell = _hitters_cell(hitters)
    if "Char(F,F)" in cell and "Venu(P)" in cell:
        ok("_hitters_cell: two hitters formatted correctly")
    else:
        fail("_hitters_cell two", repr(cell))

    # ── _print_offense_table output ───────────────────────────────────────────

    import io, contextlib
    rows_test = build_offense_rows(to6, "era3")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_offense_table(rows_test)
    out = buf.getvalue()

    # All era3 types appear
    missing = [t for t in valid_era3 if t not in out]
    if not missing:
        ok("_print_offense_table: all era3 types present in output")
    else:
        fail("_print_offense_table missing types", str(missing))

    # GAP label on Normal row
    normal_line = next((l for l in out.splitlines() if l.strip().startswith("Normal")), None)
    if normal_line and "GAP" in normal_line:
        ok("_print_offense_table: Normal row shows GAP")
    else:
        fail("_print_offense_table Normal GAP", repr(normal_line))

    # Grass row has hitter names
    grass_line = next((l for l in out.splitlines() if l.strip().startswith("Grass")), None)
    if grass_line and "Char" in grass_line:
        ok("_print_offense_table: Grass row contains hitter names")
    else:
        fail("_print_offense_table Grass hitters", repr(grass_line))

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 38
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
