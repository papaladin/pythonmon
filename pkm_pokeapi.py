#!/usr/bin/env python3
"""
pkm_pokeapi.py -- PokeAPI data adapter

Fetches Pokemon, move, and learnset data from https://pokeapi.co/api/v2/
and translates responses into the same JSON schemas used by the cache layer.

Public API (all steps complete):
  fetch_pokemon(name)               → dict   forms, types, base stats, variety slugs
  fetch_move(name)                  → list   versioned move entries (from_gen / to_gen)
  fetch_all_moves(dry_run)          → dict   all ~920 moves at once with progress counter
  fetch_machines()                  → dict   TM/HM number lookup table
  fetch_learnset(variety_slug, form_name, game)
                                    → dict   learnset for one variety + game

Standalone self-test:
  python pkm_pokeapi.py             -- offline assertions (mapping tables, versioned entries)
  python pkm_pokeapi.py --verify    -- also hits the live API (all slugs + one Pokemon)
  python pkm_pokeapi.py --dry-run   -- tests move fetching (~18 moves, requires network)
"""

import sys
import json
import urllib.request
import urllib.error
import ssl

# Create an unverified SSL context for frozen builds (macOS PyInstaller)
if getattr(sys, "frozen", False):
    _unverified_ssl_context = ssl._create_unverified_context()
else:
    _unverified_ssl_context = None

# ── Import game list ───────────────────────────────────────────────────────────
try:
    import matchup_calculator as calc
    GAMES = calc.GAMES
except ModuleNotFoundError:
    print("ERROR: matchup_calculator.py not found in the same folder.")
    sys.exit(1)

BASE_URL = "https://pokeapi.co/api/v2"

# Roman numerals used by PokeAPI generation names ("generation-iv" → 4)
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
          "vi": 6, "vii": 7, "viii": 8, "ix": 9}


# ── Version-group mapping ──────────────────────────────────────────────────────
#
# Maps every display name in matchup_calculator.GAMES to the PokeAPI
# version-group slug(s) for that game entry.
#
# Rules:
#   - A display name that covers multiple games (e.g. "Red / Blue / Yellow")
#     maps to a list with one slug per distinct PokeAPI version group.
#   - Learnset queries must check ALL slugs for a given game and merge results
#     (a Pokemon may learn a move in Yellow but not Red/Blue, or vice versa).
#   - Slugs are verified against the live API via --verify.
#
# PokeAPI version-group endpoint:
#   GET https://pokeapi.co/api/v2/version-group/{slug}/

GAME_TO_VERSION_GROUPS = {
    # Gen 1
    "Red / Blue / Yellow":               ["red-blue", "yellow"],

    # Gen 2
    "Gold / Silver / Crystal":           ["gold-silver", "crystal"],

    # Gen 3
    "Ruby / Sapphire / Emerald":         ["ruby-sapphire", "emerald"],
    "FireRed / LeafGreen":               ["firered-leafgreen"],

    # Gen 4
    "Diamond / Pearl / Platinum":        ["diamond-pearl", "platinum"],
    "HeartGold / SoulSilver":            ["heartgold-soulsilver"],

    # Gen 5
    "Black / White":                     ["black-white"],
    "Black 2 / White 2":                 ["black-2-white-2"],

    # Gen 6
    "X / Y":                             ["x-y"],
    "Omega Ruby / Alpha Sapphire":       ["omega-ruby-alpha-sapphire"],

    # Gen 7
    "Sun / Moon":                        ["sun-moon"],
    "Ultra Sun / Ultra Moon":            ["ultra-sun-ultra-moon"],

    # Gen 8
    "Sword / Shield":                    ["sword-shield"],
    "Brilliant Diamond / Shining Pearl": ["brilliant-diamond-shining-pearl"],
    "Legends: Arceus":                   ["legends-arceus"],

    # Gen 9
    "Scarlet / Violet":                  ["scarlet-violet"],
    "Legends: Z-A":                      ["legends-za"],
}

# Reverse map: version-group slug -> (display_name, generation_number)
# Built automatically from GAME_TO_VERSION_GROUPS + GAMES.
# Used when translating PokeAPI past_values (which reference version_groups)
# back into generation numbers for our from_gen/to_gen schema.
VERSION_GROUP_TO_GEN = {}
for _game_name, _era_key, _gen in GAMES:
    for _slug in GAME_TO_VERSION_GROUPS.get(_game_name, []):
        VERSION_GROUP_TO_GEN[_slug] = _gen


# ── HTTP helper ────────────────────────────────────────────────────────────────

def _get(path):
    url = f"{BASE_URL}/{path.lstrip('/')}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "pkm-toolkit/2.0 (pokeapi adapter)"}
        )
        if _unverified_ssl_context:
            resp = urllib.request.urlopen(req, timeout=10, context=_unverified_ssl_context)
        else:
            resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Not found: {url}")
        raise ConnectionError(f"HTTP {e.code} fetching {url}")
    except urllib.error.URLError as e:
        raise ConnectionError(f"Could not reach pokeapi.co: {e.reason}")


def check_connectivity() -> bool:
    """
    Return True if PokeAPI is reachable, False on any network failure.

    Makes a lightweight GET to the API root (small metadata response).
    Uses a 3-second timeout — much faster than the normal 10s fetch timeout.
    Intended for the startup offline-mode check in pokemain.py; not used in
    normal data-fetching paths.
    """

    try:
        req = urllib.request.Request(
            f"{BASE_URL}/",
            headers={"User-Agent": "pkm-toolkit/2.0 (connectivity check)"}
        )
        if _unverified_ssl_context:
            urllib.request.urlopen(req, timeout=3, context=_unverified_ssl_context)
        else:
            urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


# ── Name / slug helpers ───────────────────────────────────────────────────────

def _name_to_slug(name: str) -> str:
    """Convert user-entered name to a PokeAPI slug: lowercase, spaces→hyphens."""
    import re
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _gen_name_to_int(gen_name: str) -> int:
    """'generation-iv' → 4.  Falls back to 0 on unrecognised input."""
    roman = gen_name.split("-")[-1].lower()
    return _ROMAN.get(roman, 0)


def _en_name(names_list: list, fallback: str) -> str:
    """Return the English entry from a PokeAPI 'names' array, or fallback."""
    for entry in names_list:
        if entry.get("language", {}).get("name") == "en":
            return entry["name"]
    return fallback


# ── Step 2: Pokemon fetch ─────────────────────────────────────────────────────

def fetch_pokemon(name: str) -> dict:
    """
    Fetch all forms, types, base stats, and species generation for a Pokemon.

    Returns a dict matching the cache/pokemon/<n>.json schema:
      {
        "pokemon"    : "charizard",
        "species_gen": 1,
        "forms": [
          {
            "name"      : "Charizard",
            "types"     : ["Fire", "Flying"],
            "base_stats": {"hp": 78, "attack": 84, ...},
            "abilities" : [{"slug": "blaze", "is_hidden": false},
                           {"slug": "solar-power", "is_hidden": false},
                           {"slug": "drought", "is_hidden": true}]
          },
          ...
        ]
      }

    Raises ValueError if the Pokemon is not found (404).
    Raises ConnectionError on network failure.

    Deduplication: if every form has identical types, only the base (default)
    form is returned -- same behaviour as the original pokemondb.net scraper.
    """
    slug = _name_to_slug(name)

    # 1. Species: generation + English display name + varieties list
    species = _get(f"pokemon-species/{slug}")
    species_gen   = _gen_name_to_int(species["generation"]["name"])
    species_en    = _en_name(species.get("names", []), name.title())

    forms = []
    for variety in species["varieties"]:
        variety_slug = variety["pokemon"]["name"]

        # 2. Pokemon: types + base stats
        pkm = _get(f"pokemon/{variety_slug}")
        types = [
            t["type"]["name"].capitalize()
            for t in sorted(pkm["types"], key=lambda x: x["slot"])
        ]
        base_stats = {
            s["stat"]["name"]: s["base_stat"]
            for s in pkm["stats"]
        }
        abilities = [
            {
                "slug"     : a["ability"]["name"],
                "is_hidden": a["is_hidden"],
            }
            for a in sorted(pkm["abilities"], key=lambda x: x["slot"])
        ]

        # 3. Form display name via pokemon-form endpoint
        #    The first entry in pkm["forms"] is the canonical form for this variant.
        form_slug  = pkm["forms"][0]["name"]
        form_data  = _get(f"pokemon-form/{form_slug}")
        en = _en_name(form_data.get("names", []), None)
        if en:
            display_name = en
        elif variety["is_default"]:
            display_name = species_en          # base form: use species name
        else:
            # last-resort fallback: title-case the slug
            display_name = form_slug.replace("-", " ").title()

        forms.append({
            "name"        : display_name,
            "variety_slug": variety_slug,
            "types"       : types,
            "base_stats"  : base_stats,
            "abilities"   : abilities,
        })

    # Deduplicate: if all forms share identical types, keep only the default form
    if len({tuple(f["types"]) for f in forms}) == 1:
        default = next((f for f, v in zip(forms, species["varieties"])
                        if v["is_default"]), forms[0])
        forms = [default]

    return {
        "pokemon"           : slug,
        "species_gen"       : species_gen,
        "egg_groups"        : [g["name"] for g in species.get("egg_groups", [])],
        "evolution_chain_id": _parse_chain_id(species),
        "forms"             : forms,
    }


