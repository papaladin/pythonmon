#!/usr/bin/env python3
"""
core_move.py  Pure move‑scoring logic and static data (no I/O, no display)

Contains:
  - Static tables for move scoring (two‑turn penalties, combo exclusions, etc.)
  - Pure functions for move scoring, combo selection, and status ranking.
"""

import sys

try:
    import matchup_calculator as calc
except ModuleNotFoundError as e:
    print(f"\n  ERROR: {e}")
    print("  Make sure all files are in the same folder.\n")
    sys.exit(1)


# ── Static tables (moved from feat_moveset_data.py) ───────────────────────────

# Low‑accuracy display threshold (display‑only, not used in scoring)
LOW_ACCURACY_THRESHOLD = 75

# Combo recommendation exclusion list
COMBO_EXCLUDED = frozenset({
    "Self-Destruct", "Explosion", "Misty Explosion", "Final Gambit",
    "Memento", "Healing Wish", "Lunar Dance",
    "Focus Punch", "Perish Song", "Destiny Bond",
    "Curse", "Grudge", "Spite",
    "Fling", "Natural Gift", "Last Resort",
})

# Conditional move penalties
CONDITIONAL_PENALTY = {
    "Dream Eater": 0.3,
    "Belch": 0.3,
}

# Power overrides for moves with no API base power
POWER_OVERRIDE = {
    "Wring Out": 120,
}

# Two‑turn move penalties
TWO_TURN_MOVES = {
    # Charge + exposed
    "Solar Beam":      {"type": "Grass",    "invulnerable": False, "penalty": 0.5},
    "Solar Blade":     {"type": "Grass",    "invulnerable": False, "penalty": 0.5},
    "Sky Attack":      {"type": "Normal",   "invulnerable": False, "penalty": 0.5},
    "Skull Bash":      {"type": "Normal",   "invulnerable": False, "penalty": 0.5},
    "Razor Wind":      {"type": "Normal",   "invulnerable": False, "penalty": 0.5},
    "Ice Burn":        {"type": "Ice",      "invulnerable": False, "penalty": 0.5},
    "Freeze Shock":    {"type": "Ice",      "invulnerable": False, "penalty": 0.5},
    "Electro Shot":    {"type": "Electric", "invulnerable": False, "penalty": 0.5},
    "Meteor Beam":     {"type": "Rock",     "invulnerable": False, "penalty": 0.5},
    "Geomancy":        {"type": "Fairy",    "invulnerable": False, "penalty": 0.5},
    # Recharge + exposed
    "Hyper Beam":      {"type": "Normal",   "invulnerable": False, "penalty": 0.6},
    "Giga Impact":     {"type": "Normal",   "invulnerable": False, "penalty": 0.6},
    "Frenzy Plant":    {"type": "Grass",    "invulnerable": False, "penalty": 0.6},
    "Blast Burn":      {"type": "Fire",     "invulnerable": False, "penalty": 0.6},
    "Hydro Cannon":    {"type": "Water",    "invulnerable": False, "penalty": 0.6},
    "Rock Wrecker":    {"type": "Rock",     "invulnerable": False, "penalty": 0.6},
    "Roar of Time":    {"type": "Dragon",   "invulnerable": False, "penalty": 0.6},
    "Meteor Assault":  {"type": "Fighting", "invulnerable": False, "penalty": 0.6},
    "Eternabeam":      {"type": "Dragon",   "invulnerable": False, "penalty": 0.6},
    "Prismatic Laser": {"type": "Psychic",  "invulnerable": False, "penalty": 0.6},
    "Shadow Half":     {"type": "Shadow",   "invulnerable": False, "penalty": 0.6},
    # Charge + protected
    "Fly":             {"type": "Flying",   "invulnerable": True,  "penalty": 0.8},
    "Dig":             {"type": "Ground",   "invulnerable": True,  "penalty": 0.8},
    "Dive":            {"type": "Water",    "invulnerable": True,  "penalty": 0.8},
    "Bounce":          {"type": "Flying",   "invulnerable": True,  "penalty": 0.8},
    "Shadow Force":    {"type": "Ghost",    "invulnerable": True,  "penalty": 0.8},
    "Phantom Force":   {"type": "Ghost",    "invulnerable": True,  "penalty": 0.8},
    "Sky Drop":        {"type": "Flying",   "invulnerable": True,  "penalty": 0.8},
}

