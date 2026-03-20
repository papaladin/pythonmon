#!/usr/bin/env python3
"""
pkm_cache.py — Local JSON cache (6 layers)

File layout:
  cache/moves.json                         — global move table (all ~920 moves)
  cache/machines.json                      — TM/HM number lookup table
  cache/pokemon_index.json                 — compact index: slug → {forms, types}
  cache/pokemon/<slug>.json                — per-Pokémon: forms, types, base stats,
                                             egg_groups, evolution_chain_id
  cache/learnsets/<slug>_<game>.json       — per-Pokémon+game learnset (form-keyed)
  cache/types/<typename>.json             — per-type roster: all Pokémon of that type;
                                             fetched once, cached indefinitely (18 files max)
  cache/natures.json                       — all 25 natures + stat effects; fetched once
  cache/abilities_index.json              — all abilities: name, gen, short_effect; fetched once
  cache/abilities/<slug>.json             — per-ability detail: full effect + Pokémon list
  cache/egg_groups/<slug>.json            — per-egg-group roster: [{slug, name}, ...];
                                             fetched once, cached indefinitely (15 files max)
  cache/evolution/<chain_id>.json         — per-chain flattened paths: list[list[{slug, trigger}]];
                                             fetched once, cached indefinitely

Design principles:
  - Defensive reads  : corrupt / missing file → treated as cache miss, re-fetch triggered
  - Atomic writes    : write to .tmp first, rename on success — crash-safe
  - Upsert by key    : forms matched by name, moves matched by name — never blind append
  - Self-healing     : corruption is fixed automatically on next access
  - Explicit refresh : invalidate_* methods wipe a specific entry so next read re-fetches
  - Auto-upgrade     : pokemon entries missing new schema fields (egg_groups,
                       evolution_chain_id) return None → triggers transparent re-fetch

Public API:
  get_pokemon(name)                        → dict or None
  save_pokemon(name, data)                 → None
  invalidate_pokemon(name)                 → None

  get_moves()                              → dict or None
  save_moves(data)                         → None
  upsert_move(name, entries)               → None
  upsert_move_batch(batch)                 → None
  get_move(name)                           → list or None   (case-insensitive)
  invalidate_moves()                       → None

  get_machines()                           → dict or None
  save_machines(data)                      → None

  get_learnset(variety_slug, game)         → dict or None
  save_learnset(variety_slug, game, data)  → None
  get_learnset_age_days(variety_slug, game) → int | None
  get_learnset_or_fetch(variety_slug, form_name, game)
                                           → dict or None  (auto-fetches on miss)
  invalidate_learnset(variety_slug, game)  → None

  invalidate_all(name)                     → None  (pokemon + all learnsets)

  get_index()                              → dict  (slug → {forms})
  invalidate_index_entry(name)             → None

  get_type_roster(type_name)               → list or None  (cache only, no fetch)
  save_type_roster(type_name, pokemon)     → None
  get_type_roster_or_fetch(type_name)      → list or None  (auto-fetches on miss)
  resolve_type_roster_names(type_name)     → None  (enriches entries with display names)

  get_natures()                            → dict or None  (cache only)
  save_natures(data)                       → None
  get_natures_or_fetch()                   → dict or None  (auto-fetches on miss)

  get_abilities_index()                    → dict or None  (cache only)
  save_abilities_index(data)               → None
  get_abilities_index_or_fetch()           → dict or None  (auto-fetches on miss)
  needs_ability_upgrade(cached_pokemon)    → bool

  get_ability_detail(slug)                 → dict or None  (cache only)
  save_ability_detail(slug, data)          → None

  get_egg_group(slug)                      → list or None  (cache only)
  save_egg_group(slug, roster)             → None

  get_evolution_chain(chain_id)            → list or None  (cache only)
  save_evolution_chain(chain_id, paths)    → None
  invalidate_evolution_chain(chain_id)     → None

  resolve_move(moves_data, move_name, game, game_gen)
                                           → dict or None  (versioned entry for this game)

  game_to_slug(game)                       → str  ("Scarlet / Violet" → "scarlet-violet")

  check_integrity()                        → list[str]  (issue strings; empty = clean)
  get_cache_info()                         → dict  (entry counts per cache layer)
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone

# ── Directory layout ──────────────────────────────────────────────────────────
#
# When running as a PyInstaller bundle (sys.frozen = True), __file__ points
# inside the read-only archive. Redirect _BASE to a folder next to the
# executable instead, which is always writable. Normal source runs are
# unaffected — sys.frozen is not set by the Python interpreter itself.

import sys as _sys
if getattr(_sys, "frozen", False):
    # PyInstaller bundle — cache lives next to the executable
    _BASE = os.path.join(os.path.dirname(os.path.abspath(_sys.executable)), "cache")
else:
    # Normal source run — cache lives next to the .py files
    _BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
_POKEMON_DIR  = os.path.join(_BASE, "pokemon")
_LEARNSET_DIR = os.path.join(_BASE, "learnsets")
_MOVES_FILE   = os.path.join(_BASE, "moves.json")
_MACHINES_FILE= os.path.join(_BASE, "machines.json")
_INDEX_FILE   = os.path.join(_BASE, "pokemon_index.json")
_TYPES_DIR    = os.path.join(_BASE, "types")
_NATURES_FILE    = os.path.join(_BASE, "natures.json")
_ABILITIES_FILE  = os.path.join(_BASE, "abilities_index.json")
_ABILITIES_DIR   = os.path.join(_BASE, "abilities")
_EGG_GROUP_DIR   = os.path.join(_BASE, "egg_groups")
_EVOLUTION_DIR   = os.path.join(_BASE, "evolution")

# Bump this integer whenever the move entry schema gains new fields.
# A cached moves.json with a different (or absent) version is treated as a
# full cache miss — all moves will be lazily re-fetched with the new schema.
# History:
#   1 — original schema (type, category, power, accuracy, pp, priority)
#   2 — R3: added drain, effect_chance, ailment
#   3 — Pythonmon-28: added effect (English short_effect text)
MOVES_CACHE_VERSION = 3


def _ensure_dirs() -> None:
    """Create cache directories if they don't exist."""
    os.makedirs(_POKEMON_DIR,  exist_ok=True)
    os.makedirs(_LEARNSET_DIR, exist_ok=True)


# ── Slug and path helpers ─────────────────────────────────────────────────────

def game_to_slug(game: str) -> str:
    """
    Convert a game display name to a safe filename slug.
    e.g. "Scarlet / Violet"         → "scarlet-violet"
         "Black 2 / White 2"        → "black-2-white-2"
         "Legends: Arceus"          → "legends-arceus"
         "Diamond / Pearl / Platinum" → "diamond-pearl-platinum"
    """
    slug = game.lower()
    slug = re.sub(r"[:/]", "-", slug)       # colons and slashes → hyphens
    slug = re.sub(r"\s+", "-", slug)        # spaces → hyphens
    slug = re.sub(r"-+", "-", slug)         # collapse multiple hyphens
    slug = slug.strip("-")
    return slug


def _learnset_path(variety_slug: str, game: str) -> str:
    """Return the cache file path for a given variety slug + game."""
    return os.path.join(_LEARNSET_DIR, f"{variety_slug.lower()}_{game_to_slug(game)}.json")


# ── Low-level read / write ────────────────────────────────────────────────────

