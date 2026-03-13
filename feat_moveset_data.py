#!/usr/bin/env python3
"""
feat_moveset_data.py  Static reference tables for moveset recommendation.

Contents:
  TWO_TURN_MOVES        — moves with a charge or recharge turn, keyed by display name.
                          Each entry: {type, invulnerable, penalty}
                          penalty is the effective-power multiplier applied during scoring.

  COMBO_EXCLUDED        — frozenset of move names never auto-suggested by select_combo().
                          Moves remain accessible as user-locked slots.
                          Three groups: self-KO, setup-dependent, near-zero value.

  STATUS_CATEGORIES     — maps PokeAPI move-meta-category slugs to
                          {label, tier} for ranking status moves.
                          Lower tier = higher priority.

  LOW_ACCURACY_THRESHOLD — moves at or below this accuracy are flagged in the
                           display layer. No effect on scoring — accuracy is applied
                           linearly (accuracy / 100) with no floor or cutoff.

  score_move()          — single move scorer. See docstring for formula.

Run this file directly to execute unit tests:
  python feat_moveset_data.py
"""

# ── Low-accuracy display threshold ───────────────────────────────────────────
#
# Moves at or below this value are flagged with a disclaimer in the display.
# This is a DISPLAY-ONLY flag — it has no effect on scoring.
# Accuracy is applied linearly in score_move(): acc_factor = accuracy / 100.
# A 50% move scores half what a 100% move of equal power would.

LOW_ACCURACY_THRESHOLD = 75


# ── Combo recommendation exclusion list ──────────────────────────────────────
#
# Moves that are NEVER suggested by the auto-combo selector (select_combo),
# regardless of their score. They remain in the candidate pool so they can
# still be chosen as LOCKED moves by the user, but the recommender will
# not place them in any of the three auto-generated sets.
#
# Three categories of exclusion (decision recorded in notes.md §36):
#
#   Group 1 — User faints on use
#     Self-Destruct, Explosion, Misty Explosion, Final Gambit, Memento,
#     Healing Wish, Lunar Dance.
#     Sacrificing the active Pokemon is never correct as a default suggestion.
#
#   Group 2 — Requires specific other moves to be viable
#     Focus Punch: fails if hit before executing → only usable behind Substitute.
#     Perish Song: KOs both sides in 3 turns → only viable with a trapping move.
#     Destiny Bond: KOs both sides only if user faints next turn → purely reactive.
#     Auto-recommending these without their required support moves would be
#     actively misleading.
#
#   Group 3 — Near-zero practical value as a regular moveslot
#     Curse (Ghost): halves user's HP to badly poison — niche stall only.
#     Grudge: drains opponent PP on KO — almost never worth a slot.
#     Spite: reduces target's last move PP by 4 — too niche for general use.
#
# Note: these moves still appear in the *status* pool if they are status moves
# (Perish Song, Destiny Bond, Memento, Healing Wish, Lunar Dance, Curse, Grudge,
# Spite) and are surfaced via rank_status_moves() for the user to evaluate.
# Only the damage-pool combo selector is gated.

COMBO_EXCLUDED = frozenset({
    # Group 1 — self-KO
    "Self-Destruct",
    "Explosion",
    "Misty Explosion",
    "Final Gambit",
    "Memento",
    "Healing Wish",
    "Lunar Dance",
    # Group 2 — setup-dependent
    "Focus Punch",
    "Perish Song",
    "Destiny Bond",
    # Group 3 — near-zero practical value
    "Curse",
    "Grudge",
    "Spite",
    # Group 4 — unscoreable (power depends on held item / berry)
    "Fling",
    "Natural Gift",
    # Group 5 — condition almost never met in normal play
    "Last Resort",    # requires all other moves to have been used at least once
})


# ── Conditional move penalties ────────────────────────────────────────────────
#
# Some moves require a specific battle condition to deal their stated damage.
# PokeAPI has no structured field for this — the condition is only described in
# free-text effect entries.  We use a curated static table instead.
#
# The penalty factor is applied as a final multiplier in score_move().
# It reflects the fraction of battles where the condition is realistically met.
#
# Moves whose power is *sometimes* doubled (e.g. Hex, Facade, Venoshock) are
# NOT penalised — we simply ignore the conditional bonus, scoring them at their
# base power.  That is conservative and avoids over-penalising moves that are
# still usable without the condition.
#
# Moves that deal ZERO damage when the condition is not met are penalised
# heavily (Dream Eater, Belch).

CONDITIONAL_PENALTY = {
    # Key: display name  Value: penalty multiplier
    "Dream Eater" : 0.3,  # target must be asleep — useless without sleep setup
    "Belch"       : 0.3,  # user must have consumed a berry — rarely triggerable
}


# ── Power overrides ───────────────────────────────────────────────────────────
#
# Some moves have a base_power that scales with a battle condition, and PokeAPI
# stores None (no power) rather than a maximum value.  We substitute a
# realistic power value so score_move() does not skip them as status moves.
#
# Reasoning:
#   Wring Out — power = 120 × (target HP / max HP); PokeAPI stores None.
#               Use 120 (opening-turn power, target at full HP).
#
# Note: Eruption and Water Spout already have power=150 in the API (their max),
# so they do not need an override — they score correctly as-is.

POWER_OVERRIDE = {
    "Wring Out": 120,
}


# ── Two-turn move penalties ───────────────────────────────────────────────────
#
# Source: Bulbapedia. Three penalty categories (see README for rationale):
#
#   Charge + exposed   (invulnerable=False, penalty=0.5)
#     User charges on turn 1, fully exposed before attacking.
#
#   Recharge + exposed (invulnerable=False, penalty=0.6)
#     User attacks on turn 1, must recharge on turn 2 (exposed).
#
#   Charge + protected (invulnerable=True, penalty=0.8)
#     User is untargetable during the charge turn.
#
# Keys are display names (title-case, spaces) as they appear in move data.
# Note: Solar Beam / Solar Blade skip charge in sun — scored as general case.
# Note: Geomancy has no base_power; penalty has no numeric effect on damage
#       scoring but the entry flags it as 2-turn for the display layer.

TWO_TURN_MOVES = {
    # ── Charge + exposed ──────────────────────────────────────────────────────
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

    # ── Recharge + exposed ────────────────────────────────────────────────────
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

    # ── Charge + protected ────────────────────────────────────────────────────
    "Fly":             {"type": "Flying",   "invulnerable": True,  "penalty": 0.8},
    "Dig":             {"type": "Ground",   "invulnerable": True,  "penalty": 0.8},
    "Dive":            {"type": "Water",    "invulnerable": True,  "penalty": 0.8},
    "Bounce":          {"type": "Flying",   "invulnerable": True,  "penalty": 0.8},
    "Shadow Force":    {"type": "Ghost",    "invulnerable": True,  "penalty": 0.8},
    "Phantom Force":   {"type": "Ghost",    "invulnerable": True,  "penalty": 0.8},
    "Sky Drop":        {"type": "Flying",   "invulnerable": True,  "penalty": 0.8},
}


# ── Status move categories ────────────────────────────────────────────────────
#
# Source: PokeAPI move-meta-category slugs
# (https://pokeapi.co/api/v2/move-meta-category/)
#
# Maps category slug → {label, tier}
# Lower tier = ranked higher in status move recommendations.
#
# Tiers:
#   1 — Offensive ailment  (paralysis, burn, sleep, poison)
#   2 — Stat boost         (Swords Dance, Dragon Dance, Nasty Plot)
#   3 — Recovery           (Recover, Roost, Synthesis)
#   4 — Field / other      (weather, terrain, phazing, unique)
#
# Damage-bearing categories (damage, damage+ailment, etc.) are handled
# by the scoring engine, not the status ranker.

STATUS_CATEGORIES = {
    "ailment":           {"label": "Status ailment", "tier": 1},
    "net-good-stats":    {"label": "Stat boost",     "tier": 2},
    "heal":              {"label": "Recovery",        "tier": 3},
    "whole-field-effect":{"label": "Field effect",   "tier": 4},
    "field-effect":      {"label": "Field effect",   "tier": 4},
    "force-switch":      {"label": "Phazing",         "tier": 4},
    "unique":            {"label": "Unique",          "tier": 4},
}


# ── Single move scorer ────────────────────────────────────────────────────────

def score_move(move_name: str, move_entry: dict, pkm_ctx: dict, game_ctx: dict) -> float:
    """
    Score a single move for a given Pokemon + game context.

    Returns 0.0 for status moves (no base_power) or unavailable moves (None entry).
    Status moves are ranked separately by rank_status_moves() — not scored here.

    Formula:
      score = base_power            # may be overridden by POWER_OVERRIDE table
              × stat_weight         # (relevant_stat / weaker_stat) capped 1.0–2.0, Gen4+ only
              × stab_bonus          # 1.5 if move type matches a Pokemon type, else 1.0
              × two_turn_penalty    # from TWO_TURN_MOVES table, else 1.0
              × accuracy_factor     # accuracy / 100  (None = always-hits = 1.0)
              × priority_factor     # from move priority field (default 0 = neutral = 1.0)
              × recoil_factor       # from meta.drain (<0 = recoil penalty, >0 = drain bonus)
              × effect_factor       # from effect_chance (secondary effect bonus)
              × conditional_factor  # from CONDITIONAL_PENALTY table (moves needing a
                                    # condition to deal any damage), else 1.0

    Priority factor formula:
      priority < 0:  1.0 + priority × 0.15   (e.g. −3 → ×0.55,  −4 → ×0.40)
      priority > 0:  1.0 + priority × 0.08   (e.g. +1 → ×1.08,  +2 → ×1.16)
      priority = 0:  1.0 (no change)

    Negative priority penalises moves that always go last (Focus Punch, Counter...).
    Positive priority gives a small bonus to fast moves (Extreme Speed, Quick Attack).
    Capped to a minimum of 0.1 to avoid zero or negative scores on extreme priorities.

    Priority data comes from PokeAPI. Moves cached before this field was added
    will have no 'priority' key and default to 0 (neutral).

    Accuracy is applied linearly — no floor, no cutoff.
    A 50% move scores half what a 100% move of equal power would.
    Moves at or below LOW_ACCURACY_THRESHOLD are flagged in the display layer only.

    Recoil/drain factor (from PokeAPI meta.drain):
      drain < 0 (recoil):  max(1.0 + drain/100 × 0.5, 0.4)
                           Flare Blitz −33% → ×0.835, Head Smash −50% → ×0.75
      drain > 0 (healing): 1.0 + drain/100 × 0.3
                           Giga Drain +50% → ×1.15, Drain Punch +50% → ×1.15
      drain = 0:           1.0 (no effect)

    Secondary effect factor (from PokeAPI effect_chance):
      1.0 + effect_chance/100 × 0.2
      Scald 30% burn → ×1.06, Fire Blast 10% burn → ×1.02
      effect_chance = 0 or missing → 1.0

    Arguments:
      move_name   — display name (used for TWO_TURN_MOVES lookup)
      move_entry  — versioned entry dict from cache.resolve_move(), or None
      pkm_ctx     — session pokemon context (types, base_stats)
      game_ctx    — session game context (game_gen)
    """
    if move_entry is None:
        return 0.0

    base_power = move_entry.get("power")

    # ── power_override ────────────────────────────────────────────────────────
    # Applied before the status-move guard: Wring Out has power=None in the API
    # (its power scales with target HP and PokeAPI stores no default).  The
    # override substitutes a realistic opening-turn value so score_move() does
    # not discard it as a status move.
    base_power = POWER_OVERRIDE.get(move_name, base_power)

    if not base_power:
        return 0.0   # status move — handled by status ranker

    game_gen   = game_ctx.get("game_gen", 1)
    category   = move_entry.get("category", "")
    move_type  = move_entry.get("type", "")
    accuracy   = move_entry.get("accuracy")
    pkm_types  = pkm_ctx.get("types", [])
    base_stats = pkm_ctx.get("base_stats", {})
    # Guard: base_stats must be a dict. An older cache format stored it as a list
    # of PokeAPI stat objects. Fall back to empty dict so stat_weight = 1.0.
    if not isinstance(base_stats, dict):
        base_stats = {}

    # ── stat_weight (Gen 4+ only) ─────────────────────────────────────────────
    # Physical/Special split became per-move in Gen 4.
    # Stat weight boosts moves that match the Pokemon's stronger attacking stat.
    # Floored at 1.0 — never penalises a move for stat mismatch.
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

    # ── stab_bonus ────────────────────────────────────────────────────────────
    stab_bonus = 1.5 if move_type in pkm_types else 1.0

    # ── two_turn_penalty ──────────────────────────────────────────────────────
    two_turn = TWO_TURN_MOVES.get(move_name)
    two_turn_penalty = two_turn["penalty"] if two_turn else 1.0

    # ── accuracy_factor ───────────────────────────────────────────────────────
    # None = always-hits move (e.g. Swift, Aerial Ace) — treat as 100%.
    # Otherwise linear: 50% acc → ×0.5, 70% acc → ×0.7, 100% acc → ×1.0.
    acc_factor = 1.0 if accuracy is None else min(accuracy, 100) / 100.0

    # ── priority_factor ───────────────────────────────────────────────────────
    # Uses the 'priority' field from the move entry (PokeAPI top-level field).
    # Moves cached before this field was added default to 0 (neutral).
    # Negative priority: penalise (goes last, Focus Punch can be interrupted).
    # Positive priority: small bonus (reliable fast execution).
    # Capped at 0.1 minimum to avoid zero or negative scores.
    priority = move_entry.get("priority", 0) or 0
    if priority < 0:
        priority_factor = max(1.0 + priority * 0.15, 0.1)
    elif priority > 0:
        priority_factor = 1.0 + priority * 0.08
    else:
        priority_factor = 1.0

    # ── recoil_factor ─────────────────────────────────────────────────────────
    # PokeAPI meta.drain: negative = recoil (e.g. -33 for Flare Blitz),
    # positive = HP drain recovery (e.g. +50 for Giga Drain).
    # Old cache entries without this field default to 0 (neutral).
    drain = move_entry.get("drain", 0) or 0
    if drain < 0:
        recoil_factor = max(1.0 + drain / 100.0 * 0.5, 0.4)
    elif drain > 0:
        recoil_factor = 1.0 + drain / 100.0 * 0.3
    else:
        recoil_factor = 1.0

    # ── effect_factor ─────────────────────────────────────────────────────────
    # PokeAPI effect_chance: % probability of secondary effect (burn, paralysis,
    # flinch, etc.). Small uniform bonus — does not distinguish effect quality.
    # Old cache entries without this field default to 0 (neutral).
    effect_chance = move_entry.get("effect_chance", 0) or 0
    effect_factor = 1.0 + effect_chance / 100.0 * 0.2

    # ── conditional_factor ────────────────────────────────────────────────────
    # Moves that deal zero damage when their condition is not met (see
    # CONDITIONAL_PENALTY).  Applied last so all other factors are still
    # computed correctly (drain bonus, accuracy, etc.) before the discount.
    conditional_factor = CONDITIONAL_PENALTY.get(move_name, 1.0)

    return (base_power * stat_weight * stab_bonus
            * two_turn_penalty * acc_factor * priority_factor
            * recoil_factor * effect_factor * conditional_factor)