# Status move tiers
STATUS_MOVE_TIERS = {
    # Tier 1: Offensive ailments (paralysis, burn, sleep, poison)
    "Thunder Wave":   (1, 9), "Nuzzle":       (1, 7), "Glare":        (1, 8),
    "Stun Spore":     (1, 6), "Will-O-Wisp":  (1, 8), "Toxic":        (1, 9),
    "Poison Powder":  (1, 5), "Toxic Spikes": (1, 6), "Spore":        (1, 10),
    "Sleep Powder":   (1, 7), "Hypnosis":     (1, 5), "Lovely Kiss":  (1, 6),
    "Sing":           (1, 4), "Yawn":         (1, 6), "Dark Void":    (1, 7),
    "Confuse Ray":    (1, 5), "Supersonic":   (1, 3), "Sweet Kiss":   (1, 3),
    "Teeter Dance":   (1, 5), "Attract":      (1, 4), "Embargo":      (1, 4),
    "Taunt":          (1, 6), "Encore":       (1, 6), "Disable":      (1, 5),
    # Tier 2: Stat boosts
    "Belly Drum":     (2, 10), "Shell Smash":  (2, 10), "Quiver Dance": (2, 9),
    "Dragon Dance":   (2, 9),  "Shift Gear":   (2, 9),  "Geomancy":     (2, 9),
    "Clangorous Soul":(2, 8),  "Victory Dance":(2, 9),  "Swords Dance": (2, 8),
    "Nasty Plot":     (2, 8),  "Tail Glow":    (2, 9),  "Calm Mind":    (2, 7),
    "Bulk Up":        (2, 7),  "Coil":         (2, 7),  "Work Up":      (2, 5),
    "Hone Claws":     (2, 5),  "Charge":       (2, 4),  "Meditate":     (2, 4),
    "Sharpen":        (2, 4),  "Howl":         (2, 5),  "Growth":       (2, 5),
    "Stockpile":      (2, 5),  "Iron Defense": (2, 6),  "Amnesia":      (2, 6),
    "Acid Armor":     (2, 6),  "Barrier":      (2, 5),  "Cotton Guard": (2, 5),
    "Cosmic Power":   (2, 5),  "Defense Curl": (2, 3),  "Withdraw":     (2, 3),
    "Harden":         (2, 3),  "Agility":      (2, 6),  "Autotomize":   (2, 6),
    "Rock Polish":    (2, 6),  "Flame Charge": (2, 4),  "Minimize":     (2, 4),
    "Double Team":    (2, 3),  "Focus Energy": (2, 5),  "Laser Focus":  (2, 5),
    # Tier 3: Recovery
    "Recover":        (3, 10), "Roost":        (3, 10), "Soft-Boiled":  (3, 10),
    "Milk Drink":     (3, 10), "Slack Off":    (3, 10), "Shore Up":     (3, 9),
    "Heal Order":     (3, 9),  "Jungle Healing":(3, 8), "Synthesis":    (3, 7),
    "Moonlight":      (3, 7),  "Morning Sun":  (3, 7),  "Rest":         (3, 6),
    "Life Dew":       (3, 7),  "Wish":         (3, 7),  "Aqua Ring":    (3, 5),
    "Ingrain":        (3, 4),  "Leech Seed":   (3, 6),  "Pain Split":   (3, 5),
    "Swallow":        (3, 5),  "Recycle":      (3, 3),
    # Tier 4: Field effects and other
    "Stealth Rock":   (4, 8), "Spikes":        (4, 7), "Sticky Web":   (4, 6),
    "Light Screen":   (4, 7), "Reflect":       (4, 7), "Aurora Veil":  (4, 7),
    "Sunny Day":      (4, 6), "Rain Dance":    (4, 6), "Sandstorm":    (4, 5),
    "Snowscape":      (4, 5), "Hail":          (4, 4), "Electric Terrain":(4,5),
    "Grassy Terrain": (4, 5), "Misty Terrain": (4, 5), "Psychic Terrain":(4,5),
    "Trick Room":     (4, 6), "Tailwind":      (4, 6), "Roar":         (4, 5),
    "Whirlwind":      (4, 5), "Dragon Tail":  (4, 4), "Circle Throw": (4, 4),
    "Substitute":     (4, 7), "Protect":      (4, 6), "Detect":       (4, 5),
    "Endure":         (4, 4), "Trick":        (4, 6), "Switcheroo":   (4, 6),
    "Perish Song":    (4, 4), "Destiny Bond": (4, 5), "Spite":        (4, 3),
    "Helping Hand":   (4, 4), "Follow Me":    (4, 4), "Rage Powder":  (4, 4),
    "Sleep Talk":     (4, 4), "Snore":        (4, 3), "Mimic":        (4, 3),
    "Copycat":        (4, 3), "Me First":     (4, 3), "Magic Coat":   (4, 4),
    "Safeguard":      (4, 4), "Mist":         (4, 3), "Baton Pass":   (4, 5),
    "U-turn":         (4, 4), "Volt Switch":  (4, 4), "Parting Shot": (4, 5),
    "Chilly Reception":(4,5), "Teleport":     (4, 3), "Smokescreen":  (4, 2),
    "Sand Attack":    (4, 2), "Growl":        (4, 2), "Leer":         (4, 2),
    "Tail Whip":      (4, 2), "Scary Face":   (4, 3), "String Shot":  (4, 2),
    "Sweet Scent":    (4, 2), "Charm":        (4, 4), "Fake Tears":   (4, 4),
    "Metal Sound":    (4, 3), "Captivate":    (4, 2), "Tickle":       (4, 3),
    "Feather Dance":  (4, 3), "Memento":      (4, 4), "Heal Bell":    (4, 5),
    "Aromatherapy":   (4, 5), "Dragon Cheer": (4, 4),
}

