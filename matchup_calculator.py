#!/usr/bin/env python3
"""
Pokemon Type Matchup Tool (CLI version)

Type chart sourced directly from https://pokemondb.net/type

Three eras:
  ERA1 : Gen 1      (15 types — no Dark, Steel, Fairy)
  ERA2 : Gen 2-5    (17 types — no Fairy; Ghost & Dark not very effective vs Steel)
  ERA3 : Gen 6+     (18 types — full modern chart)
"""

# ── TYPE POOLS ────────────────────────────────────────────────────────────────

TYPES_ERA3 = [
    "Normal", "Fire", "Water", "Electric", "Grass", "Ice",
    "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug",
    "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"
]

TYPES_ERA2 = [t for t in TYPES_ERA3 if t != "Fairy"]

TYPES_ERA1 = [t for t in TYPES_ERA2 if t not in ("Dark", "Steel")]

# ── GENERATION REGISTRY ───────────────────────────────────────────────────────
# Maps generation number -> human-readable label + era key.
# Add a new entry here when a new generation is announced.
# era_key only needs updating if a new generation introduces new types or
# chart changes (e.g. if Gen 10 adds a new type, create era4 and point to it).

GENERATIONS = {
    1: {"label": "Generation 1",  "era_key": "era1"},
    2: {"label": "Generation 2",  "era_key": "era2"},
    3: {"label": "Generation 3",  "era_key": "era2"},
    4: {"label": "Generation 4",  "era_key": "era2"},
    5: {"label": "Generation 5",  "era_key": "era2"},
    6: {"label": "Generation 6",  "era_key": "era3"},
    7: {"label": "Generation 7",  "era_key": "era3"},
    8: {"label": "Generation 8",  "era_key": "era3"},
    9: {"label": "Generation 9",  "era_key": "era3"},
    # 10: {"label": "Generation 10", "era_key": "era3"},  # uncomment when needed
}

# ── GAME LIST ─────────────────────────────────────────────────────────────────
# Each entry: (display_name, era_key, generation_number)
# To add a new game: append a tuple with the correct gen number.
# If the game introduces a new type chart, also add a new era + chart above.

GAMES = [
    ("Red / Blue / Yellow",               "era1", 1),
    ("Gold / Silver / Crystal",           "era2", 2),
    ("Ruby / Sapphire / Emerald",         "era2", 3),
    ("FireRed / LeafGreen",               "era2", 3),
    ("Diamond / Pearl / Platinum",        "era2", 4),
    ("HeartGold / SoulSilver",            "era2", 4),
    ("Black / White",                     "era2", 5),
    ("Black 2 / White 2",                 "era2", 5),
    ("X / Y",                             "era3", 6),
    ("Omega Ruby / Alpha Sapphire",       "era3", 6),
    ("Sun / Moon",                        "era3", 7),
    ("Ultra Sun / Ultra Moon",            "era3", 7),
    ("Sword / Shield",                    "era3", 8),
    ("Brilliant Diamond / Shining Pearl", "era3", 8),
    ("Legends: Arceus",                   "era3", 8),
    ("Scarlet / Violet",                  "era3", 9),
    ("Legends: Z-A",                      "era3", 9),
]

# ── ERA 3 CHART (Gen 6+) ──────────────────────────────────────────────────────
# Sourced row by row from https://pokemondb.net/type
# chart[ATK][DEF] = multiplier  (only non-1.0 values stored)
# Columns order: Nor,Fir,Wat,Ele,Gra,Ice,Fig,Poi,Gro,Fly,Psy,Bug,Roc,Gho,Dra,Dar,Ste,Fai

H = 0.5  # not very effective
Z = 0.0  # immune
S = 2.0  # super effective

