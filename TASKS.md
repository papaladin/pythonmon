# TASKS.md
# Current work — V2 Package 2: SQLite data layer

**Status:** 🔄 PLANNED  
**Complexity:** 🔴 High  
**Effort:** 🟡 Medium  
**Goal:** Replace the JSON file cache with a single SQLite database, preserving the same public API in `pkm_cache.py`. The rest of the toolkit (feature modules, core modules) must remain unchanged. Lazy‑fetch behaviour is retained; the database is created on first use and populated on‑demand.

---

## Design decisions

1. **Single database file**: `cache/pokemon.db` (or `pokemon.db` in the same base directory as the current JSON cache). The path is determined by the existing `_BASE` logic (frozen‑safe, user‑writable).
2. **Tables**: We'll design a relational schema that mirrors the current JSON structure:
   - `pokemon` – species data (forms are stored as JSON in a text column for simplicity, but we can normalise later)
   - `learnsets` – one row per `(variety_slug, game_slug)`, with `forms` stored as JSON
   - `moves` – move entries (name, versioned entries stored as JSON)
   - `machines` – machine URL → label mapping (JSON)
   - `type_rosters` – per‑type roster (JSON)
   - `natures` – nature data (JSON)
   - `abilities` – index and detail (JSON)
   - `egg_groups` – per‑group roster (JSON)
   - `evolution_chains` – per‑chain flattened paths (JSON)
   - `metadata` – schema version, timestamps
3. **Backward compatibility**: On first run, if the database does not exist, create it and initialise empty tables. Existing JSON cache files are not automatically migrated; users can keep their old cache or delete it (the database will repopulate lazily). We may add a one‑time migration script later, but it's optional.
4. **Public API unchanged**: Functions like `get_move(name)`, `get_pokemon(slug)`, `upsert_move_batch(batch)`, etc., will continue to work exactly as before, but their internals will use SQLite instead of JSON files.
5. **Atomicity**: SQLite transactions replace the `write‑tmp‑move` pattern. We'll use `with conn:` to ensure rollback on error.
6. **Testing**: All existing tests that use the cache must pass. New tests for the SQLite layer will be added, but they can reuse the existing test data and patterns.

---

## Step 2.1 — Schema design and database initialisation

**Goal:** Define the SQLite schema and implement functions to create the database and tables on first use.

**2.1.1** Create a new module `pkm_sqlite.py` (or integrate into `pkm_cache.py`). We'll keep it separate initially to avoid disrupting the existing code, then later replace the JSON logic.

**2.1.2** Define table schemas (as SQL `CREATE TABLE` statements). Use `TEXT` columns for JSON data to keep the transition simple. For example:

