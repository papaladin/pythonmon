#!/usr/bin/env python3
"""
pkm_sync.py  One‑time full data import from PokeAPI to SQLite.
"""

import sys
import time
import os

try:
    import pkm_cache as cache
    import pkm_pokeapi as pokeapi
    import matchup_calculator as calc
    from core_egg import _EGG_GROUP_NAMES
    from core_evolution import flatten_chain
except ImportError as e:
    print(f"ERROR: {e}")
    print("Make sure all core and feature modules are in the same folder.")
    sys.exit(1)


def _section_completed(key: str) -> bool:
    """Return True if a sync section has been marked completed."""
    return cache.pkm_sqlite.get_sync_status(key) == "done"


def _mark_completed(key: str) -> None:
    """Mark a sync section as completed."""
    cache.pkm_sqlite.set_sync_status(key, "done")


def sync_all(force=False):
    """Fetch all data from PokeAPI and store in SQLite database."""
    db_path = os.path.join(cache._BASE, "pokemon.db")

    if not force and os.path.exists(db_path):
        # Check if the sync was already fully completed
        if _section_completed("full_sync"):
            print("\n  Database already fully synced. Use --force to re‑sync.")
            print("  Sync cancelled.")
            return
        # Otherwise, we will resume from where we left off
        print("\n  Resuming partial sync...")

    if not force:
        print("\n  Starting full data sync...")
        print("  This will download all Pokémon, moves, type rosters, etc.")
        print("  It may take 20–40 minutes depending on your internet speed.")
        print("  You can interrupt and restart; progress will be saved.")
        confirm = input("  Proceed? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Sync cancelled.")
            return

    # If forcing, delete the old database
    if force and os.path.exists(db_path):
        print("  Removing existing database...")
        os.remove(db_path)

    start = time.time()

    # 1. Moves
    if not _section_completed("moves"):
        print("\n  --- Moves ---")
        moves = pokeapi.fetch_all_moves()
        cache.save_moves(moves)
        _mark_completed("moves")
        print(f"  Saved {len(moves)} moves.")
    else:
        print("\n  --- Moves (already synced) ---")

    # 2. Pokémon
    if not _section_completed("pokemon"):
        print("\n  --- Pokémon ---")
        pokemon = pokeapi.fetch_all_pokemon()
        for slug, data in pokemon.items():
            cache.save_pokemon(slug, data)
        _mark_completed("pokemon")
        print(f"  Saved {len(pokemon)} Pokémon.")
    else:
        print("\n  --- Pokémon (already synced) ---")
        # We still need the pokemon dict for evolution chains, so reload it
        pokemon = {}
        with cache.pkm_sqlite.get_connection() as conn:
            cur = conn.execute("SELECT slug, data FROM pokemon")
            for slug, data_json in cur:
                import json
                pokemon[slug] = json.loads(data_json)

    # 3. Type rosters
    if not _section_completed("type_rosters"):
        print("\n  --- Type rosters ---")
        for t in calc.TYPES_ERA3:
            print(f"  {t}...", end=" ", flush=True)
            roster = pokeapi.fetch_type_roster(t)
            cache.save_type_roster(t, roster)
            print(f"{len(roster)} Pokémon.")
        _mark_completed("type_rosters")
    else:
        print("\n  --- Type rosters (already synced) ---")

    # 4. Natures
    if not _section_completed("natures"):
        print("\n  --- Natures ---")
        natures = pokeapi.fetch_natures()
        cache.save_natures(natures)
        _mark_completed("natures")
        print(f"  Saved {len(natures)} natures.")
    else:
        print("\n  --- Natures (already synced) ---")

    # 5. Abilities index
    if not _section_completed("abilities_index"):
        print("\n  --- Abilities index ---")
        abilities = pokeapi.fetch_abilities_index()
        cache.save_abilities_index(abilities)
        _mark_completed("abilities_index")
        print(f"  Saved {len(abilities)} abilities.")
    else:
        print("\n  --- Abilities index (already synced) ---")

    # 6. Egg groups
    if not _section_completed("egg_groups"):
        print("\n  --- Egg groups ---")
        for slug in _EGG_GROUP_NAMES.keys():
            print(f"  {slug}...", end=" ", flush=True)
            roster = pokeapi.fetch_egg_group(slug)
            cache.save_egg_group(slug, roster)
            print(f"{len(roster)} Pokémon.")
        _mark_completed("egg_groups")
    else:
        print("\n  --- Egg groups (already synced) ---")

    # 7. Evolution chains
    if not _section_completed("evolution"):
        print("\n  --- Evolution chains ---")
        chain_ids = set()
        for slug, data in pokemon.items():
            cid = data.get("evolution_chain_id")
            if cid:
                chain_ids.add(cid)
        total = len(chain_ids)
        for i, cid in enumerate(sorted(chain_ids), 1):
            print(f"  {i}/{total}  chain {cid}...", end="\r", flush=True)
            node = pokeapi.fetch_evolution_chain(cid)
            paths = flatten_chain(node)
            cache.save_evolution_chain(cid, paths)
        _mark_completed("evolution")
        print(f"  Saved {total} evolution chains.          ")
    else:
        print("\n  --- Evolution chains (already synced) ---")

    _mark_completed("full_sync")

    elapsed = time.time() - start
    print(f"\n  Sync completed in {elapsed:.1f} seconds.")


if __name__ == "__main__":
    force = "--force" in sys.argv
    sync_all(force)