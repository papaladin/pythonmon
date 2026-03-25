Current work — Post‑V2 UI polish & consolidation
Status: 🔄 PLANNED
Complexity: 🟡 Medium
Goal: Improve team builder suggestions by filtering out intermediate evolution stages (those that evolve purely by level‑up), and merge the stat comparison feature (C) into the learnset comparison screen (L) to reduce menu clutter and streamline the user experience.

Task 1 — Team builder: filter out level‑up‑only evolutions
Problem
The team builder currently suggests every Pokémon that matches the team’s gaps, including the base form and its evolution(s) that are obtained solely by level‑up (e.g., Dratini, Dragonair, Dragonite). Users typically want the final, most powerful form, not the middle stage, unless the middle stage offers a different typing or role that is still relevant (e.g., Seadra → Kingdra requires a trade + item, so both may be valid suggestions).

Desired behaviour
If a Pokémon evolves only via level‑up (no trade, no item, no other special condition), and a later stage also matches the team’s gaps, only the highest stage should appear as a candidate.

If the evolution involves a non‑level‑up trigger (trade, use item, high friendship, etc.), both forms should be considered independently because they represent different acquisition methods and may have different typings or roles.

Steps
1.1 Add helper to determine if an evolution path is pure level‑up
In core_evolution.py, add a function is_pure_level_up_chain(chain_paths: list, target_slug: str) -> bool that returns True if the only way to reach target_slug from its base is via level‑up triggers.

The function should traverse the path from base to target and check that every trigger string contains only "Level" (and no other keywords like Trade, Use, Friendship, etc.).

Because PokeAPI triggers may contain additional text (e.g., "Level up (day)", "High Friendship"), we can check "Level" in trigger and that no other condition keywords appear. A safe rule: trigger is considered pure level‑up if it starts with "Level" and contains none of the words "Trade", "Use", "Friendship", "Happiness", "Item", "Move", "Time", "Location". We'll define a constant set _NON_LEVEL_KEYWORDS in core_evolution.py.

Write tests for various evolution chains (Charizard, Dragonite, Kingdra, Espeon, etc.).

1.2 Integrate filter into candidate pool building
In feat_team_builder.build_suggestion_pool, after gathering candidates, run a pass that removes lower‑stage forms that are pure level‑up evolutions and have a higher‑stage form also in the pool.

Use evolution_chain_id from the cache to get the flattened chain for each candidate. This requires loading the evolution chain for each slug (maybe cached). For performance, we can batch‑load chains for all candidate slugs.

If a higher stage exists and is also in the candidates, discard the lower stage.

For safety, we should also check that the higher stage has the same (or better) typing coverage regarding gaps (i.e., it's not a form that loses a relevant type). Since the higher stage may have different typing, we need to ensure it actually covers the same gaps. We'll do a simple check: if the higher stage’s types are a superset (or at least cover the same offensive/defensive gaps) as the lower stage, we can filter the lower; otherwise, keep both.

1.3 Update tests
Add unit tests for is_pure_level_up_chain.

Add integration tests in feat_team_builder._run_tests (with mocks) to verify filtering works as expected.

Task 2 — Merge stat comparison into learnset comparison
Problem
The stat comparison (key C) and learnset comparison (key L) both compare two Pokémon side‑by‑side. The learnset comparison already includes a stat header at the top, making the stat comparison screen largely redundant. Consolidating these into a single feature reduces menu clutter and provides a more comprehensive comparison in one place.

Desired behaviour
Remove the separate C menu entry and its handler.

Enhance the learnset comparison screen (L) to also allow the user to view only the stat comparison, if they prefer, or always show the stats header with an option to toggle off the move sections.

Alternatively, we can keep the stat comparison as an optional sub‑menu within the learnset comparison, but the simplest is to keep the current learnset comparison and just drop the standalone C screen.

Steps
2.1 Remove stat comparison from menu
In pokemain.py, remove the C. Compare stats line from _build_menu_lines.

Remove the handler for elif choice == "c".

2.2 Ensure learnset comparison is complete
The current learnset comparison already shows a stat header. Confirm it uses feat_stat_compare.compare_stats, total_stats, infer_role, infer_speed_tier. It does.

No functional changes needed to feat_learnset_compare.py.

2.3 Update documentation
Remove C from the menu description in README.md.

Update the "Features" section to note that stat comparison is integrated into the learnset comparison.

Update ARCHITECTURE.md and HISTORY.md accordingly.

2.4 (Optional) Add a toggle in learnset comparison to show/hide move sections
If users still want a pure stat comparison without scrolling through moves, we could add a prompt after picking the second Pokémon: "Show full learnset comparison? (y/n)". If no, only the stat header is displayed.

This keeps the feature optional without adding a separate menu key.

This would require changes to feat_learnset_compare.display_learnset_comparison to accept a full parameter, and in run() we could ask the user.

Given the scope, we can include this as a nice‑to‑have but not mandatory.