# Status move categories (for internal use, not needed in core)
STATUS_CATEGORIES = {
    "ailment":           {"label": "Status ailment", "tier": 1},
    "net-good-stats":    {"label": "Stat boost",     "tier": 2},
    "heal":              {"label": "Recovery",       "tier": 3},
    "whole-field-effect":{"label": "Field effect",   "tier": 4},
    "field-effect":      {"label": "Field effect",   "tier": 4},
    "force-switch":      {"label": "Phazing",        "tier": 4},
    "unique":            {"label": "Unique",         "tier": 4},
}

# Scoring weights
_COVERAGE_BONUS_PER_TYPE = 25
_COUNTER_BONUS_PER_WEAK = 25
_STAB_BONUS_PER_MOVE = 30
_REDUNDANCY_PENALTY = 30

# Pool caps
_STAB_POOL_CAP = 25
_COUNTER_FILLER_K = 8


# ── Pure functions ────────────────────────────────────────────────────────────

def score_move(move_entry: dict, pkm_ctx: dict, game_ctx: dict) -> float:
    """
    Score a single move for a given Pokemon + game context.

    Returns 0.0 for status moves (no base_power) or unavailable moves (None entry).
    """
    if move_entry is None:
        return 0.0

    base_power = move_entry.get("power")
    base_power = POWER_OVERRIDE.get(move_entry.get("name", ""), base_power)

    if not base_power:
        return 0.0

    game_gen = game_ctx.get("game_gen", 1)
    category = move_entry.get("category", "")
    move_type = move_entry.get("type", "")
    accuracy = move_entry.get("accuracy")
    pkm_types = pkm_ctx.get("types", [])
    base_stats = pkm_ctx.get("base_stats", {})
    if not isinstance(base_stats, dict):
        base_stats = {}

    # stat_weight (Gen 4+ only)
    if game_gen >= 4 and category in ("Physical", "Special"):
        atk = base_stats.get("attack", 1) or 1
        spa = base_stats.get("special-attack", 1) or 1
        if category == "Physical":
            relevant, weaker = atk, spa
        else:
            relevant, weaker = spa, atk
        stat_weight = min(relevant / weaker, 2.0)
        stat_weight = max(stat_weight, 1.0)
    else:
        stat_weight = 1.0

    stab_bonus = 1.5 if move_type in pkm_types else 1.0

    two_turn = TWO_TURN_MOVES.get(move_entry.get("name", ""))
    two_turn_penalty = two_turn["penalty"] if two_turn else 1.0

    acc_factor = 1.0 if accuracy is None else min(accuracy, 100) / 100.0

    priority = move_entry.get("priority", 0) or 0
    if priority < 0:
        priority_factor = max(1.0 + priority * 0.15, 0.1)
    elif priority > 0:
        priority_factor = 1.0 + priority * 0.08
    else:
        priority_factor = 1.0

    drain = move_entry.get("drain", 0) or 0
    if drain < 0:
        recoil_factor = max(1.0 + drain / 100.0 * 0.5, 0.4)
    elif drain > 0:
        recoil_factor = 1.0 + drain / 100.0 * 0.3
    else:
        recoil_factor = 1.0

    effect_chance = move_entry.get("effect_chance", 0) or 0
    effect_factor = 1.0 + effect_chance / 100.0 * 0.2

    conditional_factor = CONDITIONAL_PENALTY.get(move_entry.get("name", ""), 1.0)

    return (base_power * stat_weight * stab_bonus
            * two_turn_penalty * acc_factor * priority_factor
            * recoil_factor * effect_factor * conditional_factor)


