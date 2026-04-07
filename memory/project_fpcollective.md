---
name: FP Collective Scraper Project
description: Fishing Planet loadout analyzer — scrapes fp-collective.com API + wiki.fishingplanet.com, analyzes loadout screenshots, generates interactive React HTML reports hosted at fpreports.click
type: project
---

## Overview
Tool that scrapes **fp-collective.com REST API** (at `api.fp-collective.com/wp-json/fp-collective/v2/`) and **wiki.fishingplanet.com** (MediaWiki API) for Fishing Planet PC game data, analyzes player loadout screenshots, and generates interactive single-page React HTML reports.

## Key Script: `fp_analyzer.py`
- `--location <slug>` — generate report for a location
- `--list-locations` — show all 27 locations
- `--analysis-file <path>` — use manual analysis JSON (our primary workflow)
- `--deploy` — upload reports to AWS S3/CloudFront
- `--archive` — move current loadout to past_loadouts
- `--no-vision` — skip Claude Vision API (we always use manual analysis instead)

## Data Sources
- **fp-collective API**: fish, baits, lures, hooks, jigheads, spots, weather/bite charts, license costs, ubersheet data
- **wiki.fishingplanet.com**: equipment images, howToCatch guides, rod/reel/line stats
- **Manual analysis JSONs**: per-location loadout analysis with slot ratings, issues, improvements, leader recommendations, passive fishing strategy, boat info, mission plans

## Report Features (React SPA tabs)
- Loadout Analysis (per-slot with screenshots, ratings, leader recommendations)
- Mission Plan (when applicable — target fish strategy)
- Recommended Loadout (with wiki equipment images)
- Priority Actions
- Fish & Tackle (activity times, preferred depth, recommended hook, ubersheet data, preferred baits with images, lure types)
- Fishing Spots
- Bite Charts (weather patterns)
- Passive Fishing (rod stand strategy, income estimates)
- Gear & Equipment (boat recommendations for boat-enabled locations)
- Licenses & Costs
- XP & Income Guide
- Reports Menu button linking back to index

## Hosting
- **AWS S3** bucket: `fp-reports-726138838993`
- **CloudFront** distribution: `E3TOOZU85OXSCW`
- **Custom domain**: `fpreports.click` (Route53 + ACM SSL)
- **AWS profile**: `fp-deploy` (IAM user with long-lived API key, no session expiry)
- Reports sorted by level on index page with level badges

## File Structure
- `fp_analyzer.py` — main script (cross-platform: macOS + Windows)
- `manual_analysis_*.json` — per-location analysis files (9 locations so far)
- `player_inventory.json` — full gear inventory (rods, reels, lines, leaders, tackle, boats)
- `reports/index.html` — report index template
- `current_loadout/` — latest loadout screenshots (HEIC from iPhone or JPG from PC)
- `home-inventory/` — home storage inventory screenshots
- `memory/` — Claude memory files

## Workflow
1. Player screenshots loadout in-game (iPhone HEIC or PC JPG)
2. Copy screenshots to `current_loadout/`
3. Claude reads screenshots, fetches location API data, builds manual analysis JSON
4. Run `python3 fp_analyzer.py --location <slug> --analysis-file <file>` to generate report
5. Run `python3 fp_analyzer.py --deploy` to push to fpreports.click

**Why:** User plays Fishing Planet and wants data-driven loadout optimization per location to maximize XP and income.