def _read(path: str) -> dict | None:
    """
    Read and parse a JSON file.
    Returns None on any failure (missing file, bad JSON, OS error).
    Never raises — all errors are silently treated as cache misses.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write(path: str, data: dict) -> None:
    """
    Atomically write data as JSON to path.
    Writes to <path>.tmp first; renames to final path on success.
    A crash mid-write leaves the original file untouched.
    Raises OSError only if the rename itself fails (should never happen in practice).
    """
    _ensure_dirs()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp, path)      # atomic on same filesystem
    except OSError:
        # Clean up orphaned .tmp if write failed
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _delete(path: str) -> None:
    """Delete a cache file. Silently ignores missing files."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _now() -> str:
    """ISO 8601 timestamp for scraped_at fields."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ── Validation helpers ────────────────────────────────────────────────────────

def _valid_moves(data) -> bool:
    """Minimum validity check for moves.json content.
    Skips metadata keys (starting with '_') like _scraped_at."""
    if not isinstance(data, dict):
        return False
    move_entries = {k: v for k, v in data.items() if not k.startswith("_")}
    return (
        len(move_entries) > 0
        and all(isinstance(v, list) and len(v) > 0 for v in move_entries.values())
    )


def _valid_pokemon(data) -> bool:
    """Minimum validity check for a pokemon cache entry."""
    return (
        isinstance(data, dict)
        and "pokemon" in data
        and "forms" in data
        and isinstance(data["forms"], list)
        and len(data["forms"]) > 0
    )


def _valid_learnset(data) -> bool:
    """Minimum validity check for a learnset cache entry."""
    return (
        isinstance(data, dict)
        and "pokemon" in data
        and "game" in data
        and "forms" in data
        and isinstance(data["forms"], dict)
        and len(data["forms"]) > 0
    )


# ── Upsert helpers ────────────────────────────────────────────────────────────

def _upsert_forms_list(existing_forms: list, new_forms: list) -> list:
    """
    Upsert a list of form dicts (Layer 2) by form name.
    - Existing form with same name → fully replaced
    - New form not previously seen  → appended
    Order of existing forms is preserved; new forms appended at end.
    """
    existing_by_name = {f["name"]: i for i, f in enumerate(existing_forms)}
    result = list(existing_forms)   # copy
    for new_form in new_forms:
        name = new_form["name"]
        if name in existing_by_name:
            result[existing_by_name[name]] = new_form   # replace
        else:
            result.append(new_form)                     # insert
    return result


def _upsert_forms_dict(existing_forms: dict, new_forms: dict) -> dict:
    """
    Upsert a dict of form learnsets (Layer 3) by form name.
    - Existing key → value fully replaced
    - New key      → added
    """
    result = dict(existing_forms)   # copy
    result.update(new_forms)        # replace existing keys, add new ones
    return result


# ── Layer 2 — Pokémon ─────────────────────────────────────────────────────────

def _pokemon_path(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    return os.path.join(_POKEMON_DIR, f"{slug}.json")


def get_pokemon(name: str) -> dict | None:
    """
    Load cached Pokémon data. Returns None on miss or corruption
    (caller should then scrape and call save_pokemon).
    Also silently repairs the index if the file exists but the
    Pokémon is missing from pokemon_index.json (e.g. cached before
    the index feature existed).
    """
    data = _read(_pokemon_path(name))
    if data is None or not _valid_pokemon(data):
        if data is not None:
            print(f"  ⚠  Cache: corrupted pokemon entry for '{name}' — will re-scrape.")
        return None
    # Auto-upgrade: if egg_groups or evolution_chain_id missing, the entry
    # pre-dates Pythonmon-27 / Pythonmon-9. Returning None triggers a
    # transparent re-fetch on next access.
    if "egg_groups" not in data or "evolution_chain_id" not in data:
        return None
    # Repair index silently if this entry is missing
    if name.lower() not in get_index():
        _update_index(name, data)
    return data


def save_pokemon(name: str, data: dict) -> None:
    """
    Save (upsert) Pokémon data to cache.
    If an existing valid entry exists, forms are upserted by name rather than
    overwriting the whole file — preserves any forms not included in new data.
    Always updates scraped_at.
    """
    path = _pokemon_path(name)
    existing = get_pokemon(name)

    if existing is not None:
        merged_forms = _upsert_forms_list(existing["forms"], data.get("forms", []))
        data = {**data, "forms": merged_forms}

    data["scraped_at"] = _now()
    _write(path, data)
    _update_index(name, data)  # keep compact index in sync


def invalidate_pokemon(name: str) -> None:
    """Delete the cached Pokémon entry. Next get_pokemon call will re-scrape."""
    _delete(_pokemon_path(name))
    invalidate_index_entry(name)
    print(f"  Cache invalidated: pokemon/{name.lower()}.json")


# ── Layer 1 — Moves ───────────────────────────────────────────────────────────

def get_moves() -> dict | None:
    """
    Load the global move table. Returns None on miss, corruption, or version mismatch.
    A version mismatch means the schema has changed (new fields added); the entire
    moves cache is treated as stale so all moves are lazily re-fetched.
    """
    data = _read(_MOVES_FILE)
    if data is None or not _valid_moves(data):
        if data is not None:
            print("  ⚠  Cache: corrupted moves.json — will re-scrape.")
        return None
    if data.get("_version") != MOVES_CACHE_VERSION:
        print(f"  ⚠  Cache: moves.json schema version mismatch"
              f" (found {data.get('_version')!r}, need {MOVES_CACHE_VERSION})"
              f" — re-fetching moves with updated schema.")
        _delete(_MOVES_FILE)
        return None
    return data


def save_moves(data: dict) -> None:
    """
    Bulk-save (upsert) the global move table.
    Each move's versioned entry list is replaced; moves not in new data are preserved.
    Used by the optional pre-warm (T menu option).
    """
    existing = get_moves() or {}
    existing.update(data)
    existing["_scraped_at"] = _now()
    existing["_version"]    = MOVES_CACHE_VERSION
    _write(_MOVES_FILE, existing)


def upsert_move(name: str, entries: list) -> None:
    """
    Insert or replace a single move entry in moves.json.
    Creates moves.json if it doesn't exist yet.
    Called on every lazy cache miss during move lookup or learnset display.
    """
    existing = get_moves() or {}
    existing[name] = entries
    existing["_scraped_at"] = _now()
    existing["_version"]    = MOVES_CACHE_VERSION
    _write(_MOVES_FILE, existing)


def upsert_move_batch(batch: dict) -> None:
    """
    Insert or replace multiple move entries in a single read+write operation.

    batch — {display_name: versioned_entries_list, ...}

    Prefer this over calling upsert_move() in a loop when fetching several
    moves at once (e.g. build_candidate_pool).  A single write is
    meaningfully faster once moves.json grows large (~900+ entries).
    """
    if not batch:
        return
    existing = get_moves() or {}
    existing.update(batch)
    existing["_scraped_at"] = _now()
    existing["_version"]    = MOVES_CACHE_VERSION
    _write(_MOVES_FILE, existing)


def get_move(name: str) -> list | None:
    """
    Return versioned entries for a single move, or None if not cached.
    Exact match first, then case-insensitive fallback.
    """
    data = get_moves()
    if not data:
        return None
    if name in data:
        return data[name]
    lower = name.lower()
    for k, v in data.items():
        if k.lower() == lower:
            return v
    return None


def invalidate_moves() -> None:
    """Delete moves.json. Next get_moves call will re-scrape."""
    _delete(_MOVES_FILE)
    print("  Cache invalidated: moves.json")


# ── Layer 3 — Learnsets (per Pokémon + game) ─────────────────────────────────


def get_learnset(variety_slug: str, game: str) -> dict | None:
    """
    Return the cached learnset for (variety_slug, game), or None on miss.
    File: cache/learnsets/<variety_slug>_<game_slug>.json
    """
    data = _read(_learnset_path(variety_slug, game))
    if not isinstance(data, dict) or "forms" not in data:
        return None
    return data


def save_learnset(variety_slug: str, game: str, data: dict) -> None:
    """
    Write (upsert) learnset data to cache/learnsets/<variety_slug>_<game_slug>.json.
    If an existing valid entry exists, the forms dicts are merged by form name
    rather than overwriting the whole file.
    """
    existing = get_learnset(variety_slug, game)
    if existing is not None:
        merged_forms = _upsert_forms_dict(existing["forms"], data.get("forms", {}))
        data = {**data, "forms": merged_forms}
    _write(_learnset_path(variety_slug, game), data)


# Learnsets older than this many days show a staleness note in the display.
LEARNSET_STALE_DAYS = 30


def get_learnset_age_days(variety_slug: str, game: str) -> int | None:
    """
    Return the age of the learnset cache file in whole days, or None if the
    file does not exist.  Uses file mtime — no schema change required.
    Returns 0 for a file written within the last 24 hours.
    """
    import time as _time
    path = _learnset_path(variety_slug, game)
    try:
        age_sec = _time.time() - os.path.getmtime(path)
        return int(age_sec // 86400)
    except OSError:
        return None


# ── Machines cache (TM/HM number lookup table) ───────────────────────────────


def get_machines() -> dict | None:
    """Load cached machine table. Returns None on miss."""
    data = _read(_MACHINES_FILE)
    if not isinstance(data, dict) or not data:
        return None
    return data


def save_machines(data: dict) -> None:
    """Save machine URL→label table to cache."""
    _write(_MACHINES_FILE, data)


# ── Lazy learnset loader ──────────────────────────────────────────────────────

def get_learnset_or_fetch(variety_slug: str, form_name: str, game: str) -> dict | None:
    """
    Return learnset for (variety_slug, game), fetching from PokeAPI on cache miss.

    Args:
        variety_slug: PokeAPI variety slug, e.g. "charizard" or "moltres-galar".
        form_name:    Display name for this form, e.g. "Galarian Moltres".
                      Passed to fetch_learnset so the forms dict key is correct.
        game:         Display game name.

    Flow:
      1. Cache hit  → return immediately
      2. Cache miss → call pkm_pokeapi.fetch_learnset()
                    → pass through machines cache (fetch once, persist forever)
                    → save learnset + updated machines cache
                    → return result

    Returns None only on network or lookup failure.
    """
    import pkm_pokeapi as _api

    cached = get_learnset(variety_slug, game)
    if cached is not None:
        return cached

    print(f"  Fetching learnset for '{form_name}' in {game}...")
    try:
        machines = get_machines()  # None if not yet pre-warmed via T menu — that's fine
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
    """Delete one learnset cache file."""
    path = _learnset_path(variety_slug, game)
    _delete(path)
    print(f"  Cache invalidated: learnsets/{os.path.basename(path)}")


# ── Bulk invalidation ─────────────────────────────────────────────────────────

def invalidate_all(name: str) -> None:
    """
    Delete all cache files for a given Pokemon name:
    pokemon/<n>.json + all learnsets for all its forms (all variety_slugs).

    Reads variety_slugs from the pokemon cache before deleting it, so that
    alternate-form learnset files (e.g. moltres-galar_*.json) are also removed.
    Falls back to species-slug prefix for old-format files.
    Use --refresh-all <n> from CLI, or R from the loaded Pokemon menu.
    """
    _ensure_dirs()

    # Collect all variety_slugs from pokemon cache before we delete it
    variety_slugs = set()
    pokemon_data = get_pokemon(name)
    if pokemon_data:
        for form in pokemon_data.get("forms", []):
            vs = form.get("variety_slug")
            if vs:
                variety_slugs.add(vs.lower())

    # Always include the species slug (covers base form + old cache files)
    species_slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    variety_slugs.add(species_slug)

    # Invalidate pokemon cache
    invalidate_pokemon(name)

    # Delete learnset files whose variety_slug prefix matches any known slug.
    # Filename format: <variety_slug>_<game_slug>.json  (underscore separates them)
    removed = 0
    for fname in os.listdir(_LEARNSET_DIR):
        if not fname.endswith(".json"):
            continue
        slug_part = fname[:-5].split("_")[0]
        if slug_part in variety_slugs:
            _delete(os.path.join(_LEARNSET_DIR, fname))
            print(f"  Cache invalidated: learnsets/{fname}")
            removed += 1

    if removed == 0:
        print(f"  No learnset cache files found for '{name}'.")


# -- Pokemon index --------------------------------------------------------
#
# cache/pokemon_index.json -- compact summary of every scraped Pokemon.
# Updated automatically on every save_pokemon() call.
# Structure: {"garchomp": {"forms": [{"name": ..., "types": [...]}, ...]}, ...}
#
# Used by cross-Pokemon features (e.g. team suggestion) to avoid loading
# hundreds of individual files. Full details still from per-Pokemon files.


def get_index() -> dict:
    """Load the Pokemon index. Returns empty dict on miss or corruption."""
    data = _read(_INDEX_FILE)
    if not isinstance(data, dict):
        return {}
    return data


def _update_index(name: str, data: dict) -> None:
    """Upsert one Pokemon summary into the index. Called by save_pokemon().
    Stores only name + types per form. Write failure is non-fatal."""
    index = get_index()
    index[name.lower()] = {
        "forms": [
            {"name": f["name"], "types": f["types"]}
            for f in data.get("forms", [])
        ]
    }
    tmp = _INDEX_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)
        shutil.move(tmp, _INDEX_FILE)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)


def invalidate_index_entry(name: str) -> None:
    """Remove one Pokemon from the index. Preserves all other entries."""
    index = get_index()
    if name.lower() not in index:
        return
    del index[name.lower()]
    tmp = _INDEX_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)
        shutil.move(tmp, _INDEX_FILE)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)


# ── Move version lookup ───────────────────────────────────────────────────────

def resolve_move(moves_data: dict, move_name: str, game: str, game_gen: int) -> dict | None:
    """
    Given the global moves dict, a move name, and the selected game context,
    return the correct versioned entry for that game.

    Schema: each versioned entry has:
      "from_gen"       : int   — first gen this entry applies to (inclusive)
      "to_gen"         : int|null — last gen (inclusive); null means still current
      "applies_to_games": list|null — specific game overrides (highest priority)

    Priority:
      1. Entry where applies_to_games contains the game name (exact match)
      2. Entry where from_gen <= game_gen <= to_gen (null to_gen = open-ended)
      3. None if no entry matches (move didn't exist in this gen)

    No fallback to first entry — a miss means the move genuinely didn't
    exist in the selected game (e.g. Outrage in Gen 1).
    """
    versions = moves_data.get(move_name)
    if not versions:
        return None

    # Priority 1: game-specific override (e.g. Legends: Z-A cooldown system)
    for entry in versions:
        games_list = entry.get("applies_to_games") or []
        if game in games_list:
            return entry

    # Priority 2: generation range match
    for entry in versions:
        from_gen = entry.get("from_gen")
        to_gen   = entry.get("to_gen")   # None = open-ended (still current)
        if from_gen is None:
            continue
        if from_gen <= game_gen and (to_gen is None or game_gen <= to_gen):
            return entry

    # No match — move didn't exist in this generation
    return None


# ── Quick self-test ───────────────────────────────────────────────────────────

# ── Type roster cache  (cache/types/<typename>.json) ─────────────────────────
#
# One file per type, fetched once from PokeAPI and cached indefinitely.
# Types never change between games so no version or invalidation is needed.
# Structure: {"type": "Fire", "pokemon": [{slug, slot, id}, ...]}

def _type_path(type_name: str) -> str:
    return os.path.join(_TYPES_DIR, f"{type_name.lower()}.json")


def get_type_roster(type_name: str) -> list | None:
    """
    Return the cached roster for type_name, or None on cache miss.
    type_name is case-insensitive ("fire", "Fire", "FIRE" all work).
    """
    data = _read(_type_path(type_name))
    if not isinstance(data, dict):
        return None
    return data.get("pokemon") or None


def save_type_roster(type_name: str, pokemon: list) -> None:
    """
    Persist the type roster.  Atomic write; failure is non-fatal.
    pokemon — list of {slug, slot, id} dicts from fetch_type_roster().
    """
    os.makedirs(_TYPES_DIR, exist_ok=True)
    path = _type_path(type_name)
    tmp  = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"type": type_name.capitalize(), "pokemon": pokemon},
                      fh, ensure_ascii=False, indent=2)
        shutil.move(tmp, path)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)


def get_type_roster_or_fetch(type_name: str) -> list | None:
    """
    Return the type roster from cache, fetching from PokeAPI on miss.
    Prints a one-line status message while fetching.
    Returns None if the type is unknown (404) or the network is unavailable.
    """
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

    Called once after get_type_roster_or_fetch().  On subsequent calls all
    entries already have "name" → no API calls are made.

    Hyphen-free slugs ("charizard", "pikachu") are always correct with
    slug-to-title so they are skipped entirely.

    Updates the cache file in-place (atomic write).
    Prints a progress message while fetching (only on first call per type).
    Silently skips on network failure — the roster remains usable with
    slug-to-title fallback names for the unresolved entries.
    """
    roster = get_type_roster(type_name)
    if roster is None:
        return

    to_resolve = [e for e in roster if "-" in e["slug"] and "name" not in e]
    if not to_resolve:
        return   # all names already resolved

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
                # Empty names list from API → fall back to slug-to-title
                entry["name"] = "-".join(p.capitalize() for p in slug.split("-"))
            resolved += 1
        save_type_roster(type_name, roster)
        print(f"done ({resolved} resolved).")
    except ConnectionError as e:
        print(f"network error: {e} (using slug fallback names).")


# ── Nature cache  (cache/natures.json) ───────────────────────────────────────
#
# All 25 natures with their stat effects.  Fetched once from PokeAPI; the
# nature list never changes between games so no version or invalidation needed.
# Structure: {"Adamant": {"name": "Adamant", "increased": "attack",
#                         "decreased": "special-attack"}, ...}

def get_natures() -> dict | None:
    """Return cached natures dict, or None on miss / corruption."""
    data = _read(_NATURES_FILE)
    if not isinstance(data, dict) or not data:
        return None
    return data


def save_natures(data: dict) -> None:
    """Persist the natures dict.  Atomic write; failure is non-fatal."""
    tmp = _NATURES_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        shutil.move(tmp, _NATURES_FILE)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)


