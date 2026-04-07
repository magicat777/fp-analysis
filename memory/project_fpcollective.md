---
name: FP Collective Scraper Project
description: Fishing Planet loadout analyzer that scrapes fp-collective.com API and generates interactive React HTML reports with loadout analysis
type: project
---

Tool built to scrape fp-collective.com REST API (at api.fp-collective.com/wp-json/fp-collective/v2/) for Fishing Planet PC game data, analyze player loadout screenshots via Claude Vision, and generate interactive single-page React HTML reports.

**Why:** User plays Fishing Planet and wants data-driven loadout optimization per location to maximize XP and income.

**How to apply:** The script is `fp_analyzer.py`. It supports `--location`, `--list-locations`, `--archive`, `--no-vision`, `--analysis-file`, and `--output` flags. HEIC screenshots go in project root and get auto-moved to `current_loadout/`. Reports go to `reports/`. Past loadouts archived with timestamps to `past_loadouts/`. User's Anthropic API key is stored at `/Users/jasonholt/Claude Projects/secrets/claude.api.s` but had zero credits as of 2026-04-01.