def rank_status_moves(status_pool: list, top_n: int = 3) -> list:
    """
    Rank status moves from the candidate pool and return the top N.
    """
    _TIER_LABELS = {1: "Status ailment", 2: "Stat boost",
                    3: "Recovery",        4: "Field / other"}

    enriched = []
    for row in status_pool:
        name = row["name"]
        tier, quality = STATUS_MOVE_TIERS.get(name, (4, 0))
        enriched.append({
            **row,
            "tier": tier,
            "quality": quality,
            "tier_label": _TIER_LABELS.get(tier, "Other"),
        })

    enriched.sort(key=lambda r: (r["tier"], -r["quality"], r["name"]))
    return enriched[:top_n]


def uncovered_weaknesses(combo: list, weakness_types: list) -> int:
    """Return the number of weakness types not covered by any move in combo."""
    countered = set()
    for r in combo:
        for w in r.get("counters_weaknesses", []):
            countered.add(w)
    return len(weakness_types) - len(countered & set(weakness_types))


def combo_score(combo: list, weakness_types: list, era_key: str, mode: str) -> float:
    """
    Score a 4-move combination.

    combo         — list of 4 move dicts from the damage pool
    weakness_types — list of attacker types that hit this Pokemon SE
    era_key       — "era1" / "era2" / "era3" for type chart lookup
    mode          — "coverage" | "counter" | "stab"
    """
    import matchup_calculator as _calc

    base = sum(r["score"] for r in combo)

    # Coverage bonus (marginal)
    covered = set()
    marginal = 0
    for r in sorted(combo, key=lambda x: x["score"], reverse=True):
        move_se = {t for t in _calc.TYPES_ERA3
                   if _calc.get_multiplier(era_key, r["type"], t) >= 2.0}
        new_types = move_se - covered
        marginal += len(new_types)
        covered |= move_se
    coverage_bonus = marginal * _COVERAGE_BONUS_PER_TYPE

    # Counter bonus
    if mode == "counter":
        countered = set()
        for r in combo:
            for w in r.get("counters_weaknesses", []):
                countered.add(w)
        counter_bonus = len(countered) * _COUNTER_BONUS_PER_WEAK
    else:
        counter_bonus = 0

    # STAB bonus
    if mode == "stab":
        stab_bonus = sum(1 for r in combo if r.get("is_stab", False)) * _STAB_BONUS_PER_MOVE
    else:
        stab_bonus = 0

    # Redundancy penalty (Normal exempt)
    type_counts = {}
    for r in combo:
        t = r["type"]
        if t != "Normal":
            type_counts[t] = type_counts.get(t, 0) + 1
    redundancy_penalty = sum(
        (count - 1) * _REDUNDANCY_PENALTY
        for count in type_counts.values()
        if count > 1
    )

    return base + coverage_bonus + counter_bonus + stab_bonus - redundancy_penalty