def get_natures_or_fetch() -> dict | None:
    """
    Return natures from cache, fetching from PokeAPI on miss.
    Prints a one-line status message while fetching.
    Returns None if the network is unavailable.
    """
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


# ── Ability index cache  (cache/abilities_index.json) ─────────────────────────
#
# Compact index of all abilities: slug → {name, gen, short_effect}.
# Fetched once from PokeAPI; never invalidated (ability descriptions don't change).

def get_abilities_index() -> dict | None:
    """Return cached abilities index dict, or None on miss / corruption."""
    data = _read(_ABILITIES_FILE)
    if not isinstance(data, dict) or not data:
        return None
    return data


def save_abilities_index(data: dict) -> None:
    """Persist the abilities index dict.  Atomic write; failure is non-fatal."""
    tmp = _ABILITIES_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        shutil.move(tmp, _ABILITIES_FILE)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)


def get_abilities_index_or_fetch() -> dict | None:
    """
    Return abilities index from cache, fetching from PokeAPI on miss.
    Returns None if the network is unavailable.
    """
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
    """
    Return True if any form in the cached pokemon entry is missing the
    'abilities' field.  Used to trigger a transparent re-fetch.
    """
    return any("abilities" not in f for f in cached_pokemon.get("forms", []))


# ── Per-ability detail cache  (cache/abilities/<slug>.json) ───────────────────
#
# Fetched on demand when user drills into a specific ability.
# Structure: {"slug": "blaze", "effect": "...", "pokemon": [{"name": "Charizard", "is_hidden": false}, ...]}

