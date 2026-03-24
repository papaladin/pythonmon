#!/usr/bin/env python3
"""
feat_nature_browser.py  Nature browser and recommender

Displays all 25 natures and their stat effects.
When a Pokémon is loaded, also shows the concrete stat-point impact of each
nature on that Pokémon's base stats, and gives a top-3 role-aware recommendation.

Natures were introduced in Gen 3. A warning is shown for Gen 1/2 games but the
feature is always accessible — the user may want to browse natures regardless.

Nature data is fetched from PokeAPI once and cached in cache/natures.json.
The data never changes between games.

Entry points:
  run(game_ctx=None, pkm_ctx=None)   called from pokemain
  main()                             standalone
"""

import sys

try:
    import pkm_cache as cache
    from core_stat import infer_role, infer_speed_tier
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Static data ───────────────────────────────────────────────────────────────

# Short display labels for stat names (PokeAPI slugs → abbreviations)
STAT_SHORT = {
    "attack":          "Atk",
    "defense":         "Def",
    "special-attack":  "SpA",
    "special-defense": "SpD",
    "speed":           "Spe",
}

# Canonical display order for the nature table (grouped by boosted stat)
_NATURE_ORDER = [
    # Atk boosters
    "Lonely", "Brave", "Adamant", "Naughty",
    # Def boosters
    "Bold", "Relaxed", "Impish", "Lax",
    # SpA boosters
    "Modest", "Mild", "Quiet", "Rash",
    # SpD boosters
    "Calm", "Gentle", "Sassy", "Careful",
    # Spe boosters
    "Timid", "Hasty", "Jolly", "Naive",
    # Neutral (no effect)
    "Hardy", "Docile", "Serious", "Bashful", "Quirky",
]

# Generation in which natures were introduced
_NATURE_MIN_GEN = 3


# ── Role-aware scorer ─────────────────────────────────────────────────────────

def _role_score(inc: str | None, dec: str | None, stats: dict) -> float:
    """
    Compute a role-aware desirability score for a nature on a given Pokémon.

    Returns 0.0 for neutral natures (inc/dec both None).

    Scoring model:
      role_score = boost_value - cut_value
        boost_value = base_stat[inc] × 0.1 × weight(inc)
        cut_value   = base_stat[dec] × 0.1 × weight(dec)

    weight(stat) depends on three factors:
      1. Attacking role  (Atk vs SpA, threshold 1.2×)
           key attacking stat   → 1.5  (directly powers damage)
           dump attacking stat  → 0.3  (cutting it is nearly free)
      2. Speed tier  (Spe ≥ 90 = fast, 70–89 = mid, < 70 = slow)
           fast → 1.0, mid → 0.6, slow → 0.2
      3. Bulk relevance  (Def / SpD)
           weight = min(stat / 80, 1.0)  so low bulk hurts less to cut
    """
    if inc is None:
        return 0.0

    atk = stats.get("attack", 1) or 1
    spa = stats.get("special-attack", 1) or 1
    spe = stats.get("speed", 1) or 1
    df  = stats.get("defense", 1) or 1
    spd = stats.get("special-defense", 1) or 1

    # Attacking role
    if atk >= spa * 1.2:
        key_atk, dump_atk = "attack", "special-attack"
    elif spa >= atk * 1.2:
        key_atk, dump_atk = "special-attack", "attack"
    else:
        key_atk, dump_atk = None, None     # mixed: neither is clearly the dump

    # Speed tier weight
    if spe >= 90:   spe_w = 1.0
    elif spe >= 70: spe_w = 0.6
    else:           spe_w = 0.2

    def _weight(stat: str) -> float:
        if stat == key_atk:   return 1.5
        if stat == dump_atk:  return 0.3
        if stat == "speed":   return spe_w
        if stat == "defense": return min(df / 80.0, 1.0)
        if stat == "special-defense": return min(spd / 80.0, 1.0)
        return 0.8     # mixed attacker: treat both attack stats as moderately important

    boost_val = stats[inc] * 0.1 * _weight(inc)
    cut_val   = stats[dec] * 0.1 * _weight(dec)
    return boost_val - cut_val


