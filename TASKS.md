# TASKS.md

# Current work — Pythonmon-31: Team coverage vs in-game opponents

**Status:** 🔄 ACTIVE
**Complexity:** 🟡 Medium
**New API call:** No — all data is static / locally bundled
**Cache structure change:** No — trainer data lives in a bundled JSON file,
  not in the user-facing cache layer

## Background

Pythonmon-31 was previously blocked on the absence of trainer data in PokeAPI
(open issue since 2019, no endpoint exists). The feature as a plain type-combo
input ("enter Water / Ground") was dismissed because it misses the core use
case: "can my team beat Cynthia?". The decision was to revisit when either
PokeAPI adds trainer data, or we build a static table ourselves.

This task implements the static table approach.

---

## What we're building

A new feature screen (key X) that lets the player select a named in-game
opponent — gym leader, Elite Four member, or Champion — and see a full
matchup breakdown of their loaded team against that opponent's known party.

Example output:

```
  Team vs Cynthia  [Diamond / Pearl / Platinum — Sinnoh Champion]
  ════════════════════════════════════════════════════════════

  Spiritomb   [Ghost / Dark]   Lv 61
    ✗  Lapras       — weak x4 (Ghost x2, Dark x2)
    ✓  Snorlax      — neutral
    ★  Gengar       — hits SE (Ghost)

  Roserade    [Grass / Poison]  Lv 60
    ★  Charizard    — hits SE (Fire, Flying)
    ...

  ── Summary ──────────────────────────────────────────────
  Uncovered threats: Togekiss, Milotic
  Best leads: Charizard (4 SE), Gengar (3 SE)
```

---

## Data design

### Static trainer data file: data/trainers.json

Bundled with the project (not in cache/ — this is source data, not fetched
data). Lives in a data/ subdirectory at the project root.

Schema:

```json
{
  "diamond-pearl": {
    "Cynthia": {
      "title": "Champion",
      "order": 12,
      "party": [
        {
          "name": "Spiritomb",
          "types": ["Ghost", "Dark"],
          "level": 61,
          "moves": ["Psychic", "Dark Pulse", "Shadow Ball", "Embargo"]
        },
        {
          "name": "Roserade",
          "types": ["Grass", "Poison"],
          "level": 60,
          "moves": ["Grass Knot", "Sludge Bomb", "Shadow Ball", "Extrasensory"]
        },
        {
          "name": "Garchomp",
          "types": ["Dragon", "Ground"],
          "level": 66,
          "moves": ["Dragon Rush", "Earthquake", "Giga Impact", "Crunch"]
        }
      ]
    }
  }
}
```

Key design decisions:
- Keyed by game_slug (matches game_ctx["game_slug"]) then trainer name.
  The G key already filters to the right opponents automatically.
- Types stored directly in the data file — no PokeAPI call needed at runtime.
- Moves field includes the opponent Pokémon's moveset (typically 1–4 moves) for matchup analysis. Enables move-specific coverage calculations and strategy recommendations
- Level included for display context only; not used in calculations.
- "order" field controls picker sort order (gym 1 first, E4 after, Champion
  last). Falls back to alphabetical if absent.
- The file ships with the repository and is read-only at runtime.
- Initial scope: all main-series games from Gen 1 to Gen 9 — gym leaders,
  Elite Four, Champion, notable rival final battles.

### Coverage scope for initial release

Priority order for data entry:

Phase 1 (ship with initial release):
- Red / Blue / Yellow — 8 gyms + E4 + Blue
- Diamond / Pearl / Platinum — 8 gyms + E4 + Cynthia + Barry final
- Scarlet / Violet — 8 gyms + E4 + Geeta + Nemona final

Phase 2 (follow-up, one game at a time):
- Gen 2, Gen 3, Gen 5, Gen 6, Gen 7, Gen 8

Data sources: Bulbapedia trainer pages. All types are era-correct for the
game (e.g. Clefable is Normal in Gen 1–5, Fairy only from Gen 6).

---

## Implementation — four iterations

### Iteration A — Data file + loader

