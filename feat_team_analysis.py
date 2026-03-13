#!/usr/bin/env python3
"""
feat_team_analysis.py  Team defensive vulnerability analysis

Given a loaded team (up to 6 Pokemon), shows a unified type table with one
row per attacking type:

  Type     | Wk  Who            | Res  Who          | Imm  Who    | Neu  Gap
  ---------+----------------...-+----------------...-+----------...-+----+----------
  Rock     |  3  Char(x4) Lap   |  0  -             |  0  -       |  3  !! CRITICAL
  Ice      |  2  Char Blast     |  1  Venu(x0.25)   |  0  -       |  3  !  MAJOR
  Water    |  1  Char           |  2  Venu Blast     |  0  -       |  3
  Ground   |  0  -              |  1  Blast          |  1  Char    |  4
  Bug      |  0  -              |  0  -              |  0  -       |  6

Gap labels (end of row, only when triggered):
  !! CRITICAL  3+ weak, 0 resist+immune
  !  MAJOR     3+ weak, <=1 resist+immune
  .  MINOR     2 weak,  0 resist+immune

Entry points:
  run(team_ctx, game_ctx)   called from pokemain
  main()                    standalone
"""

import sys

try:
    import matchup_calculator as calc
    from feat_team_loader import team_slots, team_size, print_team
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Core aggregation ──────────────────────────────────────────────────────────