def _net_pts(inc: str | None, dec: str | None, stats: dict) -> tuple[int, int]:
    """
    Return (gain_pts, loss_pts) for a nature on a given Pokémon.
    Uses floor(base_stat × 0.1) as an approximation of the ±10% effect.
    Both values are non-negative; caller formats them with +/- signs.
    Returns (0, 0) for neutral natures.
    """
    if inc is None:
        return 0, 0
    return int(stats[inc] * 0.1), int(stats[dec] * 0.1)


# ── Display ───────────────────────────────────────────────────────────────────

# Column widths (content only; GAP added uniformly between columns)
_C_NAME =  12   # nature name
_C_STAT =   5   # stat abbreviation
_C_PTS  =   6   # +pts / -pts values
_C_NET  =   5   # net value
_GAP    = "  "  # 2-space separator between every column
_MINUS  = "\u2212"  # Unicode minus sign (−), defined outside f-strings
                    # for Python < 3.12 compatibility


def _table_header(with_pts: bool) -> str:
    """Build the header row for the nature table."""
    _ms = _MINUS + "Stat"
    r = f"  {'Nature':<{_C_NAME}}{_GAP}{'+Stat':<{_C_STAT}}{_GAP}{_ms:<{_C_STAT}}"
    if with_pts:
        _mp = _MINUS + "pts"
        r += f"{_GAP}{'+pts':>{_C_PTS}}{_GAP}{_mp:>{_C_PTS}}{_GAP}{'net':>{_C_NET}}"
    return r


def _table_row(name: str, inc_s: str, dec_s: str,
               gain: int | None = None, loss: int | None = None,
               net: int | None = None) -> str:
    """Build one data row for the nature table."""
    r = f"  {name:<{_C_NAME}}{_GAP}{inc_s:<{_C_STAT}}{_GAP}{dec_s:<{_C_STAT}}"
    if gain is not None:
        r += (f"{_GAP}{'+'+str(gain):>{_C_PTS}}"
              f"{_GAP}{'-'+str(loss):>{_C_PTS}}"
              f"{_GAP}{net:>+{_C_NET}d}")
    return r


def _group_label(boosted: str | None) -> str:
    if boosted is None:
        return "Neutral (no stat change)"
    return f"{STAT_SHORT[boosted]} boosters"


def _print_nature_table(natures: dict, stats: dict | None) -> None:
    """
    Print the full 25-nature table.
    If stats is provided, add +pts / -pts / net columns.
    """
    with_pts = stats is not None
    header   = _table_header(with_pts)
    sep      = "  " + "─" * (len(header) - 2)

    # Group natures by boosted stat for display
    groups = {}   # boosted_stat_or_None → [nature_name, ...]
    for name in _NATURE_ORDER:
        entry = natures.get(name)
        if entry is None:
            continue
        key = entry["increased"]   # None for neutral
        groups.setdefault(key, []).append(name)

    group_order = ["attack", "defense", "special-attack",
                   "special-defense", "speed", None]

    first_group = True
    for gkey in group_order:
        names_in_group = groups.get(gkey, [])
        if not names_in_group:
            continue
        if not first_group:
            print()
        first_group = False
        print(f"\n  {_group_label(gkey)}")
        print(header)
        print(sep)
        for name in names_in_group:
            entry = natures[name]
            inc   = entry["increased"]
            dec   = entry["decreased"]
            inc_s = STAT_SHORT.get(inc, "—") if inc else "—"
            dec_s = STAT_SHORT.get(dec, "—") if dec else "—"

            if with_pts:
                if inc:
                    gain, loss = _net_pts(inc, dec, stats)
                    print(_table_row(name, inc_s, dec_s, gain, loss, gain - loss))
                else:
                    # Neutral nature: show dashes in pts/net columns
                    row = (f"  {name:<{_C_NAME}}{_GAP}{'—':<{_C_STAT}}{_GAP}{'—':<{_C_STAT}}"
                           f"{_GAP}{'—':>{_C_PTS}}{_GAP}{'—':>{_C_PTS}}{_GAP}{'—':>{_C_NET}}")
                    print(row)
            else:
                print(_table_row(name, inc_s, dec_s))


_C_RANK = 14    # "1. Modest     " — rank + nature name column

