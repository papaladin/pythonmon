#!/usr/bin/env python3
"""
pkm_cache.py — Local SQLite cache (single database)

All cache data is stored in a single SQLite database file at
<BASE>/pokemon.db. The database is created on first access.

All public functions remain unchanged from the JSON version.
"""

import sys
import os
from datetime import datetime, timezone
import pkm_sqlite

# ── Base directory (where pokemon.db will live) ───────────────────────────────
#
# When running as a PyInstaller bundle (sys.frozen = True), __file__ points
# inside the read-only archive. Redirect _BASE to a folder next to the
# executable instead, which is always writable. Normal source runs are
# unaffected — sys.frozen is not set by the Python interpreter itself.

if getattr(sys, "frozen", False):
    # PyInstaller bundle — cache lives next to the executable
    _BASE = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "cache")
else:
    # Normal source run — cache lives next to the .py files
    _BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

# Set the base path for the SQLite module
pkm_sqlite.set_base(_BASE)

# ── Move version constant ─────────────────────────────────────────────────────
MOVES_CACHE_VERSION = 3

# Learnset staleness threshold (days)
LEARNSET_STALE_DAYS = 30


# ── Helper to get current timestamp ──────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ── Layer 1 — Moves ──────────────────────────────────────────────────────────

def get_moves() -> dict | None:
    """Load the global move table. Returns None on miss or version mismatch."""
    if pkm_sqlite.get_metadata("moves_schema_version") != str(MOVES_CACHE_VERSION):
        return None
    moves = pkm_sqlite.get_all_moves()
    return moves if moves else None


def save_moves(data: dict) -> None:
    """Bulk-save the global move table."""
    pkm_sqlite.save_moves_batch(data, MOVES_CACHE_VERSION)
    pkm_sqlite.set_metadata("moves_schema_version", str(MOVES_CACHE_VERSION))


def upsert_move(name: str, entries: list) -> None:
    """Insert or replace a single move entry."""
    pkm_sqlite.save_move(name, entries, MOVES_CACHE_VERSION)
    pkm_sqlite.set_metadata("moves_schema_version", str(MOVES_CACHE_VERSION))


def upsert_move_batch(batch: dict) -> None:
    """Insert or replace multiple move entries in a single transaction."""
    if not batch:
        return
    pkm_sqlite.save_moves_batch(batch, MOVES_CACHE_VERSION)
    pkm_sqlite.set_metadata("moves_schema_version", str(MOVES_CACHE_VERSION))


def get_move(name: str) -> list | None:
    """Return versioned entries for a single move, or None if not cached."""
    return pkm_sqlite.get_move(name)


def invalidate_moves() -> None:
    """Delete the moves table."""
    pkm_sqlite.invalidate_moves()
    pkm_sqlite.set_metadata("moves_schema_version", "0")  # force re‑fetch


# ── Layer 2 — Pokémon ─────────────────────────────────────────────────────────

def get_pokemon(name: str) -> dict | None:
    """Load cached Pokémon data. Returns None on miss or corruption."""
    data = pkm_sqlite.get_pokemon(name)
    if data is None:
        return None
    # Auto‑upgrade check: if egg_groups or evolution_chain_id missing, return None
    if "egg_groups" not in data or "evolution_chain_id" not in data:
        return None
    return data


def save_pokemon(name: str, data: dict) -> None:
    """Save (upsert) Pokémon data to cache."""
    pkm_sqlite.save_pokemon(name, data, _now())


def invalidate_pokemon(name: str) -> None:
    """Delete the cached Pokémon entry."""
    pkm_sqlite.invalidate_pokemon(name)


# ── Layer 3 — Learnsets ──────────────────────────────────────────────────────

def get_learnset(variety_slug: str, game: str) -> dict | None:
    """Return cached learnset for (variety_slug, game), or None on miss."""
    return pkm_sqlite.get_learnset(variety_slug, game)


def save_learnset(variety_slug: str, game: str, data: dict) -> None:
    """Write (upsert) learnset data to cache."""
    pkm_sqlite.save_learnset(variety_slug, game, data, _now())


def get_learnset_age_days(variety_slug: str, game: str) -> int | None:
    """Return age of learnset cache file in whole days, or None if missing."""
    return pkm_sqlite.get_learnset_age(variety_slug, game)