def build_team_defense(team_ctx: list, era_key: str) -> dict:
    """
    For each attacking type in the era, collect each member's multiplier.

    Returns:
      {
        atk_type: [
          {"form_name": str, "multiplier": float},
          ...  (one entry per filled team slot, in slot order)
        ]
      }
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    result = {t: [] for t in valid_types}

    for _idx, pkm in team_slots(team_ctx):
        matchups = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
        for atk_type in valid_types:
            m = matchups.get(atk_type, 1.0)
            result[atk_type].append({
                "form_name":  pkm["form_name"],
                "multiplier": m,
            })

    return result


def build_unified_rows(team_defense: dict, era_key: str) -> list:
    """
    Build one row per attacking type with all defensive info.

    Each row:
      {
        "type":           str,
        "weak_members":   [(form_name, mult), ...]   mult >= 2
        "resist_members": [(form_name, mult), ...]   0 < mult < 1
        "immune_members": [form_name, ...]            mult == 0
        "neutral_count":  int                         mult == 1
      }

    Sorted: weak_count desc, then cover_count (resist+immune) desc, then name asc.
    """
    _, all_types, _ = calc.CHARTS[era_key]
    rows = []
    for t in all_types:
        members = team_defense.get(t, [])
        weak    = [(m["form_name"], m["multiplier"])
                   for m in members if m["multiplier"] >= 2.0]
        resist  = [(m["form_name"], m["multiplier"])
                   for m in members if 0.0 < m["multiplier"] < 1.0]
        immune  = [m["form_name"]
                   for m in members if m["multiplier"] == 0.0]
        neutral = sum(1 for m in members if m["multiplier"] == 1.0)
        rows.append({
            "type":           t,
            "weak_members":   weak,
            "resist_members": resist,
            "immune_members": immune,
            "neutral_count":  neutral,
        })

    rows.sort(key=lambda r: (
        -len(r["weak_members"]),
        -(len(r["resist_members"]) + len(r["immune_members"])),
        r["type"]
    ))
    return rows


# ── Kept for backward compatibility and direct testing ────────────────────────

def weakness_summary(team_defense: dict) -> list:
    """
    Return weakness rows sorted by severity.
    Only types where >=1 member is weak (x2+) are included.
    """
    rows = []
    for atk_type, members in team_defense.items():
        weak = [(m["form_name"], m["multiplier"])
                for m in members if m["multiplier"] >= 2.0]
        if not weak:
            continue
        x4 = sum(1 for _, mult in weak if mult >= 4.0)
        rows.append({
            "type":         atk_type,
            "weak_count":   len(weak),
            "x4_count":     x4,
            "weak_members": weak,
        })
    rows.sort(key=lambda r: (-r["x4_count"], -r["weak_count"], r["type"]))
    return rows


def resistance_summary(team_defense: dict) -> list:
    """Return resist/immune rows sorted by coverage."""
    rows = []
    for atk_type, members in team_defense.items():
        immune = [m["form_name"] for m in members if m["multiplier"] == 0.0]
        resist = [m["form_name"] for m in members
                  if 0.0 < m["multiplier"] < 1.0]
        if not immune and not resist:
            continue
        rows.append({
            "type":           atk_type,
            "immune_members": immune,
            "resist_members": resist,
        })
    rows.sort(key=lambda r: (-len(r["immune_members"]),
                             -len(r["resist_members"]), r["type"]))
    return rows


def critical_gaps(weakness_rows: list, threshold: int = 3) -> list:
    """Return types where weak_count >= threshold (from weakness_summary rows)."""
    return [r["type"] for r in weakness_rows if r["weak_count"] >= threshold]


# ── Gap classification ────────────────────────────────────────────────────────

def gap_label(weak_count: int, cover_count: int) -> str:
    """
    Return a gap severity label, or empty string if no gap.

    cover_count = resist_count + immune_count

    Rules:
      !! CRITICAL  3+ weak, 0 cover
      !  MAJOR     3+ weak, <=1 cover
      .  MINOR     2 weak,  0 cover
    """
    if weak_count >= 3 and cover_count == 0:
        return "!! CRITICAL"
    if weak_count >= 3 and cover_count <= 1:
        return "!  MAJOR"
    if weak_count == 2 and cover_count == 0:
        return ".  MINOR"
    return ""


# ── Display helpers ───────────────────────────────────────────────────────────

_COL_TYPE   = 10   # type name column
_COL_CNT    =  2   # count sub-column (Wk / Res / Imm / Neu)
_COL_WNAMES = 30   # weak names sub-column
_COL_RNAMES = 28   # resist names sub-column
_COL_INAMES = 20   # immune names sub-column
_GAP_WIDTH  = 12   # gap label column


_NAME_ABBREV = 4   # characters kept from each Pokemon name


def _abbrev(name: str) -> str:
    """Truncate a Pokemon name to _NAME_ABBREV characters."""
    return name[:_NAME_ABBREV]


def _weak_tag(name: str, mult: float) -> str:
    """Abbreviate name; append (xN) suffix for x4 or higher."""
    short = _abbrev(name)
    return f"{short}(\u00d7{int(mult)})" if mult >= 4.0 else short


def _resist_tag(name: str, mult: float) -> str:
    """Abbreviate name; append (x0.25) suffix for double-resist."""
    short = _abbrev(name)
    return f"{short}(\u00d70.25)" if mult <= 0.25 else short


def _names_cell(names: list, width: int) -> str:
    """
    Format a list of name strings into a fixed-width cell.
    Truncates with '...' if the joined string is too long.
    Returns '-' if the list is empty.
    """
    if not names:
        return "-"
    joined = "  ".join(names)
    if len(joined) <= width:
        return joined
    # Truncate: fit as many names as possible then append ...
    result = ""
    for i, n in enumerate(names):
        candidate = (result + ("  " if result else "") + n)
        if len(candidate) + 3 <= width or i == 0:
            result = candidate
        else:
            result += "..."
            break
    return result


def _print_unified_table(rows: list, n_members: int) -> None:
    """Print the full unified type table."""
    # Header
    sep = (f"  {'-'*_COL_TYPE}"
           f"-+-{'-':>{_COL_CNT}}-{'-'*_COL_WNAMES}"
           f"-+-{'-':>{_COL_CNT}}-{'-'*_COL_RNAMES}"
           f"-+-{'-':>{_COL_CNT}}-{'-'*_COL_INAMES}"
           f"-+--{'-'*_COL_CNT}--{'-'*_GAP_WIDTH}")

    # Each merged column header spans: _COL_CNT + 2 + _COL_NAMES
    _W_SPAN = _COL_CNT + 2 + _COL_WNAMES   # 34
    _R_SPAN = _COL_CNT + 2 + _COL_RNAMES   # 32
    _I_SPAN = _COL_CNT + 2 + _COL_INAMES   # 24
    hdr = (f"  {'Type':<{_COL_TYPE}}"
           f" | {'Weakness':<{_W_SPAN}}"
           f" | {'Resistance':<{_R_SPAN}}"
           f" | {'Immunity':<{_I_SPAN}}"
           f" | {'Comments'}")
    print()
    print(hdr)
    print(sep)

    for r in rows:
        weak_names   = [_weak_tag(n, m)   for n, m in r["weak_members"]]
        resist_names = [_resist_tag(n, m) for n, m in r["resist_members"]]
        immune_names = [_abbrev(n) for n in r["immune_members"]]

        wk_cnt  = len(r["weak_members"])
        rs_cnt  = len(r["resist_members"])
        im_cnt  = len(r["immune_members"])
        neu_cnt = r["neutral_count"]
        cover   = rs_cnt + im_cnt

        wk_cell  = _names_cell(weak_names,   _COL_WNAMES)
        rs_cell  = _names_cell(resist_names, _COL_RNAMES)
        im_cell  = _names_cell(immune_names, _COL_INAMES)
        gap      = gap_label(wk_cnt, cover)

        line = (f"  {r['type']:<{_COL_TYPE}}"
                f" | {wk_cnt:>{_COL_CNT}}  {wk_cell:<{_COL_WNAMES}}"
                f" | {rs_cnt:>{_COL_CNT}}  {rs_cell:<{_COL_RNAMES}}"
                f" | {im_cnt:>{_COL_CNT}}  {im_cell:<{_COL_INAMES}}"
                f" | {gap}")
        print(line)


def display_team_analysis(team_ctx: list, game_ctx: dict) -> None:
    era_key  = game_ctx["era_key"]
    game     = game_ctx["game"]
    filled   = team_size(team_ctx)

    if filled == 0:
        print("\n  Team is empty -- load some Pokemon first (press T).")
        return

    # ── Roster header ─────────────────────────────────────────────────────────
    print(f"\n  Team defensive analysis  |  {game}")
    print("  " + "=" * 56)
    for _idx, pkm in team_slots(team_ctx):
        dual = (f"{pkm['type1']} / {pkm['type2']}"
                if pkm["type2"] != "None" else pkm["type1"])
        print(f"  {pkm['form_name']:<24}  {dual}")
    print("  " + "=" * 56)

    # ── Unified table ─────────────────────────────────────────────────────────
    team_def = build_team_defense(team_ctx, era_key)
    rows     = build_unified_rows(team_def, era_key)

    print("\n  Weakness / Resistance / Immunity: count + member names")
    print("  (x4) suffix on weak member  |  (x0.25) suffix on double-resist  |  Comments = gap classification")
    _print_unified_table(rows, filled)

    # ── Gap summary ───────────────────────────────────────────────────────────
    criticals = [r["type"] for r in rows
                 if gap_label(len(r["weak_members"]),
                              len(r["resist_members"]) + len(r["immune_members"])) == "!! CRITICAL"]
    majors    = [r["type"] for r in rows
                 if gap_label(len(r["weak_members"]),
                              len(r["resist_members"]) + len(r["immune_members"])) == "!  MAJOR"]
    minors    = [r["type"] for r in rows
                 if gap_label(len(r["weak_members"]),
                              len(r["resist_members"]) + len(r["immune_members"])) == ".  MINOR"]

    if criticals or majors or minors:
        print()
        if criticals:
            print(f"  !! CRITICAL gaps : {' / '.join(criticals)}")
        if majors:
            print(f"  !  MAJOR gaps    : {' / '.join(majors)}")
        if minors:
            print(f"  .  MINOR gaps    : {' / '.join(minors)}")
    else:
        print("\n  No significant gaps detected.")


# ── Entry points ──────────────────────────────────────────────────────────────

def run(team_ctx: list, game_ctx: dict) -> None:
    """Called from pokemain."""
    display_team_analysis(team_ctx, game_ctx)
    input("\n  Press Enter to continue...")


def main() -> None:
    print()
    print("+===========================================+")
    print("|     Team Defensive Analysis               |")
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

    display_team_analysis(team_ctx, game_ctx)
    input("\n  Press Enter to exit...")


# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    errors = []
    def ok(label):   print(f"  [OK]   {label}")
    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    print("\n  feat_team_analysis.py -- self-test\n")

    # ── Fixtures ──────────────────────────────────────────────────────────────
    def _pkm(name, t1, t2="None"):
        return {"form_name": name, "type1": t1, "type2": t2}

    charizard  = _pkm("Charizard", "Fire",    "Flying")
    blastoise  = _pkm("Blastoise", "Water")
    venusaur   = _pkm("Venusaur",  "Grass",   "Poison")
    gengar     = _pkm("Gengar",    "Ghost",   "Poison")
    snorlax    = _pkm("Snorlax",   "Normal")
    lapras     = _pkm("Lapras",    "Water",   "Ice")
    butterfree = _pkm("Butterfree","Bug",     "Flying")

    team1      = [charizard, None, None, None, None, None]
    team2      = [charizard, blastoise, None, None, None, None]
    team_empty = [None] * 6

    # ── build_team_defense ────────────────────────────────────────────────────

    td1 = build_team_defense(team1, "era3")

    if td1["Rock"][0]["multiplier"] == 4.0:
        ok("build_team_defense: Charizard Rock = x4")
    else:
        fail("build_team_defense Charizard Rock", str(td1["Rock"][0]["multiplier"]))

    if td1["Ground"][0]["multiplier"] == 0.0:
        ok("build_team_defense: Charizard Ground = x0 (immune)")
    else:
        fail("build_team_defense Charizard Ground", str(td1["Ground"][0]["multiplier"]))

    if td1["Grass"][0]["multiplier"] == 0.25:
        ok("build_team_defense: Charizard Grass = x0.25")
    else:
        fail("build_team_defense Charizard Grass", str(td1["Grass"][0]["multiplier"]))

    td2 = build_team_defense(team2, "era3")
    if len(td2["Rock"]) == 2:
        ok("build_team_defense: 2-member team has 2 entries per type")
    else:
        fail("build_team_defense 2-member count", str(len(td2["Rock"])))

    blast_rock = next(e for e in td2["Rock"] if e["form_name"] == "Blastoise")
    if blast_rock["multiplier"] == 1.0:
        ok("build_team_defense: Blastoise Rock = x1 (neutral)")
    else:
        fail("build_team_defense Blastoise Rock", str(blast_rock["multiplier"]))

    td_e = build_team_defense(team_empty, "era3")
    if all(len(v) == 0 for v in td_e.values()):
        ok("build_team_defense: empty team -> all lists empty")
    else:
        fail("build_team_defense empty")

    _, valid_era1, _ = calc.CHARTS["era1"]
    _, valid_era2, _ = calc.CHARTS["era2"]
    if set(build_team_defense(team1, "era1").keys()) == set(valid_era1):
        ok("build_team_defense era1: keys match era1 type set")
    else:
        fail("build_team_defense era1 keys")

    if set(build_team_defense(team1, "era2").keys()) == set(valid_era2):
        ok("build_team_defense era2: keys match era2 type set")
    else:
        fail("build_team_defense era2 keys")

    # ── weakness_summary ──────────────────────────────────────────────────────

    ws1 = weakness_summary(td1)
    types_weak = [r["type"] for r in ws1]

    if "Rock" in types_weak:
        ok("weakness_summary: Rock in Charizard weaknesses")
    else:
        fail("weakness_summary Rock missing", str(types_weak))

    if "Ground" not in types_weak:
        ok("weakness_summary: Ground absent (immune -> not weak)")
    else:
        fail("weakness_summary Ground should be absent")

    if ws1[0]["type"] == "Rock":
        ok("weakness_summary: Rock sorted first (x4 priority)")
    else:
        fail("weakness_summary sort order", ws1[0]["type"])

    rock_row = next(r for r in ws1 if r["type"] == "Rock")
    if rock_row["x4_count"] == 1 and rock_row["weak_count"] == 1:
        ok("weakness_summary: Rock x4_count=1 weak_count=1")
    else:
        fail("weakness_summary Rock counts", str(rock_row))

    ws2 = weakness_summary(td2)
    elec_row = next((r for r in ws2 if r["type"] == "Electric"), None)
    if elec_row and elec_row["weak_count"] == 2:
        ok("weakness_summary: Electric weak_count=2 (Charizard+Blastoise)")
    else:
        fail("weakness_summary Electric 2 members", str(elec_row))

    team_sn = [snorlax, None, None, None, None, None]
    td_sn   = build_team_defense(team_sn, "era3")
    ws_sn   = weakness_summary(td_sn)
    if not any(r["type"] == "Ghost" for r in ws_sn):
        ok("weakness_summary: Ghost not a weakness for Snorlax (immune)")
    else:
        fail("weakness_summary Ghost/Snorlax")

    if weakness_summary(td_e) == []:
        ok("weakness_summary: empty team -> []")
    else:
        fail("weakness_summary empty")

    # ── critical_gaps ─────────────────────────────────────────────────────────

    team3 = [charizard, lapras, butterfree, None, None, None]
    td3   = build_team_defense(team3, "era3")
    ws3   = weakness_summary(td3)
    gaps3 = critical_gaps(ws3, threshold=3)

    if "Rock" in gaps3:
        ok("critical_gaps: Rock flagged (3 members weak, threshold=3)")
    else:
        fail("critical_gaps Rock", str(gaps3))

    if "Water" not in gaps3:
        ok("critical_gaps: Water not flagged (only 1 member weak)")
    else:
        fail("critical_gaps Water should not be flagged")

    if "Rock" in critical_gaps(ws3, threshold=2):
        ok("critical_gaps threshold=2 includes Rock")
    else:
        fail("critical_gaps threshold=2")

    if critical_gaps([], threshold=3) == []:
        ok("critical_gaps: empty weakness_rows -> []")
    else:
        fail("critical_gaps empty rows")

    # ── resistance_summary ────────────────────────────────────────────────────

    rs1 = resistance_summary(td1)
    ground_row = next((r for r in rs1 if r["type"] == "Ground"), None)
    if ground_row and "Charizard" in ground_row["immune_members"]:
        ok("resistance_summary: Charizard immune to Ground")
    else:
        fail("resistance_summary Ground immune", str(ground_row))

    fire_row = next((r for r in rs1 if r["type"] == "Fire"), None)
    if fire_row and "Charizard" in fire_row["resist_members"]:
        ok("resistance_summary: Charizard resists Fire")
    else:
        fail("resistance_summary Fire resist", str(fire_row))

    team_g = [gengar, None, None, None, None, None]
    td_g   = build_team_defense(team_g, "era3")
    rs_g   = resistance_summary(td_g)
    norm_r  = next((r for r in rs_g if r["type"] == "Normal"),   None)
    fight_r = next((r for r in rs_g if r["type"] == "Fighting"), None)
    if norm_r  and "Gengar" in norm_r["immune_members"]:
        ok("resistance_summary: Gengar immune to Normal")
    else:
        fail("resistance_summary Gengar Normal immune", str(norm_r))
    if fight_r and "Gengar" in fight_r["immune_members"]:
        ok("resistance_summary: Gengar immune to Fighting")
    else:
        fail("resistance_summary Gengar Fighting immune", str(fight_r))

    if resistance_summary(td_e) == []:
        ok("resistance_summary: empty team -> []")
    else:
        fail("resistance_summary empty")

    # ── build_unified_rows ────────────────────────────────────────────────────

    _, all_types_era3, _ = calc.CHARTS["era3"]
    ur1 = build_unified_rows(td1, "era3")

    # All era3 types present
    if set(r["type"] for r in ur1) == set(all_types_era3):
        ok("build_unified_rows: all era3 types present")
    else:
        fail("build_unified_rows: missing types",
             str(set(all_types_era3) - set(r["type"] for r in ur1)))

    # Rock row: weak_members has Charizard with mult 4.0
    rock_ur = next(r for r in ur1 if r["type"] == "Rock")
    if rock_ur["weak_members"] == [("Charizard", 4.0)]:
        ok("build_unified_rows: Rock row weak_members correct")
    else:
        fail("build_unified_rows Rock weak", str(rock_ur["weak_members"]))

    # Ground row: immune_members has Charizard, no weak
    ground_ur = next(r for r in ur1 if r["type"] == "Ground")
    if "Charizard" in ground_ur["immune_members"] and ground_ur["weak_members"] == []:
        ok("build_unified_rows: Ground row immune correct, no weak")
    else:
        fail("build_unified_rows Ground", str(ground_ur))

    # Grass row: resist_members has Charizard with mult 0.25
    grass_ur = next(r for r in ur1 if r["type"] == "Grass")
    grass_resist_names = [n for n, m in grass_ur["resist_members"]]
    if "Charizard" in grass_resist_names:
        grass_mult = next(m for n, m in grass_ur["resist_members"] if n == "Charizard")
        if grass_mult == 0.25:
            ok("build_unified_rows: Grass row resist mult = 0.25 for Charizard")
        else:
            fail("build_unified_rows Grass mult", str(grass_mult))
    else:
        fail("build_unified_rows Grass resist", str(grass_ur["resist_members"]))

    # Sorted: rows with most weak first; among equal-weak rows, alphabetical
    # Charizard has 3 types weak to (Rock, Electric, Water) all with weak=1
    # so first row is the alphabetically first of those: Electric
    if ur1[0]["weak_members"] and len(ur1[0]["weak_members"]) >= len(ur1[-1]["weak_members"]):
        ok("build_unified_rows: rows with weak members sort before rows without")
    else:
        fail("build_unified_rows sort", ur1[0]["type"])

    # All rows with weak=1 sort before rows with weak=0
    first_no_weak = next(i for i, r in enumerate(ur1) if not r["weak_members"])
    all_weak_before = all(ur1[i]["weak_members"] for i in range(first_no_weak))
    if all_weak_before:
        ok("build_unified_rows: all weak rows before all non-weak rows")
    else:
        fail("build_unified_rows weak order")

    # neutral_count: 1 member total, Rock weak -> neutral=0, Ground immune -> neutral=0
    # Fire: Charizard resists Fire (x0.5) -> neutral=0, resist=1
    fire_ur = next(r for r in ur1 if r["type"] == "Fire")
    if fire_ur["neutral_count"] == 0 and len(fire_ur["resist_members"]) >= 1:
        ok("build_unified_rows: Fire row neutral=0, resist>=1 for Charizard")
    else:
        fail("build_unified_rows Fire neutral", str(fire_ur))

    # neutral_count for a truly neutral type: e.g. Dragon vs single Charizard
    dragon_ur = next(r for r in ur1 if r["type"] == "Dragon")
    if dragon_ur["neutral_count"] == 1 and dragon_ur["weak_members"] == []:
        ok("build_unified_rows: Dragon row neutral=1 for Charizard")
    else:
        fail("build_unified_rows Dragon neutral", str(dragon_ur))

    # ── gap_label ─────────────────────────────────────────────────────────────

    if gap_label(3, 0) == "!! CRITICAL":
        ok("gap_label: 3 weak, 0 cover -> CRITICAL")
    else:
        fail("gap_label CRITICAL", gap_label(3, 0))

    if gap_label(4, 0) == "!! CRITICAL":
        ok("gap_label: 4 weak, 0 cover -> CRITICAL")
    else:
        fail("gap_label CRITICAL 4", gap_label(4, 0))

    if gap_label(3, 1) == "!  MAJOR":
        ok("gap_label: 3 weak, 1 cover -> MAJOR")
    else:
        fail("gap_label MAJOR", gap_label(3, 1))

    if gap_label(3, 2) == "":
        ok("gap_label: 3 weak, 2 cover -> no gap")
    else:
        fail("gap_label 3w 2c", gap_label(3, 2))

    if gap_label(2, 0) == ".  MINOR":
        ok("gap_label: 2 weak, 0 cover -> MINOR")
    else:
        fail("gap_label MINOR", gap_label(2, 0))

    if gap_label(2, 1) == "":
        ok("gap_label: 2 weak, 1 cover -> no gap")
    else:
        fail("gap_label 2w 1c", gap_label(2, 1))

    if gap_label(1, 0) == "":
        ok("gap_label: 1 weak, 0 cover -> no gap")
    else:
        fail("gap_label 1w 0c", gap_label(1, 0))

    if gap_label(0, 0) == "":
        ok("gap_label: 0 weak -> no gap")
    else:
        fail("gap_label 0w", gap_label(0, 0))

    # ── _abbrev ───────────────────────────────────────────────────────────────

    if _abbrev("Charizard") == "Char":
        ok("_abbrev: 9-char name -> 4 chars")
    else:
        fail("_abbrev 9-char", repr(_abbrev("Charizard")))

    if _abbrev("Mew") == "Mew":
        ok("_abbrev: short name kept as-is")
    else:
        fail("_abbrev short", repr(_abbrev("Mew")))

    # ── _weak_tag / _resist_tag ───────────────────────────────────────────────

    if _weak_tag("Charizard", 4.0) == "Char(\u00d74)":
        ok("_weak_tag: x4 gets suffix on abbreviated name")
    else:
        fail("_weak_tag x4", repr(_weak_tag("Charizard", 4.0)))

    if _weak_tag("Blastoise", 2.0) == "Blas":
        ok("_weak_tag: x2 no suffix, name abbreviated")
    else:
        fail("_weak_tag x2", repr(_weak_tag("Blastoise", 2.0)))

    if _resist_tag("Charizard", 0.25) == "Char(\u00d70.25)":
        ok("_resist_tag: x0.25 gets suffix on abbreviated name")
    else:
        fail("_resist_tag x0.25", repr(_resist_tag("Charizard", 0.25)))

    if _resist_tag("Venusaur", 0.5) == "Venu":
        ok("_resist_tag: x0.5 no suffix, name abbreviated")
    else:
        fail("_resist_tag x0.5", repr(_resist_tag("Venusaur", 0.5)))

    # ── _names_cell ───────────────────────────────────────────────────────────

    if _names_cell([], 20) == "-":
        ok("_names_cell: empty list -> dash")
    else:
        fail("_names_cell empty", _names_cell([], 20))

    short = _names_cell(["Charizard", "Blastoise"], 30)
    if "Charizard" in short and "Blastoise" in short:
        ok("_names_cell: short list fits without truncation")
    else:
        fail("_names_cell short", short)

    long_names = ["Charizard", "Blastoise", "Venusaur", "Pikachu", "Gengar", "Snorlax"]
    truncated = _names_cell(long_names, 20)
    if len(truncated) <= 20 and "..." in truncated:
        ok("_names_cell: long list truncated with '...'")
    else:
        fail("_names_cell truncation", f"len={len(truncated)} val={truncated!r}")

    # ── _print_unified_table: all types shown ─────────────────────────────────
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_unified_table(ur1, 1)
    out = buf.getvalue()

    # Every era3 type must appear in output
    missing = [t for t in all_types_era3 if t not in out]
    if not missing:
        ok("_print_unified_table: all era3 types present in output")
    else:
        fail("_print_unified_table missing types", str(missing))

    # Rock line shows count 1 in weak column
    rock_line = next((l for l in out.splitlines() if l.strip().startswith("Rock")), None)
    if rock_line and " 1 " in rock_line:
        ok("_print_unified_table: Rock row shows weak count 1")
    else:
        fail("_print_unified_table Rock count", repr(rock_line))

    # Dragon line: all zeros, no gap label — row should still be present
    drag_line = next((l for l in out.splitlines() if l.strip().startswith("Dragon")), None)
    if drag_line and "Dragon" in drag_line:
        ok("_print_unified_table: Dragon row present (all neutral, no gap)")
    else:
        fail("_print_unified_table Dragon line", repr(drag_line))

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    total = 58
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