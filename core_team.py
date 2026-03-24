#!/usr/bin/env python3
"""
core_team.py  Pure team‑related logic (no I/O, no display)

Contains functions for:
  - Defensive analysis (build_team_defense, build_unified_rows, gap_label, weakness pairs)
  - Offensive analysis (hitting_types, build_team_offense, build_offense_rows, coverage_gaps)
  - Moveset synergy (weakness_types, se_types, build_offensive_coverage, formatting helpers)
  - Team builder (offensive/defensive gaps, candidate scoring, ranking)
"""

import sys

try:
    import matchup_calculator as calc
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Constants for display (used in formatting functions) ──────────────────────
_NAME_ABBREV = 4          # characters to keep when abbreviating Pokémon names
_COL_TYPE = 10
_COL_CNT = 2
_COL_WNAMES = 30
_COL_RNAMES = 28
_COL_INAMES = 20
_GAP_WIDTH = 12

# Offensive table constants
_COL_HITTERS = 70
_MOVE_NAME_LEN = 12

# Moveset synergy constants
_COL_MOVE = 22
_BLOCK_SEP = 56

# Team builder scoring weights
_W_OFFENSIVE   = 10
_W_DEFENSIVE   = 8
_W_WEAK_PAIR   = 6
_W_ROLE        = 4
_LOOKAHEAD_END = 2


# ── Defensive analysis ────────────────────────────────────────────────────────

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

    for pkm in team_ctx:
        if pkm is None:
            continue
        matchups = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
        for atk_type in valid_types:
            m = matchups.get(atk_type, 1.0)
            result[atk_type].append({
                "form_name": pkm["form_name"],
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
        immune  = [m["form_name"] for m in members if m["multiplier"] == 0.0]
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


def gap_label(weak_count: int, cover_count: int) -> str:
    """
    Return a gap severity label, or empty string if no gap.

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


def build_weakness_pairs(team_ctx: list, era_key: str) -> list:
    """
    For each pair of filled team slots (i < j), find types where both members
    are weak (multiplier > 1.0). Return pairs with ≥ 2 shared weaknesses.

    Each result dict:
      {
        "name_a":       str,
        "name_b":       str,
        "shared_types": list[str],   # alphabetically sorted
        "shared_count": int,
      }

    Sorted descending by shared_count, then name_a ascending.
    """
    slots = [(i, pkm) for i, pkm in enumerate(team_ctx) if pkm is not None]
    pairs = []
    for ai, (_, pkm_a) in enumerate(slots):
        def_a = calc.compute_defense(era_key, pkm_a["type1"], pkm_a["type2"])
        weak_a = {t for t, m in def_a.items() if m > 1.0}
        for _, (_, pkm_b) in enumerate(slots[ai + 1:]):
            def_b = calc.compute_defense(era_key, pkm_b["type1"], pkm_b["type2"])
            weak_b = {t for t, m in def_b.items() if m > 1.0}
            shared = sorted(weak_a & weak_b)
            if len(shared) >= 2:
                pairs.append({
                    "name_a":       pkm_a["form_name"],
                    "name_b":       pkm_b["form_name"],
                    "shared_types": shared,
                    "shared_count": len(shared),
                })
    pairs.sort(key=lambda p: (-p["shared_count"], p["name_a"]))
    return pairs


def gap_pair_label(shared_count: int) -> str:
    """Return severity label for a weakness-sharing pair."""
    return "!! CRITICAL" if shared_count >= 3 else ""


# ── Offensive analysis ────────────────────────────────────────────────────────

def hitting_types(era_key: str, type1: str, type2: str, target: str) -> list:
    """
    Return list of first letters of the member's types that hit target SE (x2+).
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
          {
            "form_name":       str,
            "hitting_letters": [str, ...],
            "hitting_types":   [str, ...],
          },
          ...
        ]
      }
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    result = {t: [] for t in valid_types}

    for pkm in team_ctx:
        if pkm is None:
            continue
        t1, t2 = pkm["type1"], pkm["type2"]
        for target in valid_types:
            letters = hitting_types(era_key, t1, t2, target)
            if letters:
                full_types = [
                    t for t in [t1, t2]
                    if t != "None" and calc.get_multiplier(era_key, t, target) >= 2.0
                ]
                result[target].append({
                    "form_name":      pkm["form_name"],
                    "hitting_letters": letters,
                    "hitting_types":  full_types,
                })
    return result


