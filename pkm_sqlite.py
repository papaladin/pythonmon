#!/usr/bin/env python3
"""
pkm_sqlite.py  SQLite database layer for Pokemon Toolkit.

Manages a single SQLite database file, creating tables on first use.
Provides low-level functions to read/write data as JSON strings.
All public functions in pkm_cache.py will eventually call these.
"""

import sqlite3
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

# ── Database path determination ───────────────────────────────────────────────

_BASE = None

def set_base(base_path: str) -> None:
    """Set the base directory where the database file will be stored."""
    global _BASE
    _BASE = base_path

def _db_path() -> str:
    """Return the full path to the SQLite database file."""
    if _BASE is None:
        raise RuntimeError("Database base path not set. Call set_base() first.")
    return os.path.join(_BASE, "pokemon.db")


# ── Connection and initialisation ────────────────────────────────────────────

@contextmanager
def get_connection():
    """Yield a sqlite3 connection, ensuring tables exist and commit/rollback."""
    # Ensure the directory exists
    os.makedirs(_BASE, exist_ok=True)
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        _ensure_tables(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist (idempotent)."""
    # metadata table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Create all other tables (if not exists)
    _create_tables(conn)
    # Set schema version if not already set
    cur = conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
    row = cur.fetchone()
    if row is None:
        conn.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '1')")


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create all tables (idempotent)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pokemon (
            slug TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            scraped_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS learnsets (
            variety_slug TEXT,
            game_slug TEXT,
            data TEXT NOT NULL,
            scraped_at TEXT,
            PRIMARY KEY (variety_slug, game_slug)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS moves (
            name TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            version INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS machines (
            url TEXT PRIMARY KEY,
            label TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS types (
            type_name TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS natures (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS abilities_index (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS abilities (
            slug TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS egg_groups (
            slug TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evolution (
            chain_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_status (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)


# ── Low-level data access functions ──────────────────────────────────────────

def _json_loads(text):
    return json.loads(text) if text else None

def _json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=None) if obj is not None else None


# Move functions
def get_move(name: str):
    with get_connection() as conn:
        cur = conn.execute("SELECT data FROM moves WHERE name = ?", (name,))
        row = cur.fetchone()
        return _json_loads(row["data"]) if row else None

def save_move(name: str, entries: list, version: int):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO moves (name, data, version) VALUES (?, ?, ?)",
            (name, _json_dumps(entries), version)
        )

def save_moves_batch(batch: dict, version: int):
    with get_connection() as conn:
        for name, entries in batch.items():
            conn.execute(
                "INSERT OR REPLACE INTO moves (name, data, version) VALUES (?, ?, ?)",
                (name, _json_dumps(entries), version)
            )

def get_all_moves():
    with get_connection() as conn:
        cur = conn.execute("SELECT name, data FROM moves")
        rows = cur.fetchall()
        return {row["name"]: _json_loads(row["data"]) for row in rows}

def invalidate_moves():
    with get_connection() as conn:
        conn.execute("DELETE FROM moves")


# Pokemon functions
def get_pokemon(slug: str):
    with get_connection() as conn:
        cur = conn.execute("SELECT data, scraped_at FROM pokemon WHERE slug = ?", (slug,))
        row = cur.fetchone()
        return _json_loads(row["data"]) if row else None

def save_pokemon(slug: str, data: dict, scraped_at: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pokemon (slug, data, scraped_at) VALUES (?, ?, ?)",
            (slug, _json_dumps(data), scraped_at)
        )

def invalidate_pokemon(slug: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM pokemon WHERE slug = ?", (slug,))


# Learnset functions
def get_learnset(variety_slug: str, game_slug: str):
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT data, scraped_at FROM learnsets WHERE variety_slug = ? AND game_slug = ?",
            (variety_slug, game_slug)
        )
        row = cur.fetchone()
        return _json_loads(row["data"]) if row else None

def save_learnset(variety_slug: str, game_slug: str, data: dict, scraped_at: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO learnsets (variety_slug, game_slug, data, scraped_at) VALUES (?, ?, ?, ?)",
            (variety_slug, game_slug, _json_dumps(data), scraped_at)
        )

def get_learnset_age(variety_slug: str, game_slug: str):
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT scraped_at FROM learnsets WHERE variety_slug = ? AND game_slug = ?",
            (variety_slug, game_slug)
        )
        row = cur.fetchone()
        if row and row["scraped_at"]:
            scraped = datetime.fromisoformat(row["scraped_at"]).replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = now - scraped
            return delta.days
        return None

def invalidate_learnset(variety_slug: str, game_slug: str):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM learnsets WHERE variety_slug = ? AND game_slug = ?",
            (variety_slug, game_slug)
        )


# Machines
def get_machines():
    with get_connection() as conn:
        cur = conn.execute("SELECT url, label FROM machines")
        rows = cur.fetchall()
        return {row["url"]: row["label"] for row in rows}

def save_machines(data: dict):
    with get_connection() as conn:
        conn.execute("DELETE FROM machines")
        for url, label in data.items():
            conn.execute("INSERT INTO machines (url, label) VALUES (?, ?)", (url, label))


# Type rosters
def get_type_roster(type_name: str):
    with get_connection() as conn:
        cur = conn.execute("SELECT data FROM types WHERE type_name = ?", (type_name,))
        row = cur.fetchone()
        return _json_loads(row["data"]) if row else None

def save_type_roster(type_name: str, roster: list):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO types (type_name, data) VALUES (?, ?)",
            (type_name, _json_dumps(roster))
        )


# Natures
def get_natures():
    with get_connection() as conn:
        cur = conn.execute("SELECT data FROM natures WHERE id = 1")
        row = cur.fetchone()
        return _json_loads(row["data"]) if row else None

def save_natures(data: dict):
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO natures (id, data) VALUES (1, ?)", (_json_dumps(data),))


# Abilities index
def get_abilities_index():
    with get_connection() as conn:
        cur = conn.execute("SELECT data FROM abilities_index WHERE id = 1")
        row = cur.fetchone()
        return _json_loads(row["data"]) if row else None

def save_abilities_index(data: dict):
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO abilities_index (id, data) VALUES (1, ?)", (_json_dumps(data),))


# Per-ability detail
def get_ability_detail(slug: str):
    with get_connection() as conn:
        cur = conn.execute("SELECT data FROM abilities WHERE slug = ?", (slug,))
        row = cur.fetchone()
        return _json_loads(row["data"]) if row else None

def save_ability_detail(slug: str, data: dict):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO abilities (slug, data) VALUES (?, ?)",
            (slug, _json_dumps(data))
        )


# Egg groups
def get_egg_group(slug: str):
    with get_connection() as conn:
        cur = conn.execute("SELECT data FROM egg_groups WHERE slug = ?", (slug,))
        row = cur.fetchone()
        return _json_loads(row["data"]) if row else None

def save_egg_group(slug: str, roster: list):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO egg_groups (slug, data) VALUES (?, ?)",
            (slug, _json_dumps(roster))
        )


# Evolution chains
def get_evolution_chain(chain_id: int):
    with get_connection() as conn:
        cur = conn.execute("SELECT data FROM evolution WHERE chain_id = ?", (chain_id,))
        row = cur.fetchone()
        return _json_loads(row["data"]) if row else None

def save_evolution_chain(chain_id: int, paths: list):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO evolution (chain_id, data) VALUES (?, ?)",
            (chain_id, _json_dumps(paths))
        )

def invalidate_evolution_chain(chain_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM evolution WHERE chain_id = ?", (chain_id,))


# Metadata
def get_metadata(key: str):
    with get_connection() as conn:
        cur = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

def set_metadata(key: str, value: str):
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value))


# Sync status
def get_sync_status(key: str):
    with get_connection() as conn:
        cur = conn.execute("SELECT value FROM sync_status WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

def set_sync_status(key: str, value: str):
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO sync_status (key, value) VALUES (?, ?)", (key, value))


# Cache info and integrity
def get_cache_info():
    """Return a dict with counts of entries per table."""
    info = {}
    with get_connection() as conn:
        for table in ("pokemon", "learnsets", "moves", "machines", "types", "natures",
                      "abilities_index", "abilities", "egg_groups", "evolution"):
            cur = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            row = cur.fetchone()
            info[table] = row["cnt"]
    return info

def check_integrity():
    """Return a list of issue strings; empty if clean."""
    issues = []
    with get_connection() as conn:
        # Check that moves JSON is valid
        cur = conn.execute("SELECT name, data FROM moves")
        for name, data in cur:
            try:
                json.loads(data)
            except json.JSONDecodeError:
                issues.append(f"moves: {name} has invalid JSON")
        # Other tables could be checked similarly, but for now it's enough.
    return issues