def _print_top5(natures: dict, stats: dict, form_name: str) -> None:
    """
    Print the top-5 role-aware nature recommendations for a Pokémon.
    Effect column shows base stats + delta for full context,
    e.g.  109+10 SpA,  84−8 Atk
    """
    role = infer_role(stats)
    tier = infer_speed_tier(stats)

    scored = []
    for name, entry in natures.items():
        inc = entry["increased"]
        dec = entry["decreased"]
        if inc is None:
            continue    # neutral natures never recommended
        rs         = _role_score(inc, dec, stats)
        gain, loss = _net_pts(inc, dec, stats)
        scored.append((rs, name, inc, dec, gain, loss))

    scored.sort(key=lambda r: r[0], reverse=True)
    top5 = scored[:5]

    print(f"\n  Top-5 recommended natures for {form_name}  [{role}, {tier} speed]")
    hdr = (f"  {'':<{_C_RANK}}{_GAP}{'Boost':<{_C_STAT}}"
           f"{_GAP}{'Cut':<{_C_STAT}}{_GAP}Effect")
    print(hdr)
    print("  " + "─" * (len(hdr) + 12))
    for rank, (rs, name, inc, dec, gain, loss) in enumerate(top5, 1):
        inc_s  = STAT_SHORT[inc]
        dec_s  = STAT_SHORT[dec]
        effect = f"{stats[inc]}+{gain} {inc_s},  {stats[dec]}{_MINUS}{loss} {dec_s}"
        label  = f"{rank}. {name}"
        print(f"  {label:<{_C_RANK}}{_GAP}{inc_s:<{_C_STAT}}{_GAP}{dec_s:<{_C_STAT}}{_GAP}{effect}")
    print()


# ── Main feature entry point ──────────────────────────────────────────────────

# ── Stat calculator (Lv 100, 31 IVs assumed) ─────────────────────────────────
#
# ASSUMPTION: All calculations assume Level 100, 31 IVs in every stat.
# This is the standard competitive baseline. Actual in-game stats will differ
# for Pokemon at lower levels or with non-31 IVs.
#
# Formulae (Generation 3+):
#   HP    = (2*B + IV + floor(EV/4)) * Lv/100 + Lv + 10
#   Other = floor(((2*B + IV + floor(EV/4)) * Lv/100 + 5) * nature_mod)
#
# At Lv 100, IV=31:
#   HP    = 2*B + 31 + floor(EV/4) + 110
#   Other = floor((2*B + 31 + floor(EV/4) + 5) * nature_mod)

_LV    = 100
_IV    = 31
_STATS = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]
_STAT_LABELS = {
    "hp"            : "HP",
    "attack"        : "Attack",
    "defense"       : "Defense",
    "special-attack": "Sp. Attack",
    "special-defense": "Sp. Defense",
    "speed"         : "Speed",
}


def _calc_stat(key: str, base: int, ev: int, nature_name: str,
               natures: dict) -> int:
    """
    Compute a single stat value at Lv 100 with 31 IVs.

    key         — PokeAPI stat slug  e.g. "attack", "hp"
    base        — base stat value
    ev          — EV allocation for this stat (0–252, multiple of 4 assumed)
    nature_name — nature display name e.g. "Modest"; used to look up +/− modifier
    natures     — loaded natures dict from cache

    Returns the final integer stat value.
    Assumption: Level 100, 31 IVs. See module comment above.
    """
    ev_contrib = ev // 4
    inner      = 2 * base + _IV + ev_contrib
    if key == "hp":
        return inner + _LV + 10

    # Nature modifier: +10% if this stat is increased, -10% if decreased
    entry = natures.get(nature_name, {})
    if entry.get("increased") == key:
        mod = 1.1
    elif entry.get("decreased") == key:
        mod = 0.9
    else:
        mod = 1.0
    return int((inner + 5) * mod)


# ── Build profile tables ──────────────────────────────────────────────────────
#
# Each profile is a (label, nature_name, ev_spread) triple.
# Two profiles are always generated — one prioritising speed safety, one
# prioritising raw attacking power.
#
# EV spreads are role-based:
#   Physical sweeper (fast/mid) : 252 Atk / 252 Spe / 4 HP
#   Physical tank   (slow)      : 252 HP  / 252 Def / 4 Atk
#   Special sweeper (fast/mid)  : 252 SpA / 252 Spe / 4 HP
#   Special tank    (slow)      : 252 HP  / 252 SpD / 4 SpA
#   Mixed           (fast/mid)  : 128 Atk / 128 SpA / 252 Spe
#   Mixed           (slow)      : 252 HP  / 128 Atk / 128 SpA