def build_offense_rows(team_offense: dict, era_key: str) -> list:
    """
    Build one row per defending type, sorted: most covered first, gaps last.
    Rows with equal SE count are sorted alphabetically by type name.

    Each row:
      {
        "type":     str,
        "hitters":  [{"form_name": str, "hitting_letters": [...],
                      "hitting_types": [...], ...}, ...]
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


# ── Moveset synergy ───────────────────────────────────────────────────────────

def weakness_types(pkm_ctx: dict, era_key: str) -> list:
    """Return types that hit this Pokemon SE (multiplier > 1.0)."""
    defense = calc.compute_defense(era_key, pkm_ctx["type1"], pkm_ctx["type2"])
    return [t for t, m in defense.items() if m > 1.0]


def se_types(combo: list, era_key: str) -> list:
    """
    Return types hit SE (>= 2x) by at least one move in the combo,
    over all valid single-type defenders for the era.
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    move_types = [mv["type"] for mv in combo if mv.get("type")]
    if not move_types:
        return []
    se = []
    for def_type in valid_types:
        best = max(calc.get_multiplier(era_key, mt, def_type) for mt in move_types)
        if best >= 2.0:
            se.append(def_type)
    return se


def build_offensive_coverage(member_results: list, era_key: str) -> dict:
    """
    Aggregate SE coverage across all member results.

    Each member result is a dict with key "se_types" (list of type strings).
    Returns:
      {
        "counts":      {type: int},   — how many members cover each type SE
        "covered":     list[str],     — types covered by ≥1 member
        "gaps":        list[str],     — types covered by 0 members
        "overlap":     [(type, int)], — types covered by ≥3 members, desc count
        "total_types": int,           — total type count for the era
      }
    """
    _, valid_types, _ = calc.CHARTS[era_key]

    counts = {t: 0 for t in valid_types}
    for result in member_results:
        for t in result.get("se_types", []):
            if t in counts:
                counts[t] += 1

    covered = [t for t in valid_types if counts[t] >= 1]
    gaps    = [t for t in valid_types if counts[t] == 0]
    overlap = sorted(
        [(t, counts[t]) for t in valid_types if counts[t] >= 3],
        key=lambda x: (-x[1], x[0]),
    )

    return {
        "counts":      counts,
        "covered":     covered,
        "gaps":        gaps,
        "overlap":     overlap,
        "total_types": len(valid_types),
    }


def empty_member_result(form_name: str) -> dict:
    """Return a correctly-shaped empty member result dict."""
    return {
        "form_name":      form_name,
        "types":          [],
        "moves":          [],
        "weakness_types": [],
        "se_types":       [],
    }


def format_weak_line(weakness_types: list) -> str:
    """Format the weakness summary line for one member block."""
    if not weakness_types:
        return "Weak:  —"
    return "Weak:  " + "  ".join(weakness_types)


def format_move_pair(left: str | None, right: str | None) -> str:
    """
    Format two move names side by side.  None renders as "—".
    Left column is _COL_MOVE characters wide.
    """
    l = left  if left  is not None else "—"
    r = right if right is not None else "—"
    return f"{l:<{_COL_MOVE}}  {r}"


def format_se_line(se_types: list, era_key: str) -> str:
    """Format the SE coverage count line."""
    _, valid_types, _ = calc.CHARTS[era_key]
    return f"SE: {len(se_types)} / {len(valid_types)} types"


# ── Team builder ──────────────────────────────────────────────────────────────

