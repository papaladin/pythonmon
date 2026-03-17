#!/usr/bin/env python3
"""
pkm_cache.py — Local JSON cache (4 layers)

File layout:
  cache/moves.json                         — global move table (all ~920 moves)
  cache/machines.json                      — TM/HM number lookup table
  cache/pokemon_index.json                 — compact index: slug → {forms, types}
  cache/pokemon/<slug>.json                — per-Pokémon forms, types, base stats
  cache/learnsets/<slug>_<game>.json        — per-Pokémon+game learnset (form-keyed)
  cache/types/<typename>.json              — per-type roster: all Pokémon of that type
                                             fetched once, cached indefinitely (18 files max)
  cache/natures.json                       — all 25 natures + stat effects; fetched once
  cache/abilities_index.json               — all abilities: name, gen, short_effect; fetched once
  cache/abilities/<slug>.json              — per-ability detail: full effect + Pokémon list

Design principles:
  - Defensive reads  : corrupt / missing file → treated as cache miss, re-fetch triggered
  - Atomic writes    : write to .tmp first, rename on success — crash-safe
  - Upsert by key    : forms matched by name, moves matched by name — never blind append
  - Self-healing     : corruption is fixed automatically on next access
  - Explicit refresh : invalidate_* methods wipe a specific entry so next read re-fetches

Public API:
  get_pokemon(name)                        → dict or None
  save_pokemon(name, data)                 → None
  invalidate_pokemon(name)                 → None

  get_moves()                              → dict or None
  save_moves(data)                         → None
  upsert_move(name, entries)               → None
  upsert_move_batch(batch)                 → None
  get_move(name)                           → list or None
  invalidate_moves()                       → None

  get_machines()                           → dict or None
  save_machines(data)                      → None

  get_learnset(variety_slug, game)         → dict or None
  save_learnset(variety_slug, game, data)  → None
  get_learnset_or_fetch(variety_slug, form_name, game)
                                           → dict or None  (auto-fetches on miss)
  invalidate_learnset(variety_slug, game)  → None

  invalidate_all(name)                     → None  (pokemon + all learnsets)

  get_index()                              → dict  (slug → {forms})
  invalidate_index_entry(name)             → None

  get_type_roster(type_name)               → list or None  (cache only, no fetch)
  save_type_roster(type_name, pokemon)     → None
  get_type_roster_or_fetch(type_name)      → list or None  (auto-fetches on miss)
  resolve_type_roster_names(type_name)     → None  (enriches hyphenated entries with
                                             proper display names; no-op if already done)

  get_natures()                            → dict or None  (cache only, no fetch)
  save_natures(data)                       → None
  get_natures_or_fetch()                   → dict or None  (auto-fetches on miss)

  get_abilities_index()                    → dict or None  (cache only)
  save_abilities_index(data)               → None
  get_abilities_index_or_fetch()           → dict or None  (auto-fetches on miss)
  needs_ability_upgrade(cached_pokemon)    → bool

  resolve_move(moves_data, move_name, game, game_gen)
                                           → dict or None  (versioned entry for this game)

  game_to_slug(game)                       → str  ("Scarlet / Violet" → "scarlet-violet")
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone

# ── Directory layout ──────────────────────────────────────────────────────────

_BASE         = os.path.join(os.path.dirname(__file__), "cache")
_POKEMON_DIR  = os.path.join(_BASE, "pokemon")
_LEARNSET_DIR = os.path.join(_BASE, "learnsets")


def _learnset_path(variety_slug: str, game: str) -> str:
    """Return the cache file path for a given variety slug + game."""
    return os.path.join(_LEARNSET_DIR, f"{variety_slug.lower()}_{game_to_slug(game)}.json")
_MOVES_FILE   = os.path.join(_BASE, "moves.json")
_MACHINES_FILE= os.path.join(_BASE, "machines.json")
_INDEX_FILE   = os.path.join(_BASE, "pokemon_index.json")
_TYPES_DIR    = os.path.join(_BASE, "types")
_NATURES_FILE    = os.path.join(_BASE, "natures.json")
_ABILITIES_FILE  = os.path.join(_BASE, "abilities_index.json")
_ABILITIES_DIR   = os.path.join(_BASE, "abilities")

# Bump this integer whenever the move entry schema gains new fields.
# A cached moves.json with a different (or absent) version is treated as a
# full cache miss — all moves will be lazily re-fetched with the new schema.
# History:
#   1 — original schema (type, category, power, accuracy, pp, priority)
#   2 — R3: added drain, effect_chance, ailment
MOVES_CACHE_VERSION = 2


def _ensure_dirs() -> None:
    """Create cache directories if they don't exist."""
    os.makedirs(_POKEMON_DIR,  exist_ok=True)
    os.makedirs(_LEARNSET_DIR, exist_ok=True)


# ── Slug helper ───────────────────────────────────────────────────────────────

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


# ── Machines cache (TM/HM number lookup table) ───────────────────────────────

_MACHINES_FILE = os.path.join(_BASE, "machines.json")


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
        _self._ensure_dirs()

        # pokemon save + get
        pkm = {"pokemon": "garchomp", "forms": [
            {"name": "Garchomp",      "types": ["Dragon","Ground"], "base_stats": []},
            {"name": "Mega Garchomp", "types": ["Dragon","Ground"], "base_stats": []},
        ]}
        _self.save_pokemon("garchomp", pkm)
        loaded = _self.get_pokemon("garchomp")
        assert loaded is not None and len(loaded["forms"]) == 2
        _ok("  pokemon save/get   OK")

        # upsert: update one form, add one
        pkm2 = {"pokemon": "garchomp", "forms": [
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
        _self.save_pokemon("charizard", {"pokemon": "charizard", "forms": [
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
        _self.save_pokemon("charizard", {"pokemon": "charizard", "forms": [
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
        _self.save_pokemon("mewtwo", {"pokemon": "mewtwo", "forms": [
            {"name": "Mewtwo", "types": ["Psychic"], "base_stats": []},
        ]})
        # Manually remove from index to simulate pre-index cache file
        _self.invalidate_index_entry("mewtwo")
        assert "mewtwo" not in _self.get_index(), "setup failed"
        # get_pokemon should silently repair the index
        _self.get_pokemon("mewtwo")
        assert "mewtwo" in _self.get_index(), "index not repaired by get_pokemon"
        _ok("  index repair       OK")

    print()
    if errors:
        print(f"  {passed[0]} passed, {len(errors)} failed out of {passed[0]+len(errors)} tests.")
        print(f"  FAILED: {errors}")
        sys.exit(1)
    else:
        print(f"  {passed[0]} passed, 0 failed out of {passed[0]} tests.")
        print("  All tests passed ✓\n")