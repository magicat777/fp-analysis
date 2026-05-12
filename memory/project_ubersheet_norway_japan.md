---
name: Ubersheet Norway/Japan update outreach
description: User contacted FP Ubersheet project owner on Reddit on 2026-04-30 to request community ubersheet data for Norway (Skarland Fjord) and Japan locations
type: project
---

User reached out to the **FP Ubersheet project owner on Reddit** on 2026-04-30 to ask whether they will be updating the ubersheet for **Norway (Skarland Fjord, L105 Ocean)** and **Japan** locations.

**Why:** Confirmed 2026-04-30 that the fp-collective `/wp-json/fp-collective/v2/fish/{slug}` endpoint returns empty `ubersheetBaitIds` / `ubersheetLureIds` / `ubersheetHookIds` for all Skarland species — and that the data quality issue is upstream (the Ubersheet project itself, not the API). Until Norway/Japan are added to the ubersheet, the per-fish "UBERSHEET RECOMMENDED" panel will be missing on Skarland (and presumably Maldives + Japan when reached). Workaround in place: bite-map aggregation derived from `/wp-json/fp-collective/v2/fish-markers?placeId={id}` covers the gap with community catch data (446 markers for Skarland giving max weight, top baits/lures/hooks per fish).

**How to apply:**

1. **Recheck the v2/fish endpoint periodically** for Skarland species (atlantic-cod, greenland-shark, atlantic-halibut, etc.) — once `ubersheetBaitIds` becomes non-empty, the existing renderer code will automatically prefer the curated ubersheet panel over the bite-map fallback. No code change needed when that happens.

2. **If user mentions ubersheet, Norway, or Japan tackle data:** check this memory first to see whether the Reddit outreach has resulted in an update. May need to follow up with user on whether they got a response.

3. **For new ocean DLC unlocks (Maldives L94, Japan locations):** assume bite-map aggregation will be the primary data source until the ubersheet catches up. The fallback chain (`fishDetails.max_weight` → `fish endpoint maxWeight` → `bite-map aggregate max`) handles this automatically.

4. **Don't overpromise data quality on saltwater locations** when coaching the user — until the ubersheet is updated, recommendations should lean on `howToCatch` prose + bite-map aggregates + the user's own player_records, not on missing ubersheet fields.

**Open status:** Awaiting Reddit response. No timeline yet.