ERA3_CHART = {
    # ROW = attacking type, COLUMN = defending type
    # Columns:          Normal  Fire  Water  Electric  Grass   Ice  Fighting  Poison  Ground  Flying  Psychic   Bug   Rock  Ghost  Dragon   Dark  Steel  Fairy
    "Normal":        [    1,     1,     1,      1,       1,     1,     1,       1,      1,      1,      1,       1,    H,    Z,      1,      1,    H,     1  ],
    "Fire":          [    1,     H,     H,      1,       S,     S,     1,       1,      1,      1,      1,       S,    H,    1,      H,      1,    S,     1  ],
    "Water":         [    1,     S,     H,      1,       H,     1,     1,       1,      S,      1,      1,       1,    S,    1,      H,      1,    1,     1  ],
    "Electric":      [    1,     1,     S,      H,       H,     1,     1,       1,      Z,      S,      1,       1,    1,    1,      H,      1,    1,     1  ],
    "Grass":         [    1,     H,     S,      1,       H,     1,     1,       H,      S,      H,      1,       H,    S,    1,      H,      1,    H,     1  ],
    "Ice":           [    1,     H,     H,      1,       S,     H,     1,       1,      S,      S,      1,       1,    1,    1,      S,      1,    H,     1  ],
    "Fighting":      [    S,     1,     1,      1,       1,     S,     1,       H,      1,      H,      H,       H,    S,    Z,      1,      S,    S,     H  ],
    "Poison":        [    1,     1,     1,      1,       S,     1,     1,       H,      H,      1,      1,       1,    H,    H,      1,      1,    Z,     S  ],
    "Ground":        [    1,     S,     1,      S,       H,     1,     1,       S,      1,      Z,      1,       H,    S,    1,      1,      1,    S,     1  ],
    "Flying":        [    1,     1,     1,      H,       S,     1,     S,       1,      1,      1,      1,       S,    H,    1,      1,      1,    H,     1  ],
    "Psychic":       [    1,     1,     1,      1,       1,     1,     S,       S,      1,      1,      H,       1,    1,    1,      1,      Z,    H,     1  ],
    "Bug":           [    1,     H,     1,      1,       S,     1,     H,       H,      1,      H,      S,       1,    1,    H,      1,      S,    H,     H  ],
    "Rock":          [    1,     S,     1,      1,       1,     S,     H,       1,      H,      S,      1,       S,    1,    1,      1,      1,    H,     1  ],
    "Ghost":         [    Z,     1,     1,      1,       1,     1,     1,       1,      1,      1,      S,       1,    1,    S,      1,      H,    1,     1  ],
    "Dragon":        [    1,     1,     1,      1,       1,     1,     1,       1,      1,      1,      1,       1,    1,    1,      S,      1,    H,     Z  ],
    "Dark":          [    1,     1,     1,      1,       1,     1,     H,       1,      1,      1,      S,       1,    1,    S,      1,      H,    1,     H  ],
    "Steel":         [    1,     H,     H,      H,       1,     S,     1,       1,      1,      1,      1,       1,    S,    1,      1,      1,    H,     S  ],
    "Fairy":         [    1,     H,     1,      1,       1,     1,     S,       H,      1,      1,      1,       1,    1,    1,      S,      S,    H,     1  ],
}

# Column index maps — each era has its own
_COL3 = {t: i for i, t in enumerate(TYPES_ERA3)}
_COL2 = {t: i for i, t in enumerate(TYPES_ERA2)}
_COL1 = {t: i for i, t in enumerate(TYPES_ERA1)}


# ── ERA 2 CHART (Gen 2-5) ─────────────────────────────────────────────────────
# Sourced directly from https://pokemondb.net/type/old  (first table)
# ROW = attacking type, COLUMN = defending type
# Columns: Normal  Fire  Water  Electric  Grass   Ice  Fighting  Poison  Ground  Flying  Psychic   Bug   Rock  Ghost  Dragon   Dark  Steel