Deliverable: data/trainers.json populated for Phase 1 games. Loader
functions in new feat_opponent.py. No display yet.

A1 — feat_opponent.py data loader:

```python
def load_trainer_data() -> dict
    # Load the bundled trainers.json. Returns {} on missing file.

def get_trainers_for_game(game_slug: str) -> dict
    # Return {trainer_name: {title, order, party}} for the game slug.

def list_trainer_names(game_slug: str) -> list[str]
    # Return trainer names sorted by "order" field, then alphabetical.
```

Iteration A tests (pure, no I/O — use fixture dicts):
- get_trainers_for_game with fixture → correct trainer dict returned
- get_trainers_for_game with unknown slug → {}
- list_trainer_names returns names sorted by order field
- list_trainer_names on empty game → []

---

### Iteration B — Pure matchup logic

Deliverable: analyze_matchup() pure function. Fully testable offline.

B1 — feat_opponent.py analysis engine:

```python
def analyze_matchup(team_ctx, trainer, era_key) -> list[dict]
    # For each trainer Pokemon, compute:
    #   threats  — team members weak to it (form_name, multiplier)
    #   resists  — team members that resist it (form_name, multiplier)
    #   counters — team members with SE type advantage (form_name, [types])
    #   moveset  — opponent's moves, used for defensive/offensive coverage analysis

def uncovered_threats(matchup_results) -> list[dict]
    # Trainer Pokemon that no team member can hit SE.

def recommended_leads(matchup_results, team_ctx) -> list[str]
    # Team members sorted by number of trainer Pokemon they cover SE.
```

Iteration B tests (pure):
- Single team member vs known trainer party → correct threats/resists/counters
- Dual-type trainer Pokemon: combined defensive multiplier applied correctly
- uncovered_threats correctly identifies Pokemon with zero SE coverage
- recommended_leads returns highest-coverage member first
- Empty team → all trainer Pokemon uncovered, no leads
- Era-awareness: Fairy absent in era1/era2, present in era3

---

### Iteration C — Display

Deliverable: display_opponent_analysis() prints full matchup screen.

Per-trainer-Pokemon block format:
```
  Spiritomb   [Ghost / Dark]   Lv 61
    ✗  Lapras     — weak x4 (Ghost x2, Dark x2)
    ✓  Snorlax    — neutral
    ★  Gengar     — hits SE (Ghost)
```

Summary block:
```
  ── Summary ──────────────────────────────
  Uncovered: Togekiss, Milotic
  Best leads: Gengar (4 SE), Charizard (3 SE)
```

Iteration C tests (stdout capture):
- All trainer Pokemon names present in output
- Star markers present for SE coverage entries
- X markers present for threat entries
- Summary section present with "Uncovered" and "Best leads" lines

---

### Iteration D — Menu wiring + trainer picker

Deliverable: Key X in pokemain. Interactive trainer picker. End-to-end.

D1 — Trainer picker:
```
  Select opponent  |  Diamond / Pearl / Platinum
  ──────────────────────────────────────────────
   1. Roark          (Gym Leader 1 — Rock)
   2. Gardenia        (Gym Leader 2 — Grass)
   ...
  12. Cynthia         (Champion)
  13. Barry           (Rival — final)
```

D2 — pokemain.py:
- Import feat_opponent
- Menu line: "X. Team vs opponent" — shown when has_game and team_size > 0
- Handler: show picker, run analysis, wait for Enter

D3 — run_tests.py: add feat_opponent to SUITES (offline)

---

## Completion criteria

Pythonmon-31 is complete when:

* data/trainers.json populated for all Phase 1 games
* feat_opponent.py implements all four iteration deliverables
* Key X accessible from pokemain when team + game are loaded
* Trainer picker shows trainers filtered to selected game, sorted by order
* Matchup display shows per-trainer-Pokemon blocks + summary
* Era-aware: type chart matches game_ctx["era_key"]
* All offline tests pass (python run_tests.py --offline)
* HISTORY.md, ROADMAP.md, ARCHITECTURE.md updated
* data/ directory documented in ARCHITECTURE.md file layout
