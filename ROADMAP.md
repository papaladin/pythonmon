# ROADMAP.md
# Long-term feature goals for the Pokemon Toolkit

> Items marked ✅ are complete. Items marked ⬜ are planned.
> For granular steps of the item currently in progress, see TASKS.md.
> For completed item details, see HISTORY.md.

---

## Completed features

| Feature | Description | History ref |
|---|---|---|
| Core CLI skeleton | Menu loop, game + Pokemon context, cache layer | §1–§11 |
| Web scraper (move data) | pokemondb.net move table + modifications scraper | §1–§11 |
| PokeAPI migration | Replaced web scraper with PokeAPI; move versioning schema | §12–§13 |
| Type vulnerabilities | Full defensive chart, all 3 type chart eras | §15 |
| Learnable move list | Level-up / TM-HM / tutor / egg with stats per row | §16–§19 |
| Moveset recommendation | Scored pool + 3 modes (Coverage / Counter / STAB), locked slots | §21–§50 |
| Type coverage display | Types hit SE shown in moveset output; uncoverable weakness annotation | §44, §54 |
| Per-variety learnsets | Regional / alternate forms get correct move pool (variety_slug) | §42–§43 |
| Type browser | List all Pokemon of a given type or type combo | §51–§52 |
| Nature browser | 25-nature table + stat recommender by role and speed tier | §53 |
| Ability browser | Browse all abilities + full effect + Pokemon roster drill-in | §57 |
| Quick view (option 1) | Base stats bar chart + abilities + type chart in one screen | §58 |
| Team loader | Session-only team of up to 6 Pokemon; T key; add/remove/clear | §59 |
| Team defensive analysis | Unified type table: weak/resist/immune per type, gap labels | §60–§61 |

---

## Team features roadmap (active area)

### Step 3a — Team offensive coverage by type (✅ Done §62)

For each attacking type in the era, show how many team members can hit SE.
- Input: team_ctx + game_ctx
- Output: table of types the team covers offensively (STAB or not), types with no SE coverage
- Approach: for each member, find types they hit SE based on their own types (STAB only first pass)
- Gap detection: types with zero SE coverage across the whole team
- New file: `feat_team_offense.py`
- New key: `O` in pokemain (visible when team loaded + game selected)

### Step 3b — Team offensive coverage by learnable moves (⬜ Next)

Extend step 3a: instead of only using member types, check actual learnable moves in cache.
- For each member: fetch learnset, find moves that hit SE against each type
- Richer gap detection: "can hit Electric SE, but only Blastoise with Thunderbolt"
- Requires all 6 members to have learnsets cached
- Potentially slow on first run (6 × PokeAPI calls) — show progress indicator

### Step 4 — Team moveset synergy (⬜ Planned)

Run moveset recommendation for each member, then aggregate:
- Show per-slot recommended moveset (Coverage / Counter / STAB, one mode per slot)
- Team-level coverage summary: types the combined movesets cover SE
- Identify remaining gaps: types no moveset covers
- Option to re-run one slot with a different mode and see impact on team coverage
- New file: `feat_team_moveset.py`

### Step 5 — Team builder / slot suggestion (⬜ Planned)

Given a partial team (1–5 members), suggest types / roles that would fill coverage gaps.
- Analyse current team's defensive gaps and offensive gaps
- Suggest: "You need something that resists Rock and can hit Electric SE"
- Optional: suggest specific Pokemon from the type roster (requires types cache)
- This is the highest-complexity feature — depends on steps 3 and 4 being solid first

---

## Other planned improvements

### Pokemon features

| Feature | Description | Priority |
|---|---|---|
| Stat comparison | Compare base stats of two Pokemon side by side | Low |
| Evolution chain | Show evolution conditions and stat changes | Low |
| Per-form learnset | Fetch actual per-form move list for forms where it differs (Rotom, Wormadam, Megas) | Low |

### UX improvements

| Feature | Description | Priority |
|---|---|---|
| Team persistence | Save/load team to a named JSON file | Medium |
| Fuzzy name matching | Accept partial names with ranked suggestions (e.g. "char" → Charizard / Charmander / Charmeleon) | Medium |
| Move filter in pool | Filter learnable move list by type, category, or power range | Low |
| History within session | Navigate back through recently viewed Pokemon | Low |

### Data / infrastructure

| Feature | Description | Priority |
|---|---|---|
| STATUS_MOVE_TIERS auto-update | Detect moves with no tier and prompt user to classify | Low |
| Cache integrity check | Scan all cache files and report corrupt / outdated entries | Low |
| Legends: Z-A cooldown | Model cooldown system once PokeAPI supports it | Blocked (PokeAPI) |

---

## Out of scope (deliberate)

- **GUI / web interface** — CLI by design; Thonny compatibility required
- **Online multiplayer meta analysis** — this tool is for in-game teams, not competitive
- **Database migration** — JSON cache is sufficient; SQLite documented as future option only
- **Pip packages beyond requests** — hard constraint
