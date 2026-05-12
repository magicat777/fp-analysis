---
name: Pre-trip checklist  -  avoid failed-travel losses
description: User lost ~$100k on trips to locations that didn't support rod-pods/boats or required gear they didn't bring; enforce pre-trip review
type: feedback
---

On 2026-04-20 user arrived at Saint-Croix with only ~$1.98M after losing ~$100k on failed trips to locations that didn't match the brought gear (rod-pod-required competitions without a rod-pod; boat-required locations without a boat loaded).

**Rule:** Before recommending any location, verify the user's gear matches the location's constraints.

**Why:** Travel costs are non-refundable in FP. Arriving at a location and discovering a constraint (no rod-pods allowed, boat required for target spot, license expired) wastes the trip and the travel fee. Multiple failed trips in a row can cost ~$100k+.

**How to apply:**
- Before any trip recommendation, ask or confirm:
  1. **Competition rules** (if competition): rod-pods allowed? e-rods? boats? keepnets only?
  2. **License status**  -  Advanced license active and unexpired?
  3. **Boat/kayak**  -  is the location a shore-only spot, or does the target species require a boat? Is the boat in backpack inventory?
  4. **Rod-pod**  -  is the target tactic rod-pod-dependent? If yes, confirm it's packed.
  5. **Groundbait + feeder**  -  needed for the target fish? Packed?
- If the user mentions a new location, proactively flag constraints from the location's `manual_analysis_*.json` file or the fp-collective API
- Update location analysis files when new gear-constraint info is discovered