def _ev_spread(role: str, speed_tier: str) -> dict:
    """Return an EV spread dict keyed by PokeAPI stat slugs."""
    base = {k: 0 for k in _STATS}
    if role == "physical":
        if speed_tier == "slow":
            base.update({"hp": 252, "defense": 252, "attack": 4})
        else:
            base.update({"attack": 252, "speed": 252, "hp": 4})
    elif role == "special":
        if speed_tier == "slow":
            base.update({"hp": 252, "special-defense": 252, "special-attack": 4})
        else:
            base.update({"special-attack": 252, "speed": 252, "hp": 4})
    else:  # mixed
        if speed_tier == "slow":
            base.update({"hp": 252, "attack": 128, "special-attack": 128})
        else:
            base.update({"speed": 252, "attack": 128, "special-attack": 128})
    return base


_PROFILE_NATURES = {
    # (role, speed_tier): [(label, nature_name), (label, nature_name)]
    ("physical", "fast") : [("Sweeper — speed-safe", "Jolly"),
                             ("Sweeper — power-max",  "Adamant")],
    ("physical", "mid")  : [("Sweeper — speed-safe", "Jolly"),
                             ("Sweeper — power-max",  "Adamant")],
    ("physical", "slow") : [("Tank — no speed loss", "Brave"),
                             ("Tank — atk boost",     "Adamant")],
    ("special",  "fast") : [("Sweeper — speed-safe", "Timid"),
                             ("Sweeper — power-max",  "Modest")],
    ("special",  "mid")  : [("Sweeper — speed-safe", "Timid"),
                             ("Sweeper — power-max",  "Modest")],
    ("special",  "slow") : [("Tank — no speed loss", "Quiet"),
                             ("Tank — SpA boost",     "Modest")],
    ("mixed",    "fast") : [("Mixed — speed-safe",   "Hasty"),
                             ("Mixed — sp. power",    "Naive")],
    ("mixed",    "mid")  : [("Mixed — speed-safe",   "Hasty"),
                             ("Mixed — sp. power",    "Naive")],
    ("mixed",    "slow") : [("Mixed — atk/SpA",      "Rash"),
                             ("Mixed — atk/SpA",      "Mild")],
}


def build_profiles(base_stats: dict, natures: dict) -> list:
    """
    Build two recommended build profiles for a Pokémon.

    Each profile dict:
      {
        "label"      : str,          # e.g. "Sweeper — speed-safe"
        "nature"     : str,          # e.g. "Timid"
        "nature_inc" : str | None,   # increased stat slug
        "nature_dec" : str | None,   # decreased stat slug
        "ev_spread"  : dict,         # {stat_slug: ev_amount}
        "stats"      : [             # one entry per stat in _STATS order
          {"key": str, "label": str,
           "base": int, "final": int, "change": int,
           "ev": int, "nature_effect": str}  # "+", "-", ""
        ]
      }

    Assumption: Level 100, 31 IVs in all stats.
    """
    role  = infer_role(base_stats)
    tier  = infer_speed_tier(base_stats)
    pairs = _PROFILE_NATURES.get((role, tier), _PROFILE_NATURES[("special", "fast")])
    evs   = _ev_spread(role, tier)

    profiles = []
    for label, nature_name in pairs:
        entry  = natures.get(nature_name, {})
        n_inc  = entry.get("increased")
        n_dec  = entry.get("decreased")
        stats_rows = []
        for key in _STATS:
            base  = base_stats.get(key, 0)
            ev    = evs[key]
            final = _calc_stat(key, base, ev, nature_name, natures)
            # Nature effect indicator
            if n_inc == key:   nat_eff = "+"
            elif n_dec == key: nat_eff = "-"
            else:               nat_eff = ""
            stats_rows.append({
                "key"           : key,
                "label"         : _STAT_LABELS[key],
                "base"          : base,
                "final"         : final,
                "change"        : final - (2 * base + _IV + 110 if key == "hp"
                                          else int((2 * base + _IV + 5))),
                "ev"            : ev,
                "nature_effect" : nat_eff,
            })
        profiles.append({
            "label"     : label,
            "nature"    : nature_name,
            "nature_inc": n_inc,
            "nature_dec": n_dec,
            "ev_spread" : evs,
            "stats"     : stats_rows,
        })
    return profiles


def _ev_label(ev: int) -> str:
    """Short EV annotation for the change column."""
    if ev == 252: return "max EVs"
    if ev > 0:    return f"{ev} EVs"
    return ""