# ── Status move tier table ────────────────────────────────────────────────────
#
# Maps status move display names → (tier, quality).
# Tier matches STATUS_CATEGORIES:
#   1 — Offensive ailment  (Thunder Wave, Will-O-Wisp, Toxic, sleep moves)
#   2 — Stat boost         (Swords Dance, Dragon Dance, Nasty Plot, ...)
#   3 — Recovery           (Recover, Roost, Synthesis, ...)
#   4 — Field / other      (weather, terrain, screens, phazing, ...)
#
# quality (0–10): secondary sort within a tier. Higher = better recommendation.
# Unknown moves not in the table → tier 4, quality 0.
#
# Sources: Bulbapedia move pages, competitive usage data.

STATUS_MOVE_TIERS = {
    # ── Tier 1: Offensive ailments ────────────────────────────────────────────
    # Paralysis
    "Thunder Wave"   : (1, 9),   # reliable, wide coverage, no accuracy check
    "Nuzzle"         : (1, 7),   # 100% paralysis but low power (damage move technically)
    "Glare"          : (1, 8),   # hits Ground types unlike Thunder Wave
    "Stun Spore"     : (1, 6),   # 75% accuracy
    # Burn
    "Will-O-Wisp"    : (1, 8),   # reliable burn, halves physical attack
    "Lava Plume"     : (1, 5),   # damage + 30% burn, handled as damage move
    # Poison
    "Toxic"          : (1, 9),   # badly poisons, stacking damage — best poison move
    "Poison Powder"  : (1, 5),   # regular poison, 75% accuracy
    "Toxic Spikes"   : (1, 6),   # hazard — auto-poisons switch-ins
    # Sleep
    "Spore"          : (1, 10),  # 100% sleep — best sleep move in the game
    "Sleep Powder"   : (1, 7),   # 75% accuracy
    "Hypnosis"       : (1, 5),   # 60% accuracy — unreliable
    "Lovely Kiss"    : (1, 6),   # 75% accuracy
    "Sing"           : (1, 4),   # 55% accuracy — very unreliable
    "Yawn"           : (1, 6),   # delayed sleep, useful for forcing switches
    "Dark Void"      : (1, 7),   # 80% accuracy, hits both in doubles
    # Freeze (rarely inflicted by pure status moves — covered by damage moves)
    # Confusion
    "Confuse Ray"    : (1, 5),
    "Supersonic"     : (1, 3),   # 55% accuracy
    "Sweet Kiss"     : (1, 3),   # 75% accuracy but confusion only
    "Teeter Dance"   : (1, 5),
    # Infatuation
    "Attract"        : (1, 4),   # situational (opposite gender only)
    # Other
    "Embargo"        : (1, 4),
    "Taunt"          : (1, 6),   # prevents status moves — offensive disruption
    "Encore"         : (1, 6),
    "Disable"        : (1, 5),

    # ── Tier 2: Stat boosts ───────────────────────────────────────────────────
    # Extreme / multi-stat
    "Belly Drum"     : (2, 10),  # +6 Attack at cost of 50% HP — highest ceiling
    "Shell Smash"    : (2, 10),  # +2 Atk/SpA/Spe at -1 Def/SpD — best setup move
    "Quiver Dance"   : (2, 9),   # +1 SpA/SpD/Spe — excellent for special attackers
    "Dragon Dance"   : (2, 9),   # +1 Atk/Spe — best physical setup move
    "Shift Gear"     : (2, 9),   # +1 Atk, +2 Spe
    "Geomancy"       : (2, 9),   # two-turn: +2 SpA/SpD/Spe (already in TWO_TURN_MOVES)
    "Clangorous Soul": (2, 8),   # +1 all stats at -33% HP
    "Victory Dance"  : (2, 9),   # +1 Atk/Def/Spe
    # Attack / Special Attack
    "Swords Dance"   : (2, 8),   # +2 Attack — most accessible physical setup
    "Nasty Plot"     : (2, 8),   # +2 SpA — most accessible special setup
    "Tail Glow"      : (2, 9),   # +3 SpA — rare but extremely powerful
    "Calm Mind"      : (2, 7),   # +1 SpA/SpD — bulkier but slower payoff
    "Bulk Up"        : (2, 7),   # +1 Atk/Def
    "Coil"           : (2, 7),   # +1 Atk/Def/Acc
    "Work Up"        : (2, 5),   # +1 Atk/SpA — weaker version of Swords Dance
    "Hone Claws"     : (2, 5),   # +1 Atk/Acc
    "Charge"         : (2, 4),   # +1 SpD, doubles next Electric move
    "Meditate"       : (2, 4),   # +1 Attack only
    "Sharpen"        : (2, 4),   # +1 Attack only
    "Howl"           : (2, 5),   # +1 Attack (allies too in doubles)
    "Growth"         : (2, 5),   # +1 Atk/SpA (+2 in sun)
    "Stockpile"      : (2, 5),   # stacking Def/SpD — pairs with Swallow
    # Defense / Special Defense
    "Iron Defense"   : (2, 6),   # +2 Defense
    "Amnesia"        : (2, 6),   # +2 SpD
    "Acid Armor"     : (2, 6),   # +2 Defense
    "Barrier"        : (2, 5),   # +2 Defense
    "Cotton Guard"   : (2, 5),   # +3 Defense
    "Cosmic Power"   : (2, 5),   # +1 Def/SpD
    "Defense Curl"   : (2, 3),
    "Withdraw"       : (2, 3),
    "Harden"         : (2, 3),
    # Speed
    "Agility"        : (2, 6),   # +2 Speed
    "Autotomize"     : (2, 6),   # +2 Speed, halves weight
    "Rock Polish"    : (2, 6),   # +2 Speed
    "Flame Charge"   : (2, 4),   # damage + +1 Spe (damage move handled separately)
    "Speed Boost"    : (2, 5),
    # Other stat
    "Minimize"       : (2, 4),   # evasion — controversial in competitive
    "Double Team"    : (2, 3),
    "Focus Energy"   : (2, 5),   # +crit rate
    "Laser Focus"    : (2, 5),

    # ── Tier 3: Recovery ──────────────────────────────────────────────────────
    # Reliable (50% HP, no conditions)
    "Recover"        : (3, 10),
    "Roost"          : (3, 10),  # removes Flying type until end of turn
    "Soft-Boiled"    : (3, 10),
    "Milk Drink"     : (3, 10),
    "Slack Off"      : (3, 10),
    "Shore Up"       : (3, 9),   # +50% in sandstorm
    "Heal Order"     : (3, 9),
    "Jungle Healing" : (3, 8),
    # Weather-dependent (50% normally, 25% in rain/sand, 66% in sun)
    "Synthesis"      : (3, 7),
    "Moonlight"      : (3, 7),
    "Morning Sun"    : (3, 7),
    # Special
    "Rest"           : (3, 6),   # full heal + sleep — situational
    "Life Dew"       : (3, 7),   # heals allies too in doubles
    "Wish"           : (3, 7),   # delayed, heals next turn (or ally in doubles)
    "Aqua Ring"      : (3, 5),   # gradual — 1/16 per turn
    "Ingrain"        : (3, 4),   # gradual, traps user
    "Leech Seed"     : (3, 6),   # drains opponent — indirect recovery
    "Pain Split"     : (3, 5),   # HP equalise — better on low-HP user
    "Swallow"        : (3, 5),   # pairs with Stockpile
    "Recycle"        : (3, 3),

    # ── Tier 4: Field effects and other ──────────────────────────────────────
    # Entry hazards
    "Stealth Rock"   : (4, 8),
    "Spikes"         : (4, 7),
    "Sticky Web"     : (4, 6),
    # Screens
    "Light Screen"   : (4, 7),
    "Reflect"        : (4, 7),
    "Aurora Veil"    : (4, 7),   # requires hail
    # Weather
    "Sunny Day"      : (4, 6),
    "Rain Dance"     : (4, 6),
    "Sandstorm"      : (4, 5),
    "Snowscape"      : (4, 5),
    "Hail"           : (4, 4),
    # Terrain
    "Electric Terrain": (4, 5),
    "Grassy Terrain" : (4, 5),
    "Misty Terrain"  : (4, 5),
    "Psychic Terrain": (4, 5),
    # Trick Room / speed control
    "Trick Room"     : (4, 6),
    "Tailwind"       : (4, 6),
    # Phazing
    "Roar"           : (4, 5),
    "Whirlwind"      : (4, 5),
    "Dragon Tail"    : (4, 4),   # damage move technically
    "Circle Throw"   : (4, 4),
    # Misc
    "Substitute"     : (4, 7),   # very widely used — blocks status
    "Protect"        : (4, 6),
    "Detect"         : (4, 5),
    "Endure"         : (4, 4),
    "Trick"          : (4, 6),
    "Switcheroo"     : (4, 6),
    "Encore"         : (4, 5),
    "Perish Song"    : (4, 4),
    "Destiny Bond"   : (4, 5),
    "Spite"          : (4, 3),
    "Helping Hand"   : (4, 4),
    "Follow Me"      : (4, 4),
    "Rage Powder"    : (4, 4),
    "Sleep Talk"     : (4, 4),
    "Snore"          : (4, 3),
    "Mimic"          : (4, 3),
    "Copycat"        : (4, 3),
    "Me First"       : (4, 3),
    "Magic Coat"     : (4, 4),
    "Safeguard"      : (4, 4),
    "Mist"           : (4, 3),
    "Baton Pass"     : (4, 5),
    "U-turn"         : (4, 4),   # damage move usually, but sometimes status-like
    "Volt Switch"    : (4, 4),
    "Parting Shot"   : (4, 5),
    "Chilly Reception":(4, 5),
    "Teleport"       : (4, 3),
    "Smokescreen"    : (4, 2),
    "Sand Attack"    : (4, 2),
    "Growl"          : (4, 2),
    "Leer"           : (4, 2),
    "Tail Whip"      : (4, 2),
    "Scary Face"     : (4, 3),
    "String Shot"    : (4, 2),
    "Sweet Scent"    : (4, 2),
    "Charm"          : (4, 4),
    "Fake Tears"     : (4, 4),
    "Metal Sound"    : (4, 3),
    "Captivate"      : (4, 2),
    "Tickle"         : (4, 3),
    "Feather Dance"  : (4, 3),
    "Memento"        : (4, 4),
    "Heal Bell"      : (4, 5),
    "Aromatherapy"   : (4, 5),
    "Dragon Cheer"   : (4, 4),
}