ERA2_CHART = {
    "Normal":   [  1,    1,    1,     1,      1,    1,    1,       1,      1,      1,      1,       1,    H,    Z,     1,      1,    H  ],
    "Fire":     [  1,    H,    H,     1,      S,    S,    1,       1,      1,      1,      1,       S,    H,    1,     H,      1,    S  ],
    "Water":    [  1,    S,    H,     1,      H,    1,    1,       1,      S,      1,      1,       1,    S,    1,     H,      1,    1  ],
    "Electric": [  1,    1,    S,     H,      H,    1,    1,       1,      Z,      S,      1,       1,    1,    1,     H,      1,    1  ],
    "Grass":    [  1,    H,    S,     1,      H,    1,    1,       H,      S,      H,      1,       H,    S,    1,     H,      1,    H  ],
    "Ice":      [  1,    H,    H,     1,      S,    H,    1,       1,      S,      S,      1,       1,    1,    1,     S,      1,    H  ],
    "Fighting": [  S,    1,    1,     1,      1,    S,    1,       H,      1,      H,      H,       H,    S,    Z,     1,      S,    S  ],
    "Poison":   [  1,    1,    1,     1,      S,    1,    1,       H,      H,      1,      1,       1,    H,    H,     1,      1,    Z  ],
    "Ground":   [  1,    S,    1,     S,      H,    1,    1,       S,      1,      Z,      1,       H,    S,    1,     1,      1,    S  ],
    "Flying":   [  1,    1,    1,     H,      S,    1,    S,       1,      1,      1,      1,       S,    H,    1,     1,      1,    H  ],
    "Psychic":  [  1,    1,    1,     1,      1,    1,    S,       S,      1,      1,      H,       1,    1,    1,     1,      Z,    H  ],
    "Bug":      [  1,    H,    1,     1,      S,    1,    H,       H,      1,      H,      S,       1,    1,    H,     1,      S,    H  ],
    "Rock":     [  1,    S,    1,     1,      1,    S,    H,       1,      H,      S,      1,       S,    1,    1,     1,      1,    H  ],
    "Ghost":    [  Z,    1,    1,     1,      1,    1,    1,       1,      1,      1,      S,       1,    1,    S,     1,      H,    H  ],
    "Dragon":   [  1,    1,    1,     1,      1,    1,    1,       1,      1,      1,      1,       1,    1,    1,     S,      1,    H  ],
    "Dark":     [  1,    1,    1,     1,      1,    1,    H,       1,      1,      1,      S,       1,    1,    S,     1,      H,    H  ],
    "Steel":    [  1,    H,    H,     H,      1,    S,    1,       1,      1,      1,      1,       1,    S,    1,     1,      1,    H  ],
}


# ── ERA 1 CHART (Gen 1) ───────────────────────────────────────────────────────
# Sourced directly from https://pokemondb.net/type/old  (second/last table)
# ROW = attacking type, COLUMN = defending type
# Columns: Normal  Fire  Water  Electric  Grass   Ice  Fighting  Poison  Ground  Flying  Psychic   Bug   Rock  Ghost  Dragon

ERA1_CHART = {
    "Normal":   [  1,    1,    1,     1,      1,    1,    1,       1,      1,      1,      1,       1,    H,    Z,     1  ],
    "Fire":     [  1,    H,    H,     1,      S,    S,    1,       1,      1,      1,      1,       S,    H,    1,     H  ],
    "Water":    [  1,    S,    H,     1,      H,    1,    1,       1,      S,      1,      1,       1,    S,    1,     H  ],
    "Electric": [  1,    1,    S,     H,      H,    1,    1,       1,      Z,      S,      1,       1,    1,    1,     H  ],
    "Grass":    [  1,    H,    S,     1,      H,    1,    1,       H,      S,      H,      1,       H,    S,    1,     H  ],
    "Ice":      [  1,    1,    H,     1,      S,    H,    1,       1,      S,      S,      1,       1,    1,    1,     S  ],
    "Fighting": [  S,    1,    1,     1,      1,    S,    1,       H,      1,      H,      H,       H,    S,    Z,     1  ],
    "Poison":   [  1,    1,    1,     1,      S,    1,    1,       H,      H,      1,      1,       S,    H,    H,     1  ],
    "Ground":   [  1,    S,    1,     S,      H,    1,    1,       S,      1,      Z,      1,       H,    S,    1,     1  ],
    "Flying":   [  1,    1,    1,     H,      S,    1,    S,       1,      1,      1,      1,       S,    H,    1,     1  ],
    "Psychic":  [  1,    1,    1,     1,      1,    1,    S,       S,      1,      1,      H,       1,    1,    1,     1  ],
    "Bug":      [  1,    H,    1,     1,      S,    1,    H,       S,      1,      H,      S,       1,    1,    H,     1  ],
    "Rock":     [  1,    S,    1,     1,      1,    S,    H,       1,      H,      S,      1,       S,    1,    1,     1  ],
    "Ghost":    [  Z,    1,    1,     1,      1,    1,    1,       1,      1,      1,      Z,       1,    1,    S,     1  ],
    "Dragon":   [  1,    1,    1,     1,      1,    1,    1,       1,      1,      1,      1,       1,    1,    1,     S  ],
}