def _print_build_profiles(profiles: list, form_name: str) -> None:
    """Print the two build profiles for a Pokémon."""
    _SEP = "═" * 62
    _DIV = "─" * 62

    role_line = f"{profiles[0]['label'].split(' — ')[0]}"  # e.g. "Sweeper"

    print(f"\n  Build advisor  |  {form_name}")
    print(f"  ⚠  Assumes Lv 100, 31 IVs all stats")
    print("  " + _SEP)

    for i, p in enumerate(profiles):
        nature_entry = p["nature"]
        inc_s = STAT_SHORT.get(p["nature_inc"], "—") if p["nature_inc"] else "—"
        dec_s = STAT_SHORT.get(p["nature_dec"], "—") if p["nature_dec"] else "—"
        ev_parts = []
        for key in _STATS:
            ev = p["ev_spread"][key]
            if ev > 0:
                ev_parts.append(f"{ev} {STAT_SHORT.get(key, key)}")
        ev_str = " / ".join(ev_parts)

        print(f"  ── Profile {i+1}: {p['label']}")
        print(f"  Nature  {nature_entry:<10}  (+{inc_s} / −{dec_s})"
              f"      EVs  {ev_str}")
        print()
        print(f"  {'Stat':<14}{'Base':>5}{'Final':>7}{'Change':>8}  Notes")
        print("  " + _DIV)

        for r in p["stats"]:
            notes = []
            if r["ev"]:          notes.append(_ev_label(r["ev"]))
            if r["nature_effect"] == "+": notes.append(f"+{inc_s}")
            if r["nature_effect"] == "-": notes.append(f"−{dec_s}")
            change_str = f"+{r['change']}" if r["change"] >= 0 else str(r["change"])
            print(f"  {r['label']:<14}{r['base']:>5}{r['final']:>7}"
                  f"{change_str:>8}  {'  '.join(notes)}")

        if i == 0 and len(profiles) > 1:
            print()

    print("  " + _SEP)



def run(game_ctx=None, pkm_ctx=None) -> None:
    """
    Nature & EV build advisor entry point. Always accessible; warns for Gen 1/2 games.
    When a Pokémon is loaded: (1) full nature table with stat impact,
    (2) top-5 role-aware nature ranking, (3) two EV build profiles.
    """
    # Gen 1/2 warning
    if game_ctx is not None:
        game_gen = game_ctx.get("game_gen", 1)
        if game_gen < _NATURE_MIN_GEN:
            game_name = game_ctx.get("game", f"Gen {game_gen}")
            print(f"\n  ⚠  Natures did not exist in {game_name}.")
            print(    "     They were introduced in Generation 3 (Ruby / Sapphire).")
            print(    "     The table below is shown for reference only.\n")

    # Fetch natures from cache / PokeAPI
    natures = cache.get_natures_or_fetch()
    if natures is None:
        print("\n  Could not load nature data (network unavailable and no cache).")
        return

    # Reorder to canonical display order (fill in any that are in cache but not
    # in our static order list — unlikely but safe)
    ordered = {k: natures[k] for k in _NATURE_ORDER if k in natures}
    for k in natures:
        if k not in ordered:
            ordered[k] = natures[k]

    stats = None
    form_name = None
    if pkm_ctx is not None:
        stats = pkm_ctx.get("base_stats")
        if not isinstance(stats, dict) or not stats:
            stats = None
        form_name = pkm_ctx.get("form_name", pkm_ctx.get("pokemon", "?"))

    if stats:
        print(f"\n  Nature impact for {form_name}")
        print( "  (\u00b1pts = approximate stat change at base stat level; "
               "actual values depend on level, EVs, IVs)")
    else:
        print("\n  All natures  (load a Pokémon to see stat impact)")

    # 1) Full 25-nature table
    _print_nature_table(ordered, stats)

    # 2) Top-5 role-aware ranking
    if stats:
        _print_top5(ordered, stats, form_name)

    # 3) EV build profiles — shown last, after all nature reference material
    if stats:
        profiles = build_profiles(stats, ordered)
        _print_build_profiles(profiles, form_name)

    input("\n  Press Enter to continue...")


# ── Standalone entry point ────────────────────────────────────────────────────

def main() -> None:
    run()


# ── Unit tests ────────────────────────────────────────────────────────────────