def get_learnset_or_fetch(variety_slug: str, form_name: str, game: str) -> dict | None:
    """
    Return learnset for (variety_slug, game), fetching from PokeAPI on cache miss.
    (This function remains unchanged; it still uses the same pkm_pokeapi calls.)
    """
    import pkm_pokeapi as _api

    cached = get_learnset(variety_slug, game)
    if cached is not None:
        return cached

    print(f"  Fetching learnset for '{form_name}' in {game}...")
    try:
        machines = get_machines()  # None if not pre‑warmed
        result = _api.fetch_learnset(variety_slug, form_name, game, machines=machines)
    except ValueError as e:
        print(f"  ⚠  {e}")
        return None
    except ConnectionError as e:
        print(f"  ⚠  Connection error: {e}")
        return None

    save_learnset(variety_slug, game, result)
    print(f"  (learnset cached)")
    return result


def invalidate_learnset(variety_slug: str, game: str) -> None:
    """Delete one learnset cache entry."""
    pkm_sqlite.invalidate_learnset(variety_slug, game)


def invalidate_all(name: str) -> None:
    """
    Delete all cache entries for a given Pokemon name:
    pokemon row + all learnsets for all its forms (all variety_slugs).
    """
    # Get variety_slugs from pokemon cache before deleting it
    variety_slugs = set()
    pokemon_data = get_pokemon(name)
    if pokemon_data:
        for form in pokemon_data.get("forms", []):
            vs = form.get("variety_slug")
            if vs:
                variety_slugs.add(vs.lower())
    # Always include the species slug
    species_slug = name.lower().replace(" ", "-")
    variety_slugs.add(species_slug)

    # Invalidate pokemon
    invalidate_pokemon(name)

    # Delete learnsets for all variety_slugs
    with pkm_sqlite.get_connection() as conn:
        for vs in variety_slugs:
            conn.execute("DELETE FROM learnsets WHERE variety_slug = ?", (vs,))
    print(f"  Cache invalidated for '{name}' (pokemon + learnsets).")


# ── Machines cache ───────────────────────────────────────────────────────────

def get_machines() -> dict | None:
    """Load cached machine table. Returns None on miss."""
    return pkm_sqlite.get_machines() or None


def save_machines(data: dict) -> None:
    """Save machine URL→label table to cache."""
    pkm_sqlite.save_machines(data)


# ── Type roster cache ────────────────────────────────────────────────────────

def get_type_roster(type_name: str) -> list | None:
    """Return cached roster for type_name, or None on miss."""
    return pkm_sqlite.get_type_roster(type_name)


def save_type_roster(type_name: str, pokemon: list) -> None:
    """Persist the type roster."""
    pkm_sqlite.save_type_roster(type_name, pokemon)


def get_type_roster_or_fetch(type_name: str) -> list | None:
    """Return the type roster from cache, fetching from PokeAPI on miss."""
    roster = get_type_roster(type_name)
    if roster is not None:
        return roster
    try:
        import pkm_pokeapi as pokeapi
        print(f"  Fetching {type_name} type roster from PokeAPI...", end=" ", flush=True)
        roster = pokeapi.fetch_type_roster(type_name)
        save_type_roster(type_name, roster)
        print(f"{len(roster)} Pokemon cached.")
        return roster
    except ValueError:
        print("not found.")
        return None
    except ConnectionError as e:
        print(f"connection error: {e}")
        return None


def resolve_type_roster_names(type_name: str) -> None:
    """
    Enrich every hyphenated roster entry that lacks a "name" field with its
    proper English display name from PokeAPI pokemon-form/{slug}.
    """
    roster = get_type_roster(type_name)
    if roster is None:
        return

    to_resolve = [e for e in roster if "-" in e["slug"] and "name" not in e]
    if not to_resolve:
        return

    try:
        import pkm_pokeapi as pokeapi
        print(f"  Resolving {len(to_resolve)} form name(s) for {type_name} type...",
              end=" ", flush=True)
        resolved = 0
        for entry in to_resolve:
            slug = entry["slug"]
            name = pokeapi.fetch_form_display_name(slug)
            if name:
                entry["name"] = name
            else:
                entry["name"] = "-".join(p.capitalize() for p in slug.split("-"))
            resolved += 1
        save_type_roster(type_name, roster)
        print(f"done ({resolved} resolved).")
    except ConnectionError as e:
        print(f"network error: {e} (using slug fallback names).")


# ── Nature cache ─────────────────────────────────────────────────────────────

def get_natures() -> dict | None:
    """Return cached natures dict, or None on miss / corruption."""
    return pkm_sqlite.get_natures()


def save_natures(data: dict) -> None:
    """Persist the natures dict."""
    pkm_sqlite.save_natures(data)