def team_offensive_gaps(team_ctx: list, era_key: str) -> list:
    """
    Return era types that no filled team member can hit SE using their own types.

    Empty team → all era types are gaps.
    Returns sorted list.
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    slots = [(i, pkm) for i, pkm in enumerate(team_ctx) if pkm is not None]

    if not slots:
        return sorted(valid_types)

    covered = set()
    for _, pkm in slots:
        for atk_type in [pkm["type1"]] + (
                [pkm["type2"]] if pkm["type2"] != "None" else []):
            for def_type in valid_types:
                if calc.get_multiplier(era_key, atk_type, def_type) >= 2.0:
                    covered.add(def_type)

    return sorted(t for t in valid_types if t not in covered)


def team_defensive_gaps(team_ctx: list, era_key: str) -> list:
    """
    Return types that are CRITICAL defensive gaps for the team.

    A type is critical when:
      - ≥2 team members are weak to it (multiplier > 1.0), AND
      - 0 team members resist or are immune to it (multiplier < 1.0)

    Single-member teams can never have a critical gap (threshold is 2).
    Returns sorted list.
    """
    _, valid_types, _ = calc.CHARTS[era_key]
    slots = [(i, pkm) for i, pkm in enumerate(team_ctx) if pkm is not None]
    gaps = []

    for atk_type in valid_types:
        weak_count   = 0
        cover_count  = 0
        for _, pkm in slots:
            defense = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
            m = defense.get(atk_type, 1.0)
            if m > 1.0:
                weak_count  += 1
            elif m < 1.0:
                cover_count += 1
        if weak_count >= 2 and cover_count == 0:
            gaps.append(atk_type)

    return sorted(gaps)


def candidate_passes_filter(candidate_types: list, off_gaps: list,
                             def_gaps: list, era_key: str) -> bool:
    """
    Return True if the candidate is relevant to the team's gaps.

    Passes if at least one candidate type:
      - hits ≥1 offensive gap type SE (get_multiplier ≥ 2.0), OR
      - resists or is immune to ≥1 critical defensive gap (get_multiplier ≤ 0.5)
    """
    if not off_gaps and not def_gaps:
        return True

    for ctype in candidate_types:
        for gap in off_gaps:
            if calc.get_multiplier(era_key, ctype, gap) >= 2.0:
                return True
        for gap in def_gaps:
            # gap_type attacking candidate_type: ≤0.5 means candidate resists/immune
            if calc.get_multiplier(era_key, gap, ctype) <= 0.5:
                return True
    return False


def patchability_score(remaining_off_gaps: list, era_key: str) -> float:
    """
    Measure how easy the remaining offensive gaps are to fill.

    For each remaining gap type G: count era types T that hit G SE.
    Return the sum across all gaps. Higher = easier to patch.
    """
    if not remaining_off_gaps:
        return 0.0

    _, valid_types, _ = calc.CHARTS[era_key]
    total = 0.0
    for gap in remaining_off_gaps:
        count = sum(
            1 for t in valid_types
            if calc.get_multiplier(era_key, t, gap) >= 2.0
        )
        total += count
    return total


def shared_weakness_count(candidate_types: list, team_ctx: list,
                           era_key: str) -> int:
    """
    Count existing team members that would share ≥2 weakness types with
    the candidate if added.
    """
    ctype1 = candidate_types[0]
    ctype2 = candidate_types[1] if len(candidate_types) > 1 else "None"
    cand_defense = calc.compute_defense(era_key, ctype1, ctype2)
    cand_weak = {t for t, m in cand_defense.items() if m > 1.0}

    count = 0
    for pkm in team_ctx:
        if pkm is None:
            continue
        member_defense = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
        member_weak = {t for t, m in member_defense.items() if m > 1.0}
        if len(cand_weak & member_weak) >= 2:
            count += 1
    return count


def new_weak_pairs(candidate_types: list, team_ctx: list,
                    era_key: str) -> list:
    """
    Return human-readable strings describing new shared-weakness pairs.
    e.g. ["Charizard + Candidate share: Ice  Electric"]
    """
    ctype1 = candidate_types[0]
    ctype2 = candidate_types[1] if len(candidate_types) > 1 else "None"
    cand_defense = calc.compute_defense(era_key, ctype1, ctype2)
    cand_weak = {t for t, m in cand_defense.items() if m > 1.0}

    pairs = []
    for pkm in team_ctx:
        if pkm is None:
            continue
        member_defense = calc.compute_defense(era_key, pkm["type1"], pkm["type2"])
        member_weak = {t for t, m in member_defense.items() if m > 1.0}
        shared = sorted(cand_weak & member_weak)
        if len(shared) >= 2:
            pairs.append(f"{pkm['form_name']} shares: {'  '.join(shared)}")
    return pairs


def score_candidate(candidate_types: list, team_ctx: list, era_key: str,
                    off_gaps: list, def_gaps: list,
                    slots_remaining: int,
                    base_stats: dict = None) -> float:
    """
    Compute the composite score for a candidate Pokémon.

    candidate_types — list of 1–2 type strings
    team_ctx        — current team (used for shared-weakness + role checks)
    era_key         — "era1" | "era2" | "era3"
    off_gaps        — team's current offensive gap types
    def_gaps        — team's current critical defensive gap types
    slots_remaining — empty slots left after adding this candidate
    base_stats      — dict from pokemon cache, or None for type-only scoring

    Returns float. Higher is better.
    """
    # Offensive contribution
    off_covered = [
        g for g in off_gaps
        if any(calc.get_multiplier(era_key, ct, g) >= 2.0
               for ct in candidate_types)
    ]
    offensive_contribution = len(off_covered)

    # Defensive contribution
    def_covered = [
        g for g in def_gaps
        if any(calc.get_multiplier(era_key, g, ct) <= 0.5
               for ct in candidate_types)
    ]
    defensive_contribution = len(def_covered)

    # Shared weakness penalty
    shared_penalty = shared_weakness_count(candidate_types, team_ctx, era_key)

    # Role diversity bonus
    role_bonus = 0
    if base_stats and isinstance(base_stats, dict):
        try:
            from core_stat import infer_role
            candidate_role = infer_role(base_stats)
            team_roles = set()
            for pkm in team_ctx:
                if pkm is None:
                    continue
                bs = pkm.get("base_stats", {})
                if bs:
                    team_roles.add(infer_role(bs))
            if candidate_role not in team_roles:
                role_bonus = 1
        except (ImportError, Exception):
            pass

    # Intrinsic score
    intrinsic = (
        offensive_contribution  * _W_OFFENSIVE
        + defensive_contribution  * _W_DEFENSIVE
        - shared_penalty          * _W_WEAK_PAIR
        + role_bonus              * _W_ROLE
    )

    # Lookahead score
    remaining_off_gaps = [g for g in off_gaps if g not in off_covered]
    patch = patchability_score(remaining_off_gaps, era_key)

    weight = _LOOKAHEAD_END if slots_remaining <= 2 else 1
    lookahead = patch / max(slots_remaining, 1) * weight

    return intrinsic + lookahead


def rank_candidates(candidates: list, team_ctx: list, era_key: str,
                    off_gaps: list, def_gaps: list,
                    slots_remaining: int,
                    top_n: int = 6) -> list:
    """
    Score all candidates and return the top_n sorted by score descending.

    Each candidate dict in:
      { slug, form_name, types, base_stats (or None) }

    Each result dict out:
      {
        slug, form_name, types, score,
        off_covered, def_covered,
        new_weak_pairs,
        remaining_off_gaps,
        role, speed_tier
      }
    """
    if not candidates:
        return []

    scored = []
    for c in candidates:
        ctypes = c["types"]
        base_stats = c.get("base_stats")

        s = score_candidate(ctypes, team_ctx, era_key,
                            off_gaps, def_gaps,
                            slots_remaining, base_stats)

        off_covered = [
            g for g in off_gaps
            if any(calc.get_multiplier(era_key, ct, g) >= 2.0
                   for ct in ctypes)
        ]
        def_covered = [
            g for g in def_gaps
            if any(calc.get_multiplier(era_key, g, ct) <= 0.5
                   for ct in ctypes)
        ]
        remaining = [g for g in off_gaps if g not in off_covered]
        pairs = new_weak_pairs(ctypes, team_ctx, era_key)

        role = None
        speed_tier = None
        if base_stats and isinstance(base_stats, dict):
            try:
                from core_stat import infer_role, infer_speed_tier
                role = infer_role(base_stats)
                speed_tier = infer_speed_tier(base_stats)
            except (ImportError, Exception):
                pass

        scored.append({
            "slug":               c["slug"],
            "form_name":          c["form_name"],
            "types":              ctypes,
            "score":              s,
            "off_covered":        off_covered,
            "def_covered":        def_covered,
            "new_weak_pairs":     pairs,
            "remaining_off_gaps": remaining,
            "role":               role,
            "speed_tier":         speed_tier,
        })

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_n]


# ── Self‑tests ────────────────────────────────────────────────────────────────

def _run_tests():
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

    print("\n  core_team.py — self-test\n")

    # ── Fixtures ──────────────────────────────────────────────────────────────
    def _pkm(name, t1, t2="None"):
        return {"form_name": name, "type1": t1, "type2": t2}

    charizard = _pkm("Charizard", "Fire", "Flying")
    blastoise = _pkm("Blastoise", "Water")
    venusaur = _pkm("Venusaur", "Grass", "Poison")
    lapras = _pkm("Lapras", "Water", "Ice")
    snorlax = _pkm("Snorlax", "Normal")

    team1 = [charizard, None, None, None, None, None]
    team2 = [charizard, blastoise, None, None, None, None]
    team_cc = [charizard, charizard, None, None, None, None]   # two Charizard
    team3 = [charizard, blastoise, venusaur, None, None, None]

    ERA = "era3"

    # ── build_team_defense ───────────────────────────────────────────────────
    td = build_team_defense(team1, ERA)
    if td["Rock"][0]["multiplier"] == 4.0:
        ok("build_team_defense: Charizard Rock x4")
    else:
        fail("build_team_defense Rock", str(td["Rock"][0]["multiplier"]))

    # ── build_unified_rows ───────────────────────────────────────────────────
    rows = build_unified_rows(td, ERA)
    rock_row = next(r for r in rows if r["type"] == "Rock")
    if rock_row["weak_members"] == [("Charizard", 4.0)]:
        ok("build_unified_rows: Rock row correct")
    else:
        fail("build_unified_rows Rock", str(rock_row))

    # ── gap_label ────────────────────────────────────────────────────────────
    if gap_label(3, 0) == "!! CRITICAL":
        ok("gap_label: CRITICAL")
    else:
        fail("gap_label CRITICAL", gap_label(3, 0))
    if gap_label(3, 1) == "!  MAJOR":
        ok("gap_label: MAJOR")
    else:
        fail("gap_label MAJOR", gap_label(3, 1))
    if gap_label(2, 0) == ".  MINOR":
        ok("gap_label: MINOR")
    else:
        fail("gap_label MINOR", gap_label(2, 0))

    # ── build_weakness_pairs ─────────────────────────────────────────────────
    pairs = build_weakness_pairs(team_cc, ERA)
    if len(pairs) == 1 and pairs[0]["shared_count"] == 3:
        ok("build_weakness_pairs: two Charizard share 3 weaknesses")
    else:
        fail("build_weakness_pairs two Charizard", str(pairs))

    # ── hitting_types ────────────────────────────────────────────────────────
    if hitting_types(ERA, "Fire", "Flying", "Grass") == ["F", "F"]:
        ok("hitting_types: Charizard vs Grass -> [F,F]")
    else:
        fail("hitting_types Charizard/Grass", str(hitting_types(ERA, "Fire", "Flying", "Grass")))

    # ── build_team_offense ───────────────────────────────────────────────────
    to = build_team_offense(team1, ERA)
    grass_hitters = to["Grass"]
    if len(grass_hitters) == 1 and grass_hitters[0]["form_name"] == "Charizard":
        ok("build_team_offense: Charizard hits Grass SE")
    else:
        fail("build_team_offense Grass", str(grass_hitters))

    # ── build_offense_rows ───────────────────────────────────────────────────
    rows_off = build_offense_rows(to, ERA)
    if len(rows_off) == len(calc.TYPES_ERA3) and rows_off[0]["hitters"]:
        ok("build_offense_rows: correct length and sorted")
    else:
        fail("build_offense_rows", f"len={len(rows_off)} first hitters={rows_off[0]['hitters']}")

    # ── coverage_gaps ────────────────────────────────────────────────────────
    gaps = coverage_gaps(rows_off)
    if "Normal" in gaps:
        ok("coverage_gaps: Normal is a gap for Charizard")
    else:
        fail("coverage_gaps", str(gaps))

    # ── weakness_types ───────────────────────────────────────────────────────
    weak = weakness_types(charizard, ERA)
    if "Rock" in weak and "Water" in weak and "Electric" in weak:
        ok("weakness_types: Charizard weak to Rock, Water, Electric")
    else:
        fail("weakness_types", str(weak))

    # ── se_types ─────────────────────────────────────────────────────────────
    combo = [{"type": "Fire"}, {"type": "Water"}]
    se = se_types(combo, ERA)
    if "Grass" in se and "Fire" in se:
        ok("se_types: Fire+Water hits Grass and Fire SE")
    else:
        fail("se_types", str(se))

    # ── build_offensive_coverage ─────────────────────────────────────────────
    member_res = [{"se_types": ["Fire", "Water"]}, {"se_types": ["Grass"]}]
    cov = build_offensive_coverage(member_res, ERA)
    if "Fire" in cov["covered"] and "Grass" in cov["covered"] and "Electric" not in cov["covered"]:
        ok("build_offensive_coverage: correct coverage")
    else:
        fail("build_offensive_coverage", str(cov))

    # ── empty_member_result ─────────────────────────────────────────────────
    emp = empty_member_result("Test")
    if emp["form_name"] == "Test" and emp["moves"] == [] and emp["weakness_types"] == []:
        ok("empty_member_result: correct shape")
    else:
        fail("empty_member_result", str(emp))

    # ── format_weak_line ────────────────────────────────────────────────────
    if format_weak_line(["Rock", "Water"]) == "Weak:  Rock  Water":
        ok("format_weak_line: correct")
    else:
        fail("format_weak_line", format_weak_line(["Rock", "Water"]))

    # ── format_move_pair ────────────────────────────────────────────────────
    if "Flamethrower" in format_move_pair("Flamethrower", "Air Slash"):
        ok("format_move_pair: basic")
    else:
        fail("format_move_pair", format_move_pair("Flamethrower", "Air Slash"))

    # ── format_se_line ──────────────────────────────────────────────────────
    if format_se_line(["Fire", "Water"], ERA).startswith("SE: 2 / 18"):
        ok("format_se_line: correct format")
    else:
        fail("format_se_line", format_se_line(["Fire", "Water"], ERA))

    # ── team_offensive_gaps ─────────────────────────────────────────────────
    gaps_off = team_offensive_gaps(team1, ERA)
    if "Normal" in gaps_off:
        ok("team_offensive_gaps: Normal gap for Charizard")
    else:
        fail("team_offensive_gaps", str(gaps_off))

    # ── team_defensive_gaps ─────────────────────────────────────────────────
    # Two Charizard → Rock should be a gap
    gaps_def_cc = team_defensive_gaps(team_cc, ERA)
    if "Rock" in gaps_def_cc:
        ok("team_defensive_gaps: two Charizard -> Rock critical")
    else:
        fail("team_defensive_gaps two Charizard", str(gaps_def_cc))

    # Charizard + Blastoise → Rock not critical (only 1 weak)
    gaps_def_cb = team_defensive_gaps(team2, ERA)
    if "Rock" not in gaps_def_cb:
        ok("team_defensive_gaps: Charizard+Blastoise -> Rock not critical")
    else:
        fail("team_defensive_gaps Char+Blas", str(gaps_def_cb))

    # ── candidate_passes_filter ─────────────────────────────────────────────
    if candidate_passes_filter(["Ground"], ["Electric"], ["Electric"], ERA):
        ok("candidate_passes_filter: Ground passes")
    else:
        fail("candidate_passes_filter")

    # ── patchability_score ──────────────────────────────────────────────────
    if patchability_score(["Normal"], ERA) == 1.0:
        ok("patchability_score: Normal = 1")
    else:
        fail("patchability_score", str(patchability_score(["Normal"], ERA)))

    # ── shared_weakness_count ───────────────────────────────────────────────
    # Candidate not in team -> should be 0
    cnt = shared_weakness_count(["Water"], team1, ERA)
    if cnt == 0:
        ok("shared_weakness_count: candidate not in team -> 0")
    else:
        fail("shared_weakness_count", str(cnt))

    # ── new_weak_pairs ──────────────────────────────────────────────────────
    pairs_new = new_weak_pairs(["Water"], team1, ERA)
    if pairs_new == []:
        ok("new_weak_pairs: candidate not in team -> []")
    else:
        fail("new_weak_pairs", str(pairs_new))

    # ── score_candidate ─────────────────────────────────────────────────────
    score = score_candidate(["Ground"], team1, ERA, ["Electric"], ["Electric"], 5)
    if score > 0:
        ok("score_candidate: returns number")
    else:
        fail("score_candidate", str(score))

    # ── rank_candidates ─────────────────────────────────────────────────────
    candidates = [{"slug": "garchomp", "form_name": "Garchomp", "types": ["Dragon","Ground"], "base_stats": None}]
    ranked = rank_candidates(candidates, team1, ERA, ["Electric"], [], 5)
    if len(ranked) == 1 and ranked[0]["slug"] == "garchomp":
        ok("rank_candidates: basic")
    else:
        fail("rank_candidates", str(ranked))

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
        print("This module is a library; run with --autotest to test.")