def _run_tests(with_cache: bool = False) -> None:
    passed = 0
    failed = 0

    def check(label, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")

    # ── infer_role (from feat_stat_compare) ───────────────────────────────────────────────────────────
    check("role: Machamp physical (Atk 130, SpA 65)",
          infer_role({"attack": 130, "special-attack": 65}) == "physical")
    check("role: Alakazam special (Atk 45, SpA 135)",
          infer_role({"attack": 45, "special-attack": 135}) == "special")
    check("role: mixed when ratio < 1.2× (Atk 85, SpA 90 → 1.06×)",
          infer_role({"attack": 85, "special-attack": 90}) == "mixed")
    check("role: exactly 1.2× threshold is physical",
          infer_role({"attack": 120, "special-attack": 100}) == "physical")
    check("role: just below 1.2× threshold is mixed",
          infer_role({"attack": 119, "special-attack": 100}) == "mixed")

    # ── infer_speed_tier (from feat_stat_compare) ─────────────────────────────────────────────────────
    check("speed tier: 90 → fast",  infer_speed_tier({"speed": 90})  == "fast")
    check("speed tier: 89 → mid",   infer_speed_tier({"speed": 89})  == "mid")
    check("speed tier: 70 → mid",   infer_speed_tier({"speed": 70})  == "mid")
    check("speed tier: 69 → slow",  infer_speed_tier({"speed": 69})  == "slow")
    check("speed tier: 30 → slow",  infer_speed_tier({"speed": 30})  == "slow")

    # ── _net_pts ──────────────────────────────────────────────────────────────
    # Modest (+SpA/-Atk) on Charizard (SpA 109, Atk 84)
    gain, loss = _net_pts("special-attack", "attack",
                          {"attack": 84, "special-attack": 109})
    check("net_pts: Modest Charizard gain=10 (floor(109*0.1))", gain == 10)
    check("net_pts: Modest Charizard loss=8  (floor(84*0.1))",  loss == 8)

    # Neutral nature
    gain0, loss0 = _net_pts(None, None, {"attack": 100, "special-attack": 100})
    check("net_pts: neutral → (0, 0)", gain0 == 0 and loss0 == 0)

    # ── _role_score ───────────────────────────────────────────────────────────
    # Charizard (special, fast): Modest > Timid > Adamant
    charizard = {"attack": 84, "defense": 78, "special-attack": 109,
                 "special-defense": 85, "speed": 100}
    modest_s  = _role_score("special-attack", "attack",    charizard)
    timid_s   = _role_score("speed",          "attack",    charizard)
    adamant_s = _role_score("attack",         "special-attack", charizard)
    check("role_score Charizard: Modest > Timid",   modest_s  > timid_s)
    check("role_score Charizard: Modest > Adamant", modest_s  > adamant_s)
    check("role_score Charizard: Adamant negative", adamant_s < 0)

    # Machamp (physical, slow): Adamant > Modest
    machamp = {"attack": 130, "defense": 80, "special-attack": 65,
               "special-defense": 85, "speed": 55}
    adamant_m = _role_score("attack",         "special-attack", machamp)
    modest_m  = _role_score("special-attack", "attack",         machamp)
    check("role_score Machamp: Adamant > Modest", adamant_m > modest_m)
    check("role_score Machamp: Adamant positive", adamant_m > 0)

    # Snorlax (physical, slow): Brave (+Atk/-Spe) better than Lonely (+Atk/-Def)
    # because cutting useless speed (weight 0.2) hurts much less than cutting Def
    snorlax = {"attack": 110, "defense": 65, "special-attack": 65,
               "special-defense": 110, "speed": 30}
    brave_s  = _role_score("attack", "speed",   snorlax)
    lonely_s = _role_score("attack", "defense", snorlax)
    check("role_score Snorlax: Brave > Lonely (cutting Spe is nearly free)", brave_s > lonely_s)

    # Neutral nature always scores 0.0
    check("role_score neutral → 0.0",
          _role_score(None, None, charizard) == 0.0)

    # ── _NATURE_ORDER completeness ────────────────────────────────────────────
    check("_NATURE_ORDER has exactly 25 entries", len(_NATURE_ORDER) == 25)
    check("_NATURE_ORDER has no duplicates",      len(set(_NATURE_ORDER)) == 25)

    # ── STAT_SHORT coverage ───────────────────────────────────────────────────
    for stat in ("attack", "defense", "special-attack", "special-defense", "speed"):
        check(f"STAT_SHORT has '{stat}'", stat in STAT_SHORT)

    # ── withcache tests ───────────────────────────────────────────────────────
    if with_cache:
        natures = cache.get_natures_or_fetch()
        check("withcache: natures dict is non-empty",
              isinstance(natures, dict) and len(natures) > 0)
        check("withcache: exactly 25 natures",
              len(natures) == 25)

        # Spot-check a few known natures
        check('withcache: Adamant present',   "Adamant" in natures)
        check('withcache: Modest present',    "Modest"  in natures)
        check('withcache: Hardy present',     "Hardy"   in natures)

        adamant = natures.get("Adamant", {})
        check('withcache: Adamant increases attack',
              adamant.get("increased") == "attack")
        check('withcache: Adamant decreases special-attack',
              adamant.get("decreased") == "special-attack")

        modest = natures.get("Modest", {})
        check('withcache: Modest increases special-attack',
              modest.get("increased") == "special-attack")
        check('withcache: Modest decreases attack',
              modest.get("decreased") == "attack")

        hardy = natures.get("Hardy", {})
        check('withcache: Hardy is neutral (increased=None)',
              hardy.get("increased") is None)
        check('withcache: Hardy is neutral (decreased=None)',
              hardy.get("decreased") is None)

        # All 25 entries must have name / increased / decreased keys
        all_valid = all(
            "name" in v and "increased" in v and "decreased" in v
            for v in natures.values()
        )
        check("withcache: all entries have required keys", all_valid)

        # Neutral count must be exactly 5
        neutral_count = sum(1 for v in natures.values() if v["increased"] is None)
        check("withcache: exactly 5 neutral natures", neutral_count == 5)

    # ── _calc_stat ────────────────────────────────────────────────────────────

    # Fake minimal natures dict for stat tests
    _natures_test = {
        "Modest": {"increased": "special-attack", "decreased": "attack"},
        "Timid" : {"increased": "speed",           "decreased": "attack"},
        "Hardy" : {"increased": None,              "decreased": None},
    }

    # HP formula: 2*78 + 31 + 63 + 110 = 360 (Charizard HP, 252 EVs)
    hp_val = _calc_stat("hp", 78, 252, "Hardy", _natures_test)
    check("_calc_stat: HP 252 EVs = 2*78+31+63+110=360", hp_val == 360)

    # HP no EVs: 2*78 + 31 + 0 + 110 = 297
    hp0 = _calc_stat("hp", 78, 0, "Hardy", _natures_test)
    check("_calc_stat: HP 0 EVs = 297", hp0 == 297)

    # Other stat neutral: 2*109 + 31 + 63 + 5 = 317 (Charizard SpA, 252 EVs, Hardy)
    spa_neutral = _calc_stat("special-attack", 109, 252, "Hardy", _natures_test)
    check("_calc_stat: SpA neutral 252 EVs = 317", spa_neutral == 317)

    # Other stat +10% (Modest SpA): floor(317 * 1.1) = floor(348.7) = 348
    spa_modest = _calc_stat("special-attack", 109, 252, "Modest", _natures_test)
    check("_calc_stat: SpA +Modest 252 EVs = 348", spa_modest == 348)

    # Other stat -10% (Timid Atk on base 84, 0 EVs): floor((2*84+31+5) * 0.9) = floor(204*0.9) = floor(183.6) = 183
    atk_timid = _calc_stat("attack", 84, 0, "Timid", _natures_test)
    check("_calc_stat: Atk -Timid 0 EVs = 183", atk_timid == 183)

    # Speed +10% (Timid, 252 EVs, base 100): floor((2*100+31+63+5)*1.1) = floor(299*1.1) = floor(328.9) = 328
    spe_timid = _calc_stat("speed", 100, 252, "Timid", _natures_test)
    check("_calc_stat: Spe +Timid 252 EVs = 328", spe_timid == 328)

    # ── build_profiles ────────────────────────────────────────────────────────

    # Need a fuller natures dict — build minimal one covering all profile natures
    _all_natures = {
        "Jolly"  : {"increased": "speed",            "decreased": "special-attack"},
        "Adamant": {"increased": "attack",            "decreased": "special-attack"},
        "Brave"  : {"increased": "attack",            "decreased": "speed"},
        "Timid"  : {"increased": "speed",             "decreased": "attack"},
        "Modest" : {"increased": "special-attack",    "decreased": "attack"},
        "Quiet"  : {"increased": "special-attack",    "decreased": "speed"},
        "Hasty"  : {"increased": "speed",             "decreased": "defense"},
        "Naive"  : {"increased": "speed",             "decreased": "special-defense"},
        "Rash"   : {"increased": "special-attack",    "decreased": "special-defense"},
        "Mild"   : {"increased": "special-attack",    "decreased": "defense"},
        "Hardy"  : {"increased": None,                "decreased": None},
    }

    # Special fast Pokémon (Charizard: SpA 109 > Atk 84, Speed 100 ≥ 90)
    _char_stats = {"hp": 78, "attack": 84, "defense": 78,
                   "special-attack": 109, "special-defense": 85, "speed": 100}
    profiles = build_profiles(_char_stats, _all_natures)

    check("build_profiles: always returns exactly 2 profiles", len(profiles) == 2)

    required_keys = {"label", "nature", "nature_inc", "nature_dec", "ev_spread", "stats"}
    check("build_profiles: each profile has required keys",
          all(required_keys <= set(p.keys()) for p in profiles))

    check("build_profiles: each profile has 6 stat rows",
          all(len(p["stats"]) == 6 for p in profiles))

    # Special fast → Timid profile 1, Modest profile 2
    check("build_profiles: special+fast profile 1 → Timid",
          profiles[0]["nature"] == "Timid")
    check("build_profiles: special+fast profile 2 → Modest",
          profiles[1]["nature"] == "Modest")

    # Physical fast Pokémon (Garchomp: Atk 130 > SpA 80, Speed 102 ≥ 90)
    _garc_stats = {"hp": 108, "attack": 130, "defense": 95,
                   "special-attack": 80, "special-defense": 85, "speed": 102}
    profiles_g = build_profiles(_garc_stats, _all_natures)
    check("build_profiles: physical+fast profile 1 → Jolly",
          profiles_g[0]["nature"] == "Jolly")
    check("build_profiles: physical+fast profile 2 → Adamant",
          profiles_g[1]["nature"] == "Adamant")

    # EV total per profile = 508 (252+252+4)
    check("build_profiles: EV total = 508 per profile",
          all(sum(p["ev_spread"].values()) == 508 for p in profiles))

    # Timid profile 1 final SpA > Modest profile 1 final SpA (speed-safe has no +SpA)
    sp1 = next(r["final"] for r in profiles[0]["stats"] if r["key"] == "special-attack")
    sp2 = next(r["final"] for r in profiles[1]["stats"] if r["key"] == "special-attack")
    check("build_profiles: Modest profile has higher SpA than Timid profile",
          sp2 > sp1)

    # Timid profile 1 final Speed > Modest profile 2 final Speed (more speed with +Spe)
    spe1 = next(r["final"] for r in profiles[0]["stats"] if r["key"] == "speed")
    spe2 = next(r["final"] for r in profiles[1]["stats"] if r["key"] == "speed")
    check("build_profiles: Timid profile has higher Speed than Modest profile",
          spe1 > spe2)

    # ── _print_build_profiles (stdout capture) ────────────────────────────────
    import io as _io3, contextlib as _cl3
    buf_b = _io3.StringIO()
    with _cl3.redirect_stdout(buf_b):
        _print_build_profiles(profiles, "Charizard")
    out_b = buf_b.getvalue()

    check("_print_build_profiles: form name present", "Charizard" in out_b)
    check("_print_build_profiles: Timid nature shown", "Timid" in out_b)
    check("_print_build_profiles: Modest nature shown", "Modest" in out_b)
    check("_print_build_profiles: assumption note shown", "31 IVs" in out_b)
    check("_print_build_profiles: Sp. Attack shown in stat rows", "Sp. Attack" in out_b)

    print()
    if failed:
        print(f"  {passed} passed, {failed} failed out of {passed+failed} tests.")
        sys.exit(1)
    else:
        print(f"  {passed} passed, 0 failed out of {passed} tests.")
        print("  All tests passed.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--autotest",  action="store_true")
    parser.add_argument("--withcache", action="store_true")
    args = parser.parse_args()
    if args.autotest:
        _run_tests(with_cache=args.withcache)
    else:
        main()