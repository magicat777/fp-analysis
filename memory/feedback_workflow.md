---
name: Workflow preferences and feedback
description: How the user likes to work — analysis approach, report format, deployment, communication style
type: feedback
---

## Analysis Workflow
- User provides loadout screenshots (iPhone HEIC or PC JPG) in `current_loadout/`
- Claude reads ALL screenshots, identifies every component, cross-references with fp-collective API data
- Build manual analysis JSON with per-slot ratings, issues, improvements, leader recommendations
- Include passive fishing strategy, boat recommendations (when available), income estimates
- Generate report and deploy to fpreports.click in one flow

**Why:** Vision API credits ran out early on, so we do manual analysis by reading screenshots directly. This became the standard workflow.

**How to apply:** Always read screenshots first, fetch location API data, build the analysis JSON, generate report, and deploy. Don't ask to use the Vision API.

## Report Preferences
- Imperial units throughout (feet, lbs, inches) — user explicitly requested this
- Fish prices converted to $/lb for consistency (game uses $/kg internally but we convert for imperial display)
- Include recommended hook sizes per fish (from howToCatch API data)
- Include fish activity times and preferred depths
- Include ubersheet (community-tested) recommended tackle
- Include preferred baits with wiki images
- Include leader length and depth setting recommendations for float rigs
- Reports Menu button on every page to return to index
- Index page sorted by level with level badges
- Deploy after every report generation

**Why:** User accesses reports from tablet and other devices via fpreports.click while playing.

## Gear Recommendations
- Always check `player_inventory.json` first before recommending purchases
- User has extensive DLC inventory — often already owns the ideal gear
- When recommending new purchases, specify baitcoin vs credit cost and level requirement
- Consider rod line weight limits carefully — user discovered rods damage with overweight line
- Bottom rods accept sinkers; feeder rods accept feeders; match rods accept floats; spinning/casting accept lures only

**Why:** User was frustrated when recommended tackle didn't fit rods due to weight/type restrictions.

## Communication Style
- Be concise and direct
- Use tables for loadout summaries
- Always include the "why" for recommendations
- Flag missing species coverage prominently
- Night fishing strategies are important — many high-value fish are nocturnal