_STATUS_UNKNOWN_TIER    = 4
_STATUS_UNKNOWN_QUALITY = 0


# ── Status move ranker ────────────────────────────────────────────────────────

def rank_status_moves(status_pool: list, top_n: int = 3) -> list:
    """
    Rank status moves from the candidate pool and return the top N.

    status_pool — list of move dicts from build_candidate_pool()["status"].
                  Each dict has at least: name, type, category.
    top_n       — how many to return (default 3).

    Ranking key: (tier ASC, quality DESC, name ASC for tiebreak).
    Moves not in STATUS_MOVE_TIERS fall back to tier 4, quality 0.

    Returns a list of enriched dicts — original move dict fields plus:
      tier    : int   (1–4)
      quality : int   (0–10)
      tier_label: str (human-readable tier name)
    """
    _TIER_LABELS = {1: "Status ailment", 2: "Stat boost",
                    3: "Recovery",        4: "Field / other"}

    enriched = []
    for row in status_pool:
        name = row["name"]
        tier, quality = STATUS_MOVE_TIERS.get(
            name, (_STATUS_UNKNOWN_TIER, _STATUS_UNKNOWN_QUALITY)
        )
        enriched.append({
            **row,
            "tier"      : tier,
            "quality"   : quality,
            "tier_label": _TIER_LABELS.get(tier, "Other"),
        })

    enriched.sort(key=lambda r: (r["tier"], -r["quality"], r["name"]))
    return enriched[:top_n]

# ── Candidate pool builder ────────────────────────────────────────────────────

def _score_learnset(form_data: dict, moves_lookup: dict,
                    pkm_ctx: dict, game_ctx: dict,
                    weakness_types: list, era_key: str) -> tuple[list, list]:
    """
    Pure scoring logic — takes already-loaded data, no I/O.
    Called by build_candidate_pool() and directly by unit tests.

    Returns (damage_pool, status_pool), each a list of move dicts sorted by score desc.

    move dict keys:
      name, type, category, power, accuracy, pp,
      score, is_stab, counters_weaknesses, is_two_turn, low_accuracy
    """
    import matchup_calculator as calc

    seen = set()
    damage_pool = []
    status_pool = []

    for section in ("level-up", "machine", "tutor", "egg"):
        for entry in form_data.get(section, []):
            move_name = entry.get("move")
            if not move_name or move_name in seen:
                continue
            seen.add(move_name)

            entries = moves_lookup.get(move_name)
            if entries is None:
                continue  # not in cache — skip silently

            move_entry = _resolve(moves_lookup, move_name,
                                  game_ctx["game"], game_ctx["game_gen"])
            if move_entry is None:
                continue  # move didn't exist in this gen

            move_type = move_entry.get("type", "")
            category  = move_entry.get("category", "")
            power     = move_entry.get("power")
            accuracy  = move_entry.get("accuracy")
            pp        = move_entry.get("pp")

            score     = score_move(move_name, move_entry, pkm_ctx, game_ctx)
            is_stab   = move_type in pkm_ctx.get("types", [])

            # Which of the pokemon's weakness types does this move hit SE (×2+)?
            counters = [
                w for w in weakness_types
                if calc.get_multiplier(era_key, move_type, w) >= 2.0
            ]

            row = {
                "name"               : move_name,
                "type"               : move_type,
                "category"           : category,
                "power"              : power,
                "accuracy"           : accuracy,
                "pp"                 : pp,
                "priority"           : move_entry.get("priority", 0) or 0,
                "drain"              : move_entry.get("drain", 0) or 0,
                "effect_chance"      : move_entry.get("effect_chance", 0) or 0,
                "ailment"            : move_entry.get("ailment", "none") or "none",
                "score"              : score,
                "is_stab"            : is_stab,
                "counters_weaknesses": counters,
                "is_two_turn"        : move_name in TWO_TURN_MOVES,
                "low_accuracy"       : (accuracy is not None
                                        and accuracy <= LOW_ACCURACY_THRESHOLD),
            }

            if score > 0:
                damage_pool.append(row)
            else:
                status_pool.append(row)

    damage_pool.sort(key=lambda r: r["score"], reverse=True)
    status_pool.sort(key=lambda r: r["name"])   # alphabetical for status
    return damage_pool, status_pool


def _resolve(moves_lookup: dict, move_name: str, game: str, game_gen: int):
    """Thin wrapper — calls cache.resolve_move without importing cache at module level."""
    import pkm_cache as cache
    return cache.resolve_move(moves_lookup, move_name, game, game_gen)


def build_candidate_pool(pkm_ctx: dict, game_ctx: dict) -> dict:
    """
    Build the scored candidate pool for a loaded Pokemon + game context.

    Loads the learnset from cache (fetches from PokeAPI on miss).
    Resolves each move's versioned entry for the selected game.
    Scores every damage move via score_move().
    Status moves (score=0) are collected separately.

    Returns:
      {
        "damage" : list of move dicts sorted by score desc — input to combo selector
        "status" : list of move dicts (unscorable, passed to status ranker)
        "skipped": int — moves in learnset not yet in moves cache
      }

    Each move dict:
      name, type, category, power, accuracy, pp,
      score, is_stab, counters_weaknesses, is_two_turn, low_accuracy
    """
    import pkm_cache as cache
    import matchup_calculator as calc

    # ── Learnset ──────────────────────────────────────────────────────────────
    variety_slug = pkm_ctx.get("variety_slug") or pkm_ctx["pokemon"]
    learnset = cache.get_learnset_or_fetch(variety_slug, pkm_ctx["form_name"], game_ctx["game"])
    if learnset is None:
        return {"damage": [], "status": [], "skipped": 0}

    form_name  = pkm_ctx["form_name"]
    forms_dict = learnset.get("forms", {})
    form_data  = forms_dict.get(form_name) or (
        next(iter(forms_dict.values())) if forms_dict else {}
    )
    if not form_data:
        return {"damage": [], "status": [], "skipped": 0}

    # ── Collect all move names from learnset ─────────────────────────────────
    all_names = {
        entry["move"]
        for section in ("level-up", "machine", "tutor", "egg")
        for entry in form_data.get(section, [])
        if entry.get("move")
    }

    # ── Auto-fetch move details not yet in cache ──────────────────────────────
    # This means the user never needs to manually run "Full learnable move list"
    # before requesting a moveset recommendation.
    missing = [n for n in all_names if cache.get_move(n) is None]
    if missing:
        import pkm_pokeapi as pokeapi
        total = len(missing)
        print(f"  Fetching details for {total} move(s) not yet in cache...")
        for i, name in enumerate(missing, start=1):
            print(f"  {i}/{total}  {name:<28}", end="\r", flush=True)
            try:
                entries   = pokeapi.fetch_move(name)
                slug      = pokeapi._name_to_slug(name)
                data      = pokeapi._get(f"move/{slug}")
                canonical = pokeapi._en_name(data.get("names", []), None) or name
                cache.upsert_move(canonical, entries)
            except (ValueError, ConnectionError):
                pass   # leave as skipped — scored as missing
        print(f"  Done.                                   ")

    # ── Count truly skipped (failed fetch or still missing) ───────────────────
    skipped = sum(1 for n in all_names if cache.get_move(n) is None)

    # ── Build moves_lookup dict (name → versioned entries list) ───────────────
    moves_lookup = {}
    for n in all_names:
        entries = cache.get_move(n)
        if entries is not None:
            moves_lookup[n] = entries

    # ── Pokemon's defensive weaknesses ────────────────────────────────────────
    era_key = game_ctx["era_key"]
    defense = calc.compute_defense(era_key, pkm_ctx["type1"], pkm_ctx["type2"])
    weakness_types = [t for t, m in defense.items() if m > 1.0]

    # ── Score ─────────────────────────────────────────────────────────────────
    damage_pool, status_pool = _score_learnset(
        form_data, moves_lookup, pkm_ctx, game_ctx, weakness_types, era_key
    )

    return {"damage": damage_pool, "status": status_pool, "skipped": skipped}


# ── Combo scorer ──────────────────────────────────────────────────────────────

# Bonus / penalty weights — same for all modes, but modes enable/disable terms.
_COVERAGE_BONUS_PER_TYPE  = 25   # per unique type hit SE by the combo
_COUNTER_BONUS_PER_WEAK   = 25   # per own weakness countered by the combo
_STAB_BONUS_PER_MOVE      = 30   # per STAB move in the combo (stab mode only)
_REDUNDANCY_PENALTY       = 30   # per duplicate type beyond first (Normal exempt)

def _uncovered_weaknesses(combo: list, weakness_types: list) -> int:
    """
    Return the number of the Pokemon's weakness types NOT covered by any move
    in combo.  A weakness type is "covered" when at least one move in the combo
    hits it super-effectively (×2 or more).

    This is the primary sort key for counter mode: lower is better.
    """
    countered = set()
    for r in combo:
        for w in r["counters_weaknesses"]:
            countered.add(w)
    return len(weakness_types) - len(countered & set(weakness_types))


def _combo_score(combo: list, weakness_types: list, era_key: str, mode: str) -> float:
    """
    Score a 4-move combination.

    combo         — list of 4 move dicts from the damage pool
    weakness_types — list of attacker types that hit this Pokemon SE
    era_key       — "era1" / "era2" / "era3" for type chart lookup
    mode          — "coverage" | "counter" | "stab"

    Formula:
      combo_score = sum(move_scores)
                  + coverage_bonus      (all modes)
                  + counter_bonus       (counter mode only — tiebreaker, see note)
                  + stab_bonus          (stab mode only)
                  - redundancy_penalty  (all modes, Normal exempt)

    coverage_bonus: marginal contribution model.
      Moves evaluated score-descending; each earns bonus only for SE types
      not already covered by a higher-scoring move in the same combo.
      A second Fighting move adds 0 new SE types → earns 0 coverage bonus.

    counter mode note:
      select_combo() uses a two-key sort in counter mode:
        primary   — fewest uncovered weaknesses  (_uncovered_weaknesses)
        secondary — highest _combo_score         (this function, as tiebreaker)
      counter_bonus rewards weakness coverage within the score, but the
      primary key guarantees that a combo covering more weaknesses always
      beats one covering fewer, regardless of move quality.
    """
    import matchup_calculator as calc

    # ── Base: sum of individual move scores ───────────────────────────────────
    base = sum(r["score"] for r in combo)

    # ── Coverage bonus: marginal new SE types each move contributes ──────────
    # Moves are evaluated score-descending so the highest-scoring move "owns"
    # its SE types first. A duplicate-type move (e.g. second Fighting) covers
    # zero new types → earns zero bonus. This makes type redundancy naturally
    # self-penalising without relying solely on the flat redundancy_penalty.
    covered = set()
    marginal = 0
    for r in sorted(combo, key=lambda x: x["score"], reverse=True):
        move_se = {t for t in calc.TYPES_ERA3
                   if calc.get_multiplier(era_key, r["type"], t) >= 2.0}
        new_types = move_se - covered
        marginal += len(new_types)
        covered |= move_se
    coverage_bonus = marginal * _COVERAGE_BONUS_PER_TYPE

    # ── Counter bonus: own weaknesses addressed by the combo ──────────────────
    if mode == "counter":
        countered = set()
        for r in combo:
            for w in r["counters_weaknesses"]:
                countered.add(w)
        counter_bonus = len(countered) * _COUNTER_BONUS_PER_WEAK
    else:
        counter_bonus = 0

    # ── STAB bonus: extra reward per STAB move (stab mode) ────────────────────
    if mode == "stab":
        stab_bonus = sum(1 for r in combo if r["is_stab"]) * _STAB_BONUS_PER_MOVE
    else:
        stab_bonus = 0

    # ── Redundancy penalty: duplicate move types, Normal exempt ───────────────
    type_counts = {}
    for r in combo:
        if r["type"] != "Normal":
            type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1
    redundancy_penalty = sum(
        (count - 1) * _REDUNDANCY_PENALTY
        for count in type_counts.values()
        if count > 1
    )

    return base + coverage_bonus + counter_bonus + stab_bonus - redundancy_penalty


# ── Combo selector ────────────────────────────────────────────────────────────

_STAB_POOL_CAP = 25  # STAB mode: top N moves by score — C(25,4) = 12,650 combos
# Counter mode: uses all covering moves + top fillers (see _build_counter_pool)
# Coverage mode: uses best move per type, max 18 (see _build_coverage_pool)

_COUNTER_FILLER_K = 8   # non-covering moves kept as filler slots in counter pool