```sql
CREATE TABLE IF NOT EXISTS pokemon (
    slug TEXT PRIMARY KEY,
    data TEXT NOT NULL,   -- JSON: whole pokemon dict
    scraped_at TEXT
);

CREATE TABLE IF NOT EXISTS learnsets (
    variety_slug TEXT,
    game_slug TEXT,
    data TEXT NOT NULL,
    scraped_at TEXT,
    PRIMARY KEY (variety_slug, game_slug)
);

CREATE TABLE IF NOT EXISTS moves (
    name TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    version INTEGER   -- MOVES_CACHE_VERSION
);

CREATE TABLE IF NOT EXISTS machines (
    url TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

-- similarly for types, natures, abilities_index, abilities_detail, egg_groups, evolution_chains

2.1.3 Add a metadata table to store schema version and any other global flags:
sql

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

2.1.4 Write a function _init_db() that creates the database and tables if they don't exist. Call it whenever the database is opened.

2.1.5 Write a helper _get_connection() that returns a sqlite3.Connection object, ensuring the database is initialised.

2.1.6 Add a self‑test in pkm_cache.py to verify that _init_db() creates the expected tables.

---

Step 2.2 — Adapt pkm_cache.py to use SQLite

Goal: Replace the JSON read/write functions with SQLite equivalents, while keeping the same public API.

2.2.1 Modify get_moves() to read from the moves table instead of moves.json. If the table is empty or missing, return None.

2.2.2 Modify save_moves(data) to write to the moves table (using INSERT OR REPLACE).

2.2.3 Modify upsert_move(name, entries) and upsert_move_batch(batch) to use SQLite.

2.2.4 Adapt get_move(name) to query the moves table.

2.2.5 Adapt invalidate_moves() to delete the moves table (or truncate it).

2.2.6 Repeat for all other cache functions: get_pokemon, save_pokemon, invalidate_pokemon, get_learnset, save_learnset, invalidate_learnset, get_machines, save_machines, get_type_roster, save_type_roster, get_natures, save_natures, get_abilities_index, save_abilities_index, get_ability_detail, save_ability_detail, get_egg_group, save_egg_group, get_evolution_chain, save_evolution_chain, invalidate_evolution_chain, check_integrity, get_cache_info, get_learnset_age_days.

2.2.7 For functions that return a dict or list, ensure the JSON stored in the database is parsed back into Python objects.

2.2.8 Implement check_integrity() using SQL queries (e.g., count rows, check for malformed JSON). Keep the same output format (list of issue strings).

2.2.9 Implement get_cache_info() using SQL SELECT COUNT(*) queries.

2.2.10 Implement get_learnset_age_days(variety_slug, game_slug) by reading the scraped_at column from the learnsets table.

---

Step 2.3 — Handle legacy JSON files (optional migration)

Goal: Provide a smooth transition for existing users. We can decide to ignore old JSON files (the database will be empty and will repopulate lazily). However, we may add a one‑time migration command --migrate-json that reads all JSON files and inserts them into SQLite.

2.3.1 (Optional) Add a command‑line flag --migrate-json to pokemain.py. It would call a function in pkm_cache.py that scans the JSON cache directories and inserts everything into SQLite.

2.3.2 (Optional) Implement the migration function.

Decision: Postpone migration to a later step; keep it optional. We'll document that users can delete their old cache/ folder after the database is populated (or keep it as a backup). The database will fill up gradually as they use the tool.

---

Step 2.4 — Update run_tests.py

Goal: Ensure the test suite works with SQLite.

2.4.1 The existing tests already mock the cache layer (they use a temporary directory). We need to adjust the mock to use a temporary SQLite database instead of JSON files. This will require changes in the test setup to create a temporary SQLite file and redirect _BASE appropriately.

2.4.2 Since many tests depend on the cache being empty, we can keep the same approach: use a temporary directory and set _BASE to that directory. The SQLite database file will be created inside that directory.

2.4.3 Add new tests specifically for SQLite features (e.g., transaction atomicity, concurrent access) if needed.

2.4.4 Verify that all existing tests pass.

---

Step 2.5 — Update documentation

Goal: Document the change in README.md and ARCHITECTURE.md.

2.5.1 Update README.md:

    In the "Files" section, replace cache/ description with cache/ (still a directory, but now contains a single pokemon.db file).

    Add a note that the cache is now stored in a SQLite database (transparent to the user).

    Update any troubleshooting entries if needed.

2.5.2 Update ARCHITECTURE.md:

    Rewrite the cache layout section to describe the SQLite database and its tables.

    Mention the metadata table for schema versioning.

    Note that JSON files are no longer used.

2.5.3 Update HISTORY.md with a new section (e.g., §110) describing the SQLite migration.


---


Step 2.6 — Final verification

Goal: Ensure the toolkit works as expected with the new database.

2.6.1 Run python run_tests.py (both offline and with network) to confirm all tests pass.

2.6.2 Manually test the following workflows:

    First run (no database): select a game, load a Pokémon, view learnable moves, etc. Verify that the database is created and populated correctly.

    Second run (database already exists): verify that data is read from the database and no new fetches occur.

    Check that --cache-info shows correct counts (should match the number of rows in each table).

    Check that --check-cache runs without errors.

2.6.3 Run the build script (python build.py) and test the frozen executable on each platform to ensure SQLite works in the frozen environment (the sqlite3 module is included in Python's standard library, so no extra bundling is needed).


---

Completion criteria for this package

    All public cache functions in pkm_cache.py use SQLite instead of JSON files.

    The database is created automatically on first access.

    All existing tests pass.

    Manual testing confirms that the toolkit behaves identically to the JSON version.

    Documentation is updated to reflect the change.

---

Next steps after this package

Once the SQLite data layer is in place, we can proceed to Step 3: One‑time full data import (--sync command) and Step 4: Terminal UI. The core logic and team features are already separated and will work with the new database without changes.