# ── Step 3: Move fetch ────────────────────────────────────────────────────────

# PokeAPI type slug → capitalised display name
# (most are just .capitalize(), but a few need special casing)
_TYPE_NAMES = {
    "normal": "Normal", "fire": "Fire", "water": "Water",
    "electric": "Electric", "grass": "Grass", "ice": "Ice",
    "fighting": "Fighting", "poison": "Poison", "ground": "Ground",
    "flying": "Flying", "psychic": "Psychic", "bug": "Bug",
    "rock": "Rock", "ghost": "Ghost", "dragon": "Dragon",
    "dark": "Dark", "steel": "Steel", "fairy": "Fairy",
}

_CATEGORY_NAMES = {
    "physical": "Physical",
    "special":  "Special",
    "status":   "Status",
}

# Gen 1-3: category was determined by the move's TYPE, not individually.
# Special types: Fire, Water, Grass, Electric, Ice, Psychic, Dragon (Gen1+),
#                Dark (Gen2+, added with GSC).
# All other types (Normal, Fighting, Poison, Ground, Flying, Bug, Rock,
#                  Ghost, Steel) were Physical in Gen1-3.
_SPECIAL_TYPES_GEN1_3 = frozenset({
    "Fire", "Water", "Grass", "Electric", "Ice", "Psychic", "Dragon", "Dark"
})


def _apply_gen1_3_category_rule(entries: list) -> list:
    """
    Post-process versioned entries to apply the Gen1-3 type-based category rule.

    In Gen1-3, a move's category was determined by its type (not individually).
    PokeAPI only stores the individual category (assigned at the Gen4 Phys/Spe
    split), so we must patch any entry that covers Gen1-3 gens.

    Only splits an entry at the Gen3/Gen4 boundary if the Gen1-3 category
    actually differs from the stored category (e.g. a Physical Dragon move
    needs to become Special for Gen2-3 but stays Physical from Gen4).
    """
    result = []
    for entry in entries:
        fg = entry.get("from_gen")
        tg = entry.get("to_gen")  # None = open-ended

        # Only relevant for entries that cover Gen1-3
        if fg is None or fg > 3:
            result.append(entry)
            continue

        move_type    = entry.get("type", "")
        cat_gen1_3   = "Special" if move_type in _SPECIAL_TYPES_GEN1_3 else "Physical"
        stored_cat   = entry.get("category")
        spans_gen4   = (tg is None or tg >= 4)

        if cat_gen1_3 == stored_cat:
            # Category is the same before and after split — no change needed
            result.append(entry)
        elif spans_gen4:
            # Split: Gen1-3 portion with corrected category, Gen4+ unchanged
            result.append({**entry, "to_gen": 3, "category": cat_gen1_3})
            result.append({**entry, "from_gen": 4})
        else:
            # Entry is entirely within Gen1-3 (to_gen <= 3) — just patch category
            result.append({**entry, "category": cat_gen1_3})

    return result


def _build_versioned_entries(current: dict, intro_gen: int,
                              past_values: list) -> list:
    """
    Translate PokeAPI past_values list into our from_gen/to_gen schema.

    Each past_value entry describes the field values that applied in a specific
    version_group (and all earlier version_groups back to intro or the previous
    boundary). The version_group is the LAST one where those old values applied.

    Algorithm:
      1. Map each past_value to a gen number via VERSION_GROUP_TO_GEN.
      2. Group by gen, merge fields (multiple version_groups in the same gen
         are merged — last one wins per field).
      3. Sort change gens ascending: [g1, g2, ..., gk].
      4. Build spans:
         - [intro_gen .. g1] : current values overridden by ALL past changes
           (g1 and later), because the oldest span has ALL later changes applied.
         - [g(i-1)+1 .. gi]  : current values overridden by changes at gi and later.
         - [gk+1 .. None]    : current values only.

    Returns list of versioned entry dicts, sorted ascending by from_gen.
    """
    if not past_values:
        return [{"from_gen": intro_gen, "to_gen": None,
                 "applies_to_games": None, **current}]

    # Collect change points: gen → {field: old_value}
    change_points = {}
    for pv in past_values:
        vg_slug = pv.get("version_group", {}).get("name", "")
        vg_gen  = VERSION_GROUP_TO_GEN.get(vg_slug)
        if vg_gen is None:
            continue  # unknown version group — skip

        fields = {}
        if pv.get("power") is not None:
            fields["power"] = pv["power"]
        if pv.get("accuracy") is not None:
            fields["accuracy"] = pv["accuracy"]
        if pv.get("pp") is not None:
            fields["pp"] = pv["pp"]
        t = pv.get("type")
        if t is not None:
            fields["type"] = _TYPE_NAMES.get(t["name"], t["name"].capitalize())
        dc = pv.get("move_damage_class")
        if dc is not None:
            fields["category"] = _CATEGORY_NAMES.get(dc["name"],
                                                      dc["name"].capitalize())

        if fields:
            if vg_gen not in change_points:
                change_points[vg_gen] = {}
            change_points[vg_gen].update(fields)

    if not change_points:
        return _apply_gen1_3_category_rule(
            [{"from_gen": intro_gen, "to_gen": None,
              "applies_to_games": None, **current}]
        )

    sorted_gens = sorted(change_points.keys())
    entries     = []
    prev_from   = intro_gen

    for cp_gen in sorted_gens:
        # Each past_value entry is a complete snapshot of all fields that differed
        # from current at that version_group. Apply only this span's own snapshot.
        entries.append({
            "from_gen"       : prev_from,
            "to_gen"         : cp_gen,
            "applies_to_games": None,
            **{**current, **change_points[cp_gen]},
        })
        prev_from = cp_gen + 1

    # Final span: fully current values
    entries.append({
        "from_gen"       : prev_from,
        "to_gen"         : None,
        "applies_to_games": None,
        **current,
    })

    return _apply_gen1_3_category_rule(entries)