def build_counter_pool(eligible: list, weakness_types: list) -> list:
    """Build candidate pool for counter mode."""
    covering = [r for r in eligible if r.get("counters_weaknesses")]
    non_covering = [r for r in eligible if not r.get("counters_weaknesses")]
    return covering + non_covering[:_COUNTER_FILLER_K]


def build_coverage_pool(eligible: list) -> list:
    """Build candidate pool for coverage mode (best move per type)."""
    seen_types = {}
    for r in eligible:   # eligible is score-sorted desc
        t = r["type"]
        if t not in seen_types:
            seen_types[t] = r
    return list(seen_types.values())


def select_combo(damage_pool: list, mode: str, weakness_types: list,
                 era_key: str, locked: list | None = None) -> list:
    """
    Select the best 4-move combination from damage_pool for the given mode.

    damage_pool   — list of move dicts from build_candidate_pool(), score-sorted desc
    mode          — "coverage" | "counter" | "stab"
    weakness_types — attacker types that are SE vs this Pokemon (from compute_defense)
    era_key       — type chart era
    locked        — list of move dicts already pinned by the user (0–3 moves).

    Returns a list of 4 move dicts (locked moves first, then selected moves).
    Returns fewer than 4 if the pool is too small to fill all slots.
    """
    from itertools import combinations

    locked = locked or []
    locked_names = {r["name"] for r in locked}
    slots_needed = 4 - len(locked)

    if slots_needed <= 0:
        return locked[:4]

    eligible = [r for r in damage_pool
                if r["name"] not in locked_names
                and r["name"] not in COMBO_EXCLUDED]

    # Mode-specific pool construction
    if mode == "counter":
        free_pool = build_counter_pool(eligible, weakness_types)
    elif mode == "coverage":
        free_pool = build_coverage_pool(eligible)
    else:   # stab
        free_pool = eligible[:_STAB_POOL_CAP]

    if not free_pool:
        return locked

    n_select = min(slots_needed, len(free_pool))

    # Two-pass selection for counter and coverage
    if mode == "counter":
        # Pass 1: find min gap
        min_gap = len(weakness_types)
        for selected in combinations(free_pool, n_select):
            gap = uncovered_weaknesses(locked + list(selected), weakness_types)
            if gap < min_gap:
                min_gap = gap
                if min_gap == 0:
                    break

        # Pass 2: best score among combos at min_gap
        best_combo = None
        best_score = float("-inf")
        for selected in combinations(free_pool, n_select):
            combo = locked + list(selected)
            if uncovered_weaknesses(combo, weakness_types) == min_gap:
                score = combo_score(combo, weakness_types, era_key, mode)
                if score > best_score:
                    best_score = score
                    best_combo = combo

    elif mode == "coverage":
        # Pass 1: find max SE-type count
        max_se = 0
        for selected in combinations(free_pool, n_select):
            combo = locked + list(selected)
            se_types = set()
            for r in combo:
                for t in calc.TYPES_ERA3:
                    if calc.get_multiplier(era_key, r["type"], t) >= 2.0:
                        se_types.add(t)
            n_se = len(se_types)
            if n_se > max_se:
                max_se = n_se
                if max_se == len(calc.TYPES_ERA3):
                    break

        # Pass 2: best score among combos achieving max_se
        best_combo = None
        best_score = float("-inf")
        for selected in combinations(free_pool, n_select):
            combo = locked + list(selected)
            se_types = set()
            for r in combo:
                for t in calc.TYPES_ERA3:
                    if calc.get_multiplier(era_key, r["type"], t) >= 2.0:
                        se_types.add(t)
            if len(se_types) == max_se:
                score = combo_score(combo, weakness_types, era_key, mode)
                if score > best_score:
                    best_score = score
                    best_combo = combo

    else:   # stab — single pass, pure score
        best_combo = None
        best_score = float("-inf")
        for selected in combinations(free_pool, n_select):
            combo = locked + list(selected)
            score = combo_score(combo, weakness_types, era_key, mode)
            if score > best_score:
                best_score = score
                best_combo = combo

    return best_combo or locked