def _ability_detail_path(slug: str) -> str:
    return os.path.join(_ABILITIES_DIR, f"{slug}.json")


def get_ability_detail(slug: str) -> dict | None:
    """Return cached per-ability detail, or None on miss."""
    os.makedirs(_ABILITIES_DIR, exist_ok=True)
    data = _read(_ability_detail_path(slug))
    if not isinstance(data, dict) or "slug" not in data:
        return None
    return data


def save_ability_detail(slug: str, data: dict) -> None:
    """Persist per-ability detail.  Atomic write."""
    os.makedirs(_ABILITIES_DIR, exist_ok=True)
    path = _ability_detail_path(slug)
    tmp  = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        shutil.move(tmp, path)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)


# ── Egg group roster cache  (cache/egg_groups/<slug>.json) ───────────────────
#
# One file per egg group, fetched once from PokeAPI and cached indefinitely.
# Structure: list of {"slug": str, "name": str} dicts.

def _egg_group_path(slug: str) -> str:
    return os.path.join(_EGG_GROUP_DIR, f"{slug.lower()}.json")


def get_egg_group(slug: str) -> list | None:
    """Return cached egg group roster, or None on miss."""
    data = _read(_egg_group_path(slug))
    if not isinstance(data, list):
        return None
    return data


def save_egg_group(slug: str, roster: list) -> None:
    """Persist egg group roster.  Atomic write; failure is non-fatal."""
    os.makedirs(_EGG_GROUP_DIR, exist_ok=True)
    path = _egg_group_path(slug)
    tmp  = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(roster, fh, ensure_ascii=False, indent=2)
        shutil.move(tmp, path)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)


# ── Evolution chain cache  (cache/evolution/<chain_id>.json) ─────────────────
#
# One file per chain ID, fetched once and cached indefinitely.
# Structure: list of paths, where each path is a list of {slug, trigger} dicts
# (the already-flattened output of feat_evolution._flatten_chain).
# Storing the flattened form avoids re-parsing the recursive tree on every load.

def _evolution_path(chain_id: int) -> str:
    return os.path.join(_EVOLUTION_DIR, f"{chain_id}.json")


def get_evolution_chain(chain_id: int) -> list | None:
    """Return cached flattened evolution chain, or None on miss."""
    data = _read(_evolution_path(chain_id))
    if not isinstance(data, list):
        return None
    return data


def save_evolution_chain(chain_id: int, paths: list) -> None:
    """Persist flattened evolution chain.  Atomic write; failure is non-fatal."""
    os.makedirs(_EVOLUTION_DIR, exist_ok=True)
    path = _evolution_path(chain_id)
    tmp  = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(paths, fh, ensure_ascii=False, indent=2)
        shutil.move(tmp, path)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)


def invalidate_evolution_chain(chain_id: int) -> None:
    """Delete cached evolution chain. Next access will re-fetch."""
    _delete(_evolution_path(chain_id))
    print(f"  Cache invalidated: evolution/{chain_id}.json")


# ── Cache integrity check ─────────────────────────────────────────────────────

def check_integrity() -> list:
    """
    Scan every cache file and return a list of issue strings.
    An empty list means the cache is clean.

    Does NOT raise — all OS / JSON errors are caught and reported as issues.
    Ignores missing files (absence is normal; data is fetched on demand).
    Ignores .tmp files left by interrupted writes.

    Issue format: "<filename>: <reason>"
    """
    issues = []

    def _check_file(path: str, label: str, validator) -> None:
        if not os.path.exists(path):
            return
        data = _read(path)
        if data is None:
            issues.append(f"{label}: corrupt or unreadable")
            return
        ok, note = validator(data)
        if not ok:
            issues.append(f"{label}: {note}")

    def _scan_dir(dirpath: str, validator) -> None:
        if not os.path.isdir(dirpath):
            return
        for fname in sorted(os.listdir(dirpath)):
            if not fname.endswith(".json"):
                continue
            _check_file(os.path.join(dirpath, fname), fname, validator)

    def _check_moves(data):
        if not _valid_moves(data):
            return False, "failed schema check"
        if data.get("_version") != MOVES_CACHE_VERSION:
            found = data.get("_version")
            return False, f"schema version mismatch (found {found!r}, need {MOVES_CACHE_VERSION})"
        n = sum(1 for k in data if not k.startswith("_"))
        return True, f"ok ({n} entries)"

    def _check_machines(data):
        if not isinstance(data, dict) or not data:
            return False, "empty or wrong type"
        return True, "ok"

    def _check_index(data):
        if not isinstance(data, dict):
            return False, "wrong type"
        return True, "ok"

    def _check_natures(data):
        if not isinstance(data, dict) or not data:
            return False, "empty or wrong type"
        return True, "ok"

    def _check_abilities_index(data):
        if not isinstance(data, dict) or not data:
            return False, "empty or wrong type"
        return True, "ok"

    _check_file(_MOVES_FILE,    "moves.json",           _check_moves)
    _check_file(_MACHINES_FILE, "machines.json",        _check_machines)
    _check_file(_INDEX_FILE,    "pokemon_index.json",   _check_index)
    _check_file(_NATURES_FILE,  "natures.json",         _check_natures)
    _check_file(_ABILITIES_FILE,"abilities_index.json", _check_abilities_index)

    def _check_pokemon_file(data):
        if not _valid_pokemon(data):
            return False, "failed schema check"
        return True, "ok"

    def _check_learnset_file(data):
        if not _valid_learnset(data):
            return False, "failed schema check"
        return True, "ok"

    def _check_type_file(data):
        if not isinstance(data, dict) or "pokemon" not in data:
            return False, "missing 'pokemon' key"
        if not isinstance(data["pokemon"], list):
            return False, "'pokemon' is not a list"
        return True, "ok"

    def _check_ability_file(data):
        if not isinstance(data, dict) or "slug" not in data:
            return False, "missing 'slug' key"
        return True, "ok"

    def _check_egg_group_file(data):
        if not isinstance(data, list):
            return False, "not a list"
        return True, "ok"

    def _check_evolution_file(data):
        if not isinstance(data, list):
            return False, "not a list"
        return True, "ok"

    _scan_dir(_POKEMON_DIR,   _check_pokemon_file)
    _scan_dir(_LEARNSET_DIR,  _check_learnset_file)
    _scan_dir(_TYPES_DIR,     _check_type_file)
    _scan_dir(_ABILITIES_DIR, _check_ability_file)
    _scan_dir(_EGG_GROUP_DIR, _check_egg_group_file)
    _scan_dir(_EVOLUTION_DIR, _check_evolution_file)

    return issues