def fetch_move(name: str) -> list:
    """
    Fetch one move from PokeAPI and return its versioned entry list.
    Raises ValueError on 404, ConnectionError on network failure.

    Returns a list of versioned dicts (same schema as moves.json values).
    """
    data = _get(f"move/{_name_to_slug(name)}")

    # Current (latest) values
    # Note: priority does not appear in past_values — it is constant across all
    # generations for a given move — so it is included once in current and
    # propagates to every versioned entry via **current.
    meta = data.get("meta") or {}
    effect = ""
    for entry in data.get("effect_entries", []):
        if entry.get("language", {}).get("name") == "en":
            effect = entry.get("short_effect", "").replace("\n", " ").strip()
            break
    current = {
        "type"        : _TYPE_NAMES.get(data["type"]["name"],
                                        data["type"]["name"].capitalize()),
        "category"    : _CATEGORY_NAMES.get(data["damage_class"]["name"],
                                            data["damage_class"]["name"].capitalize()),
        "power"       : data.get("power"),
        "accuracy"    : data.get("accuracy"),
        "pp"          : data.get("pp"),
        "priority"    : data.get("priority", 0),
        # R3 fields — constant across generations (not in past_values)
        # drain: negative = recoil (e.g. -33 for Flare Blitz), positive = hp drain
        "drain"        : meta.get("drain", 0) or 0,
        # effect_chance: % chance of secondary effect (e.g. 30 for Scald burn)
        "effect_chance": data.get("effect_chance") or 0,
        # ailment: secondary status effect name for display (e.g. "burn", "paralysis")
        "ailment"      : (meta.get("ailment") or {}).get("name", "none"),
        # effect: English short_effect text (constant across generations)
        "effect"       : effect,
    }

    intro_gen = _gen_name_to_int(data["generation"]["name"])
    past_vals = data.get("past_values", [])

    return _build_versioned_entries(current, intro_gen, past_vals)


def fetch_all_moves(dry_run: bool = False) -> dict:
    """
    Fetch the complete move table from PokeAPI.

    Returns a dict: {move_display_name: [versioned_entry, ...]}
    ready to be saved as cache/moves.json.

    dry_run=True fetches only the first 15 moves plus Flamethrower / Outrage /
    Thunderbolt (for assertion testing), without writing anything to disk.
    Prints a progress counter that overwrites the same line.
    """
    # 1. Get the full move name list
    all_moves_data = _get("move?limit=2000")
    all_slugs = [e["name"] for e in all_moves_data["results"]]

    if dry_run:
        sample  = all_slugs[:15]
        # Always include our test moves regardless of position in list
        for must_have in ("flamethrower", "outrage", "thunderbolt"):
            if must_have not in sample:
                sample.append(must_have)
        slugs_to_fetch = sample
    else:
        slugs_to_fetch = all_slugs

    total   = len(slugs_to_fetch)
    results = {}

    for i, slug in enumerate(slugs_to_fetch, start=1):
        # Progress counter — overwrites same line
        print(f"  Fetching moves: {i} / {total}   ", end="\r", flush=True)

        try:
            # Display name: prefer English name from /move/{slug}, use title slug as fallback
            move_data = _get(f"move/{slug}")
            display_name = _en_name(move_data.get("names", []), None)
            if not display_name:
                display_name = slug.replace("-", " ").title()

            meta = move_data.get("meta") or {}
            effect = ""
            for eff_entry in move_data.get("effect_entries", []):
                if eff_entry.get("language", {}).get("name") == "en":
                    effect = eff_entry.get("short_effect", "").replace("\n", " ").strip()
                    break
            current = {
                "type"         : _TYPE_NAMES.get(move_data["type"]["name"],
                                                 move_data["type"]["name"].capitalize()),
                "category"     : _CATEGORY_NAMES.get(move_data["damage_class"]["name"],
                                                     move_data["damage_class"]["name"].capitalize()),
                "power"        : move_data.get("power"),
                "accuracy"     : move_data.get("accuracy"),
                "pp"           : move_data.get("pp"),
                "priority"     : move_data.get("priority", 0),
                "drain"        : meta.get("drain", 0) or 0,
                "effect_chance": move_data.get("effect_chance") or 0,
                "ailment"      : (meta.get("ailment") or {}).get("name", "none"),
                "effect"       : effect,
            }

            intro_gen = _gen_name_to_int(move_data["generation"]["name"])
            past_vals = move_data.get("past_values", [])

            results[display_name] = _build_versioned_entries(current, intro_gen,
                                                              past_vals)
        except (ValueError, ConnectionError):
            pass   # skip moves that 404 or fail (rare alternate-form moves)

    print(f"  Fetched {len(results)} moves.                     ")
    return results


def fetch_missing_moves() -> dict:
    """
    Fetch only the moves not yet in moves.json.

    Queries the full move list from PokeAPI, checks each slug against the
    local cache (case-insensitive), and fetches only the missing ones.
    Returns {display_name: [versioned_entry, ...]} for newly fetched moves only.
    Returns an empty dict if the cache is already complete.

    Raises ConnectionError if the initial move-list request fails.
    Individual per-move failures are silently skipped (same behaviour as
    fetch_all_moves).
    """
    import pkm_cache as _cache

    all_data  = _get("move?limit=2000")
    all_slugs = [e["name"] for e in all_data["results"]]
    missing   = [s for s in all_slugs if _cache.get_move(s) is None]

    if not missing:
        return {}

    total   = len(missing)
    results = {}

    for i, slug in enumerate(missing, start=1):
        print(f"  Fetching moves: {i} / {total}   ", end="\r", flush=True)
        try:
            move_data    = _get(f"move/{slug}")
            display_name = _en_name(move_data.get("names", []), None)
            if not display_name:
                display_name = slug.replace("-", " ").title()

            meta   = move_data.get("meta") or {}
            effect = ""
            for eff_entry in move_data.get("effect_entries", []):
                if eff_entry.get("language", {}).get("name") == "en":
                    effect = eff_entry.get("short_effect", "").replace("\n", " ").strip()
                    break
            current = {
                "type"         : _TYPE_NAMES.get(move_data["type"]["name"],
                                                 move_data["type"]["name"].capitalize()),
                "category"     : _CATEGORY_NAMES.get(move_data["damage_class"]["name"],
                                                     move_data["damage_class"]["name"].capitalize()),
                "power"        : move_data.get("power"),
                "accuracy"     : move_data.get("accuracy"),
                "pp"           : move_data.get("pp"),
                "priority"     : move_data.get("priority", 0),
                "drain"        : meta.get("drain", 0) or 0,
                "effect_chance": move_data.get("effect_chance") or 0,
                "ailment"      : (meta.get("ailment") or {}).get("name", "none"),
                "effect"       : effect,
            }
            intro_gen = _gen_name_to_int(move_data["generation"]["name"])
            past_vals = move_data.get("past_values", [])
            results[display_name] = _build_versioned_entries(current, intro_gen, past_vals)
        except (ValueError, ConnectionError):
            pass

    print(f"  Fetched {len(results)} missing move(s).                    ")
    return results


# ── Step 4: Learnset fetch ────────────────────────────────────────────────────

# Learn-method slug → display label
_LEARN_METHOD_NAMES = {
    "level-up": "level-up",
    "machine":  "machine",
    "tutor":    "tutor",
    "egg":      "egg",
}

# Methods we surface (others like "light-ball-egg", "stadium-surfing" are skipped)
_LEARN_METHODS_KEPT = frozenset(["level-up", "machine", "tutor", "egg"])


def _fetch_machines(version_group_slugs: list) -> dict:
    """
    For every TM/HM in the given version groups, return a dict:
      { machine_resource_url: "TM06" | "HM04" | ... }

    We fetch /api/v2/machine?limit=2000 once, then filter by version_group.
    This is cached by the caller as cache/machines.json.
    """
    all_data   = _get("machine?limit=2000")
    vg_set     = set(version_group_slugs)
    result     = {}

    for entry in all_data.get("results", []):
        url = entry["url"]
        try:
            m    = _get(url.split("/api/v2/")[1].rstrip("/"))
            vg   = m.get("version_group", {}).get("name", "")
            if vg not in vg_set:
                continue
            item_name = m.get("item", {}).get("name", "")   # e.g. "tm06", "hm04"
            if item_name.startswith("tm"):
                label = f"TM{item_name[2:].lstrip('0') or '0'}"
            elif item_name.startswith("hm"):
                label = f"HM{item_name[2:].lstrip('0') or '0'}"
            else:
                label = item_name.upper()
            move_url = m.get("move", {}).get("url", "")
            result[move_url] = label
        except (ValueError, ConnectionError, KeyError):
            continue

    return result


# ── Step 4a: Machine table (TM/HM numbers) ───────────────────────────────────