def get_natures_or_fetch() -> dict | None:
    """Return natures from cache, fetching from PokeAPI on miss."""
    data = get_natures()
    if data is not None:
        return data
    try:
        import pkm_pokeapi as pokeapi
        print("  Fetching natures from PokeAPI...", end=" ", flush=True)
        data = pokeapi.fetch_natures()
        save_natures(data)
        print(f"{len(data)} natures cached.")
        return data
    except ConnectionError as e:
        print(f"connection error: {e}")
        return None


# ── Ability cache ────────────────────────────────────────────────────────────

def get_abilities_index() -> dict | None:
    """Return cached abilities index dict, or None on miss / corruption."""
    return pkm_sqlite.get_abilities_index()


def save_abilities_index(data: dict) -> None:
    """Persist the abilities index dict."""
    pkm_sqlite.save_abilities_index(data)


def get_abilities_index_or_fetch() -> dict | None:
    """Return abilities index from cache, fetching from PokeAPI on miss."""
    data = get_abilities_index()
    if data is not None:
        return data
    try:
        import pkm_pokeapi as pokeapi
        print("  Fetching abilities index from PokeAPI...", end=" ", flush=True)
        data = pokeapi.fetch_abilities_index()
        save_abilities_index(data)
        print(f"  {len(data)} abilities cached.")
        return data
    except ConnectionError as e:
        print(f"connection error: {e}")
        return None


def needs_ability_upgrade(cached_pokemon: dict) -> bool:
    """Return True if any form in the cached pokemon entry is missing the 'abilities' field."""
    return any("abilities" not in f for f in cached_pokemon.get("forms", []))


def get_ability_detail(slug: str) -> dict | None:
    """Return cached per-ability detail, or None on miss."""
    return pkm_sqlite.get_ability_detail(slug)


def save_ability_detail(slug: str, data: dict) -> None:
    """Persist per-ability detail."""
    pkm_sqlite.save_ability_detail(slug, data)


# ── Egg group roster cache ───────────────────────────────────────────────────

def get_egg_group(slug: str) -> list | None:
    """Return cached egg group roster, or None on miss."""
    return pkm_sqlite.get_egg_group(slug)


def save_egg_group(slug: str, roster: list) -> None:
    """Persist egg group roster."""
    pkm_sqlite.save_egg_group(slug, roster)


# ── Evolution chain cache ────────────────────────────────────────────────────

def get_evolution_chain(chain_id: int) -> list | None:
    """Return cached flattened evolution chain, or None on miss."""
    return pkm_sqlite.get_evolution_chain(chain_id)


def save_evolution_chain(chain_id: int, paths: list) -> None:
    """Persist flattened evolution chain."""
    pkm_sqlite.save_evolution_chain(chain_id, paths)


def invalidate_evolution_chain(chain_id: int) -> None:
    """Delete cached evolution chain."""
    pkm_sqlite.invalidate_evolution_chain(chain_id)


# ── Cache integrity and info ─────────────────────────────────────────────────

def check_integrity() -> list:
    """Scan the database and return a list of issue strings."""
    return pkm_sqlite.check_integrity()


def get_cache_info() -> dict:
    """Return a summary dict of how many entries are in each cache table."""
    return pkm_sqlite.get_cache_info()

def get_index() -> dict:
    """
    Return a compact index of all cached Pokémon, similar to the old JSON index file.
    Structure: {slug: {"forms": [{"name": str, "types": list[str]}, ...]}}
    """
    import json
    with pkm_sqlite.get_connection() as conn:
        cur = conn.execute("SELECT slug, data FROM pokemon")
        rows = cur.fetchall()
        index = {}
        for slug, data_json in rows:
            data = json.loads(data_json)
            forms = []
            for form in data.get("forms", []):
                forms.append({
                    "name": form.get("name"),
                    "types": form.get("types", [])
                })
            index[slug] = {"forms": forms}
        return index


# ── Move version lookup (unchanged) ──────────────────────────────────────────

def resolve_move(moves_data: dict, move_name: str, game: str, game_gen: int) -> dict | None:
    """
    Given the global moves dict, a move name, and the selected game context,
    return the correct versioned entry for that game.
    (This function is pure and doesn't use the cache directly.)
    """
    versions = moves_data.get(move_name)
    if not versions:
        return None

    # Priority 1: game-specific override
    for entry in versions:
        games_list = entry.get("applies_to_games") or []
        if game in games_list:
            return entry

    # Priority 2: generation range match
    for entry in versions:
        from_gen = entry.get("from_gen")
        to_gen   = entry.get("to_gen")
        if from_gen is None:
            continue
        if from_gen <= game_gen and (to_gen is None or game_gen <= to_gen):
            return entry

    return None