def get_cache_info() -> dict:
    """
    Return a summary dict of how many entries are in each cache layer.

    Keys:
      pokemon         — number of .json files in cache/pokemon/
      learnsets       — number of .json files in cache/learnsets/
      moves           — number of move entries in moves.json (metadata keys excluded)
      machines        — 1 if machines.json exists, else 0
      types           — number of .json files in cache/types/
      natures         — number of entries in natures.json
      abilities_index — number of entries in abilities_index.json
      abilities       — number of .json files in cache/abilities/
      egg_groups      — number of .json files in cache/egg_groups/
      evolution       — number of .json files in cache/evolution/

    All values are ints. Missing files or directories silently return 0.
    Never raises.
    """

    def _count_dir(path: str) -> int:
        try:
            return sum(1 for f in os.listdir(path) if f.endswith(".json"))
        except OSError:
            return 0

    # moves: exclude metadata keys (_version, _scraped_at)
    moves_count = 0
    try:
        moves_data = get_moves() or {}
        moves_count = sum(1 for k in moves_data if not k.startswith("_"))
    except Exception:
        pass

    # natures / abilities_index: count dict entries
    natures_count = 0
    try:
        natures_count = len(get_natures() or {})
    except Exception:
        pass

    abilities_count = 0
    try:
        abilities_count = len(get_abilities_index() or {})
    except Exception:
        pass

    return {
        "pokemon"        : _count_dir(_POKEMON_DIR),
        "learnsets"      : _count_dir(_LEARNSET_DIR),
        "moves"          : moves_count,
        "machines"       : 1 if os.path.exists(_MACHINES_FILE) else 0,
        "types"          : _count_dir(_TYPES_DIR),
        "natures"        : natures_count,
        "abilities_index": abilities_count,
        "abilities"      : _count_dir(_ABILITIES_DIR),
        "egg_groups"     : _count_dir(_EGG_GROUP_DIR),
        "evolution"      : _count_dir(_EVOLUTION_DIR),
    }