# ── LOOKUP HELPERS ────────────────────────────────────────────────────────────

CHARTS = {
    "era1": (ERA1_CHART, TYPES_ERA1, _COL1),
    "era2": (ERA2_CHART, TYPES_ERA2, _COL2),
    "era3": (ERA3_CHART, TYPES_ERA3, _COL3),
}

ERA_LABELS = {
    "era1": "Gen 1 chart (15 types — no Dark, Steel, Fairy)",
    "era2": "Gen 2-5 chart (17 types — no Fairy)",
    "era3": "Gen 6+ chart (18 types — all types)",
}

def get_multiplier(era_key, atk, def_type):
    chart, _, col_map = CHARTS[era_key]
    row = chart.get(atk)
    if row is None:
        return 1.0
    col = col_map.get(def_type)
    if col is None:
        return 1.0
    return row[col]




def compute_defense(era_key, type1, type2):
    _, valid_types, _ = CHARTS[era_key]
    results = {}
    for atk in valid_types:
        m1 = get_multiplier(era_key, atk, type1)
        m2 = get_multiplier(era_key, atk, type2) if type2 != "None" else 1.0
        results[atk] = m1 * m2
    return results


# ── OUTPUT ────────────────────────────────────────────────────────────────────

def print_results(type1, type2, game_name, era_key):
    matchups = compute_defense(era_key, type1, type2)

    immunities  = sorted([t for t, m in matchups.items() if m == 0.0])
    resistances = sorted([t for t, m in matchups.items() if 0.0 < m < 1.0],
                         key=lambda t: matchups[t])
    weaknesses  = sorted([t for t, m in matchups.items() if m > 1.0],
                         key=lambda t: matchups[t], reverse=True)

    dual = f"{type1} / {type2}" if type2 != "None" else type1

    print()
    print("=" * 54)
    print(f"  Defending type : {dual}")
    print(f"  Game           : {game_name}")
    print(f"  Chart used     : {ERA_LABELS[era_key]}")
    print("=" * 54)

    if immunities:
        print(f"\n  IMMUNITIES (x0) :")
        for t in immunities:
            print(f"    - {t}")
    else:
        print("\n  IMMUNITIES : none")

    if resistances:
        print(f"\n  RESISTANCES :")
        for t in resistances:
            print(f"    - {t:12s}  x{matchups[t]}")
    else:
        print("\n  RESISTANCES : none")

    if weaknesses:
        print(f"\n  WEAKNESSES :")
        for t in weaknesses:
            print(f"    - {t:12s}  x{matchups[t]:.0f}")
    else:
        print("\n  WEAKNESSES : none")

    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def select_from_list(prompt, options, allow_none=False):
    print(f"\n{prompt}")
    if allow_none:
        print("   0. None (single type)")
    for i, opt in enumerate(options, start=1):
        print(f"  {i:2d}. {opt}")
    while True:
        try:
            raw = input("  Enter number: ").strip()
            idx = int(raw)
            if allow_none and idx == 0:
                return "None"
            if 1 <= idx <= len(options):
                return options[idx - 1]
            print("  Invalid choice, try again.")
        except ValueError:
            print("  Please enter a number.")