def fetch_machines() -> dict:
    """
    Fetch the complete TM/HM machine table from PokeAPI.

    Returns a dict keyed by version-group slug:
      { "scarlet-violet": { "flamethrower": "TM126", ... }, ... }

    This is a one-time bulk fetch (~900 entries).  The result is cached in
    machines.json and reused forever — TM assignments never change for a
    given game.
    """
    print("  Fetching machine table from PokeAPI...", end=" ", flush=True)
    all_data = _get("machine?limit=2000")
    # PokeAPI machine list entries only have "url", no "name"
    # e.g. {"url": "https://pokeapi.co/api/v2/machine/1/"}
    ids = [e["url"].rstrip("/").split("/")[-1] for e in all_data["results"]]

    result = {}   # {vg_slug: {move_slug: "TM##"}}
    total  = len(ids)

    for i, machine_id in enumerate(ids, start=1):
        if i % 50 == 0 or i == total:
            print(f"\r  Fetching machines: {i} / {total}   ", end="", flush=True)
        try:
            m    = _get(f"machine/{machine_id}")
            vg   = m["version_group"]["name"]
            move = m["move"]["name"]          # slug e.g. "flamethrower"
            item = m["item"]["name"]          # e.g. "tm35" or "hm01"
            # Format: "tm35" → "TM35", "hm04" → "HM04"
            label = item.upper().replace("TM0", "TM").replace("HM0", "HM")
            # Keep zero-padding for 1-digit numbers (TM01..TM09)
            # PokeAPI uses tm01 not tm1, so upper() is enough
            if vg not in result:
                result[vg] = {}
            result[vg][move] = item.upper()
        except (ValueError, KeyError):
            pass   # skip malformed entries silently

    print(f"\r  Machine table: {sum(len(v) for v in result.values())} entries "
          f"across {len(result)} version groups.")
    return result


# ── Step 4b: Learnset fetch ───────────────────────────────────────────────────

def _slug_to_display(slug: str) -> str:
    """
    Best-effort conversion of a PokeAPI move slug to a display name.
    e.g. "dragon-dance" → "Dragon Dance", "10000000-volt-thunderbolt" → keeps as-is
    Used when the move is not yet in moves.json cache.
    """
    return slug.replace("-", " ").title()


def fetch_learnset(variety_slug: str, form_name: str, game: str,
                   machines: dict | None = None) -> dict:
    """
    Fetch the learnset for one specific Pokemon form in a specific game.

    Args:
        variety_slug: PokeAPI variety slug (e.g. "charizard", "moltres-galar").
                      Each form has its own slug and its own move list on PokeAPI.
        form_name:    Display name for this form (e.g. "Galarian Moltres").
                      Used as the key in the returned forms dict.
        game:         Display game name (e.g. "Scarlet / Violet").
        machines:     Pre-loaded machines dict (from cache or fetch_machines()).
                      If None, TM/HM labels fall back to the move name only.

    Returns a dict matching the cache/learnsets schema:
      {
        "pokemon" : "moltres-galar",
        "game"    : "Scarlet / Violet",
        "forms"   : {
          "Galarian Moltres": {
            "level-up": [{"move": "Fiery Wrath", "level": 35}],
            "machine":  [{"move": "Dark Pulse",  "tm": "TM79"}],
            ...
          }
        }
      }

    Raises ValueError if the Pokemon is not found.
    Raises ConnectionError on network failure.
    """
    vg_slugs = set(GAME_TO_VERSION_GROUPS.get(game, []))
    if not vg_slugs:
        raise ValueError(f"Game '{game}' not found in GAME_TO_VERSION_GROUPS.")

    # Fetch the specific variety's data (each form has its own move list)
    pkm_data = _get(f"pokemon/{variety_slug}")

    # Build learnset grouped by learn method
    learnset: dict[str, list] = {
        "level-up": [],
        "machine" : [],
        "tutor"   : [],
        "egg"     : [],
    }

    machines_vg = {}  # merged machine lookup across all version groups for this game
    if machines:
        for vg in vg_slugs:
            machines_vg.update(machines.get(vg, {}))

    for move_entry in pkm_data.get("moves", []):
        move_slug = move_entry["move"]["name"]
        move_display = _slug_to_display(move_slug)

        for detail in move_entry.get("version_group_details", []):
            if detail["version_group"]["name"] not in vg_slugs:
                continue

            method = detail["move_learn_method"]["name"]
            level  = detail.get("level_learned_at", 0)

            if method == "level-up":
                learnset["level-up"].append({
                    "move" : move_display,
                    "level": level if level > 0 else None,
                })
            elif method == "machine":
                entry = {"move": move_display}
                if machines_vg:
                    tm = machines_vg.get(move_slug)
                    if tm:
                        entry["tm"] = tm
                learnset["machine"].append(entry)
            elif method == "tutor":
                learnset["tutor"].append({"move": move_display})
            elif method == "egg":
                learnset["egg"].append({"move": move_display})
            # Ignore other methods (e.g. "stadium-surfing-pikachu", "light-ball-egg")

            break  # one version_group match is enough; don't double-count
            # (some games have 2 VG slugs like red-blue + yellow — both may appear)

    # Sort level-up moves by level (None last)
    learnset["level-up"].sort(key=lambda e: (e["level"] is None, e["level"] or 0))

    # Remove empty method keys for cleanliness
    learnset = {k: v for k, v in learnset.items() if v}

    return {
        "pokemon": variety_slug,
        "game"   : game,
        "forms"  : {form_name: learnset},
    }


# ── Self-test ──────────────────────────────────────────────────────────────────

def _test_fetch_pokemon_live():
    """
    Live API test for fetch_pokemon().
    Checks known-good values covering key edge cases:
      - Charizard : multi-form with Mega X, Mega Y, Gigantamax (4 forms total)
      - Garchomp  : Garchomp + Mega Garchomp + Mega Garchomp Z (3 forms)
      - Rotom     : 6 forms with distinct types (deduplication must NOT fire)
      - Eevee     : single species, all Eeveelutions are separate species → 1 form

    On any mismatch, the full list of found form names is printed so you can
    see exactly what the API returned.
    """
    print("\n  Live fetch_pokemon() tests (makes network requests)...")

    # Each case: (input_name, exp_gen, exp_form_count,
    #             [(form_name, types), ...])   -- spot-checked forms
    cases = [
        ("charizard", 1, 4, [
            ("Charizard",        ["Fire", "Flying"]),
            ("Mega Charizard X", ["Fire", "Dragon"]),
            ("Mega Charizard Y", ["Fire", "Flying"]),
        ]),
        ("garchomp", 4, 3, [
            ("Garchomp",      ["Dragon", "Ground"]),
            ("Mega Garchomp", ["Dragon", "Ground"]),
        ]),
        ("rotom", 4, 6, [
            ("Heat Rotom",  ["Electric", "Fire"]),
            ("Wash Rotom",  ["Electric", "Water"]),
        ]),
        ("eevee", 1, 1, [
            ("Eevee", ["Normal"]),
        ]),
    ]

    all_ok = True
    for input_name, exp_gen, exp_form_count, spot_checks in cases:
        try:
            data = fetch_pokemon(input_name)
            found_names = [f["name"] for f in data["forms"]]

            # Gen check
            assert data["species_gen"] == exp_gen, \
                f"expected gen {exp_gen}, got {data['species_gen']}"

            # Form count check — print found names on mismatch
            assert len(data["forms"]) == exp_form_count, \
                (f"expected {exp_form_count} forms, got {len(data['forms'])}. "
                 f"Found: {found_names}")

            # Per-form spot checks
            for form_name, exp_types in spot_checks:
                form = next((f for f in data["forms"] if f["name"] == form_name), None)
                assert form is not None, \
                    f"form '{form_name}' not found. Found: {found_names}"
                assert form["types"] == exp_types, \
                    f"{form_name}: expected types {exp_types}, got {form['types']}"
                assert isinstance(form["base_stats"], dict) and "hp" in form["base_stats"], \
                    f"{form_name}: base_stats missing or malformed"

            base = data["forms"][0]
            print(f"    [OK]   {input_name:<12}  {len(data['forms'])} forms  "
                  f"base={base['name']}  types={base['types']}  "
                  f"HP={base['base_stats']['hp']}")
            if len(data["forms"]) > 1:
                for f in data["forms"][1:]:
                    print(f"             + {f['name']}  {f['types']}")

        except AssertionError as e:
            print(f"    [FAIL] {input_name}: {e}")
            all_ok = False
        except (ValueError, ConnectionError) as e:
            print(f"    [FAIL] {input_name}: {e}")
            all_ok = False

    if all_ok:
        print("  [PASS] All fetch_pokemon() assertions passed")
    else:
        print("  [FAIL] Some fetch_pokemon() assertions failed -- see above")
    return all_ok


    """Assert every GAMES entry has at least one slug in the mapping."""
    missing = []
    for game_name, _era, _gen in GAMES:
        slugs = GAME_TO_VERSION_GROUPS.get(game_name)
        if not slugs:
            missing.append(game_name)
    assert not missing, f"Missing version-group mapping for: {missing}"
    print("  [PASS] All GAMES entries have at least one version-group slug")