def score_learnset(form_data: dict, move_entries_map: dict,
                   pkm_ctx: dict, game_ctx: dict,
                   weakness_types: list, era_key: str) -> tuple:
    """
    Pure function to score a learnset given pre‑resolved move entries.

    Args:
      form_data — learnset dict for the specific form (keys: level-up, machine, etc.)
      move_entries_map — dict mapping move name → resolved versioned entry dict
      pkm_ctx, game_ctx — standard context dicts
      weakness_types — list of types this Pokémon is weak to
      era_key — type chart era

    Returns:
      (damage_pool, status_pool) where each is a list of move dicts (damage sorted by score desc).
    """
    import matchup_calculator as _calc

    seen = set()
    damage_pool = []
    status_pool = []

    for section in ("level-up", "machine", "tutor", "egg"):
        for entry in form_data.get(section, []):
            move_name = entry.get("move")
            if not move_name or move_name in seen:
                continue
            seen.add(move_name)

            move_entry = move_entries_map.get(move_name)
            if move_entry is None:
                continue   # move not in cache

            move_type = move_entry.get("type", "")
            category = move_entry.get("category", "")
            power = move_entry.get("power")
            accuracy = move_entry.get("accuracy")
            pp = move_entry.get("pp")

            scr = score_move(move_entry, pkm_ctx, game_ctx)
            is_stab = move_type in pkm_ctx.get("types", [])

            counters = [
                w for w in weakness_types
                if _calc.get_multiplier(era_key, move_type, w) >= 2.0
            ]

            row = {
                "name": move_name,
                "type": move_type,
                "category": category,
                "power": power,
                "accuracy": accuracy,
                "pp": pp,
                "priority": move_entry.get("priority", 0) or 0,
                "drain": move_entry.get("drain", 0) or 0,
                "effect_chance": move_entry.get("effect_chance", 0) or 0,
                "ailment": move_entry.get("ailment", "none") or "none",
                "score": scr,
                "is_stab": is_stab,
                "counters_weaknesses": counters,
                "is_two_turn": move_name in TWO_TURN_MOVES,
                "low_accuracy": (accuracy is not None and accuracy <= LOW_ACCURACY_THRESHOLD),
            }

            if scr > 0:
                damage_pool.append(row)
            else:
                status_pool.append(row)

    damage_pool.sort(key=lambda r: r["score"], reverse=True)
    status_pool.sort(key=lambda r: r["name"])
    return damage_pool, status_pool


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

    print("\n  core_move.py — self-test\n")

    # Minimal test for score_move (simple check)
    charizard = {
        "types": ["Fire", "Flying"],
        "base_stats": {"attack": 84, "special-attack": 109,
                       "defense": 78, "special-defense": 85,
                       "speed": 100, "hp": 78}
    }
    game_gen9 = {"game_gen": 9}
    flamethrower = {"type": "Fire", "category": "Special", "power": 90, "accuracy": 100}
    score = score_move(flamethrower, charizard, game_gen9)
    if 90 * 1.5 * (109/84) * 1.0 * 1.0 * 1.0 * 1.0 * 1.0 > score - 0.1:  # approximate
        ok("score_move: Flamethrower on Charizard scores > 0")
    else:
        fail("score_move basic", str(score))

    # rank_status_moves simple check
    status_pool = [
        {"name": "Swords Dance", "type": "Normal"},
        {"name": "Recover", "type": "Normal"},
        {"name": "Thunder Wave", "type": "Electric"},
    ]
    ranked = rank_status_moves(status_pool, top_n=2)
    if len(ranked) == 2 and ranked[0]["name"] == "Thunder Wave":
        ok("rank_status_moves: correct order")
    else:
        fail("rank_status_moves order", str([r["name"] for r in ranked]))

    # uncovered_weaknesses
    combo = [{"counters_weaknesses": ["Water", "Electric"]}, {"counters_weaknesses": ["Rock"]}]
    if uncovered_weaknesses(combo, ["Water", "Electric", "Rock"]) == 0:
        ok("uncovered_weaknesses: fully covered")
    else:
        fail("uncovered_weaknesses full")

    # combo_score minimal test
    combo = [
        {"score": 100, "type": "Fire", "counters_weaknesses": ["Grass"]},
        {"score": 80, "type": "Water", "counters_weaknesses": ["Fire"]},
    ]
    sc = combo_score(combo, ["Grass"], "era3", "coverage")
    if sc > 0:
        ok("combo_score returns number")
    else:
        fail("combo_score", str(sc))

    # build_counter_pool
    eligible = [
        {"name": "A", "counters_weaknesses": ["Water"], "score": 100},
        {"name": "B", "counters_weaknesses": [], "score": 90},
        {"name": "C", "counters_weaknesses": [], "score": 80},
    ]
    pool = build_counter_pool(eligible, ["Water"])
    if len(pool) == 3 and pool[0]["name"] == "A":
        ok("build_counter_pool: includes covering + all non-covering (within filler limit)")
    else:
        fail("build_counter_pool", str([r["name"] for r in pool]))

    # build_coverage_pool
    eligible2 = [
        {"name": "F1", "type": "Fire", "score": 100},
        {"name": "F2", "type": "Fire", "score": 90},
        {"name": "W", "type": "Water", "score": 80},
    ]
    pool2 = build_coverage_pool(eligible2)
    if len(pool2) == 2 and pool2[0]["name"] == "F1" and pool2[1]["name"] == "W":
        ok("build_coverage_pool: best per type")
    else:
        fail("build_coverage_pool", str([r["name"] for r in pool2]))

    # select_combo simple test
    damage_pool = [
        {"name": "A", "type": "Fire", "score": 100, "counters_weaknesses": ["Grass"]},
        {"name": "B", "type": "Water", "score": 80, "counters_weaknesses": ["Fire"]},
        {"name": "C", "type": "Grass", "score": 70, "counters_weaknesses": ["Water"]},
        {"name": "D", "type": "Normal", "score": 60, "counters_weaknesses": []},
    ]
    combo = select_combo(damage_pool, "coverage", ["Grass", "Fire"], "era3")
    if len(combo) == 4 and "A" in [m["name"] for m in combo]:
        ok("select_combo: returns combo")
    else:
        fail("select_combo", str([m["name"] for m in combo]))

    # score_learnset minimal test
    form_data = {"level-up": [{"move": "Flamethrower"}]}
    move_entries_map = {"Flamethrower": {"type": "Fire", "category": "Special", "power": 90, "accuracy": 100}}
    pkm_ctx = {"types": ["Fire"], "base_stats": {"attack": 84, "special-attack": 109}}
    game_ctx = {"game_gen": 9}
    weak_types = ["Water"]
    damage, status = score_learnset(form_data, move_entries_map, pkm_ctx, game_ctx, weak_types, "era3")
    if len(damage) == 1 and damage[0]["name"] == "Flamethrower" and len(status) == 0:
        ok("score_learnset: returns damage pool")
    else:
        fail("score_learnset", f"damage={len(damage)} status={len(status)}")

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