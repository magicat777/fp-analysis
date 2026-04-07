---
name: API and data source reference
description: Key API endpoints, wiki access patterns, and data sources used by the project
type: reference
---

## fp-collective API
- Base: `https://api.fp-collective.com/wp-json/fp-collective/v2/`
- Endpoints: `/places`, `/places/{slug}`, `/fish/{slug}`, `/baits`, `/lures`, `/hooks`, `/jigheads`
- Paginated: `?page=N` (20 items/page), response has `count` and `pages` fields
- Individual fish endpoint has `ubersheetBaitIds`, `ubersheetLureIds`, `ubersheetHookIds`, `ubersheetJigheadIds`
- Location endpoint has `fishDetails` (JSON string with name/types/max_weight/price), `fish` array (with baitIds/lureIds), `spots`, `dayWeatherPatterns`, `nightWeatherPatterns`, license data
- No auth required, no rate limiting observed

## wiki.fishingplanet.com
- MediaWiki API at `https://wiki.fishingplanet.com/api.php`
- SSL verification must be disabled (`verify=False`)
- Equipment pages: `Match rods`, `Spinning rods`, `Casting rods`, `Bottom rods`, `Feeder rods`, `Spinning reels`, `Casting reels`, `Simple Hooks`, `Common Jig Heads`, `Classic Bobbers`, `Soft plastic baits`, `Spoons`, `Spinners`, etc.
- Image resolution: `action=query&titles=File:NAME.png&prop=imageinfo&iiprop=url`
- Bait images use descriptive names (Bloodworms.png, Crickets.png)
- Lure images use numeric IDs (723.png) — must parse HTML tables to map
- Cache key normalization: wiki returns spaces in filenames, code uses underscores

## AWS Hosting
- S3 bucket: `fp-reports-726138838993`
- CloudFront: `E3TOOZU85OXSCW`
- Domain: `fpreports.click` (Route53 hosted zone `Z05399992FI19H26Z6LLA`)
- SSL cert: ACM `arn:aws:acm:us-east-1:726138838993:certificate/a5220e0c-8112-4e3c-9ae3-99b705535a82`
- Deploy profile: `fp-deploy` (IAM user, long-lived API key)

## Secrets (stored outside repo)
- Anthropic API key: `/Users/jasonholt/Claude Projects/secrets/claude.api.s` (Mac path)
- AWS API key: `/Users/jasonholt/Claude Projects/secrets/aws.cli.api.s` (Mac path)
- On Windows: reconfigure from the key values, don't store in repo