def _test_build_versioned_entries():
    """
    Offline unit tests for _build_versioned_entries() + _apply_gen1_3_category_rule().
    No network required — all inputs are synthetic.
    """
    errors = []

    def chk_entry(label, entry, **expected):
        for k, v in expected.items():
            if entry.get(k) != v:
                errors.append(f"{label}: {k} expected {v!r} got {entry.get(k)!r}  full={entry}")
                return False
        return True

    # ── Test 1: No past_values — single current entry ─────────────────────────
    r = _build_versioned_entries(
        {"type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35},
        1, [])
    assert len(r) == 1
    chk_entry("T1", r[0], from_gen=1, to_gen=None, power=40, pp=35, category="Physical")

    # ── Test 2: Flamethrower-style — Fire (Special in Gen1-3, and stays Special) ──
    # past_value up to x-y (gen6) had power=95; current is power=90.
    # Fire is already Special → Gen1-3 rule causes NO split.
    # Expected: [Gen1-6: power=95, Special] [Gen7+: power=90, Special]
    r = _build_versioned_entries(
        {"type": "Fire", "category": "Special", "power": 90, "accuracy": 100, "pp": 15},
        1,
        [{"version_group": {"name": "x-y"}, "power": 95, "accuracy": None,
          "pp": None, "type": None, "move_damage_class": None}])
    assert len(r) == 2, f"T2: expected 2 entries, got {len(r)}: {r}"
    chk_entry("T2a", r[0], from_gen=1, to_gen=6, power=95, category="Special")
    chk_entry("T2b", r[1], from_gen=7, to_gen=None, power=90, category="Special")

    # ── Test 3: Outrage-style — Dragon (Special in Gen1-3 BUT stored as Physical) ─
    # past_value 1: up to diamond-pearl (gen4) → power=90, pp=10
    # past_value 2: up to black-white (gen5)   → power=120, pp=15
    # current (gen6+): power=120, pp=10, Physical
    # Dragon is Special in Gen1-3 → first span (gen2-4) must be split at gen3/gen4.
    # Expected:
    #   [Gen2-3: Special, power=90, pp=10]
    #   [Gen4-4: Physical, power=90, pp=10]
    #   [Gen5-5: Physical, power=120, pp=15]
    #   [Gen6+:  Physical, power=120, pp=10]
    r = _build_versioned_entries(
        {"type": "Dragon", "category": "Physical", "power": 120, "accuracy": 100, "pp": 10},
        2,
        [
            {"version_group": {"name": "diamond-pearl"}, "power": 90, "accuracy": None,
             "pp": 10, "type": None, "move_damage_class": None},
            {"version_group": {"name": "black-white"}, "power": 120, "accuracy": None,
             "pp": 15, "type": None, "move_damage_class": None},
        ])
    assert len(r) == 4, f"T3: expected 4 entries, got {len(r)}: {[e for e in r]}"
    chk_entry("T3a", r[0], from_gen=2, to_gen=3, category="Special",  power=90, pp=10)
    chk_entry("T3b", r[1], from_gen=4, to_gen=4, category="Physical", power=90, pp=10)
    chk_entry("T3c", r[2], from_gen=5, to_gen=5, category="Physical", power=120, pp=15)
    chk_entry("T3d", r[3], from_gen=6, to_gen=None, category="Physical", power=120, pp=10)

    # ── Test 4: Physical Normal move — Gen1-3 rule agrees, no split ───────────
    r = _build_versioned_entries(
        {"type": "Normal", "category": "Physical", "power": 80, "accuracy": 100, "pp": 15},
        1,
        [{"version_group": {"name": "black-white"}, "power": 80, "accuracy": None,
          "pp": 20, "type": None, "move_damage_class": None}])
    assert len(r) == 2, f"T4: expected 2 entries, got {len(r)}: {r}"
    chk_entry("T4a", r[0], from_gen=1, to_gen=5, category="Physical")  # no split needed
    chk_entry("T4b", r[1], from_gen=6, to_gen=None, category="Physical")

    # ── Test 5: Unknown version_group — silently skipped ─────────────────────
    r = _build_versioned_entries(
        {"type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35},
        1,
        [{"version_group": {"name": "unknown-xyz"}, "power": 50, "accuracy": None,
          "pp": None, "type": None, "move_damage_class": None}])
    assert len(r) == 1
    chk_entry("T5", r[0], power=40)

    if errors:
        for e in errors:
            print(f"    [FAIL] {e}")
        return False
    print("  [PASS] All 5 offline _build_versioned_entries tests passed")
    return True


def _test_fetch_moves_live():
    """
    Live API test for fetch_all_moves() — dry_run fetches ~18 moves.

    Assertions match PokeAPI's actual data (not Bulbapedia), with the
    Gen1-3 category rule applied in code:

    Outrage (Dragon, intro Gen2):
      - Gen1      : not in game
      - Gen2-3    : Special (Dragon type → Special via Gen1-3 rule), power=90, pp=10
      - Gen4      : Physical, power=90, pp=10
      - Gen5      : Physical, power=120, pp=15   (PokeAPI records power change at Gen5)
      - Gen9      : Physical, power=120, pp=10

    Flamethrower (Fire, intro Gen1):
      - Gen1, Gen5, Gen6 : Special, power=95   (PokeAPI past_value is under x-y, so
      - Gen7+            : Special, power=90    Gen6 still returns old value)

    Thunderbolt (Electric, intro Gen1):
      - Gen9  : power=90, pp=15
      ⚠  Legends: Z-A cooldown system not yet in PokeAPI — assertion removed.
    """
    print("\n  Live fetch_all_moves(dry_run=True) test...")
    moves = fetch_all_moves(dry_run=True)

    def resolve(move_name, game_gen, game=""):
        versions = moves.get(move_name)
        if not versions:
            return None
        for entry in versions:
            games_list = entry.get("applies_to_games") or []
            if game and game in games_list:
                return entry
        for entry in versions:
            fg = entry.get("from_gen")
            tg = entry.get("to_gen")
            if fg is None:
                continue
            if fg <= game_gen and (tg is None or game_gen <= tg):
                return entry
        return None

    def chk(label, result, **expected):
        if result is None:
            if "none" in expected:
                print(f"    [OK]   {label}  (not available in this gen)")
                return True
            print(f"    [FAIL] {label}: expected {expected} but got None")
            return False
        for k, v in expected.items():
            if k == "none":
                continue
            if result.get(k) != v:
                print(f"    [FAIL] {label}: {k} expected {v!r} got {result.get(k)!r}")
                print(f"           Full entry: {result}")
                return False
        detail = "  ".join(f"{k}={v}" for k, v in expected.items() if k != "none")
        print(f"    [OK]   {label}  ({detail})")
        return True

    all_ok = True
    checks = [
        # Outrage — Dragon type, Gen1-3 rule gives Special for Gen2-3
        ("Outrage/Gen1",  resolve("Outrage", 1),  dict(none=True)),
        ("Outrage/Gen2",  resolve("Outrage", 2),  dict(category="Special",  power=90,  pp=10)),
        ("Outrage/Gen3",  resolve("Outrage", 3),  dict(category="Special",  power=90,  pp=10)),
        ("Outrage/Gen4",  resolve("Outrage", 4),  dict(category="Physical", power=90,  pp=10)),
        ("Outrage/Gen5",  resolve("Outrage", 5),  dict(category="Physical", power=120, pp=15)),
        ("Outrage/Gen9",  resolve("Outrage", 9),  dict(category="Physical", power=120, pp=10)),
        # Flamethrower — PokeAPI past_value under x-y means Gen6 still has old power
        ("Flamethrower/Gen1", resolve("Flamethrower", 1), dict(category="Special", power=95, pp=15)),
        ("Flamethrower/Gen5", resolve("Flamethrower", 5), dict(category="Special", power=95, pp=15)),
        ("Flamethrower/Gen6", resolve("Flamethrower", 6), dict(category="Special", power=95, pp=15)),
        ("Flamethrower/Gen7", resolve("Flamethrower", 7), dict(category="Special", power=90, pp=15)),
        ("Flamethrower/Gen9", resolve("Flamethrower", 9), dict(category="Special", power=90, pp=15)),
        # Thunderbolt — same nerf boundary as Flamethrower
        ("Thunderbolt/Gen9",  resolve("Thunderbolt", 9),  dict(power=90, pp=15)),
    ]

    for label, result, expected in checks:
        if not chk(label, result, **expected):
            all_ok = False

    if all_ok:
        print("  [PASS] All 12 live move assertions passed")
    else:
        print("  [FAIL] Some move assertions failed — see above")
        for move in ("Outrage", "Flamethrower", "Thunderbolt"):
            if move in moves:
                print(f"\n  Raw entries for {move}:")
                for e in moves[move]:
                    print(f"    {e}")
    return all_ok


    """
    Live API test for fetch_all_moves() / _build_versioned_entries().

    Runs --dry-run (fetches ~18 moves including Flamethrower/Outrage/Thunderbolt)
    then applies the same 12 assertions used in pkm_cache.py self-test.
    """
    print("\n  Live fetch_all_moves(dry_run=True) test...")
    moves = fetch_all_moves(dry_run=True)

    # Helper
    def resolve(move_name, game_gen, game=""):
        versions = moves.get(move_name)
        if not versions:
            return None
        for entry in versions:
            games_list = entry.get("applies_to_games") or []
            if game and game in games_list:
                return entry
        for entry in versions:
            fg = entry.get("from_gen")
            tg = entry.get("to_gen")
            if fg is None:
                continue
            if fg <= game_gen and (tg is None or game_gen <= tg):
                return entry
        return None

    def chk(label, result, **expected):
        if result is None:
            if "none" in expected:
                print(f"    [OK]   {label}  (not available in this gen)")
                return True
            print(f"    [FAIL] {label}: expected {expected} but got None")
            return False
        for k, v in expected.items():
            if k == "none":
                continue
            if result.get(k) != v:
                print(f"    [FAIL] {label}: {k} expected {v!r} got {result.get(k)!r}")
                print(f"           Full entry: {result}")
                return False
        detail = "  ".join(f"{k}={v}" for k, v in expected.items() if k != "none")
        print(f"    [OK]   {label}  ({detail})")
        return True

    all_ok = True
    checks = [
        # Outrage
        ("Outrage / Gen1",  resolve("Outrage", 1),            dict(none=True)),
        ("Outrage / Gen2",  resolve("Outrage", 2),            dict(category="Special",  power=90,  pp=15)),
        ("Outrage / Gen3",  resolve("Outrage", 3),            dict(category="Special",  power=90,  pp=15)),
        ("Outrage / Gen4",  resolve("Outrage", 4),            dict(category="Physical", power=120, pp=15)),
        ("Outrage / Gen5+", resolve("Outrage", 5),            dict(category="Physical", power=120, pp=10)),
        ("Outrage / Gen9",  resolve("Outrage", 9),            dict(category="Physical", power=120, pp=10)),
        # Flamethrower
        ("Flamethrower/Gen1",  resolve("Flamethrower", 1),    dict(category="Special",  power=95,  pp=15)),
        ("Flamethrower/Gen5",  resolve("Flamethrower", 5),    dict(category="Special",  power=95,  pp=15)),
        ("Flamethrower/Gen6",  resolve("Flamethrower", 6),    dict(category="Special",  power=90,  pp=15)),
        ("Flamethrower/Gen9",  resolve("Flamethrower", 9),    dict(category="Special",  power=90,  pp=15)),
        # Thunderbolt — Z-A game override + standard gen9
        ("Thunderbolt/Z-A",    resolve("Thunderbolt", 9, "Legends: Z-A"), dict(cooldown=2)),
        ("Thunderbolt/Gen9",   resolve("Thunderbolt", 9),     dict(power=90, pp=15)),
    ]

    for label, result, expected in checks:
        if not chk(label, result, **expected):
            all_ok = False

    if all_ok:
        print("  [PASS] All 12 move assertions passed")
    else:
        print("  [FAIL] Some move assertions failed — see above")
        # Show raw entries for failed moves to aid debugging
        for move in ("Outrage", "Flamethrower", "Thunderbolt"):
            if move in moves:
                print(f"\n  Raw entries for {move}:")
                for e in moves[move]:
                    print(f"    {e}")
    return all_ok


    """Assert every GAMES entry has at least one slug in the mapping."""
    missing = []
    for game_name, _era, _gen in GAMES:
        slugs = GAME_TO_VERSION_GROUPS.get(game_name)
        if not slugs:
            missing.append(game_name)
    assert not missing, f"Missing version-group mapping for: {missing}"
    print("  [PASS] All GAMES entries have at least one version-group slug")


def _test_mapping_completeness():
    """Assert every GAMES entry has at least one slug in the mapping."""
    missing = []
    for game_name, _era, _gen in GAMES:
        slugs = GAME_TO_VERSION_GROUPS.get(game_name)
        if not slugs:
            missing.append(game_name)
    assert not missing, f"Missing version-group mapping for: {missing}"
    print("  [PASS] All GAMES entries have at least one version-group slug")


def _test_reverse_map():
    """Assert every slug in the mapping has a reverse entry in VERSION_GROUP_TO_GEN."""
    missing = []
    for game_name, slugs in GAME_TO_VERSION_GROUPS.items():
        for slug in slugs:
            if slug not in VERSION_GROUP_TO_GEN:
                missing.append((game_name, slug))
    assert not missing, f"Reverse map missing entries: {missing}"
    print("  [PASS] VERSION_GROUP_TO_GEN covers all slugs")


def _test_gen_values():
    """Spot-check generation numbers on specific version groups."""
    cases = [
        ("red-blue",                        1),
        ("yellow",                          1),
        ("gold-silver",                     2),
        ("crystal",                         2),
        ("firered-leafgreen",               3),
        ("diamond-pearl",                   4),
        ("platinum",                        4),
        ("black-white",                     5),
        ("black-2-white-2",                 5),
        ("x-y",                             6),
        ("sun-moon",                        7),
        ("sword-shield",                    8),
        ("legends-arceus",                  8),
        ("scarlet-violet",                  9),
        ("legends-za",                      9),
    ]
    failures = []
    for slug, expected_gen in cases:
        actual = VERSION_GROUP_TO_GEN.get(slug)
        if actual != expected_gen:
            failures.append(f"{slug}: expected gen {expected_gen}, got {actual}")
    assert not failures, "\n".join(failures)
    print(f"  [PASS] Gen values correct for {len(cases)} spot-checked slugs")


def _verify_slugs_live():
    """Hit the API for every slug and confirm 200 response. Prints pass/fail per slug."""
    print("\n  Live API verification (this makes network requests)...")
    all_ok = True
    for game_name, slugs in GAME_TO_VERSION_GROUPS.items():
        for slug in slugs:
            try:
                data = _get(f"version-group/{slug}/")
                assert data["name"] == slug, f"Name mismatch: got {data['name']}"
                print(f"    [OK]   {slug}")
            except (ValueError, ConnectionError, AssertionError) as e:
                print(f"    [FAIL] {slug}  -- {e}")
                all_ok = False
    if all_ok:
        print("  [PASS] All slugs verified against live API")
    else:
        print("  [FAIL] Some slugs did not verify -- see above")
    return all_ok


def _print_mapping_table():
    """Print the full mapping table for manual review."""
    print("\n  GAME_TO_VERSION_GROUPS:")
    print(f"  {'Game':<40}  {'PokeAPI slugs'}")
    print(f"  {'-'*40}  {'-'*35}")
    for game_name, _era, _gen in GAMES:
        slugs = GAME_TO_VERSION_GROUPS.get(game_name, ["(MISSING)"])
        print(f"  {game_name:<40}  {', '.join(slugs)}")
    print()
    print(f"  VERSION_GROUP_TO_GEN ({len(VERSION_GROUP_TO_GEN)} entries):")
    for slug, gen in sorted(VERSION_GROUP_TO_GEN.items(), key=lambda x: x[1]):
        print(f"    {slug:<45}  gen {gen}")


# ── Main ──────────────────────────────────────────────────────────────────────

def _test_fetch_pokemon_offline():
    """
    Offline unit tests for fetch_pokemon() using a mocked _get().
    Covers egg_groups field extraction (Pythonmon-27A).
    """
    errors = []
    def _chk(label, cond, detail=""):
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}" + (f": {detail}" if detail else ""))
            errors.append(label)

    orig_get = globals()["_get"]

    def _make_pkm(variety_slug, types, form_slugs):
        return {
            "types"    : [{"type": {"name": t.lower()}, "slot": i+1}
                          for i, t in enumerate(types)],
            "stats"    : [{"stat": {"name": "hp"}, "base_stat": 50}],
            "abilities": [],
            "forms"    : [{"name": s} for s in form_slugs],
        }

    def _make_species(varieties, egg_groups=None, chain_id=1):
        return {
            "generation"     : {"name": "generation-i"},
            "names"          : [{"language": {"name": "en"}, "name": "TestMon"}],
            "varieties"      : [
                {"pokemon": {"name": slug}, "is_default": is_def}
                for slug, is_def in varieties
            ],
            "egg_groups"     : [{"name": g} for g in (egg_groups or [])],
            "evolution_chain": {"url": f"https://pokeapi.co/api/v2/evolution-chain/{chain_id}/"}
                               if chain_id is not None else None,
        }

    def _make_form(en_name):
        return {"names": [{"language": {"name": "en"}, "name": en_name}]}

    # ── Test: egg_groups extracted correctly ──────────────────────────────────
    _resp = {
        "pokemon-species/testmon": _make_species(
            [("testmon", True)], egg_groups=["monster", "dragon"]
        ),
        "pokemon/testmon"        : _make_pkm("testmon", ["Fire"], ["testmon"]),
        "pokemon-form/testmon"   : _make_form("Testmon"),
    }
    globals()["_get"] = lambda path: _resp[path]
    try:
        result = fetch_pokemon("testmon")
        _chk("egg_groups: two groups extracted",
             result.get("egg_groups") == ["monster", "dragon"],
             str(result.get("egg_groups")))
    finally:
        globals()["_get"] = orig_get

    # ── Test: empty egg_groups → [] ───────────────────────────────────────────
    _resp2 = {
        "pokemon-species/eggless": _make_species(
            [("eggless", True)], egg_groups=[]
        ),
        "pokemon/eggless"        : _make_pkm("eggless", ["Normal"], ["eggless"]),
        "pokemon-form/eggless"   : _make_form("Eggless"),
    }
    globals()["_get"] = lambda path: _resp2[path]
    try:
        result2 = fetch_pokemon("eggless")
        _chk("egg_groups: empty list → []",
             result2.get("egg_groups") == [],
             str(result2.get("egg_groups")))
    finally:
        globals()["_get"] = orig_get

    # ── Test: no-eggs group preserved ─────────────────────────────────────────
    _resp3 = {
        "pokemon-species/legendary": _make_species(
            [("legendary", True)], egg_groups=["no-eggs"]
        ),
        "pokemon/legendary"        : _make_pkm("legendary", ["Psychic"], ["legendary"]),
        "pokemon-form/legendary"   : _make_form("Legendary"),
    }
    globals()["_get"] = lambda path: _resp3[path]
    try:
        result3 = fetch_pokemon("legendary")
        _chk("egg_groups: no-eggs group preserved",
             result3.get("egg_groups") == ["no-eggs"],
             str(result3.get("egg_groups")))
    finally:
        globals()["_get"] = orig_get

    # ── Test: evolution_chain_id extracted correctly ───────────────────────────
    _resp4 = {
        "pokemon-species/evomon": _make_species(
            [("evomon", True)], chain_id=42
        ),
        "pokemon/evomon"        : _make_pkm("evomon", ["Fire"], ["evomon"]),
        "pokemon-form/evomon"   : _make_form("Evomon"),
    }
    globals()["_get"] = lambda path: _resp4[path]
    try:
        result4 = fetch_pokemon("evomon")
        _chk("evolution_chain_id: extracted from URL",
             result4.get("evolution_chain_id") == 42,
             str(result4.get("evolution_chain_id")))
    finally:
        globals()["_get"] = orig_get

    # ── Test: missing evolution_chain → None ──────────────────────────────────
    _resp5 = {
        "pokemon-species/nochain": _make_species(
            [("nochain", True)], chain_id=None
        ),
        "pokemon/nochain"        : _make_pkm("nochain", ["Normal"], ["nochain"]),
        "pokemon-form/nochain"   : _make_form("Nochain"),
    }
    globals()["_get"] = lambda path: _resp5[path]
    try:
        result5 = fetch_pokemon("nochain")
        _chk("evolution_chain_id: missing chain → None",
             result5.get("evolution_chain_id") is None,
             str(result5.get("evolution_chain_id")))
    finally:
        globals()["_get"] = orig_get

    print()
    if errors:
        print(f"  FAILED ({len(errors)}): {errors}")
        return False
    print("  [PASS] All 5 offline fetch_pokemon tests passed")
    return True


def _test_check_connectivity():
    """
    Offline tests for check_connectivity() using a mocked urlopen.
    Temporarily replaces urllib.request.urlopen at the module level.
    """
    import urllib.request as _ureq
    import urllib.error   as _uerr

    orig_urlopen = _ureq.urlopen
    results = []

    def _chk(label, cond):
        if cond:
            print(f"  [PASS] check_connectivity: {label}")
            results.append(True)
        else:
            print(f"  [FAIL] check_connectivity: {label}")
            results.append(False)

    try:
        # T1: urlopen succeeds → True
        class _MockResp:
            def read(self): return b"{}"
            def __enter__(self): return self
            def __exit__(self, *a): pass

        _ureq.urlopen = lambda req, timeout=None: _MockResp()
        _chk("urlopen succeeds → True", check_connectivity() is True)

        # T2: URLError → False
        def _raise_url(*a, **kw):
            raise _uerr.URLError("network unreachable")
        _ureq.urlopen = _raise_url
        _chk("URLError → False", check_connectivity() is False)

        # T3: generic OSError → False
        def _raise_os(*a, **kw):
            raise OSError("timed out")
        _ureq.urlopen = _raise_os
        _chk("OSError → False", check_connectivity() is False)

    finally:
        _ureq.urlopen = orig_urlopen

    if all(results):
        print("  [PASS] All 3 check_connectivity tests passed")
    else:
        print(f"  [FAIL] {results.count(False)} check_connectivity test(s) failed")
    return all(results)


def main():
    verify  = "--verify"   in sys.argv
    dry_run = "--dry-run"  in sys.argv

    print()
    print("pkm_pokeapi.py -- Steps 1+2+3 self-test")
    print("=" * 60)

    # Step 1 — offline
    _print_mapping_table()
    print("\nRunning Step 1 assertions (offline)...")
    _test_mapping_completeness()
    _test_reverse_map()
    _test_gen_values()
    print("  [PASS] All Step 1 assertions passed")

    print("\nRunning Step 3 offline unit tests...")
    _test_build_versioned_entries()

    print("\nRunning fetch_pokemon offline unit tests...")
    _test_fetch_pokemon_offline()

    print("\nRunning check_connectivity offline tests...")
    _test_check_connectivity()

    if verify:
        print()
        ok1 = _verify_slugs_live()
        ok2 = _test_fetch_pokemon_live()
        ok3 = _test_fetch_moves_live()
        sys.exit(0 if (ok1 and ok2 and ok3) else 1)
    elif dry_run:
        ok3 = _test_fetch_moves_live()
        sys.exit(0 if ok3 else 1)
    else:
        print("\n  Tip: run with --verify to test all live API calls (Steps 1+2+3)")
        print("  Tip: run with --dry-run to test only move fetching (Step 3, ~18 moves)")

    print("\nOffline checks complete.")


# ── Ability index fetch ───────────────────────────────────────────────────────

def fetch_abilities_index() -> dict:
    """
    Fetch all abilities from PokeAPI and return a compact index dict.

    Schema: { "blaze": {"name": "Blaze", "gen": 3,
                         "short_effect": "Powers up Fire-type moves..."}, ... }

    Only includes abilities with at least one English effect entry.
    Raises ConnectionError on network failure.
    """
    listing = _get("ability?limit=400")
    index   = {}
    total   = len(listing.get("results", []))
    print(f"  Fetching {total} abilities...", end=" ", flush=True)
    for i, item in enumerate(listing.get("results", []), 1):
        if i % 50 == 0:
            print(f"{i}/{total}", end=" ", flush=True)
        slug = item["name"]
        data = _get(f"ability/{slug}")

        # English short_effect
        short_effect = ""
        for entry in data.get("effect_entries", []):
            if entry.get("language", {}).get("name") == "en":
                short_effect = entry.get("short_effect", "")
                break

        if not short_effect:
            continue   # skip abilities with no English description

        # Display name
        en_name = _en_name(data.get("names", []), slug.replace("-", " ").title())

        # Generation introduced
        gen_slug = data.get("generation", {}).get("name", "")
        gen_num  = _gen_name_to_int(gen_slug)

        index[slug] = {
            "name"        : en_name,
            "gen"         : gen_num,
            "short_effect": short_effect,
        }
    print("done.")
    return index


# ── Per-ability detail fetch ──────────────────────────────────────────────────

def fetch_ability_detail(slug: str) -> dict:
    """
    Fetch full detail for one ability from PokeAPI.

    Returns:
      {
        "slug"   : "blaze",
        "effect" : "full English effect text",
        "pokemon": [{"name": "Charizard", "is_hidden": false}, ...]
      }

    Raises ConnectionError on network failure.
    """
    data = _get(f"ability/{slug}")

    # Full English effect
    effect = ""
    for entry in data.get("effect_entries", []):
        if entry.get("language", {}).get("name") == "en":
            effect = entry.get("effect", "").replace("\n", " ").strip()
            break

    # Pokémon list with display names
    pokemon = []
    for p in data.get("pokemon", []):
        pkm_name = p["pokemon"]["name"].replace("-", " ").title()
        pokemon.append({
            "name"     : pkm_name,
            "is_hidden": p["is_hidden"],
        })
    pokemon.sort(key=lambda x: x["name"])

    return {
        "slug"   : slug,
        "effect" : effect,
        "pokemon": pokemon,
    }


# ── Nature fetch ──────────────────────────────────────────────────────────────

def fetch_natures() -> dict:
    """
    Fetch all 25 natures from PokeAPI and return a dict keyed by display name.

    Schema per entry:
      {
        "name"      : "Adamant",
        "increased" : "attack",          # PokeAPI stat slug, or null for neutral
        "decreased" : "special-attack",  # PokeAPI stat slug, or null for neutral
      }

    Raises ConnectionError on network failure.
    """
    listing = _get("nature?limit=25")
    natures = {}
    for item in listing.get("results", []):
        data = _get(f"nature/{item['name']}")
        inc_raw = data.get("increased_stat")
        dec_raw = data.get("decreased_stat")
        en_name = _en_name(data.get("names", []), item["name"].capitalize())
        natures[en_name] = {
            "name"      : en_name,
            "increased" : inc_raw["name"] if inc_raw else None,
            "decreased" : dec_raw["name"] if dec_raw else None,
        }
    return natures


# ── Form display name fetch ───────────────────────────────────────────────────

def fetch_form_display_name(slug: str) -> str | None:
    """
    Return the English display name for a Pokemon variety slug, using the
    pokemon-form endpoint.

    Returns the English name string, or None if the names list is empty
    (caller should fall back to slug-to-title) or on network failure.

    Examples:
      "charizard-mega-x"  → "Mega Charizard X"
      "magearna-original" → "Original Color Magearna"
      "mr-mime"           → "Mr. Mime"
      "nidoran-f"         → "Nidoran♀"
      "tapu-koko"         → "Tapu Koko"
      "type-null"         → "Type: Null"

    Raises ConnectionError on network failure (caller should handle).
    """
    try:
        data = _get(f"pokemon-form/{slug}")
        name = _en_name(data.get("names", []), None)
        return name   # None if names list was empty
    except ValueError:
        return None   # 404 — unknown slug


# ── Evolution chain fetch ─────────────────────────────────────────────────────

def _parse_chain_id(species: dict) -> int | None:
    """Extract the evolution chain ID from a pokemon-species response."""
    url = (species.get("evolution_chain") or {}).get("url", "")
    if not url:
        return None
    try:
        return int(url.rstrip("/").split("/")[-1])
    except (ValueError, IndexError):
        return None


def fetch_evolution_chain(chain_id: int) -> dict:
    """
    Fetch the raw evolution chain from PokeAPI.

    Returns the `chain` node dict directly — the root of the recursive tree
    that `feat_evolution._flatten_chain` expects.

    Raises ValueError on 404 (unknown chain_id).
    Raises ConnectionError on network failure.
    """
    data = _get(f"evolution-chain/{chain_id}")
    return data["chain"]


# ── Egg group roster fetch ────────────────────────────────────────────────────

def fetch_egg_group(slug: str) -> list:
    """
    Fetch the roster of species in an egg group from PokeAPI.

    Returns a list of {"slug": str, "name": str} dicts sorted by name.
    "name" is the English display name from the species names list, or
    a title-cased slug fallback.

    Raises ValueError on unknown slug (404).
    Raises ConnectionError on network failure.
    """
    data = _get(f"egg-group/{slug}")
    roster = []
    for entry in data.get("pokemon_species", []):
        species_slug = entry["name"]
        name = _en_name(entry.get("names", []), None)
        if not name:
            name = species_slug.replace("-", " ").title()
        roster.append({"slug": species_slug, "name": name})
    return sorted(roster, key=lambda x: x["name"])


# ── Type roster fetch ─────────────────────────────────────────────────────────

def fetch_type_roster(type_name: str) -> list:
    """
    Fetch every Pokemon that has a given type from PokeAPI.

    Returns a list of dicts:
      {"slug": "charizard", "slot": 1, "id": 6}

    slug  — PokeAPI variety slug (lowercase-hyphen), same key used by learnset cache
    slot  — 1 = primary type, 2 = secondary type
    id    — national dex / variety ID extracted from the PokeAPI URL.
            Base-form IDs are 1–1025 and map directly to a generation.
            Alternate-form IDs are > 10000 (Mega, Gigantamax, regional forms).

    Raises ValueError on unknown type name (404).
    Raises ConnectionError on network failure.
    """
    data = _get(f"type/{_name_to_slug(type_name)}")
    result = []
    for entry in data.get("pokemon", []):
        slug = entry["pokemon"]["name"]
        slot = entry["slot"]
        url  = entry["pokemon"]["url"]
        try:
            id_ = int(url.rstrip("/").split("/")[-1])
        except (ValueError, IndexError):
            id_ = 0
        result.append({"slug": slug, "slot": slot, "id": id_})
    return result


if __name__ == "__main__":
    main()