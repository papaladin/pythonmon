# ROADMAP.md
# Long‑term feature goals for the Pokemon Toolkit

> Items marked ✅ are complete.  
> For completed item details, see `HISTORY.md`.  
> For granular steps of the item currently in progress, see `TASKS.md`.

---

## Roadmap to V2 (Completed)
The following V2 goals have been achieved:
- [x] Core library / presentation separation (core_*.py, feat_*.py)
- [x] SQLite data layer (single pokemon.db)
- [x] One‑time full data import (`--sync`)
- [x] UI abstraction layer (ui_base.py, ui_cli.py, ui_tui.py)
- [x] TUI foundation (split pane, modals, progress bar)
- [x] Team builder evolution filtering
- [x] Learnset comparison (merged stat comparison)
- [x] Main menu reorganisation
- [x] Move table pre‑load key change (Y) and TM/HM pre‑load (W)
- [x] Default UI for frozen builds (TUI by default)
- [x] Team builder BST bonus

---

## Long‑Term Product Roadmap (Beyond V2)

This roadmap describes the evolution of the toolkit into a complete Pokémon companion for casual players, team builders, and competitive enthusiasts. Each phase builds on the previous one and can be pursued independently.

### Phase 1: Polish & User Experience (Current)
- [ ] Fully interactive TUI with colours, mouse support, and error modals.
- [ ] Persistent team storage (save/load teams to disk).
- [ ] Batch team loading with comma‑separated names (already done).
- [ ] Finalise self‑test coverage for all modules.

### Phase 2: Data Completeness & Accuracy
- [ ] Validate move versioning against official sources; add corrections for PokeAPI gaps.
- [ ] Expand trainer database to all games, including rematches, battle facilities, and post‑game.
- [ ] Fetch full ability effect text and Pokémon lists for all abilities (partial).
- [ ] Ensure correct egg groups for all species (based on PokeAPI species data).
- [ ] Comprehensive handling of regional forms (Alolan, Galarian, Hisuian, etc.) with proper typing, stats, and learnsets.

### Phase 3: Advanced Analysis
- [ ] **Moveset optimisation**:
  - Single‑objective optimisation (coverage, power, status) replaced by multi‑objective adjustable preferences.
  - Include Z‑Moves, Dynamax, Terastallization when relevant (new data sources may be required).
- [ ] **Team builder upgrade**:
  - Joint optimisation over full 6‑Pokemon teams (beam search / genetic algorithms).
  - Counter‑team builder: given an opponent team, suggest Pokémon that counter them.
  - Synergy scoring: reward cores (e.g., Fire/Water/Grass) and penalise type overlap.
- [ ] **Damage calculator**: full battle simulation with EVs, IVs, levels, items, weather, terrain, abilities – integrated into team analysis.

### Phase 4: Personalisation & Integration
- [ ] User profiles: favourite Pokémon, custom teams, locked move preferences.
- [ ] Game progress tracking: mark gyms/E4 defeated, unlock post‑game trainers.
- [ ] Integration with game saves: read Pokémon data from save files (via pkhex‑like libraries) to analyse actual in‑game teams.
- [ ] Web version: offline‑first static site (React + IndexedDB) using the same core logic compiled to WebAssembly.

### Phase 5: Community & Extensibility
- [ ] Plugin system: allow users to add custom game data, analysis modules, or UI themes.
- [ ] REST API: expose core analysis as a service for third‑party tools.
- [ ] Mobile app: native iOS/Android app using the same core logic (via Rust or a shared library), with touch‑friendly UI.

---

## Current Status (Phase 1)
Work is focused on polishing the TUI, adding team persistence, and finalising test coverage. See `TASKS.md` for granular next steps.