# ── Slug helper ──────────────────────────────────────────────────────────────

def game_to_slug(game: str) -> str:
    """Convert a game display name to a safe filename slug (unused in SQLite, kept for compatibility)."""
    import re
    slug = game.lower()
    slug = re.sub(r"[:/]", "-", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug


# ── Self‑test ────────────────────────────────────────────────────────────────

def _run_tests():
    import tempfile
    import shutil

    # Save original _BASE and set to a temporary directory
    global _BASE
    orig_base = _BASE
    tmp_dir = tempfile.mkdtemp()
    _BASE = tmp_dir
    pkm_sqlite.set_base(_BASE)

    print("\n  pkm_cache.py — self-test (SQLite)\n")
    errors = []
    passed = 0

    def ok(label):
        nonlocal passed
        passed += 1
        print(f"  [OK]   {label}")

    def fail(label, msg=""):
        print(f"  [FAIL] {label}" + (f": {msg}" if msg else ""))
        errors.append(label)

    # ── Test database initialisation ─────────────────────────────────────────
    # This should create the database file
    conn = pkm_sqlite.get_connection().__enter__()
    conn.close()
    db_path = os.path.join(_BASE, "pokemon.db")
    if os.path.exists(db_path):
        ok("Database created on first access")
    else:
        fail("Database not created")

    # ── Test moves ──────────────────────────────────────────────────────────
    test_move_data = {"Tackle": [{"from_gen": 1, "to_gen": None, "type": "Normal"}]}
    save_moves(test_move_data)
    moves = get_moves()
    if moves == test_move_data:
        ok("save_moves / get_moves round-trip")
    else:
        fail("save_moves / get_moves", f"got {moves}")

    upsert_move("Surf", [{"from_gen": 1, "to_gen": None, "type": "Water"}])
    moves2 = get_moves()
    if "Surf" in moves2 and moves2["Surf"][0]["type"] == "Water":
        ok("upsert_move adds new move")
    else:
        fail("upsert_move", f"missing Surf in {moves2}")

    # Batch upsert
    batch = {"Flamethrower": [{"from_gen": 1, "to_gen": None, "type": "Fire"}],
             "Earthquake": [{"from_gen": 1, "to_gen": None, "type": "Ground"}]}
    upsert_move_batch(batch)
    moves3 = get_moves()
    if "Flamethrower" in moves3 and "Earthquake" in moves3:
        ok("upsert_move_batch works")
    else:
        fail("upsert_move_batch", f"missing moves in {moves3}")

    invalidate_moves()
    moves4 = get_moves()
    if moves4 is None:
        ok("invalidate_moves clears moves")
    else:
        fail("invalidate_moves", f"got {moves4}")

    # ── Test pokemon ─────────────────────────────────────────────────────────
    pkm_data = {"pokemon": "charizard", "species_gen": 1,
                "egg_groups": ["monster", "dragon"], "evolution_chain_id": 1,
                "forms": [{"name": "Charizard", "types": ["Fire", "Flying"],
                           "variety_slug": "charizard", "base_stats": {}}]}
    save_pokemon("charizard", pkm_data)
    pkm = get_pokemon("charizard")
    if pkm and pkm["pokemon"] == "charizard":
        ok("save_pokemon / get_pokemon round-trip")
    else:
        fail("save_pokemon / get_pokemon", str(pkm))

    invalidate_pokemon("charizard")
    if get_pokemon("charizard") is None:
        ok("invalidate_pokemon clears entry")
    else:
        fail("invalidate_pokemon")

    # ── Test learnsets ──────────────────────────────────────────────────────
    ls_data = {"pokemon": "charizard", "game": "Scarlet / Violet",
               "forms": {"Charizard": {"level-up": [{"move": "Flamethrower", "level": 30}]}}}
    save_learnset("charizard", "Scarlet / Violet", ls_data)
    ls = get_learnset("charizard", "Scarlet / Violet")
    if ls and ls["forms"]["Charizard"]["level-up"][0]["move"] == "Flamethrower":
        ok("save_learnset / get_learnset round-trip")
    else:
        fail("save_learnset / get_learnset", str(ls))

    age = get_learnset_age_days("charizard", "Scarlet / Violet")
    if age == 0:
        ok("get_learnset_age_days returns 0 for fresh entry")
    else:
        fail("get_learnset_age_days", str(age))

    invalidate_learnset("charizard", "Scarlet / Violet")
    if get_learnset("charizard", "Scarlet / Violet") is None:
        ok("invalidate_learnset clears entry")
    else:
        fail("invalidate_learnset")

    # ── Test invalidate_all ─────────────────────────────────────────────────
    save_pokemon("garchomp", {"pokemon": "garchomp", "species_gen": 4,
                              "egg_groups": ["monster", "dragon"], "evolution_chain_id": 1,
                              "forms": [{"name": "Garchomp", "types": ["Dragon", "Ground"],
                                         "variety_slug": "garchomp"}]})
    save_learnset("garchomp", "Scarlet / Violet", {"forms": {"Garchomp": {"level-up": []}}})
    invalidate_all("garchomp")
    if get_pokemon("garchomp") is None and get_learnset("garchomp", "Scarlet / Violet") is None:
        ok("invalidate_all removes pokemon and learnset")
    else:
        fail("invalidate_all")

    # ── Test machines ───────────────────────────────────────────────────────
    machines = {"http://example.com/1": "TM01"}
    save_machines(machines)
    if get_machines() == machines:
        ok("save_machines / get_machines round-trip")
    else:
        fail("save_machines", str(get_machines()))

    # ── Test type roster ────────────────────────────────────────────────────
    roster = [{"slug": "charizard", "slot": 1, "id": 6}]
    save_type_roster("Fire", roster)
    if get_type_roster("Fire") == roster:
        ok("save_type_roster / get_type_roster round-trip")
    else:
        fail("save_type_roster", str(get_type_roster("Fire")))

    # ── Test natures ────────────────────────────────────────────────────────
    natures = {"Adamant": {"increased": "attack", "decreased": "special-attack"}}
    save_natures(natures)
    if get_natures() == natures:
        ok("save_natures / get_natures round-trip")
    else:
        fail("save_natures", str(get_natures()))

    # ── Test abilities index ────────────────────────────────────────────────
    abilities = {"blaze": {"name": "Blaze", "gen": 3, "short_effect": "Powers up Fire moves."}}
    save_abilities_index(abilities)
    if get_abilities_index() == abilities:
        ok("save_abilities_index / get_abilities_index round-trip")
    else:
        fail("save_abilities_index", str(get_abilities_index()))

    # ── Test ability detail ─────────────────────────────────────────────────
    detail = {"slug": "blaze", "effect": "Full effect", "pokemon": []}
    save_ability_detail("blaze", detail)
    if get_ability_detail("blaze") == detail:
        ok("save_ability_detail / get_ability_detail round-trip")
    else:
        fail("save_ability_detail", str(get_ability_detail("blaze")))

    # ── Test egg group ──────────────────────────────────────────────────────
    egg_roster = [{"slug": "bulbasaur", "name": "Bulbasaur"}]
    save_egg_group("monster", egg_roster)
    if get_egg_group("monster") == egg_roster:
        ok("save_egg_group / get_egg_group round-trip")
    else:
        fail("save_egg_group", str(get_egg_group("monster")))

    # ── Test evolution chain ────────────────────────────────────────────────
    paths = [[{"slug": "charmander", "trigger": ""},
              {"slug": "charmeleon", "trigger": "Level 16"},
              {"slug": "charizard", "trigger": "Level 36"}]]
    save_evolution_chain(1, paths)
    if get_evolution_chain(1) == paths:
        ok("save_evolution_chain / get_evolution_chain round-trip")
    else:
        fail("save_evolution_chain", str(get_evolution_chain(1)))
    invalidate_evolution_chain(1)
    if get_evolution_chain(1) is None:
        ok("invalidate_evolution_chain clears entry")
    else:
        fail("invalidate_evolution_chain")

    # ── Test cache info and integrity ───────────────────────────────────────
    info = get_cache_info()
    expected_keys = {"pokemon", "learnsets", "moves", "machines", "types", "natures",
                     "abilities_index", "abilities", "egg_groups", "evolution"}
    if set(info.keys()) == expected_keys:
        ok("get_cache_info returns all expected keys")
    else:
        fail("get_cache_info keys", str(info.keys()))

    issues = check_integrity()
    if issues == []:
        ok("check_integrity returns empty list on clean db")
    else:
        fail("check_integrity", str(issues))

    # Clean up
    shutil.rmtree(tmp_dir)
    _BASE = orig_base
    pkm_sqlite.set_base(orig_base)

    print()
    if errors:
        print(f"  {passed} passed, {len(errors)} failed out of {passed + len(errors)} tests.")
        sys.exit(1)
    else:
        print(f"  {passed} passed, 0 failed out of {passed} tests.")


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        _run_tests()
    else:
        # Not meant to be run directly; self-test is the only mode.
        print("Run with --autotest to test the cache module.")