def main():
    print()
    print("╔══════════════════════════════════════╗")
    print("║    Pokemon Type Matchup Calculator   ║")
    print("╚══════════════════════════════════════╝")

    game_names = [g[0] for g in GAMES]
    game_choice = select_from_list("Select GAME:", game_names)
    era_key = next(g[1] for g in GAMES if g[0] == game_choice)
    _, valid_types, _ = CHARTS[era_key]

    type1 = select_from_list("Select PRIMARY type:", valid_types)
    remaining = [t for t in valid_types if t != type1]
    type2 = select_from_list("Select SECONDARY type (or 0 for none):", remaining, allow_none=True)

    print_results(type1, type2, game_choice, era_key)
    input("Press Enter to exit...")



# ── Self-tests ────────────────────────────────────────────────────────────────

def _run_tests():
    """
    Offline self-tests for matchup_calculator.py.
    No network, no cache, no user input required.
    Tests: get_multiplier, compute_defense, type pools, era boundaries,
           chart integrity, GAMES/GENERATIONS consistency.
    """
    passed = 0
    failed = 0

    def check(label, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  PASS  {label}")
            passed += 1
        else:
            print(f"  FAIL  {label}" + (f"  ({detail})" if detail else ""))
            failed += 1

    def m(era, atk, def_):
        return get_multiplier(era, atk, def_)

    print()
    print("matchup_calculator.py — self-test")
    print("=" * 50)

    # ── Type pool sizes ───────────────────────────────────────────────────────
    print("\n  Type pools")
    check("ERA1 has 15 types",        len(TYPES_ERA1) == 15)
    check("ERA2 has 17 types",        len(TYPES_ERA2) == 17)
    check("ERA3 has 18 types",        len(TYPES_ERA3) == 18)
    check("ERA1 has no Dark",         "Dark"  not in TYPES_ERA1)
    check("ERA1 has no Steel",        "Steel" not in TYPES_ERA1)
    check("ERA1 has no Fairy",        "Fairy" not in TYPES_ERA1)
    check("ERA2 has Dark",            "Dark"  in TYPES_ERA2)
    check("ERA2 has Steel",           "Steel" in TYPES_ERA2)
    check("ERA2 has no Fairy",        "Fairy" not in TYPES_ERA2)
    check("ERA3 has all three",       all(t in TYPES_ERA3 for t in ("Dark","Steel","Fairy")))
    check("ERA2 = ERA3 minus Fairy",  set(TYPES_ERA2) == set(TYPES_ERA3) - {"Fairy"})
    check("ERA1 = ERA2 minus Dark/Steel",
          set(TYPES_ERA1) == set(TYPES_ERA2) - {"Dark", "Steel"})

    # ── get_multiplier — era3 known values ───────────────────────────────────
    print("\n  get_multiplier (era3)")
    check("Ghost → Normal = 0×",          m("era3","Ghost","Normal")    == 0.0)
    check("Normal → Ghost = 0×",          m("era3","Normal","Ghost")    == 0.0)
    check("Fighting → Normal = 2×",       m("era3","Fighting","Normal") == 2.0)
    check("Fire → Grass = 2×",            m("era3","Fire","Grass")      == 2.0)
    check("Fire → Fire = 0.5×",           m("era3","Fire","Fire")       == 0.5)
    check("Water → Rock = 2×",            m("era3","Water","Rock")      == 2.0)
    check("Electric → Ground = 0×",       m("era3","Electric","Ground") == 0.0)
    check("Dragon → Fairy = 0×",          m("era3","Dragon","Fairy")    == 0.0)
    check("Steel → Fairy = 2×",           m("era3","Steel","Fairy")     == 2.0)
    check("Fairy → Dragon = 2×",          m("era3","Fairy","Dragon")    == 2.0)
    check("Poison → Fairy = 2×",          m("era3","Poison","Fairy")    == 2.0)
    check("Fighting → Ghost = 0×",        m("era3","Fighting","Ghost")  == 0.0)
    check("Psychic → Dark = 0×",          m("era3","Psychic","Dark")    == 0.0)

    # ── get_multiplier — era2 differences from era3 ──────────────────────────
    print("\n  get_multiplier (era2 vs era3)")
    # In era2: Ghost and Dark are ×0.5 against Steel (era3: ×1)
    check("Ghost → Steel = 0.5× (era2)",  m("era2","Ghost","Steel")    == 0.5)
    check("Dark  → Steel = 0.5× (era2)",  m("era2","Dark","Steel")     == 0.5)
    check("Ghost → Steel = 1.0× (era3)",  m("era3","Ghost","Steel")    == 1.0)
    check("Dark  → Steel = 1.0× (era3)",  m("era3","Dark","Steel")     == 1.0)
    # Fairy does not exist in era2 — unknown type falls back to 1.0
    check("Fairy atk in era2 → 1.0 fallback",  m("era2","Fairy","Water")  == 1.0)
    check("x Fairy def in era2 → 1.0 fallback",m("era2","Fire","Fairy")   == 1.0)

    # ── get_multiplier — era1 quirks ─────────────────────────────────────────
    print("\n  get_multiplier (era1 quirks)")
    # Gen 1: Ghost → Psychic = 0× (intended ×2, coded as ×0 due to a bug)
    check("Ghost → Psychic = 0× (era1 bug)",   m("era1","Ghost","Psychic") == 0.0)
    check("Ghost → Psychic = 2× (era3)",        m("era3","Ghost","Psychic") == 2.0)
    # Gen 1: Bug → Poison = 2× (changed to ×0.5 in gen 2+)
    check("Bug → Poison = 2× (era1)",           m("era1","Bug","Poison")    == 2.0)
    check("Bug → Poison = 0.5× (era2+)",        m("era2","Bug","Poison")    == 0.5)
    check("Bug → Poison = 0.5× (era3)",         m("era3","Bug","Poison")    == 0.5)
    # Gen 1: Ice → Fire = 1× (changed to ×0.5 in gen 2+)
    check("Ice → Fire = 1× (era1)",             m("era1","Ice","Fire")      == 1.0)
    check("Ice → Fire = 0.5× (era2+)",          m("era2","Ice","Fire")      == 0.5)
    # Dark/Steel don't exist in era1 — fallback to 1.0
    check("Dark atk in era1 → 1.0 fallback",    m("era1","Dark","Normal")   == 1.0)
    check("Steel def in era1 → 1.0 fallback",   m("era1","Fire","Steel")    == 1.0)

    # ── get_multiplier — unknown type fallback ────────────────────────────────
    print("\n  get_multiplier (unknown type fallback)")
    check("Unknown atk type → 1.0",   m("era3","Faketype","Water")   == 1.0)
    check("Unknown def type → 1.0",   m("era3","Fire","Faketype")    == 1.0)
    check("Both unknown → 1.0",       m("era3","Fake1","Fake2")      == 1.0)

    # ── compute_defense — single type ────────────────────────────────────────
    print("\n  compute_defense (single type)")
    fire_def = compute_defense("era3", "Fire", "None")
    check("Fire def: Water → 2×",      fire_def["Water"]    == 2.0)
    check("Fire def: Fire → 0.5×",     fire_def["Fire"]     == 0.5)
    check("Fire def: Ground → 2×",     fire_def["Ground"]   == 2.0)
    check("Fire def: all era3 types covered",
          set(fire_def.keys()) == set(TYPES_ERA3))

    # ── compute_defense — dual type ───────────────────────────────────────────
    print("\n  compute_defense (dual type)")
    # Charizard: Fire / Flying
    char = compute_defense("era3", "Fire", "Flying")
    check("Charizard: Rock → 4×",      char["Rock"]     == 4.0)
    check("Charizard: Ground → 0×",    char["Ground"]   == 0.0)  # Flying immune
    check("Charizard: Water → 2×",     char["Water"]    == 2.0)
    check("Charizard: Electric → 2×",  char["Electric"] == 2.0)
    check("Charizard: Grass → 0.25×",  char["Grass"]    == 0.25)
    check("Charizard: Fighting → 0.5×",char["Fighting"] == 0.5)  # Fire×1 * Fly×0.5
    check("Charizard: Bug → 0.25×",    char["Bug"]      == 0.25)

    # Gengar: Ghost / Poison
    gengar = compute_defense("era3", "Ghost", "Poison")
    check("Gengar: Normal → 0×",       gengar["Normal"]   == 0.0)
    check("Gengar: Fighting → 0×",     gengar["Fighting"] == 0.0)
    check("Gengar: Psychic → 2×",      gengar["Psychic"]  == 2.0)
    check("Gengar: Ground → 2×",       gengar["Ground"]   == 2.0)

    # Magnezone: Electric / Steel
    magnezone = compute_defense("era3", "Electric", "Steel")
    check("Magnezone: Ground → 4×",    magnezone["Ground"]   == 4.0)
    check("Magnezone: Fire → 2×",      magnezone["Fire"]     == 2.0)
    check("Magnezone: Electric → 0.5×",  magnezone["Electric"] == 0.5)

    # ── Era boundary: same type, different era ────────────────────────────────
    print("\n  compute_defense era boundary")
    steel_era2 = compute_defense("era2", "Steel", "None")
    steel_era3 = compute_defense("era3", "Steel", "None")
    # In era2: Ghost and Dark are ×0.5 vs Steel; era3: ×1.0
    check("Steel def era2: Ghost → 0.5×",  steel_era2.get("Ghost") == 0.5)
    check("Steel def era2: Dark  → 0.5×",  steel_era2.get("Dark")  == 0.5)
    check("Steel def era3: Ghost → 1.0×",  steel_era3.get("Ghost") == 1.0)
    check("Steel def era3: Dark  → 1.0×",  steel_era3.get("Dark")  == 1.0)
    # Fairy does not exist in era2 type pool — not in results
    check("Steel def era2: no Fairy key",  "Fairy" not in steel_era2)
    check("Steel def era3: Fairy → 0.5×",  steel_era3.get("Fairy") == 0.5)

    # ── GAMES list integrity ──────────────────────────────────────────────────
    print("\n  GAMES / GENERATIONS integrity")
    valid_era_keys = set(CHARTS.keys())
    bad_games = [g[0] for g in GAMES if g[1] not in valid_era_keys]
    check("All GAMES entries have a valid era_key",
          len(bad_games) == 0, str(bad_games))

    bad_gens = [g for g, v in GENERATIONS.items() if v["era_key"] not in valid_era_keys]
    check("All GENERATIONS entries have a valid era_key",
          len(bad_gens) == 0, str(bad_gens))

    gen_from_games = {gen for _, _, gen in GAMES}
    missing_gens = gen_from_games - set(GENERATIONS.keys())
    check("Every gen used in GAMES is in GENERATIONS",
          len(missing_gens) == 0, str(missing_gens))

    # Every era referenced in GAMES has a chart with the right column count
    for era_key in valid_era_keys:
        chart, types, col_map = CHARTS[era_key]
        n = len(types)
        bad_rows = [atk for atk, row in chart.items() if len(row) != n]
        check(f"{era_key}: all chart rows have {n} columns",
              len(bad_rows) == 0, str(bad_rows))
        check(f"{era_key}: col_map has {n} entries",
              len(col_map) == n)
        check(f"{era_key}: col_map keys match type list",
              set(col_map.keys()) == set(types))

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(f"  {passed + failed} tests: {passed} passed, {failed} failed")
    if failed:
        print("  SOME TESTS FAILED")
        import sys; sys.exit(1)
    else:
        print("  All tests passed.\n")

if __name__ == "__main__":
    import sys
    if "--autotest" in sys.argv or "--dry-run" in sys.argv:
        _run_tests()
    else:
        main()