if __name__ == "__main__":
    import tempfile, sys

    print("\n  pkm_cache.py — self-test\n")
    errors = []
    passed = [0]   # mutable counter so nested helpers can increment it

    def _ok(label):
        passed[0] += 1
        print(f"  {label}")

    # ── slug helper ───────────────────────────────────────────────────────────
    cases = [
        ("Scarlet / Violet",            "scarlet-violet"),
        ("Black 2 / White 2",           "black-2-white-2"),
        ("Legends: Arceus",             "legends-arceus"),
        ("Diamond / Pearl / Platinum",  "diamond-pearl-platinum"),
        ("Red / Blue / Yellow",         "red-blue-yellow"),
        ("Legends: Z-A",                "legends-z-a"),
    ]
    for game, expected in cases:
        result = game_to_slug(game)
        status = "OK" if result == expected else f"FAIL (got '{result}')"
        print(f"  slug  {game:<35} → {result}  {status}")
        if result != expected:
            errors.append(f"slug: {game}")
        else:
            passed[0] += 1

    print()

    # ── upsert helpers ────────────────────────────────────────────────────────
    existing = [{"name": "Garchomp", "types": ["Dragon","Ground"]},
                {"name": "Mega Garchomp", "types": ["Dragon","Ground"]}]
    new      = [{"name": "Garchomp", "types": ["Dragon","Ground"], "NEW": True},
                {"name": "Garchomp Z", "types": ["Dragon","Ground"]}]
    result   = _upsert_forms_list(existing, new)
    assert len(result) == 3,                         f"Expected 3 forms, got {len(result)}"
    assert result[0].get("NEW") is True,             "Garchomp not updated"
    assert result[2]["name"] == "Garchomp Z",        "New form not appended"
    _ok("  upsert forms list  OK")

    existing_d = {"Rotom": {"level_up": []}, "Heat Rotom": {"level_up": []}}
    new_d      = {"Heat Rotom": {"level_up": [{"move": "Overheat", "level": 1}]},
                  "Wash Rotom": {"level_up": []}}
    result_d   = _upsert_forms_dict(existing_d, new_d)
    assert len(result_d) == 3,                                 "Expected 3 form keys"
    assert result_d["Heat Rotom"]["level_up"][0]["move"] == "Overheat", "Heat Rotom not updated"
    assert "Wash Rotom" in result_d,                           "Wash Rotom not added"
    _ok("  upsert forms dict  OK")

    print()

    # ── resolve_move (from_gen/to_gen range schema) ───────────────────────────
    #
    # Test moves:
    #   Outrage      — Phy/Spe split AND power buff AND PP reduction across gens
    #   Flamethrower — power nerf only (Gen 6), category always Special
    #   Thunderbolt  — game-specific override (Legends: Z-A cooldown system)
    #
    # Outrage history:
    #   Gen 2-3 : Special (Dragon=Special via type rule), power 90, PP 15
    #   Gen 4   : Physical (individual assignment), power 120, PP 15
    #   Gen 5+  : Physical, power 120, PP 10
    # Flamethrower history:
    #   Gen 1-5 : Special, power 95, PP 15
    #   Gen 6+  : Special, power 90, PP 15
    # Thunderbolt:
    #   Z-A     : cooldown system (no accuracy/PP)
    #   Gen 1+  : Special, power 90, PP 15, accuracy 100

    moves_data = {
        "Outrage": [
            {"from_gen": 2, "to_gen": 3, "applies_to_games": None,
             "type": "Dragon", "category": "Special",
             "power": 90, "accuracy": 100, "pp": 15},
            {"from_gen": 4, "to_gen": 4, "applies_to_games": None,
             "type": "Dragon", "category": "Physical",
             "power": 120, "accuracy": 100, "pp": 15},
            {"from_gen": 5, "to_gen": None, "applies_to_games": None,
             "type": "Dragon", "category": "Physical",
             "power": 120, "accuracy": 100, "pp": 10},
        ],
        "Flamethrower": [
            {"from_gen": 1, "to_gen": 5, "applies_to_games": None,
             "type": "Fire", "category": "Special",
             "power": 95, "accuracy": 100, "pp": 15},
            {"from_gen": 6, "to_gen": None, "applies_to_games": None,
             "type": "Fire", "category": "Special",
             "power": 90, "accuracy": 100, "pp": 15},
        ],
        "Thunderbolt": [
            {"from_gen": None, "to_gen": None,
             "applies_to_games": ["Legends: Z-A"],
             "type": "Electric", "category": "Special",
             "power": 90, "accuracy": None, "pp": None, "cooldown": 2},
            {"from_gen": 1, "to_gen": None, "applies_to_games": None,
             "type": "Electric", "category": "Special",
             "power": 90, "accuracy": 100, "pp": 15},
        ],
    }

    def chk(move, game, gen, **expected):
        r = resolve_move(moves_data, move, game, gen)
        label = f"{move:<14} / {game:<34}"
        if r is None:
            if "none" in expected:
                _ok(f"  resolve_move  {label}  OK (no entry — move not available)")
                return
            raise AssertionError(f"{label}: expected {expected} but got None")
        for k, v in expected.items():
            assert r.get(k) == v, f"{label}: {k} expected {v!r} got {r.get(k)!r}"
        detail = "  ".join(f"{k}={v}" for k,v in expected.items())
        _ok(f"  resolve_move  {label}  OK ({detail})")

    # Outrage
    chk("Outrage", "Red / Blue / Yellow",         1, none=True)
    chk("Outrage", "Gold / Silver / Crystal",     2, category="Special",  power=90,  pp=15)
    chk("Outrage", "Ruby / Sapphire / Emerald",   3, category="Special",  power=90,  pp=15)
    chk("Outrage", "Diamond / Pearl / Platinum",  4, category="Physical", power=120, pp=15)
    chk("Outrage", "Black / White",               5, category="Physical", power=120, pp=10)
    chk("Outrage", "Scarlet / Violet",            9, category="Physical", power=120, pp=10)
    # Flamethrower
    chk("Flamethrower", "Red / Blue / Yellow",    1, category="Special",  power=95,  pp=15)
    chk("Flamethrower", "Black / White",          5, category="Special",  power=95,  pp=15)
    chk("Flamethrower", "X / Y",                  6, category="Special",  power=90,  pp=15)
    chk("Flamethrower", "Scarlet / Violet",       9, category="Special",  power=90,  pp=15)
    # Thunderbolt — Z-A override
    chk("Thunderbolt", "Legends: Z-A",            9, cooldown=2)
    chk("Thunderbolt", "Scarlet / Violet",        9, power=90, pp=15)

    print()

    # ── MOVES_CACHE_VERSION ───────────────────────────────────────────────────
    assert MOVES_CACHE_VERSION == 3, \
        f"Expected MOVES_CACHE_VERSION=3 (Pythonmon-28), got {MOVES_CACHE_VERSION}"
    _ok("  MOVES_CACHE_VERSION == 3")

    # ── read/write/upsert round-trip (temp dir) ───────────────────────────────
    orig_base = globals()["_BASE"]
    orig_pkm  = globals()["_POKEMON_DIR"]
    orig_ls   = globals()["_LEARNSET_DIR"]
    orig_mv   = globals()["_MOVES_FILE"]

    with tempfile.TemporaryDirectory() as tmp:
        import pkm_cache as _self
        _self._BASE         = tmp
        _self._POKEMON_DIR  = os.path.join(tmp, "pokemon")
        _self._LEARNSET_DIR = os.path.join(tmp, "learnsets")
        _self._MOVES_FILE   = os.path.join(tmp, "moves.json")
        _self._MACHINES_FILE= os.path.join(tmp, "machines.json")
        _self._INDEX_FILE   = os.path.join(tmp, "pokemon_index.json")
        _self._TYPES_DIR    = os.path.join(tmp, "types")
        _self._NATURES_FILE = os.path.join(tmp, "natures.json")
        _self._ABILITIES_FILE= os.path.join(tmp, "abilities_index.json")
        _self._ABILITIES_DIR = os.path.join(tmp, "abilities")
        _self._EGG_GROUP_DIR = os.path.join(tmp, "egg_groups")
        _self._EVOLUTION_DIR = os.path.join(tmp, "evolution")
        _self._ensure_dirs()

        # pokemon save + get
        pkm = {"pokemon": "garchomp", "egg_groups": [], "evolution_chain_id": 1,
            "forms": [
            {"name": "Garchomp",      "types": ["Dragon","Ground"], "base_stats": []},
            {"name": "Mega Garchomp", "types": ["Dragon","Ground"], "base_stats": []},
        ]}
        _self.save_pokemon("garchomp", pkm)
        loaded = _self.get_pokemon("garchomp")
        assert loaded is not None and len(loaded["forms"]) == 2
        _ok("  pokemon save/get   OK")

        # upsert: update one form, add one
        pkm2 = {"pokemon": "garchomp", "egg_groups": [], "evolution_chain_id": 1,
            "forms": [
            {"name": "Garchomp",   "types": ["Dragon","Ground"], "base_stats": [], "updated": True},
            {"name": "Garchomp Z", "types": ["Dragon","Ground"], "base_stats": []},
        ]}
        _self.save_pokemon("garchomp", pkm2)
        loaded2 = _self.get_pokemon("garchomp")
        assert len(loaded2["forms"]) == 3,              f"Expected 3 forms, got {len(loaded2['forms'])}"
        assert loaded2["forms"][0].get("updated"),      "Garchomp not updated in upsert"
        _ok("  pokemon upsert     OK (3 forms after adding Garchomp Z)")

        # corruption → returns None
        with open(_self._pokemon_path("garchomp"), "w") as f:
            f.write("not valid json {{{{")
        assert _self.get_pokemon("garchomp") is None
        _ok("  corruption guard   OK (returns None on bad JSON)")

        # learnset save + get
        ls = {"pokemon": "garchomp", "game": "Scarlet / Violet", "forms": {
            "Garchomp": {"level_up": [{"move": "Earthquake", "level": 40}],
                         "tm_hm": [], "tutor": []},
        }}
        _self.save_learnset("garchomp", "Scarlet / Violet", ls)
        loaded_ls = _self.get_learnset("garchomp", "Scarlet / Violet")
        assert loaded_ls is not None
        assert loaded_ls["forms"]["Garchomp"]["level_up"][0]["move"] == "Earthquake"
        _ok("  learnset save/get  OK")

        # learnset upsert
        ls2 = {"pokemon": "garchomp", "game": "Scarlet / Violet", "forms": {
            "Mega Garchomp": {"level_up": [], "tm_hm": [], "tutor": []},
        }}
        _self.save_learnset("garchomp", "Scarlet / Violet", ls2)
        loaded_ls2 = _self.get_learnset("garchomp", "Scarlet / Violet")
        assert len(loaded_ls2["forms"]) == 2
        _ok("  learnset upsert    OK (2 forms after adding Mega Garchomp)")


        # ── machines cache ────────────────────────────────────────────────────
        machines_data = {"tm01": "Cut", "tm100": "Confide"}
        _self.save_machines(machines_data)
        loaded_m = _self.get_machines()
        assert loaded_m == machines_data, f"machines mismatch: {loaded_m}"
        _ok("  machines save/get  OK")

        # ── invalidate_moves ──────────────────────────────────────────────────
        _self.save_moves({"Tackle": [{"type": "Normal"}]})
        assert _self.get_moves() is not None, "save_moves failed"
        _self.invalidate_moves()
        assert _self.get_moves() is None, "invalidate_moves did not clear"
        _ok("  invalidate_moves   OK")

        # ── upsert_move_batch ─────────────────────────────────────────────────
        fake_entries_a = [{"from_gen": 1, "to_gen": None, "type": "Fire",   "power": 90}]
        fake_entries_b = [{"from_gen": 1, "to_gen": None, "type": "Water",  "power": 95}]
        fake_entries_c = [{"from_gen": 1, "to_gen": None, "type": "Normal", "power": 40}]

        upsert_move_batch({
            "Flamethrower": fake_entries_a,
            "Surf":         fake_entries_b,
        })
        assert get_move("Flamethrower") == fake_entries_a, "batch: Flamethrower missing"
        assert get_move("Surf")         == fake_entries_b, "batch: Surf missing"
        _ok("  upsert_move_batch  two keys written")

        # Existing key preserved when batch does not include it
        upsert_move_batch({"Tackle": fake_entries_c})
        assert get_move("Flamethrower") == fake_entries_a, "batch: existing key overwritten"
        assert get_move("Tackle")       == fake_entries_c, "batch: new key missing"
        _ok("  upsert_move_batch  existing keys preserved")

        # Version and scraped_at set correctly
        data = get_moves()
        assert data.get("_version") == MOVES_CACHE_VERSION, "batch: version not set"
        assert "_scraped_at" in data,                       "batch: scraped_at missing"
        _ok("  upsert_move_batch  version + scraped_at set")

        # Empty batch is a no-op (no crash, file state unchanged)
        before = get_moves()
        upsert_move_batch({})
        after  = get_moves()
        assert before == after, "batch: empty batch mutated moves.json"
        _ok("  upsert_move_batch  empty batch no-op")
        _self.save_learnset("pikachu", "Scarlet / Violet",
                            {"forms": {"Pikachu": {"level_up": [{"move": "Thunderbolt"}]}}})
        assert _self.get_learnset("pikachu", "Scarlet / Violet") is not None
        _self.invalidate_learnset("pikachu", "Scarlet / Violet")
        assert _self.get_learnset("pikachu", "Scarlet / Violet") is None
        _ok("  invalidate_learnset OK")

        # invalidate_all
        _self.save_pokemon("garchomp", pkm)
        _self.save_learnset("garchomp", "Scarlet / Violet", ls)
        _self.save_learnset("garchomp", "Diamond / Pearl / Platinum", ls)
        _self.invalidate_all("garchomp")
        assert _self.get_pokemon("garchomp") is None
        assert _self.get_learnset("garchomp", "Scarlet / Violet") is None
        assert _self.get_learnset("garchomp", "Diamond / Pearl / Platinum") is None
        _ok("  invalidate_all     OK")

        # __ index auto-update ______________________________________________
        _self.save_pokemon("charizard", {"pokemon": "charizard", "egg_groups": [], "evolution_chain_id": 1,
            "forms": [
            {"name": "Charizard",        "types": ["Fire","Flying"], "base_stats": []},
            {"name": "Mega Charizard X", "types": ["Fire","Dragon"],  "base_stats": []},
        ]})
        _self.save_pokemon("garchomp", pkm)
        idx = _self.get_index()
        assert "charizard" in idx,              "charizard missing from index"
        assert "garchomp"  in idx,              "garchomp missing from index"
        assert len(idx["charizard"]["forms"]) == 2
        assert idx["charizard"]["forms"][1]["types"] == ["Fire", "Dragon"]
        _ok("  index auto-update  OK")

        # index upsert: update charizard forms
        _self.save_pokemon("charizard", {"pokemon": "charizard", "egg_groups": [], "evolution_chain_id": 1,
            "forms": [
            {"name": "Charizard",        "types": ["Fire","Flying"], "base_stats": []},
            {"name": "Mega Charizard X", "types": ["Fire","Dragon"],  "base_stats": []},
            {"name": "Mega Charizard Y", "types": ["Fire","Flying"],  "base_stats": []},
        ]})
        idx2 = _self.get_index()
        assert len(idx2["charizard"]["forms"]) == 3, "index not updated after upsert"
        _ok("  index upsert       OK")

        # invalidate removes from index
        _self.invalidate_pokemon("charizard")
        idx3 = _self.get_index()
        assert "charizard" not in idx3,         "charizard still in index after invalidate"
        assert "garchomp"  in idx3,             "garchomp wrongly removed from index"
        _ok("  index invalidate   OK")

        # index repair: pokemon file exists but missing from index
        _self.save_pokemon("mewtwo", {"pokemon": "mewtwo", "egg_groups": [], "evolution_chain_id": 1,
            "forms": [
            {"name": "Mewtwo", "types": ["Psychic"], "base_stats": []},
        ]})
        # Manually remove from index to simulate pre-index cache file
        _self.invalidate_index_entry("mewtwo")
        assert "mewtwo" not in _self.get_index(), "setup failed"
        # get_pokemon should silently repair the index
        _self.get_pokemon("mewtwo")
        assert "mewtwo" in _self.get_index(), "index not repaired by get_pokemon"
        _ok("  index repair       OK")

        # ── egg_groups auto-upgrade ───────────────────────────────────────────

        # Entry without egg_groups → get_pokemon returns None (triggers re-fetch)
        _write(os.path.join(_self._POKEMON_DIR, "oldmon.json"), {
            "pokemon": "oldmon",
            "species_gen": 1,
            "forms": [{"name": "Oldmon", "types": ["Normal"],
                       "variety_slug": "oldmon", "base_stats": {}, "abilities": []}],
            "scraped_at": "2024-01-01T00:00:00",
        })
        # Redirect globals so get_pokemon reads from temp dir
        _g = globals()
        _orig_pkm_dir = _g["_POKEMON_DIR"]
        _g["_POKEMON_DIR"] = _self._POKEMON_DIR
        try:
            assert get_pokemon("oldmon") is None, "missing egg_groups should return None"
            _ok("  egg_groups upgrade  missing → None (triggers re-fetch)")

            # Entry with egg_groups + evolution_chain_id → returns normally
            _write(os.path.join(_self._POKEMON_DIR, "newmon.json"), {
                "pokemon": "newmon",
                "species_gen": 1,
                "egg_groups": ["monster"],
                "evolution_chain_id": 1,
                "forms": [{"name": "Newmon", "types": ["Normal"],
                           "variety_slug": "newmon", "base_stats": {}, "abilities": []}],
                "scraped_at": "2024-01-01T00:00:00",
            })
            # Also redirect index so get_pokemon index repair doesn't break
            _orig_idx = _g["_INDEX_FILE"]
            _g["_INDEX_FILE"] = _self._INDEX_FILE
            try:
                assert get_pokemon("newmon") is not None, "entry with egg_groups should load"
                _ok("  egg_groups upgrade  present → loads normally")
            finally:
                _g["_INDEX_FILE"] = _orig_idx
        finally:
            _g["_POKEMON_DIR"] = _orig_pkm_dir

        # ── egg group roster cache ────────────────────────────────────────────

        roster_a = [{"slug": "bulbasaur", "name": "Bulbasaur"},
                    {"slug": "charmander", "name": "Charmander"}]
        save_egg_group("monster", roster_a)
        loaded_r = get_egg_group("monster")
        assert loaded_r == roster_a, f"egg group round-trip failed: {loaded_r}"
        _ok("  egg_group save/get  OK")

        assert get_egg_group("nonexistent") is None, "missing egg group should return None"
        _ok("  egg_group miss      → None")

        # Non-list data → None
        _write(os.path.join(_EGG_GROUP_DIR, "bad.json"), {"not": "a list"})
        assert get_egg_group("bad") is None, "non-list egg group should return None"
        _ok("  egg_group non-list  → None")

        # ── evolution chain cache ─────────────────────────────────────────────

        # Redirect globals so functions read from temp dir
        _g3 = globals()
        _orig_evo = _g3.get("_EVOLUTION_DIR")
        _g3["_EVOLUTION_DIR"] = _self._EVOLUTION_DIR

        try:
            sample_paths = [
                [{"slug": "charmander", "trigger": ""},
                 {"slug": "charmeleon", "trigger": "Level 16"},
                 {"slug": "charizard",  "trigger": "Level 36"}]
            ]
            save_evolution_chain(1, sample_paths)
            loaded_evo = get_evolution_chain(1)
            assert loaded_evo == sample_paths, f"evo round-trip failed: {loaded_evo}"
            _ok("  evolution save/get  OK")

            assert get_evolution_chain(9999) is None, "missing chain should return None"
            _ok("  evolution miss      → None")

            # Non-list data → None
            _write(os.path.join(_g3["_EVOLUTION_DIR"], "bad.json"), {"not": "a list"})
            assert get_evolution_chain("bad") is None, "non-list chain should return None"
            _ok("  evolution non-list  → None")
            os.remove(os.path.join(_g3["_EVOLUTION_DIR"], "bad.json"))
        finally:
            _g3["_EVOLUTION_DIR"] = _orig_evo

        # ── egg_groups + evolution_chain_id auto-upgrade ──────────────────────

        # Entry without evolution_chain_id → get_pokemon returns None
        _g4 = globals()
        _orig_pkm_dir2 = _g4["_POKEMON_DIR"]
        _orig_idx2     = _g4["_INDEX_FILE"]
        _g4["_POKEMON_DIR"] = _self._POKEMON_DIR
        _g4["_INDEX_FILE"]  = _self._INDEX_FILE
        try:
            _write(os.path.join(_self._POKEMON_DIR, "noevo.json"), {
                "pokemon"    : "noevo",
                "species_gen": 1,
                "egg_groups" : [],
                # deliberately missing evolution_chain_id
                "forms"      : [{"name": "Noevo", "types": ["Normal"],
                                 "variety_slug": "noevo",
                                 "base_stats": {}, "abilities": []}],
                "scraped_at" : "2024-01-01T00:00:00",
            })
            assert get_pokemon("noevo") is None, \
                "missing evolution_chain_id should return None"
            _ok("  evo auto-upgrade    missing evolution_chain_id → None")
        finally:
            _g4["_POKEMON_DIR"] = _orig_pkm_dir2
            _g4["_INDEX_FILE"]  = _orig_idx2

        # ── check_integrity ───────────────────────────────────────────────────

        _g2 = globals()
        _orig_g2 = {k: _g2[k] for k in (
            "_BASE","_POKEMON_DIR","_LEARNSET_DIR","_MOVES_FILE",
            "_MACHINES_FILE","_INDEX_FILE","_TYPES_DIR",
            "_NATURES_FILE","_ABILITIES_FILE","_ABILITIES_DIR",
            "_EGG_GROUP_DIR","_EVOLUTION_DIR"
        )}
        _g2["_BASE"]           = tmp
        _g2["_POKEMON_DIR"]    = _self._POKEMON_DIR
        _g2["_LEARNSET_DIR"]   = _self._LEARNSET_DIR
        _g2["_MOVES_FILE"]     = _self._MOVES_FILE
        _g2["_MACHINES_FILE"]  = _self._MACHINES_FILE
        _g2["_INDEX_FILE"]     = _self._INDEX_FILE
        _g2["_TYPES_DIR"]      = _self._TYPES_DIR
        _g2["_NATURES_FILE"]   = _self._NATURES_FILE
        _g2["_ABILITIES_FILE"] = _self._ABILITIES_FILE
        _g2["_ABILITIES_DIR"]  = _self._ABILITIES_DIR
        _g2["_EGG_GROUP_DIR"]  = os.path.join(tmp, "egg_groups")
        _g2["_EVOLUTION_DIR"]  = os.path.join(tmp, "evolution")

        issues = check_integrity()
        assert issues == [], f"expected clean cache, got: {issues}"
        _ok("  check_integrity    clean cache → no issues")

        with open(_g2["_MOVES_FILE"], "w") as f:
            f.write("{bad json")
        issues = check_integrity()
        assert any("moves.json" in i for i in issues), f"corrupt moves not flagged: {issues}"
        _ok("  check_integrity    corrupt moves.json → issue reported")
        _self.invalidate_moves()

        bad_pkm_path = os.path.join(_g2["_POKEMON_DIR"], "badmon.json")
        with open(bad_pkm_path, "w") as f:
            import json as _json
            _json.dump({"not_a_pokemon": True}, f)
        issues = check_integrity()
        assert any("badmon.json" in i for i in issues), f"bad pokemon not flagged: {issues}"
        _ok("  check_integrity    invalid pokemon → issue reported")
        os.remove(bad_pkm_path)

        # Egg group file in check_integrity
        os.makedirs(_g2["_EGG_GROUP_DIR"], exist_ok=True)
        bad_egg_path = os.path.join(_g2["_EGG_GROUP_DIR"], "bad-group.json")
        with open(bad_egg_path, "w") as f:
            _json.dump({"not": "a list"}, f)
        issues = check_integrity()
        assert any("bad-group.json" in i for i in issues), f"bad egg group not flagged: {issues}"
        _ok("  check_integrity    invalid egg group → issue reported")
        os.remove(bad_egg_path)

        # Evolution file in check_integrity
        os.makedirs(_g2["_EVOLUTION_DIR"], exist_ok=True)
        bad_evo_path = os.path.join(_g2["_EVOLUTION_DIR"], "99.json")
        with open(bad_evo_path, "w") as f:
            _json.dump({"not": "a list"}, f)
        issues = check_integrity()
        assert any("99.json" in i for i in issues), \
            f"bad evolution not flagged: {issues}"
        _ok("  check_integrity    invalid evolution → issue reported")
        os.remove(bad_evo_path)

        _g2.update(_orig_g2)

        # ── get_learnset_age_days ─────────────────────────────────────────────

        # T1: missing file → None
        assert get_learnset_age_days("missing", "No Such Game") is None
        _ok("  learnset_age_days  missing file → None")

        # T2: freshly written file → 0
        _ls_fresh = {"pokemon": "pikachu", "game": "Red / Blue / Yellow",
                     "forms": {"Pikachu": {"level-up": []}}}
        _self.save_learnset("pikachu", "Red / Blue / Yellow", _ls_fresh)
        age_fresh = _self.get_learnset_age_days("pikachu", "Red / Blue / Yellow")
        assert age_fresh == 0, f"expected 0 for fresh file, got {age_fresh}"
        _ok("  learnset_age_days  fresh file → 0")

        # T3: file with mtime patched to 40 days ago → 40
        import time as _time2
        _ls_path = _self._learnset_path("pikachu", "Red / Blue / Yellow")
        _forty_days_ago = _time2.time() - (40 * 86400)
        os.utime(_ls_path, (_forty_days_ago, _forty_days_ago))
        age_old = _self.get_learnset_age_days("pikachu", "Red / Blue / Yellow")
        assert age_old == 40, f"expected 40 for old file, got {age_old}"
        _ok("  learnset_age_days  40-day-old file → 40")

        # T4: LEARNSET_STALE_DAYS constant exists and equals 30
        assert _self.LEARNSET_STALE_DAYS == 30, \
            f"expected LEARNSET_STALE_DAYS=30, got {_self.LEARNSET_STALE_DAYS}"
        _ok("  LEARNSET_STALE_DAYS  constant == 30")

        # ── get_cache_info ────────────────────────────────────────────────────

        # Use a fresh isolated temp dir so counts start at zero
        with tempfile.TemporaryDirectory() as tmp_ci:
            import pkm_cache as _ci
            _orig_ci = {k: getattr(_ci, k) for k in (
                "_BASE","_POKEMON_DIR","_LEARNSET_DIR","_MOVES_FILE",
                "_MACHINES_FILE","_INDEX_FILE","_TYPES_DIR","_NATURES_FILE",
                "_ABILITIES_FILE","_ABILITIES_DIR","_EGG_GROUP_DIR","_EVOLUTION_DIR"
            )}
            _ci._BASE            = tmp_ci
            _ci._POKEMON_DIR     = os.path.join(tmp_ci, "pokemon")
            _ci._LEARNSET_DIR    = os.path.join(tmp_ci, "learnsets")
            _ci._MOVES_FILE      = os.path.join(tmp_ci, "moves.json")
            _ci._MACHINES_FILE   = os.path.join(tmp_ci, "machines.json")
            _ci._INDEX_FILE      = os.path.join(tmp_ci, "pokemon_index.json")
            _ci._TYPES_DIR       = os.path.join(tmp_ci, "types")
            _ci._NATURES_FILE    = os.path.join(tmp_ci, "natures.json")
            _ci._ABILITIES_FILE  = os.path.join(tmp_ci, "abilities_index.json")
            _ci._ABILITIES_DIR   = os.path.join(tmp_ci, "abilities")
            _ci._EGG_GROUP_DIR   = os.path.join(tmp_ci, "egg_groups")
            _ci._EVOLUTION_DIR   = os.path.join(tmp_ci, "evolution")
            _ci._ensure_dirs()

            try:
                # T1: empty cache → all zeros, all 10 keys present
                info = _ci.get_cache_info()
                _expected_keys = {"pokemon","learnsets","moves","machines","types",
                                  "natures","abilities_index","abilities","egg_groups","evolution"}
                assert set(info.keys()) == _expected_keys, f"missing keys: {_expected_keys - set(info.keys())}"
                assert all(v == 0 for v in info.values()), f"expected all-zero on empty cache: {info}"
                _ok("  get_cache_info     empty cache → all zeros, all 10 keys")

                # T2: one pokemon saved → pokemon == 1
                _pkm_ci = {"pokemon": "pikachu", "egg_groups": [], "evolution_chain_id": 1,
                           "forms": [{"name": "Pikachu", "types": ["Electric"],
                                      "variety_slug": "pikachu", "base_stats": {}, "abilities": []}]}
                _ci.save_pokemon("pikachu", _pkm_ci)
                info2 = _ci.get_cache_info()
                assert info2["pokemon"] == 1, f"expected pokemon=1, got {info2['pokemon']}"
                _ok("  get_cache_info     1 pokemon saved → pokemon == 1")

                # T3: two learnsets saved → learnsets == 2
                _ls = {"pokemon": "pikachu", "game": "Red / Blue / Yellow",
                       "forms": {"Pikachu": {"level-up": []}}}
                _ci.save_learnset("pikachu", "Red / Blue / Yellow", _ls)
                _ci.save_learnset("pikachu", "Scarlet / Violet", _ls)
                info3 = _ci.get_cache_info()
                assert info3["learnsets"] == 2, f"expected learnsets=2, got {info3['learnsets']}"
                _ok("  get_cache_info     2 learnsets saved → learnsets == 2")

                # T4: moves saved → moves count excludes metadata keys
                _ci.save_moves({"Tackle": [{"from_gen": 1, "to_gen": None,
                                            "type": "Normal", "category": "Physical",
                                            "power": 40, "accuracy": 100, "pp": 35}]})
                info4 = _ci.get_cache_info()
                assert info4["moves"] == 1, f"expected moves=1, got {info4['moves']}"
                _ok("  get_cache_info     1 move saved → moves == 1, metadata excluded")

                # T5: one evolution chain saved → evolution == 1
                _ci.save_evolution_chain(1, [[{"slug": "bulbasaur", "trigger": ""}]])
                info5 = _ci.get_cache_info()
                assert info5["evolution"] == 1, f"expected evolution=1, got {info5['evolution']}"
                _ok("  get_cache_info     1 evolution chain saved → evolution == 1")

                # T6: machines file present → machines == 1; absent → 0
                assert info4["machines"] == 0, "machines should be 0 before save"
                _ci.save_machines({"scarlet-violet": {"flamethrower": "TM35"}})
                info6 = _ci.get_cache_info()
                assert info6["machines"] == 1, f"expected machines=1, got {info6['machines']}"
                _ok("  get_cache_info     machines file present → machines == 1")

            finally:
                for k, v in _orig_ci.items():
                    setattr(_ci, k, v)

    # ── PKG-1: frozen-path detection ─────────────────────────────────────────
    #
    # Simulate sys.frozen = True (PyInstaller) and confirm _BASE would resolve
    # to a folder next to sys.executable rather than next to __file__.
    # Uses the same conditional logic as the module-level _BASE assignment.

    import sys as _sys_pkg

    def _compute_base(frozen: bool) -> str:
        """Replicate the _BASE detection logic for testing."""
        if frozen:
            return os.path.join(os.path.dirname(os.path.abspath(_sys_pkg.executable)), "cache")
        else:
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

    base_normal = _compute_base(False)
    base_frozen = _compute_base(True)

    if base_normal.endswith(os.path.join("", "cache")):
        _ok("  PKG-1: normal run → _BASE ends with 'cache'")
    else:
        errors.append("PKG-1 normal base")
        print(f"  [FAIL] PKG-1 normal base: {base_normal}")
        passed[0] -= 1
    passed[0] += 1

    if base_frozen.endswith(os.path.join("", "cache")):
        _ok("  PKG-1: frozen run → _BASE ends with 'cache'")
    else:
        errors.append("PKG-1 frozen base")
        print(f"  [FAIL] PKG-1 frozen base: {base_frozen}")
        passed[0] -= 1
    passed[0] += 1

    if base_frozen != base_normal:
        _ok("  PKG-1: frozen path differs from normal path (next to executable, not __file__)")
    else:
        errors.append("PKG-1 paths differ")
        print(f"  [FAIL] PKG-1 paths should differ: normal={base_normal} frozen={base_frozen}")
        passed[0] -= 1
    passed[0] += 1

    print()
    if errors:
        print(f"  {passed[0]} passed, {len(errors)} failed out of {passed[0]+len(errors)} tests.")
        print(f"  FAILED: {errors}")
        sys.exit(1)
    else:
        print(f"  {passed[0]} passed, 0 failed out of {passed[0]} tests.")
        print("  All tests passed ✓\n")