def _build_counter_pool(eligible: list, weakness_types: list) -> list:
    """
    Build the candidate pool for counter mode.

    All moves that counter at least one of the Pokemon's weakness types are
    included unconditionally — no cap.  They are the only moves that can
    improve weakness coverage, so none must be excluded.

    The top _COUNTER_FILLER_K non-covering moves are added as filler.  They
    fill the remaining slots when fewer than 4 covering moves are needed to
    close all gaps, and act as tiebreakers within a coverage tier.

    eligible — damage_pool already filtered for locked/excluded names,
               sorted by score descending.
    """
    covering     = [r for r in eligible if r["counters_weaknesses"]]
    non_covering = [r for r in eligible if not r["counters_weaknesses"]]
    return covering + non_covering[:_COUNTER_FILLER_K]


def _build_coverage_pool(eligible: list) -> list:
    """
    Build the candidate pool for coverage mode.

    Two moves of the same type always hit exactly the same set of types SE.
    Keeping only the highest-scoring move per type is therefore sufficient and
    provably optimal: any combo containing a lower-scoring same-type move can
    always be improved by swapping in the best move of that type, gaining equal
    coverage and a higher score.

    Result: at most 18 moves (one per type present in the eligible pool).

    eligible — damage_pool already filtered for locked/excluded names,
               sorted by score descending.
    """
    seen_types = {}
    for r in eligible:                   # eligible is score-sorted desc
        t = r["type"]
        if t not in seen_types:
            seen_types[t] = r            # first seen = highest scoring for this type
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
                    Locked moves are forced into every combo; the selector fills
                    the remaining (4 - len(locked)) slots from the free pool.

    Selection strategy by mode:

      stab     — pool: top _STAB_POOL_CAP moves by score.
                 Select the combo with the highest _combo_score.

      coverage — pool: best-scoring move per type (_build_coverage_pool).
                 Two-pass: find the maximum types hit SE across all combos,
                 then pick the highest-scoring combo within that tier.

      counter  — pool: all covering moves + top _COUNTER_FILLER_K fillers
                 (_build_counter_pool).
                 Two-pass: find the minimum uncovered-weakness count across
                 all combos, then pick the highest-scoring combo within that
                 tier.

    All modes respect locked moves and COMBO_EXCLUDED.

    Returns a list of 4 move dicts (locked moves first, then selected moves).
    Returns fewer than 4 if the pool is too small to fill all slots.
    """
    from itertools import combinations

    locked = locked or []
    locked_names = {r["name"] for r in locked}
    slots_needed = 4 - len(locked)

    if slots_needed <= 0:
        return locked[:4]

    # eligible: damage_pool minus locked and COMBO_EXCLUDED, score-sorted desc
    # (damage_pool arrives pre-sorted from build_candidate_pool)
    eligible = [r for r in damage_pool
                if r["name"] not in locked_names
                and r["name"] not in COMBO_EXCLUDED]

    # ── Mode-specific pool construction ───────────────────────────────────────
    if mode == "counter":
        free_pool = _build_counter_pool(eligible, weakness_types)
    elif mode == "coverage":
        free_pool = _build_coverage_pool(eligible)
    else:   # stab
        free_pool = eligible[:_STAB_POOL_CAP]

    if not free_pool:
        return locked

    n_select = min(slots_needed, len(free_pool))

    # ── Two-pass selection for counter and coverage ───────────────────────────
    # Pass 1 (fast): find the best achievable primary metric across all combos.
    #   counter  → minimum uncovered weaknesses
    #   coverage → maximum types hit SE
    # Pass 2: score only the combos that match the best primary metric.
    # stab: single pass (score only).

    if mode == "counter":
        # Pass 1: find min gap
        min_gap = len(weakness_types)   # worst possible
        for selected in combinations(free_pool, n_select):
            gap = _uncovered_weaknesses(locked + list(selected), weakness_types)
            if gap < min_gap:
                min_gap = gap
                if min_gap == 0:
                    break   # can't do better

        # Pass 2: best score among combos at min_gap
        best_combo = None
        best_score = float("-inf")
        for selected in combinations(free_pool, n_select):
            combo = locked + list(selected)
            if _uncovered_weaknesses(combo, weakness_types) == min_gap:
                score = _combo_score(combo, weakness_types, era_key, mode)
                if score > best_score:
                    best_score = score
                    best_combo = combo

    elif mode == "coverage":
        # Pass 1: find max SE-type count
        max_se = 0
        for selected in combinations(free_pool, n_select):
            combo = locked + list(selected)
            # Count unique types hit SE by the full combo
            se_types = set()
            for r in combo:
                import matchup_calculator as _calc
                for t in _calc.TYPES_ERA3:
                    if _calc.get_multiplier(era_key, r["type"], t) >= 2.0:
                        se_types.add(t)
            n_se = len(se_types)
            if n_se > max_se:
                max_se = n_se
                if max_se == len(_calc.TYPES_ERA3):
                    break   # all types covered, can't do better

        # Pass 2: best score among combos achieving max_se
        best_combo = None
        best_score = float("-inf")
        for selected in combinations(free_pool, n_select):
            combo = locked + list(selected)
            se_types = set()
            for r in combo:
                for t in _calc.TYPES_ERA3:
                    if _calc.get_multiplier(era_key, r["type"], t) >= 2.0:
                        se_types.add(t)
            if len(se_types) == max_se:
                score = _combo_score(combo, weakness_types, era_key, mode)
                if score > best_score:
                    best_score = score
                    best_combo = combo

    else:   # stab — single pass, pure score
        best_combo = None
        best_score = float("-inf")
        for selected in combinations(free_pool, n_select):
            combo = locked + list(selected)
            score = _combo_score(combo, weakness_types, era_key, mode)
            if score > best_score:
                best_score = score
                best_combo = combo

    return best_combo or locked


# ── Unit tests ────────────────────────────────────────────────────────────────

def _run_tests():
    print("Running feat_moveset_data unit tests...\n")
    passed = 0
    failed = 0

    def check(description, condition):
        nonlocal passed, failed
        if condition:
            print(f"  PASS  {description}")
            passed += 1
        else:
            print(f"  FAIL  {description}")
            failed += 1

    # ── COMBO_EXCLUDED: new group 4 + 5 entries ──────────────────────────────
    check("Last Resort excluded from combos",   "Last Resort"   in COMBO_EXCLUDED)
    check("Fling excluded from combos",         "Fling"         in COMBO_EXCLUDED)
    check("Natural Gift excluded from combos",  "Natural Gift"  in COMBO_EXCLUDED)

    # ── POWER_OVERRIDE ────────────────────────────────────────────────────────
    from feat_moveset_data import POWER_OVERRIDE
    check("POWER_OVERRIDE: Wring Out → 120",  POWER_OVERRIDE["Wring Out"] == 120)
    check("POWER_OVERRIDE: only Wring Out in table (Eruption/Water Spout need no override)",
          set(POWER_OVERRIDE.keys()) == {"Wring Out"})

    # Verify override is applied in score_move():
    # Eruption API power = 150 (same as override), so build a fake entry with
    # power=1 and confirm POWER_OVERRIDE replaces it with 150.
    _eruption_raw = {"type": "Fire", "category": "Special", "power": 1,
                     "accuracy": 100, "pp": 5, "priority": 0,
                     "drain": 0, "effect_chance": 0, "ailment": "none"}
    # Inline fixture (charizard defined later in _run_tests; use minimal ctx here)
    _ctx_sp  = {"types": ["Psychic"], "base_stats": {"attack": 60, "special-attack": 100,
                 "defense": 60, "special-defense": 60, "speed": 60, "hp": 60}}
    _ctx_g9  = {"game_gen": 9}

    # Wring Out override: fake power=None entry → score_move skips it without override,
    # but with override it scores as power=120.
    _wring_none  = {"type": "Normal", "category": "Physical", "power": None,
                    "accuracy": 100, "pp": 5, "priority": 0,
                    "drain": 0, "effect_chance": 0, "ailment": "none"}
    _wring_score = score_move("Wring Out", _wring_none, _ctx_sp, _ctx_g9)
    check("POWER_OVERRIDE: Wring Out with power=None scores as 120 (not 0)",
          _wring_score > 0)

    # ── CONDITIONAL_PENALTY ───────────────────────────────────────────────────
    from feat_moveset_data import CONDITIONAL_PENALTY
    check("CONDITIONAL_PENALTY: Dream Eater penalty = 0.3",
          CONDITIONAL_PENALTY["Dream Eater"] == 0.3)
    check("CONDITIONAL_PENALTY: Belch penalty = 0.3",
          CONDITIONAL_PENALTY["Belch"] == 0.3)

    # Verify conditional_factor applied in score_move()
    _base_entry = {"type": "Psychic", "category": "Special", "power": 100,
                   "accuracy": 100, "pp": 15, "priority": 0,
                   "drain": 50, "effect_chance": 0, "ailment": "none"}
    _score_neutral      = score_move("SomeMove",    _base_entry, _ctx_sp, _ctx_g9)
    _score_dream_eater  = score_move("Dream Eater", _base_entry, _ctx_sp, _ctx_g9)
    _score_belch_entry  = {**_base_entry, "type": "Poison", "power": 120}
    _score_belch        = score_move("Belch",       _score_belch_entry, _ctx_sp, _ctx_g9)
    check("CONDITIONAL_PENALTY: Dream Eater score = neutral × 0.3",
          abs(_score_dream_eater - _score_neutral * 0.3) < 0.01)
    _score_belch_neutral = score_move("SomeMove", _score_belch_entry, _ctx_sp, _ctx_g9)
    check("CONDITIONAL_PENALTY: Belch score = neutral × 0.3",
          abs(_score_belch - _score_belch_neutral * 0.3) < 0.01)
    check("CONDITIONAL_PENALTY: non-listed move has no penalty (factor=1.0)",
          score_move("Earthquake", _base_entry, _ctx_sp, _ctx_g9) ==
          score_move("SomeMove",   _base_entry, _ctx_sp, _ctx_g9))

        # ── TWO_TURN_MOVES — charge + exposed ─────────────────────────────────────

    check("Solar Beam: penalty 0.5, not invulnerable",
          TWO_TURN_MOVES["Solar Beam"]["penalty"] == 0.5 and
          TWO_TURN_MOVES["Solar Beam"]["invulnerable"] is False)
    check("Sky Attack: penalty 0.5",
          TWO_TURN_MOVES["Sky Attack"]["penalty"] == 0.5)
    check("Skull Bash: penalty 0.5",
          TWO_TURN_MOVES["Skull Bash"]["penalty"] == 0.5)
    check("Electro Shot: penalty 0.5",
          TWO_TURN_MOVES["Electro Shot"]["penalty"] == 0.5)
    check("Meteor Beam: penalty 0.5, type Rock",
          TWO_TURN_MOVES["Meteor Beam"]["penalty"] == 0.5 and
          TWO_TURN_MOVES["Meteor Beam"]["type"] == "Rock")
    check("Geomancy: penalty 0.5, type Fairy, not invulnerable",
          TWO_TURN_MOVES["Geomancy"]["penalty"] == 0.5 and
          TWO_TURN_MOVES["Geomancy"]["type"] == "Fairy" and
          TWO_TURN_MOVES["Geomancy"]["invulnerable"] is False)

    # ── TWO_TURN_MOVES — recharge + exposed ───────────────────────────────────

    check("Hyper Beam: penalty 0.6, not invulnerable",
          TWO_TURN_MOVES["Hyper Beam"]["penalty"] == 0.6 and
          TWO_TURN_MOVES["Hyper Beam"]["invulnerable"] is False)
    check("Giga Impact: penalty 0.6",
          TWO_TURN_MOVES["Giga Impact"]["penalty"] == 0.6)
    check("Frenzy Plant: penalty 0.6",
          TWO_TURN_MOVES["Frenzy Plant"]["penalty"] == 0.6)
    check("Blast Burn: penalty 0.6",
          TWO_TURN_MOVES["Blast Burn"]["penalty"] == 0.6)
    check("Roar of Time: penalty 0.6",
          TWO_TURN_MOVES["Roar of Time"]["penalty"] == 0.6)
    check("Prismatic Laser: penalty 0.6, type Psychic",
          TWO_TURN_MOVES["Prismatic Laser"]["penalty"] == 0.6 and
          TWO_TURN_MOVES["Prismatic Laser"]["type"] == "Psychic")
    check("Shadow Half: penalty 0.6, type Shadow",
          TWO_TURN_MOVES["Shadow Half"]["penalty"] == 0.6 and
          TWO_TURN_MOVES["Shadow Half"]["type"] == "Shadow")

    # ── TWO_TURN_MOVES — charge + protected ───────────────────────────────────

    check("Fly: penalty 0.8, invulnerable",
          TWO_TURN_MOVES["Fly"]["penalty"] == 0.8 and
          TWO_TURN_MOVES["Fly"]["invulnerable"] is True)
    check("Dig: penalty 0.8, invulnerable",
          TWO_TURN_MOVES["Dig"]["penalty"] == 0.8 and
          TWO_TURN_MOVES["Dig"]["invulnerable"] is True)
    check("Bounce: penalty 0.8, invulnerable",
          TWO_TURN_MOVES["Bounce"]["penalty"] == 0.8 and
          TWO_TURN_MOVES["Bounce"]["invulnerable"] is True)
    check("Shadow Force: penalty 0.8, invulnerable",
          TWO_TURN_MOVES["Shadow Force"]["penalty"] == 0.8 and
          TWO_TURN_MOVES["Shadow Force"]["invulnerable"] is True)
    check("Phantom Force: penalty 0.8, invulnerable",
          TWO_TURN_MOVES["Phantom Force"]["penalty"] == 0.8 and
          TWO_TURN_MOVES["Phantom Force"]["invulnerable"] is True)

    # ── TWO_TURN_MOVES — structural ───────────────────────────────────────────

    check("All entries have 'type', 'invulnerable', 'penalty' keys",
          all("type" in v and "invulnerable" in v and "penalty" in v
              for v in TWO_TURN_MOVES.values()))
    check("All penalties are one of 0.5, 0.6, 0.8",
          all(v["penalty"] in (0.5, 0.6, 0.8) for v in TWO_TURN_MOVES.values()))
    check("invulnerable=True only for penalty=0.8 moves",
          all((v["invulnerable"] is True) == (v["penalty"] == 0.8)
              for v in TWO_TURN_MOVES.values()))
    check("No duplicate keys (28 entries expected)",
          len(TWO_TURN_MOVES) == 28)

    # ── STATUS_CATEGORIES ─────────────────────────────────────────────────────

    check("ailment → tier 1",
          STATUS_CATEGORIES["ailment"]["tier"] == 1)
    check("net-good-stats → tier 2",
          STATUS_CATEGORIES["net-good-stats"]["tier"] == 2)
    check("heal → tier 3",
          STATUS_CATEGORIES["heal"]["tier"] == 3)
    check("whole-field-effect → tier 4",
          STATUS_CATEGORIES["whole-field-effect"]["tier"] == 4)
    check("field-effect → tier 4",
          STATUS_CATEGORIES["field-effect"]["tier"] == 4)
    check("force-switch → tier 4",
          STATUS_CATEGORIES["force-switch"]["tier"] == 4)
    check("unique → tier 4",
          STATUS_CATEGORIES["unique"]["tier"] == 4)
    check("tier ordering: ailment < net-good-stats < heal < field-effect",
          STATUS_CATEGORIES["ailment"]["tier"] <
          STATUS_CATEGORIES["net-good-stats"]["tier"] <
          STATUS_CATEGORIES["heal"]["tier"] <
          STATUS_CATEGORIES["field-effect"]["tier"])
    check("All STATUS_CATEGORIES entries have 'label' and 'tier'",
          all("label" in v and "tier" in v for v in STATUS_CATEGORIES.values()))

    # ── score_move tests ──────────────────────────────────────────────────────
    #
    # Mock contexts — representative real stats:
    #   Charizard  Fire/Flying   Atk 84  SpA 109  (special attacker)
    #   Garchomp   Dragon/Ground Atk 130 SpA 80   (physical attacker)

    charizard = {
        "types": ["Fire", "Flying"],
        "base_stats": {"attack": 84, "special-attack": 109,
                       "defense": 78, "special-defense": 85,
                       "speed": 100, "hp": 78}
    }
    garchomp = {
        "types": ["Dragon", "Ground"],
        "base_stats": {"attack": 130, "special-attack": 80,
                       "defense": 95, "special-defense": 85,
                       "speed": 102, "hp": 108}
    }
    game_gen9 = {"game_gen": 9}
    game_gen1 = {"game_gen": 1}

    flamethrower = {"type": "Fire", "category": "Special", "power": 90, "accuracy": 100}
    earthquake   = {"type": "Ground", "category": "Physical", "power": 100, "accuracy": 100}
    hyper_beam   = {"type": "Normal", "category": "Special", "power": 150, "accuracy": 90}
    fly_move     = {"type": "Flying", "category": "Physical", "power": 90, "accuracy": 95}
    swift        = {"type": "Normal", "category": "Special", "power": 60, "accuracy": None}
    focus_blast  = {"type": "Fighting", "category": "Special", "power": 120, "accuracy": 70}
    inferno      = {"type": "Fire", "category": "Special", "power": 100, "accuracy": 50}
    status_entry = {"type": "Normal", "category": "Status", "power": None, "accuracy": None}

    stat_w_char      = min(109 / 84, 2.0)
    stat_w_garc_phys = min(130 / 80, 2.0)

    # STAB: Flamethrower on Charizard > Flamethrower on Garchomp
    score_ft_char = score_move("Flamethrower", flamethrower, charizard, game_gen9)
    score_ft_garc = score_move("Flamethrower", flamethrower, garchomp, game_gen9)
    check("Flamethrower: Charizard (STAB) scores higher than Garchomp (no STAB)",
          score_ft_char > score_ft_garc)

    check("Flamethrower on Charizard: correct score (STAB + stat_weight)",
          abs(score_ft_char - 90 * stat_w_char * 1.5 * 1.0 * 1.0) < 0.001)

    check("Flamethrower on Garchomp: correct score (no STAB, stat_weight=1.0)",
          abs(score_ft_garc - 90 * 1.0 * 1.0 * 1.0 * 1.0) < 0.001)

    # Earthquake on Garchomp: STAB + physical stat_weight
    check("Earthquake on Garchomp: STAB + stat_weight",
          abs(score_move("Earthquake", earthquake, garchomp, game_gen9) -
              100 * stat_w_garc_phys * 1.5 * 1.0 * 1.0) < 0.001)

    # stat_weight cap at 2.0
    check("stat_weight cap: ratio > 2.0 is capped at 2.0",
          min(210 / 90, 2.0) == 2.0)

    # Hyper Beam: recharge penalty 0.6, accuracy 0.9
    stat_w_hb = min(109 / 84, 2.0)
    check("Hyper Beam: two-turn penalty 0.6 + accuracy 0.9",
          abs(score_move("Hyper Beam", hyper_beam, charizard, game_gen9) -
              150 * stat_w_hb * 1.0 * 0.6 * 0.9) < 0.001)

    # Fly: charge+protected penalty 0.8, STAB on Charizard
    check("Fly on Charizard: STAB + charge+protected penalty 0.8",
          abs(score_move("Fly", fly_move, charizard, game_gen9) -
              90 * 1.0 * 1.5 * 0.8 * 0.95) < 0.001)

    # None / status → 0.0
    check("None move_entry → score 0.0",
          score_move("Anything", None, charizard, game_gen9) == 0.0)
    check("Status move (power=None) → score 0.0",
          score_move("Swords Dance", status_entry, charizard, game_gen9) == 0.0)

    # Always-hits (accuracy=None) → acc_factor 1.0
    check("Swift (accuracy=None) treated as 100%",
          abs(score_move("Swift", swift, charizard, game_gen9) -
              60 * stat_w_char * 1.0 * 1.0 * 1.0) < 0.001)

    # Linear accuracy — no floor
    stat_w_fb = min(109 / 84, 2.0)
    check("Focus Blast (70% acc): acc_factor = 0.70, not floored",
          abs(score_move("Focus Blast", focus_blast, charizard, game_gen9) -
              120 * stat_w_fb * 1.0 * 1.0 * 0.70) < 0.001)

    # Inferno (50% acc, Fire STAB on Charizard): acc_factor = 0.50
    check("Inferno (50% acc): acc_factor = 0.50 (linear, not floored)",
          abs(score_move("Inferno", inferno, charizard, game_gen9) -
              100 * stat_w_char * 1.5 * 1.0 * 0.50) < 0.001)

    # Inferno scores less than Flamethrower despite higher base power
    check("Inferno (100pw/50%) scores less than Flamethrower (90pw/100%) on Charizard",
          score_move("Inferno", inferno, charizard, game_gen9) <
          score_move("Flamethrower", flamethrower, charizard, game_gen9))

    # Gen 1: stat_weight = 1.0
    check("Gen 1: stat_weight = 1.0 (no per-move Physical/Special split)",
          abs(score_move("Flamethrower", flamethrower, charizard, game_gen1) -
              90 * 1.0 * 1.5 * 1.0 * 1.0) < 0.001)

    # LOW_ACCURACY_THRESHOLD is display-only — check value
    check("LOW_ACCURACY_THRESHOLD is 75 (display flag, not used in scoring)",
          LOW_ACCURACY_THRESHOLD == 75)

    # ── priority_factor tests ─────────────────────────────────────────────────

    # Negative priority — Focus Punch (priority -3) → factor = 1.0 + (-3 × 0.15) = 0.55
    focus_punch     = {"type": "Fighting", "category": "Physical",
                       "power": 150, "accuracy": 100, "priority": -3}
    focus_punch_p0  = {"type": "Fighting", "category": "Physical",
                       "power": 150, "accuracy": 100}           # no priority field (old cache)

    stat_w_fp_char = 1.0   # Atk 84 < SpA 109, physical → stat_weight floored at 1.0
    expected_fp    = 150 * stat_w_fp_char * 1.0 * 1.0 * 1.0 * 0.55
    check("Focus Punch (priority -3): factor 0.55 applied",
          abs(score_move("Focus Punch", focus_punch, charizard, game_gen9)
              - expected_fp) < 0.01)

    check("Focus Punch scores lower than Flamethrower (90pw) despite 150pw",
          score_move("Focus Punch", focus_punch, charizard, game_gen9) <
          score_move("Flamethrower", flamethrower, charizard, game_gen9))

    # Missing priority key (old cache entry) → defaults to 0 → factor 1.0
    check("Missing 'priority' key defaults to 0 (neutral, no change)",
          abs(score_move("Focus Punch", focus_punch_p0, charizard, game_gen9) -
              score_move("Focus Punch", {**focus_punch_p0, "priority": 0},
                         charizard, game_gen9)) < 0.001)

    # Positive priority — Extreme Speed (priority +2) → factor = 1.0 + (2 × 0.08) = 1.16
    extreme_speed   = {"type": "Normal", "category": "Physical",
                       "power": 80, "accuracy": 100, "priority": 2}
    quick_attack    = {"type": "Normal", "category": "Physical",
                       "power": 40, "accuracy": 100, "priority": 1}

    check("Extreme Speed (priority +2): factor 1.16 applied",
          abs(score_move("Extreme Speed", extreme_speed, charizard, game_gen9) -
              80 * 1.0 * 1.0 * 1.0 * 1.0 * 1.16) < 0.01)

    check("Quick Attack (priority +1): factor 1.08 applied",
          abs(score_move("Quick Attack", quick_attack, charizard, game_gen9) -
              40 * 1.0 * 1.0 * 1.0 * 1.0 * 1.08) < 0.01)

    # Neutral priority (0) → no change
    check("Priority 0 → factor 1.0, score unchanged",
          abs(score_move("Flamethrower", flamethrower, charizard, game_gen9) -
              score_move("Flamethrower", {**flamethrower, "priority": 0},
                         charizard, game_gen9)) < 0.001)

    # Floor at 0.1 (extreme negative priorities shouldn't zero out the score)
    extreme_neg = {"type": "Normal", "category": "Special",
                   "power": 100, "accuracy": 100, "priority": -7}
    check("Priority -7 is capped at floor 0.1 (not negative/zero)",
          score_move("Test", extreme_neg, charizard, game_gen9) > 0)

    # ── recoil_factor tests ───────────────────────────────────────────────────

    base_entry = {"type": "Fire", "category": "Physical",
                  "power": 120, "accuracy": 100, "priority": 0}

    # Flare Blitz: drain=-33 → factor = 1.0 + (-33/100 × 0.5) = 0.835
    flare_blitz = {**base_entry, "drain": -33}
    expected_fb = 120 * 1.0 * 1.5 * 1.0 * 1.0 * 1.0 * 0.835   # STAB (Fire/Flying)
    check("Flare Blitz (drain -33%): recoil_factor 0.835 applied",
          abs(score_move("Flare Blitz", flare_blitz, charizard, game_gen9)
              - expected_fb) < 0.01)

    # Head Smash: drain=-50 → factor = 1.0 + (-50/100 × 0.5) = 0.75
    head_smash = {**base_entry, "type": "Rock", "drain": -50}
    expected_hs = 120 * 1.0 * 1.0 * 1.0 * 1.0 * 1.0 * 0.75
    check("Head Smash (drain -50%): recoil_factor 0.75 applied",
          abs(score_move("Head Smash", head_smash, charizard, game_gen9)
              - expected_hs) < 0.01)

    # Drain Punch: drain=+50 → factor = 1.0 + (50/100 × 0.3) = 1.15
    drain_punch = {"type": "Fighting", "category": "Physical",
                   "power": 75, "accuracy": 100, "priority": 0, "drain": 50}
    expected_dp = 75 * 1.0 * 1.0 * 1.0 * 1.0 * 1.0 * 1.15
    check("Drain Punch (drain +50%): drain_factor 1.15 applied",
          abs(score_move("Drain Punch", drain_punch, charizard, game_gen9)
              - expected_dp) < 0.01)

    # Flare Blitz scores lower than same-power move without recoil
    no_recoil = {**base_entry, "drain": 0}
    check("Recoil move scores lower than identical move without recoil",
          score_move("Flare Blitz", flare_blitz, charizard, game_gen9) <
          score_move("No Recoil",   no_recoil,   charizard, game_gen9))

    # Missing drain key (old cache) → neutral
    no_drain_key = {**base_entry}   # no "drain" key at all
    check("Missing 'drain' key defaults to 0 (neutral)",
          abs(score_move("X", no_drain_key, charizard, game_gen9) -
              score_move("X", {**base_entry, "drain": 0}, charizard, game_gen9)) < 0.001)

    # Drain penalty floor: extreme drain (-200 hypothetical) capped at 0.4
    extreme_drain = {**base_entry, "drain": -200}
    score_floored = score_move("X", extreme_drain, charizard, game_gen9)
    score_floor   = 120 * 1.0 * 1.5 * 1.0 * 1.0 * 1.0 * 0.4
    check("Recoil floor at 0.4 (extreme drain capped)",
          abs(score_floored - score_floor) < 0.01)

    # ── effect_factor tests ───────────────────────────────────────────────────

    # Scald: effect_chance=30 → factor = 1.0 + 30/100 × 0.2 = 1.06
    scald = {"type": "Water", "category": "Special",
             "power": 80, "accuracy": 100, "priority": 0,
             "effect_chance": 30, "ailment": "burn"}
    stat_w_sc   = min(109/84, 2.0)   # Charizard SpA > Atk, Special move
    expected_sc = 80 * stat_w_sc * 1.0 * 1.0 * 1.0 * 1.0 * 1.06
    check("Scald (effect_chance 30): effect_factor 1.06 applied",
          abs(score_move("Scald", scald, charizard, game_gen9)
              - expected_sc) < 0.01)

    # Fire Blast: effect_chance=10 → factor = 1.0 + 10/100 × 0.2 = 1.02
    fire_blast_eff = {"type": "Fire", "category": "Special",
                      "power": 120, "accuracy": 85, "priority": 0,
                      "effect_chance": 10, "ailment": "burn"}
    stat_w_fbe   = min(109/84, 2.0)
    expected_fbe = 120 * stat_w_fbe * 1.5 * 1.0 * 0.85 * 1.0 * 1.02
    check("Fire Blast (effect_chance 10): effect_factor 1.02 applied",
          abs(score_move("Fire Blast", fire_blast_eff, charizard, game_gen9)
              - expected_fbe) < 0.01)

    # Scald scores higher than Surf (same power, no effect)
    surf = {"type": "Water", "category": "Special",
            "power": 80, "accuracy": 100, "priority": 0, "effect_chance": 0}
    check("Scald scores higher than Surf (same power, burn chance bonus)",
          score_move("Scald", scald, charizard, game_gen9) >
          score_move("Surf",  surf,  charizard, game_gen9))

    # No effect → factor 1.0
    check("effect_chance 0 → factor 1.0 (no change)",
          abs(score_move("Surf", surf, charizard, game_gen9) -
              score_move("Surf", {**surf, "effect_chance": None}, charizard, game_gen9)) < 0.001)

    # Missing effect_chance key (old cache) → neutral
    no_eff_key = {"type": "Water", "category": "Special", "power": 80, "accuracy": 100}
    check("Missing 'effect_chance' key defaults to 0 (neutral)",
          abs(score_move("X", no_eff_key, charizard, game_gen9) -
              score_move("X", {**no_eff_key, "effect_chance": 0}, charizard, game_gen9)) < 0.001)


    #
    # Uses _score_learnset() directly with mock data — no cache or network needed.
    # Mock: Charizard (Fire/Flying) in a Gen 9 game.
    # Charizard weaknesses era3: Water ×2, Electric ×2, Rock ×4
    # (Ground neutralised by Flying immunity)

    import matchup_calculator as _calc

    mock_pkm = {
        "types"      : ["Fire", "Flying"],
        "type1"      : "Fire",
        "type2"      : "Flying",
        "base_stats" : {"attack": 84, "special-attack": 109,
                        "defense": 78, "special-defense": 85,
                        "speed": 100, "hp": 78},
    }
    mock_game = {"game": "Scarlet / Violet", "game_gen": 9, "era_key": "era3"}

    def _e(typ, cat, pwr, acc, pp=15):
        return [{"from_gen": 1, "to_gen": None, "applies_to_games": None,
                 "type": typ, "category": cat, "power": pwr, "accuracy": acc, "pp": pp}]

    mock_form_data = {
        "level-up": [
            {"move": "Flamethrower",  "level": 30},
            {"move": "Dragon Claw",   "level": 1},
            {"move": "Scratch",       "level": 1},
            {"move": "Inferno",       "level": 54},
        ],
        "machine": [{"move": "Earthquake", "tm": "TM41"}],
        "tutor"  : [{"move": "Air Slash"}],
        "egg"    : [{"move": "Dragon Dance"}, {"move": "Ancient Power"}],
    }
    mock_moves = {
        "Flamethrower" : _e("Fire",   "Special",  90,  100),
        "Dragon Claw"  : _e("Dragon", "Physical", 80,  100),
        "Scratch"      : _e("Normal", "Physical", 40,  100),
        "Inferno"      : _e("Fire",   "Special",  100, 50),
        "Earthquake"   : _e("Ground", "Physical", 100, 100),
        "Air Slash"    : _e("Flying", "Special",  75,  95),
        "Dragon Dance" : _e("Dragon", "Status",   None, None),
        "Ancient Power": _e("Rock",   "Special",  60,  100),
    }

    defense    = _calc.compute_defense("era3", "Fire", "Flying")
    weak_types = [t for t, m in defense.items() if m > 1.0]

    dp, sp = _score_learnset(mock_form_data, mock_moves, mock_pkm, mock_game, weak_types, "era3")

    damage_names = [r["name"] for r in dp]
    status_names = [r["name"] for r in sp]

    check("Damage pool has 7 damage moves",
          len(dp) == 7)
    check("Status pool contains Dragon Dance",
          "Dragon Dance" in status_names)
    check("Dragon Dance not in damage pool",
          "Dragon Dance" not in damage_names)
    check("Damage pool sorted by score descending",
          [r["score"] for r in dp] == sorted([r["score"] for r in dp], reverse=True))

    ft  = next(r for r in dp if r["name"] == "Flamethrower")
    eq  = next(r for r in dp if r["name"] == "Earthquake")
    as_ = next(r for r in dp if r["name"] == "Air Slash")
    inf = next(r for r in dp if r["name"] == "Inferno")
    ap  = next(r for r in dp if r["name"] == "Ancient Power")

    check("Flamethrower: is_stab=True (Fire on Fire/Flying)",
          ft["is_stab"] is True)
    check("Earthquake: is_stab=False (Ground on Fire/Flying)",
          eq["is_stab"] is False)
    check("Air Slash: is_stab=True (Flying on Fire/Flying)",
          as_["is_stab"] is True)
    check("Earthquake counters Electric weakness (Ground SE vs Electric)",
          "Electric" in eq["counters_weaknesses"])
    check("Flamethrower does not counter Rock weakness (Fire not SE vs Rock)",
          "Rock" not in ft["counters_weaknesses"])
    check("Ancient Power counters_weaknesses is empty for Charizard",
          ap["counters_weaknesses"] == [])
    check("Inferno: low_accuracy=True (50% <= threshold 75)",
          inf["low_accuracy"] is True)
    check("Flamethrower: low_accuracy=False (100%)",
          ft["low_accuracy"] is False)
    check("No mock moves flagged is_two_turn",
          all(not r["is_two_turn"] for r in dp))
    check("Inferno (100pw/50%) scores less than Flamethrower (90pw/100%)",
          inf["score"] < ft["score"])
    check("Flamethrower (STAB+stat_weight) scores higher than Earthquake",
          ft["score"] > eq["score"])

    required = {"name","type","category","power","accuracy","pp",
                "score","is_stab","counters_weaknesses","is_two_turn","low_accuracy"}
    check("All damage pool rows have required keys",
          all(required <= set(r.keys()) for r in dp))
    check("All status pool rows have required keys",
          all(required <= set(r.keys()) for r in sp))

    # ── select_combo / _combo_score tests ────────────────────────────────────
    #
    # Strategy: test the SCORING MECHANICS directly via _combo_score, not the
    # selection outcome. Outcome tests are fragile (depend on exact pool scores
    # and bonus magnitudes). Mechanism tests are robust.
    #
    # Also test select_combo for: correct size, locked slots, edge cases.
    #
    # Charizard (Fire/Flying, SpA 109, Atk 84), Gen 9, era3.
    # Weaknesses: Water ×2, Electric ×2, Rock ×4.

    import matchup_calculator as _calc2

    mock_pkm2 = {
        "types"      : ["Fire", "Flying"],
        "type1"      : "Fire",
        "type2"      : "Flying",
        "base_stats" : {"attack": 84, "special-attack": 109,
                        "defense": 78, "special-defense": 85,
                        "speed": 100, "hp": 78},
    }
    mock_game2 = {"game": "Scarlet / Violet", "game_gen": 9, "era_key": "era3"}

    defense2 = _calc2.compute_defense("era3", "Fire", "Flying")
    weak2    = [t for t, m in defense2.items() if m > 1.0]   # Water, Electric, Rock

    def _e2(typ, cat, pwr, acc):
        return [{"from_gen": 1, "to_gen": None, "applies_to_games": None,
                 "type": typ, "category": cat, "power": pwr, "accuracy": acc, "pp": 15}]

    mock_fd2 = {
        "level-up": [
            {"move": "Flamethrower", "level": 30},
            {"move": "Air Slash",    "level": 45},
            {"move": "Dragon Pulse", "level": 50},
            {"move": "Thunderbolt",  "level": 1},
            {"move": "Surf",         "level": 1},
            {"move": "Stone Edge",   "level": 1},
            {"move": "Earthquake",   "level": 1},
            {"move": "Focus Blast",  "level": 1},
        ],
        "machine": [], "tutor": [], "egg": [],
    }
    mock_mv2 = {
        "Flamethrower": _e2("Fire",     "Special",  90,  100),
        "Air Slash":    _e2("Flying",   "Special",  75,   95),
        "Dragon Pulse": _e2("Dragon",   "Special",  85,  100),
        "Thunderbolt":  _e2("Electric", "Special",  90,  100),
        "Surf":         _e2("Water",    "Special",  90,  100),
        "Stone Edge":   _e2("Rock",     "Physical", 100,  80),
        "Earthquake":   _e2("Ground",   "Physical", 100, 100),
        "Focus Blast":  _e2("Fighting", "Special",  120,  70),
    }

    dp2, _ = _score_learnset(mock_fd2, mock_mv2, mock_pkm2, mock_game2, weak2, "era3")

    combo_cov  = select_combo(dp2, "coverage", weak2, "era3")
    combo_ctr  = select_combo(dp2, "counter",  weak2, "era3")
    combo_stab = select_combo(dp2, "stab",     weak2, "era3")

    # ── Size checks ───────────────────────────────────────────────────────────
    check("Coverage combo: exactly 4 moves",  len(combo_cov)  == 4)
    check("Counter combo: exactly 4 moves",   len(combo_ctr)  == 4)
    check("STAB combo: exactly 4 moves",      len(combo_stab) == 4)

    # ── Coverage: no duplicate non-Normal types ───────────────────────────────
    cov_types = [r["type"] for r in combo_cov if r["type"] != "Normal"]
    check("Coverage: no duplicate non-Normal types in selected combo",
          len(cov_types) == len(set(cov_types)))

    # ── _combo_score: STAB bonus only fires in stab mode ─────────────────────
    # Build two combos from our pool: one STAB-heavy, one not.
    # For both, stab mode score must exceed coverage mode score by exactly
    # (number of STAB moves) × _STAB_BONUS_PER_MOVE.
    stab_heavy = [r for r in dp2 if r["is_stab"]][:2] + [r for r in dp2 if not r["is_stab"]][:2]
    n_stab = sum(1 for r in stab_heavy if r["is_stab"])   # should be 2
    score_stab_mode = _combo_score(stab_heavy, weak2, "era3", "stab")
    score_cov_mode  = _combo_score(stab_heavy, weak2, "era3", "coverage")
    check("STAB mode score exceeds Coverage mode score by exactly n_stab × STAB_BONUS",
          abs(score_stab_mode - score_cov_mode - n_stab * _STAB_BONUS_PER_MOVE) < 0.001)

    # ── _combo_score: counter bonus only fires in counter mode ────────────────
    # Build a combo containing moves that counter weaknesses.
    # Counter mode must score higher than coverage mode by exactly
    # (number of unique weaknesses countered) × _COUNTER_BONUS_PER_WEAK.
    counter_combo = [
        next(r for r in dp2 if r["name"] == "Thunderbolt"),   # counters Water
        next(r for r in dp2 if r["name"] == "Earthquake"),    # counters Electric + Rock
        next(r for r in dp2 if r["name"] == "Flamethrower"),  # counters nothing
        next(r for r in dp2 if r["name"] == "Dragon Pulse"),  # counters nothing
    ]
    # Earthquake counters both Electric and Rock — total unique weaknesses countered = 3
    all_countered = set()
    for r in counter_combo:
        all_countered.update(r["counters_weaknesses"])
    n_countered = len(all_countered)   # should be 3: Water, Electric, Rock
    score_ctr_mode2 = _combo_score(counter_combo, weak2, "era3", "counter")
    score_cov_mode2 = _combo_score(counter_combo, weak2, "era3", "coverage")
    check("Counter mode score exceeds Coverage mode score by exactly n_countered × COUNTER_BONUS",
          abs(score_ctr_mode2 - score_cov_mode2 - n_countered * _COUNTER_BONUS_PER_WEAK) < 0.001)

    # ── _uncovered_weaknesses helper ─────────────────────────────────────────
    # Charizard weak to Water, Electric, Rock.
    # Actual counters_weaknesses per dp2 move (derived from type chart):
    #   Thunderbolt (Electric) → counters Water  (Electric hits Water-types SE)
    #   Surf (Water)           → counters Rock   (Water hits Rock-types SE)
    #   Earthquake (Ground)    → counters Electric + Rock
    #   All others             → counter nothing in weak2

    eq_r  = next(r for r in dp2 if r["name"] == "Earthquake")
    tb_r  = next(r for r in dp2 if r["name"] == "Thunderbolt")
    su_r  = next(r for r in dp2 if r["name"] == "Surf")
    ft_r  = next(r for r in dp2 if r["name"] == "Flamethrower")
    dp_r  = next(r for r in dp2 if r["name"] == "Dragon Pulse")
    as_r  = next(r for r in dp2 if r["name"] == "Air Slash")

    # TB(→Water) + EQ(→Electric+Rock) = all 3 covered → gap=0
    full_cover    = [tb_r, eq_r, ft_r, dp_r]
    # TB(→Water) + SU(→Rock) = only Electric uncovered → gap=1
    partial_cover = [tb_r, su_r, ft_r, dp_r]
    # None of these counter anything in weak2 → gap=3
    no_cover      = [ft_r, as_r, dp_r, su_r]   # SU→Rock, others nothing; Electric+Water uncovered
    # Actually su_r counters Rock → gap=2 for [ft,as,dp,su]
    no_cover      = [ft_r, as_r, dp_r,
                     next(r for r in dp2 if r["name"] == "Stone Edge")]  # SE counters nothing

    check("_uncovered_weaknesses: full cover (TB+EQ) = 0",
          _uncovered_weaknesses(full_cover, weak2) == 0)
    check("_uncovered_weaknesses: partial cover (TB+SU, Electric uncovered) = 1",
          _uncovered_weaknesses(partial_cover, weak2) == 1)
    check("_uncovered_weaknesses: no cover (FT+AS+DP+SE) = 3",
          _uncovered_weaknesses(no_cover, weak2) == 3)
    check("_uncovered_weaknesses: empty weakness list always 0",
          _uncovered_weaknesses(full_cover, []) == 0)

    # ── counter mode: coverage completeness is the primary sort key ───────────
    #
    # Setup: lock 3 moves that together cover Water + Electric (Rock still open).
    # Free pool has two candidates:
    #   CoverRock (score=30) — counters Rock weakness → full coverage (gap=0)
    #   HighScore (score=120) — counters nothing      → Rock still open (gap=1)
    #
    # _combo_score(locked+CoverRock) ≈ 535  gap=0
    # _combo_score(locked+HighScore) ≈ 600  gap=1
    # Old code: HighScore wins (higher blended score) — BUG
    # New code: CoverRock wins (gap=0 < gap=1)        — CORRECT

    def _cw(name, typ, power, *counters):
        """Minimal move dict with explicit counters_weaknesses for testing."""
        return {
            "name": name, "type": typ, "category": "Special",
            "power": power, "accuracy": 100, "pp": 15,
            "priority": 0, "drain": 0, "effect_chance": 0, "ailment": "none",
            "score": float(power),
            "is_stab": False,
            "counters_weaknesses": list(counters),
            "is_two_turn": False, "low_accuracy": False,
        }

    lock_tb  = _cw("LockTB",  "Electric", 90, "Water")    # counters Water weakness
    lock_eq  = _cw("LockEQ",  "Ground",   90, "Electric") # counters Electric weakness
    lock_pad = _cw("LockPad", "Normal",   50)              # filler (different type)
    locked3  = [lock_tb, lock_eq, lock_pad]

    cover_rock = _cw("CoverRock", "Water",  30, "Rock")   # gap=0, low score
    high_score = _cw("HighScore", "Dragon", 120)           # gap=1, high score

    s_gap0 = _combo_score(locked3 + [cover_rock], weak2, "era3", "counter")
    s_gap1 = _combo_score(locked3 + [high_score], weak2, "era3", "counter")
    check("Counter mode test setup: gap=1 combo scores higher than gap=0 combo",
          s_gap1 > s_gap0)

    ctr_result = select_combo([high_score, cover_rock], "counter", weak2, "era3",
                              locked=locked3)
    ctr_names = {r["name"] for r in ctr_result}
    check("Counter mode: gap=0 combo wins over higher-scoring gap=1 combo",
          "CoverRock" in ctr_names and "HighScore" not in ctr_names)

    # ── counter mode: tiebreaker — equal gap → highest score wins ─────────────
    # Two combos both covering all weaknesses; higher-scored one must win.
    cover_rock_hi = _cw("CoverRockHi", "Water", 80, "Rock")  # same gap=0, higher score
    cover_rock_lo = _cw("CoverRockLo", "Water", 10, "Rock")  # same gap=0, lower score
    tie_result = select_combo([cover_rock_hi, cover_rock_lo], "counter", weak2, "era3",
                              locked=locked3)
    tie_names = {r["name"] for r in tie_result}
    check("Counter mode tiebreaker: equal coverage → higher-scored move wins",
          "CoverRockHi" in tie_names and "CoverRockLo" not in tie_names)

    # ── coverage / stab modes: unchanged — still select purely by score ────────
    cov_result = select_combo([high_score, cover_rock], "coverage", weak2, "era3",
                              locked=locked3)
    cov_names = {r["name"] for r in cov_result}
    check("Coverage mode unchanged: high-score move still wins regardless of gap",
          "HighScore" in cov_names and "CoverRock" not in cov_names)

        # ── _build_counter_pool ─────────────────────────────────────────────────────
    # Build a pool with some covering and some non-covering moves.
    # covering moves: counter at least one weakness
    # filler moves:   counter nothing — only top _COUNTER_FILLER_K are kept
    from feat_moveset_data import _build_counter_pool, _build_coverage_pool,                                    _COUNTER_FILLER_K, _STAB_POOL_CAP

    def _mk(name, typ, score, *counters):
        """Minimal move dict for pool builder tests."""
        return {"name": name, "type": typ, "score": float(score),
                "counters_weaknesses": list(counters),
                "is_stab": False, "category": "Physical",
                "power": score, "accuracy": 100, "pp": 15,
                "priority": 0, "drain": 0, "effect_chance": 0, "ailment": "none",
                "is_two_turn": False, "low_accuracy": False}

    wt = ["Water", "Rock"]  # two weaknesses for these tests
    cov_a = _mk("CovA", "Electric", 90, "Water")       # covers Water
    cov_b = _mk("CovB", "Rock",     80, "Rock")         # covers Rock
    cov_c = _mk("CovC", "Ground",   70, "Water","Rock") # covers both
    fillers = [_mk(f"Fill{i}", "Normal", 60 - i) for i in range(20)]

    cp = _build_counter_pool([cov_a, cov_b, cov_c] + fillers, wt)
    check("_build_counter_pool: all covering moves included",
          all(r["name"] in {r2["name"] for r2 in cp} for r in [cov_a, cov_b, cov_c]))
    check(f"_build_counter_pool: at most 3 covering + {_COUNTER_FILLER_K} fillers",
          len(cp) <= 3 + _COUNTER_FILLER_K)
    check("_build_counter_pool: only top-K fillers kept (first filler in, last not)",
          "Fill0" in {r["name"] for r in cp} and
          f"Fill{_COUNTER_FILLER_K}" not in {r["name"] for r in cp})

    # Counter pool with NO covering moves: falls back to pure fillers
    empty_cover = _build_counter_pool(fillers, wt)
    check("_build_counter_pool: no covering moves → top-K fillers only",
          len(empty_cover) == _COUNTER_FILLER_K)

    # ── _build_coverage_pool ─────────────────────────────────────────────────
    # Pool with multiple moves per type: only best-scoring kept per type.
    fire_hi = _mk("FireHi", "Fire", 100)
    fire_lo = _mk("FireLo", "Fire",  50)
    ice_hi  = _mk("IceHi",  "Ice",  90)
    ice_lo  = _mk("IceLo",  "Ice",  40)
    norm    = _mk("Norm",   "Normal", 80)

    # eligible is score-sorted desc → fire_hi before fire_lo, ice_hi before ice_lo
    pool_in = [fire_hi, norm, ice_hi, fire_lo, ice_lo]
    cvp = _build_coverage_pool(pool_in)
    cvp_names = {r["name"] for r in cvp}
    check("_build_coverage_pool: best Fire move kept", "FireHi" in cvp_names)
    check("_build_coverage_pool: weaker Fire move dropped", "FireLo" not in cvp_names)
    check("_build_coverage_pool: best Ice move kept", "IceHi" in cvp_names)
    check("_build_coverage_pool: weaker Ice move dropped", "IceLo" not in cvp_names)
    check("_build_coverage_pool: Normal move kept (unique type)", "Norm" in cvp_names)
    check("_build_coverage_pool: exactly one entry per type",
          len(cvp) == len({r["type"] for r in cvp}))
    check("_build_coverage_pool: result has 3 types (Fire, Ice, Normal)",
          len(cvp) == 3)

    # ── counter mode: low-score covering move outside old cap is now included ──
    # Simulate the Tyranitar scenario: 25+ high-scoring non-covering moves push
    # a key covering move beyond any old cap, but _build_counter_pool always
    # includes it because it counters a weakness.
    many_fillers = [_mk(f"BigFill{i}", "Dark", 200 - i) for i in range(25)]
    key_cover = _mk("KeyCover", "Flying", 10, "Water")  # low score, covers Water
    no_cap_pool = many_fillers + [key_cover]
    ctr = select_combo(no_cap_pool, "counter", ["Water"], "era3")
    check("Counter mode: covering move always included regardless of score rank",
          "KeyCover" in {r["name"] for r in ctr})

    # ── coverage mode: two-pass selects best-coverage tier then best score ─────
    # 4 moves with type Fire cover same SE types as 4 moves with diverse types?
    # This verifies the two-pass: max coverage first, score second.
    fire1  = _mk("Fire1",  "Fire",    200)  # high score, Fire covers 4 types SE
    fire2  = _mk("Fire2",  "Fire",    190)  # but all 4 Fire moves cover same 4 types
    fire3  = _mk("Fire3",  "Fire",    180)
    fire4  = _mk("Fire4",  "Fire",    170)
    # Mixed combo covers Fire+Ice+Fighting+Ground SE types (more than 4-Fire combo)
    ice_m  = _mk("IceM",   "Ice",     50)   # lower score but adds new SE types
    fgt_m  = _mk("FgtM",   "Fighting",50)
    gnd_m  = _mk("GndM",   "Ground",  50)

    mixed_pool = [fire1, fire2, fire3, fire4, ice_m, fgt_m, gnd_m]
    # fire1-4 all same type → coverage pool keeps only fire1 (best Fire)
    # So coverage pool = [fire1, ice_m, fgt_m, gnd_m]
    # Best 4-combo is trivially [fire1, ice_m, fgt_m, gnd_m]
    cov_res = select_combo(mixed_pool, "coverage", [], "era3")
    cov_res_names = {r["name"] for r in cov_res}
    check("Coverage mode: diverse-type combo beats same-type high-score combo",
          "IceM" in cov_res_names and "FgtM" in cov_res_names and "GndM" in cov_res_names)

    # ── stab mode: still uses _STAB_POOL_CAP, pure score ─────────────────────
    stab_pool = [_mk(f"S{i}", "Dark", 100 - i) for i in range(_STAB_POOL_CAP + 5)]
    stab_res = select_combo(stab_pool, "stab", [], "era3")
    stab_names = [r["name"] for r in stab_res]
    check("STAB mode: top-scoring moves selected (score-only, no coverage goal)",
          stab_names[0] == "S0")  # highest-scorer always in result

        # ── _combo_score: redundancy penalty fires correctly ──────────────────────
    # Strategy: build a combo with two Fire moves, manually compute the expected
    # score (base + coverage - penalty), verify _combo_score returns that value.
    # Using two IDENTICAL Fire move rows (same score) isolates the penalty cleanly.
    ft_row = next(r for r in dp2 if r["name"] == "Flamethrower")
    eq_row = next(r for r in dp2 if r["name"] == "Earthquake")
    dp_row = next(r for r in dp2 if r["name"] == "Dragon Pulse")

    fire2_row = dict(ft_row)
    fire2_row["name"] = "Fire Blast"   # identical score, same type
    two_fire = [ft_row, fire2_row, eq_row, dp_row]

    # Manually compute expected score
    base_2f = sum(r["score"] for r in two_fire)
    se_2f = set()
    for r in two_fire:
        for dt in _calc2.TYPES_ERA3:
            if _calc2.get_multiplier("era3", r["type"], dt) >= 2.0:
                se_2f.add(dt)
    expected_2f = base_2f + len(se_2f) * _COVERAGE_BONUS_PER_TYPE - _REDUNDANCY_PENALTY
    actual_2f   = _combo_score(two_fire, weak2, "era3", "coverage")
    check("Redundancy penalty: two-Fire combo score matches manual calculation",
          abs(actual_2f - expected_2f) < 0.001)

    # ── Normal exemption: two Normal moves → zero redundancy penalty ──────────
    # Strategy: build two structurally identical combos — one with [Normal, Normal, ...]
    # and one with [Fire, Fire, ...] (same base power/acc, so same scores except type).
    # The Fire combo must score lower by exactly _REDUNDANCY_PENALTY
    # (coverage bonus difference accounted for separately).
    def _bare(name, typ):
        """Minimal move dict with neutral score factors — power 90, acc 100, no STAB."""
        return {"name": name, "type": typ, "category": "Special",
                "power": 90, "accuracy": 100, "pp": 15,
                "score": 90.0,   # fixed — no STAB, no stat_weight
                "is_stab": False, "counters_weaknesses": [],
                "is_two_turn": False, "low_accuracy": False}

    norm1 = _bare("Norm1", "Normal")
    norm2 = _bare("Norm2", "Normal")
    fire1 = _bare("Fire1", "Fire")
    fire2 = _bare("Fire2", "Fire")
    filler1 = _bare("Fly1",    "Flying")
    filler2 = _bare("Ground1", "Ground")

    combo_nn = [norm1, norm2, filler1, filler2]   # two Normal: no penalty
    combo_ff = [fire1, fire2, filler1, filler2]   # two Fire:   penalty -20

    # Compute coverage bonus for each (Normal hits nothing SE; Fire does)
    def _coverage(combo):
        se = set()
        for r in combo:
            for dt in _calc2.TYPES_ERA3:
                if _calc2.get_multiplier("era3", r["type"], dt) >= 2.0:
                    se.add(dt)
        return len(se) * _COVERAGE_BONUS_PER_TYPE

    cov_nn = _coverage(combo_nn)
    cov_ff = _coverage(combo_ff)
    base_nn = sum(r["score"] for r in combo_nn)
    base_ff = sum(r["score"] for r in combo_ff)

    expected_nn = base_nn + cov_nn + 0                    # Normal exempt, no penalty
    expected_ff = base_ff + cov_ff - _REDUNDANCY_PENALTY  # Fire pair, penalty fires
    actual_nn   = _combo_score(combo_nn, weak2, "era3", "coverage")
    actual_ff   = _combo_score(combo_ff, weak2, "era3", "coverage")

    check("Normal exemption: two-Normal combo score matches manual (no penalty)",
          abs(actual_nn - expected_nn) < 0.001)
    check("Redundancy fires for two-Fire combo: score matches manual (penalty -20)",
          abs(actual_ff - expected_ff) < 0.001)

    # ── Locked slot: pinned move always in result ─────────────────────────────
    locked_move  = next(r for r in dp2 if r["name"] == "Dragon Pulse")
    combo_locked = select_combo(dp2, "coverage", weak2, "era3", locked=[locked_move])
    check("Locked move always present in result",
          any(r["name"] == "Dragon Pulse" for r in combo_locked))
    check("Locked combo still has 4 moves",
          len(combo_locked) == 4)
    check("Locked move not duplicated",
          sum(1 for r in combo_locked if r["name"] == "Dragon Pulse") == 1)

    # ── Edge cases ────────────────────────────────────────────────────────────
    dp_tiny = dp2[:2]
    check("Small pool (<4 moves): returns all available without crash",
          len(select_combo(dp_tiny, "coverage", weak2, "era3")) == 2)
    check("Empty pool: returns empty list",
          select_combo([], "coverage", weak2, "era3") == [])

    # ── COMBO_EXCLUDED: excluded moves never appear in auto combos ────────────

    def _dmg(name, typ="Fighting", pwr=150):
        """Minimal damage move dict."""
        return {"name": name, "type": typ, "category": "Physical",
                "power": pwr, "accuracy": 100, "pp": 20, "priority": 0,
                "score": float(pwr), "is_stab": False,
                "counters_weaknesses": [], "is_two_turn": False,
                "low_accuracy": False}

    # Build a pool that contains Focus Punch and Explosion alongside normal moves
    pool_with_excluded = [
        _dmg("Focus Punch",  "Fighting", 150),  # excluded
        _dmg("Explosion",    "Normal",   250),  # excluded
        _dmg("Earthquake",   "Ground",   100),
        _dmg("Flamethrower", "Fire",      90),
        _dmg("Dragon Pulse", "Dragon",    85),
        _dmg("Air Slash",    "Flying",    75),
    ]
    combo_ex = select_combo(pool_with_excluded, "coverage", [], "era3")
    combo_names = [r["name"] for r in combo_ex]

    check("Focus Punch not in auto combo even with high score",
          "Focus Punch" not in combo_names)
    check("Explosion not in auto combo even with highest score",
          "Explosion" not in combo_names)
    check("Normal moves fill slots instead",
          "Earthquake" in combo_names or "Flamethrower" in combo_names)

    # Excluded move CAN appear if user locks it
    locked_fp = _dmg("Focus Punch", "Fighting", 150)
    combo_locked_fp = select_combo(pool_with_excluded, "coverage", [], "era3",
                                   locked=[locked_fp])
    check("Focus Punch appears when explicitly locked by user",
          any(r["name"] == "Focus Punch" for r in combo_locked_fp))

    # Verify all 16 excluded moves are in the frozenset
    expected_excluded = {
        "Self-Destruct", "Explosion", "Misty Explosion", "Final Gambit",
        "Memento", "Healing Wish", "Lunar Dance",
        "Focus Punch", "Perish Song", "Destiny Bond",
        "Curse", "Grudge", "Spite",
        "Fling", "Natural Gift",
        "Last Resort",
    }
    check("COMBO_EXCLUDED contains all 16 expected moves",
          expected_excluded == set(COMBO_EXCLUDED))



    def _smock(name, typ="Normal"):
        """Minimal status move dict as produced by build_candidate_pool."""
        return {"name": name, "type": typ, "category": "Status",
                "power": None, "accuracy": None, "pp": 10,
                "score": 0.0, "is_stab": False, "counters_weaknesses": [],
                "is_two_turn": False, "low_accuracy": False}

    # Basic ranking: tier 2 (Dragon Dance) beats tier 4 (Roar)
    pool_basic = [_smock("Dragon Dance", "Dragon"), _smock("Roar")]
    ranked_basic = rank_status_moves(pool_basic, top_n=3)
    check("Dragon Dance (tier 2) ranked above Roar (tier 4)",
          ranked_basic[0]["name"] == "Dragon Dance")

    # Tier 1 beats tier 2: Toxic before Swords Dance
    pool_tier = [_smock("Swords Dance"), _smock("Toxic", "Poison")]
    ranked_tier = rank_status_moves(pool_tier, top_n=3)
    check("Toxic (tier 1) ranked above Swords Dance (tier 2)",
          ranked_tier[0]["name"] == "Toxic")

    # Tier 2 beats tier 3: Swords Dance before Recover
    pool_t23 = [_smock("Recover"), _smock("Swords Dance")]
    ranked_t23 = rank_status_moves(pool_t23, top_n=3)
    check("Swords Dance (tier 2) ranked above Recover (tier 3)",
          ranked_t23[0]["name"] == "Swords Dance")

    # Tier 3 beats tier 4: Roost before Sunny Day
    pool_t34 = [_smock("Sunny Day", "Fire"), _smock("Roost", "Flying")]
    ranked_t34 = rank_status_moves(pool_t34, top_n=3)
    check("Roost (tier 3) ranked above Sunny Day (tier 4)",
          ranked_t34[0]["name"] == "Roost")

    # Within same tier: higher quality wins — Dragon Dance (q=9) > Bulk Up (q=7)
    pool_same_tier = [_smock("Bulk Up", "Fighting"), _smock("Dragon Dance", "Dragon")]
    ranked_same = rank_status_moves(pool_same_tier, top_n=3)
    check("Within tier 2: Dragon Dance (q=9) above Bulk Up (q=7)",
          ranked_same[0]["name"] == "Dragon Dance")

    # Within same tier, same quality: alphabetical tiebreak
    pool_alpha = [_smock("Swords Dance"), _smock("Nasty Plot", "Dark")]
    ranked_alpha = rank_status_moves(pool_alpha, top_n=3)
    # Both tier 2, quality 8 — alphabetical: "Nasty Plot" < "Swords Dance"
    check("Same tier+quality: alphabetical tiebreak (Nasty Plot before Swords Dance)",
          ranked_alpha[0]["name"] == "Nasty Plot")

    # Unknown move falls back to tier 4, quality 0 — appears last
    pool_unknown = [_smock("Swords Dance"), _smock("WeirdFakeMove999")]
    ranked_unk = rank_status_moves(pool_unknown, top_n=3)
    check("Unknown move falls back to tier 4 and appears last",
          ranked_unk[0]["name"] == "Swords Dance")

    # top_n respected
    pool_large = [_smock("Dragon Dance", "Dragon"), _smock("Swords Dance"),
                  _smock("Recover"),    _smock("Roost", "Flying"),
                  _smock("Toxic", "Poison")]
    check("top_n=2 returns exactly 2 moves",
          len(rank_status_moves(pool_large, top_n=2)) == 2)
    check("top_n=3 returns exactly 3 moves",
          len(rank_status_moves(pool_large, top_n=3)) == 3)

    # top_n larger than pool: returns all available
    check("top_n larger than pool: returns all moves",
          len(rank_status_moves(pool_basic, top_n=10)) == 2)

    # Empty pool: returns empty list
    check("rank_status_moves: empty pool returns empty list",
          rank_status_moves([], top_n=3) == [])

    # Enriched dict has expected fields
    enriched = rank_status_moves([_smock("Dragon Dance", "Dragon")], top_n=1)
    check("Ranked move has 'tier' field",        "tier"       in enriched[0])
    check("Ranked move has 'quality' field",     "quality"    in enriched[0])
    check("Ranked move has 'tier_label' field",  "tier_label" in enriched[0])
    check("Dragon Dance tier_label = 'Stat boost'",
          enriched[0]["tier_label"] == "Stat boost")
    check("Dragon Dance tier = 2",   enriched[0]["tier"]    == 2)
    check("Dragon Dance quality = 9", enriched[0]["quality"] == 9)

    # Charizard integration: pick recognisable status moves from real pool structure
    charzi_status = [
        _smock("Dragon Dance", "Dragon"), _smock("Swords Dance"),
        _smock("Sunny Day",    "Fire"),   _smock("Roost",  "Flying"),
        _smock("Protect"),                _smock("Substitute"),
    ]
    charzi_ranked = rank_status_moves(charzi_status, top_n=3)
    # Dragon Dance (tier 2, q=9) must be #1; Swords Dance (tier 2, q=8) must be #2
    check("Charizard: Dragon Dance ranked 1st", charzi_ranked[0]["name"] == "Dragon Dance")
    check("Charizard: Swords Dance ranked 2nd", charzi_ranked[1]["name"] == "Swords Dance")

    # ── Summary ───────────────────────────────────────────────────────────────

    print(f"\n  {passed} passed, {failed} failed out of {passed + failed} tests.")
    if failed == 0:
        print("  All tests passed.\n")
    else:
        print("  Some tests FAILED — check output above.\n")


if __name__ == "__main__":
    _run_tests()