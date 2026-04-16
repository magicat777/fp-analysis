#!/usr/bin/env python3
"""
Fishing Planet Loadout Analyzer
Scrapes fp-collective.com API for location data, analyzes loadout screenshots
via Claude Vision, and generates an interactive React single-page HTML report.
"""

import os
import re
import sys
import json
import time
import glob
import base64
import shutil
import argparse
import subprocess
from pathlib import Path
from html.parser import HTMLParser

import requests
from anthropic import Anthropic

# ── Configuration ──────────────────────────────────────────────────────────────
API_BASE = "https://api.fp-collective.com/wp-json/fp-collective/v2"
WIKI_API = "https://wiki.fishingplanet.com/api.php"
PROJECT_DIR = Path(__file__).parent.resolve()
CURRENT_LOADOUT_DIR = PROJECT_DIR / "current_loadout"
PAST_LOADOUTS_DIR = PROJECT_DIR / "past_loadouts"
OUTPUT_DIR = PROJECT_DIR / "reports"

ANTHROPIC_MODEL = "claude-sonnet-4-6"
JOURNAL_DIR = PROJECT_DIR / "fishing-journal"


# ── API Fetching ───────────────────────────────────────────────────────────────
class FPCollectiveAPI:
    """Client for the fp-collective.com REST API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "FP-Analyzer/1.0"})

    def _get(self, endpoint, params=None):
        url = f"{API_BASE}/{endpoint}"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get_all_pages(self, endpoint):
        """Fetch all pages of a paginated endpoint."""
        first = self._get(endpoint, {"page": 1})
        all_data = first.get("data", [])
        total_pages = first.get("pages", 1)
        for page in range(2, total_pages + 1):
            time.sleep(0.3)
            page_data = self._get(endpoint, {"page": page})
            all_data.extend(page_data.get("data", []))
        return all_data

    def get_locations(self):
        return self._get_all_pages("places")

    def get_location(self, slug):
        return self._get(f"places/{slug}")

    def get_all_baits(self):
        return self._get_all_pages("baits")

    def get_all_lures(self):
        return self._get_all_pages("lures")

    def get_all_hooks(self):
        return self._get_all_pages("hooks")

    def get_all_jigheads(self):
        return self._get_all_pages("jigheads")

    def get_fish(self, slug):
        return self._get(f"fish/{slug}")

    def get_fish_markers(self, place_id):
        """Fetch catch-location markers for a place. Returns raw list of marker dicts."""
        try:
            res = self._get("fish-markers", {"placeId": place_id})
            return res.get("data", []) if isinstance(res, dict) else []
        except Exception as e:
            print(f"  WARN: fish-markers fetch failed for placeId {place_id}: {e}")
            return []


def fetch_location_data(api, slug):
    """Fetch complete location data with resolved bait/lure names."""
    print(f"  Fetching location: {slug}...")
    location = api.get_location(slug)

    print("  Fetching bait database...")
    all_baits = api.get_all_baits()
    bait_map = {b["id"]: b for b in all_baits}

    print("  Fetching lure database...")
    all_lures = api.get_all_lures()
    lure_map = {l["id"]: l for l in all_lures}

    print("  Fetching hook database...")
    all_hooks = api.get_all_hooks()
    hook_map = {h["id"]: h for h in all_hooks}

    print("  Fetching jighead database...")
    all_jigheads = api.get_all_jigheads()
    jighead_map = {j["id"]: j for j in all_jigheads}

    # Resolve fish bait/lure references and fetch ubersheet data
    print("  Fetching ubersheet data per fish...")
    for fish in location.get("fish", []):
        fish["baits"] = [bait_map[bid] for bid in fish.get("baitIds", []) if bid in bait_map]
        fish["lures"] = [lure_map[lid] for lid in fish.get("lureIds", []) if lid in lure_map]

        # Fetch individual fish for ubersheet fields
        try:
            fish_detail = api.get_fish(fish["slug"])
            fish["ubersheetBaits"] = [bait_map[bid] for bid in fish_detail.get("ubersheetBaitIds", []) if bid in bait_map]
            fish["ubersheetLures"] = [lure_map[lid] for lid in fish_detail.get("ubersheetLureIds", []) if lid in lure_map]
            fish["ubersheetHooks"] = [hook_map[hid] for hid in fish_detail.get("ubersheetHookIds", []) if hid in hook_map]
            fish["ubersheetJigheads"] = [jighead_map[jid] for jid in fish_detail.get("ubersheetJigheadIds", []) if jid in jighead_map]
            time.sleep(0.2)
        except Exception:
            fish["ubersheetBaits"] = []
            fish["ubersheetLures"] = []
            fish["ubersheetHooks"] = []
            fish["ubersheetJigheads"] = []

    # Parse fishDetails JSON string if present
    if isinstance(location.get("fishDetails"), str):
        try:
            location["fishDetails"] = json.loads(location["fishDetails"])
        except json.JSONDecodeError:
            pass

    # Fetch fish-map markers (crowdsourced catch locations)
    # Use top-level location id (WP post id is the correct placeId for fish-markers endpoint)
    place_id = location.get("id")
    if place_id:
        print(f"  Fetching fish map markers (placeId={place_id})...")
        location["fishMarkersRaw"] = api.get_fish_markers(place_id)
        print(f"    Found {len(location['fishMarkersRaw'])} fish markers.")
    else:
        location["fishMarkersRaw"] = []

    return {
        "location": location,
        "bait_map": bait_map,
        "lure_map": lure_map,
        "hook_map": hook_map,
        "jighead_map": jighead_map,
    }


# ── Wiki Image Scraper ────────────────────────────────────────────────────────
class WikiScraper:
    """Scrapes equipment images from wiki.fishingplanet.com."""

    # Map of wiki page names for each equipment category
    CATEGORY_PAGES = {
        "rods": ["Spinning rods", "Match rods", "Casting rods", "Bottom rods",
                 "Carp rods", "Feeder rods", "Saltwater rods", "Telescopic rods", "Spod rods"],
        "reels": ["Spinning reels", "Casting reels", "Saltwater reels"],
        "lines": ["Monofilament fishing lines", "Fluorocarbon fishing lines", "Braided fishing lines", "Saltwater lines"],
        "lures": ["Spoons", "Spinners", "Soft plastic baits", "Plugs", "Crankbaits", "Bass Jigs", "Saltwater lures"],
        "baits": ["Common Baits", "Worms & Insects Baits", "Fresh Baits", "Saltwater Baits", "Boilies & Pellets Baits"],
        "hooks": ["Simple Hooks", "Carp Hooks", "Offset Hooks", "Saltwater Hooks"],
        "jigheads": ["Common Jig Heads"],
        "floats": ["Classic Bobbers"],
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "FP-Analyzer/1.0"})
        self.session.verify = False  # Wiki has SSL cert issues
        self._image_cache = {}  # filename -> url
        self._item_image_cache = {}  # item_name_lower -> image_url

    def _api(self, **params):
        params["format"] = "json"
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = self.session.get(WIKI_API, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _normalize_fn(self, fn):
        """Normalize filename for cache lookups (wiki uses spaces, we use underscores)."""
        return fn.replace(" ", "_")

    def resolve_image_urls(self, filenames):
        """Resolve wiki filenames to full URLs, batching up to 50 at a time."""
        results = {}
        norm_map = {self._normalize_fn(fn): fn for fn in filenames}
        uncached = [fn for fn in filenames if self._normalize_fn(fn) not in self._image_cache]

        for i in range(0, len(uncached), 50):
            batch = uncached[i:i + 50]
            titles = "|".join(f"File:{fn}" for fn in batch)
            data = self._api(action="query", titles=titles, prop="imageinfo", iiprop="url")
            for pid, page in data.get("query", {}).get("pages", {}).items():
                if "imageinfo" in page:
                    fn = page["title"].replace("File:", "")
                    url = page["imageinfo"][0]["url"]
                    # Store under both space and underscore variants
                    self._image_cache[fn] = url
                    self._image_cache[fn.replace(" ", "_")] = url

        for fn in filenames:
            norm = self._normalize_fn(fn)
            results[fn] = self._image_cache.get(norm) or self._image_cache.get(fn)
        return results

    def scrape_equipment_page(self, page_name):
        """Parse a wiki equipment page and extract item name -> image filename mappings."""
        try:
            data = self._api(action="parse", page=page_name, prop="text|images")
        except requests.HTTPError:
            return {}

        html = data.get("parse", {}).get("text", {}).get("*", "")
        all_images = data.get("parse", {}).get("images", [])

        items = {}

        # Strategy 1: Extract image filenames from <a href="/File:XXX.png"> links
        # then find nearby bold text as the item name
        # Pattern: image link in one cell, bold name in next cell
        file_pattern = re.compile(
            r'<a\s+href="/File:([^"]+\.png)"[^>]*>.*?</a>'
            r'.*?</td>\s*<td[^>]*>.*?<b>([^<]+)</b>',
            re.DOTALL
        )
        for match in file_pattern.finditer(html):
            img = match.group(1)
            name = match.group(2).strip()
            name = re.sub(r'<!--.*?-->', '', name).strip()
            if img.lower() not in ("credits.png", "baitcoins.png") and len(name) > 1:
                items[name.lower()] = img

        # Strategy 2: For rods/lures — name in a header-style cell, image link below
        # Pattern: <td ...>BrandName <b>ModelName</b></td> ... <a href="/File:XXX.png">
        header_pattern = re.compile(
            r'<td[^>]*style="[^"]*font-weight:\s*bold[^"]*"[^>]*>'
            r'(?:<a[^>]*>)?([^<]+)(?:</a>)?\s*<b>([^<]+)</b>'
            r'.*?<a\s+href="/File:([^"]+\.(?:png|jpg))"',
            re.DOTALL
        )
        for match in header_pattern.finditer(html):
            brand = match.group(1).strip()
            model = match.group(2).strip()
            img = match.group(3)
            name = f"{brand} {model}".strip()
            name = re.sub(r'<!--.*?-->', '', name).strip()
            if len(name) > 2:
                items[name.lower()] = img
                items[model.lower()] = img  # Also index by model name alone

        # Strategy 3: Direct file references from page's image list
        # Map common naming patterns: Bloodworms.png -> bloodworms
        for img_fn in all_images:
            if img_fn.lower() in ("credits.png", "baitcoins.png"):
                continue
            # Strip extension and convert underscores to spaces
            base = img_fn.rsplit(".", 1)[0].replace("_", " ")
            # Skip numeric-only filenames (lure IDs)
            if not base.isdigit() and len(base) > 2:
                items[base.lower()] = img_fn

        return items

    def build_equipment_index(self, categories=None):
        """Build a name->image index for specified equipment categories."""
        if categories is None:
            categories = list(self.CATEGORY_PAGES.keys())

        for cat in categories:
            pages = self.CATEGORY_PAGES.get(cat, [])
            for page in pages:
                print(f"    Indexing wiki page: {page}...")
                items = self.scrape_equipment_page(page)
                self._item_image_cache.update(items)
                time.sleep(0.3)

        # Also add common direct-name mappings for baits (these have predictable filenames)
        common_baits = [
            "Bloodworms", "Maggots", "Crickets", "Grasshoppers", "Flies", "Mayflies",
            "Red Worms", "Wax Worms", "Night Crawlers", "Marshmallows", "Semolina Balls",
            "Dragonflies", "Leeches", "Dough balls", "Bread",
            "Small Minnows", "Natural Eggs", "Artificial Salmon Eggs", "Spawn Sack",
            "Dried Locusts", "Pinkies",
        ]
        for bait in common_baits:
            key = bait.lower()
            if key not in self._item_image_cache:
                # Try the wiki filename convention: spaces -> underscores
                self._item_image_cache[key] = bait.replace(" ", "_") + ".png"

        print(f"    Indexed {len(self._item_image_cache)} equipment items.")

    def get_item_image_url(self, item_name):
        """Look up an item by name and return its wiki image URL."""
        key = item_name.lower().strip()

        # Direct match
        filename = self._item_image_cache.get(key)

        # Try partial match if no direct hit
        if not filename:
            for cached_key, cached_fn in self._item_image_cache.items():
                if key in cached_key or cached_key in key:
                    filename = cached_fn
                    break

        if not filename:
            return None

        # Resolve to full URL
        if filename in self._image_cache:
            return self._image_cache[filename]

        urls = self.resolve_image_urls([filename])
        return urls.get(filename)

    def get_recommended_loadout_images(self, analysis):
        """Extract all equipment names from analysis and resolve wiki images."""
        equipment_names = set()

        # Collect bait/lure names from slots
        for slot in analysis.get("slots", []):
            if slot.get("bait"):
                equipment_names.add(slot["bait"])

        # Scan full analysis text for known bait/equipment names
        all_text = json.dumps(analysis).lower()
        known_items = [
            "Bloodworms", "Maggots", "Crickets", "Grasshoppers", "Flies", "Mayflies",
            "Red Worms", "Wax Worms", "Night Crawlers", "Marshmallows", "Semolina Balls",
            "Dragonflies", "Dried Locusts", "Small Minnows", "Natural Eggs",
            "Artificial Salmon Eggs", "Spawn Sack", "Dough Balls", "Leeches",
            "Bread", "Corn", "Cheese", "Peas", "Pet Food", "Pinkies",
        ]
        for name in known_items:
            if name.lower() in all_text:
                equipment_names.add(name)

        # Build candidate filenames for each name (try multiple)
        name_to_fns = {}
        for name in equipment_names:
            candidates = set()
            # Direct name -> filename
            candidates.add(name.replace(" ", "_") + ".png")
            # Indexed cache entry
            key = name.lower()
            if key in self._item_image_cache:
                candidates.add(self._item_image_cache[key])
            # Plural/singular variants
            if name.endswith("s"):
                candidates.add(name[:-1].replace(" ", "_") + ".png")
            else:
                candidates.add((name + "s").replace(" ", "_") + ".png")
            name_to_fns[name] = candidates

        # Batch resolve ALL candidate filenames
        all_fns = set()
        for fns in name_to_fns.values():
            all_fns.update(fns)
        url_map = self.resolve_image_urls(list(all_fns))

        result = {}
        for name, fns in name_to_fns.items():
            for fn in fns:
                url = url_map.get(fn)
                if url:
                    result[name] = url
                    break

        return result


# ── HEIC Conversion ───────────────────────────────────────────────────────────
def convert_heic_to_jpg(source_dir, dest_dir):
    """Convert all HEIC files in source_dir to JPG in dest_dir. Cross-platform."""
    import platform
    dest_dir.mkdir(parents=True, exist_ok=True)
    heic_files = list(source_dir.glob("*.heic")) + list(source_dir.glob("*.HEIC"))

    if not heic_files:
        print("  No HEIC files found to convert.")
        return []

    is_mac = platform.system() == "Darwin"

    # On Windows/Linux, try pillow-heif for HEIC support
    if not is_mac:
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
            print("  Using pillow-heif for HEIC conversion.")
        except ImportError:
            print("  WARNING: pillow-heif not installed. Install with: pip install pillow-heif")
            print("  HEIC files will be skipped. Convert manually or install pillow-heif.")
            return []

    converted = []
    for heic in heic_files:
        jpg_name = heic.stem + ".jpg"
        jpg_path = dest_dir / jpg_name
        if jpg_path.exists():
            print(f"  Already converted: {jpg_name}")
            converted.append(jpg_path)
            continue
        print(f"  Converting {heic.name} -> {jpg_name}...")

        if is_mac:
            # macOS: use native sips command
            result = subprocess.run(
                ["sips", "-s", "format", "jpeg", str(heic), "--out", str(jpg_path)],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                converted.append(jpg_path)
            else:
                print(f"  ERROR converting {heic.name}: {result.stderr}")
        else:
            # Windows/Linux: use Pillow with pillow-heif
            try:
                from PIL import Image
                img = Image.open(str(heic))
                img.save(str(jpg_path), "JPEG", quality=95)
                converted.append(jpg_path)
            except Exception as e:
                print(f"  ERROR converting {heic.name}: {e}")

    return converted


# ── Screenshot Analysis via Claude Vision ──────────────────────────────────────
def analyze_loadout_screenshots(jpg_files, location_data):
    """Use Claude Vision to analyze loadout screenshots and compare with location data."""
    if not jpg_files:
        return {"error": "No loadout screenshots found to analyze."}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  WARNING: ANTHROPIC_API_KEY not set. Skipping vision analysis.")
        return {"error": "ANTHROPIC_API_KEY not set. Set it to enable loadout analysis."}

    client = Anthropic(api_key=api_key)

    # Build image content blocks
    image_blocks = []
    for jpg in sorted(jpg_files):
        with open(jpg, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
        image_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img_data,
            },
        })

    # Build location context for the prompt
    loc = location_data["location"]
    fish_summary = []
    for fd in loc.get("fishDetails", []):
        if isinstance(fd, dict):
            fish_summary.append(
                f"- {fd['name']}: max {round(fd.get('max_weight', 0) * 2.205, 1)} lb, "
                f"${round(fd.get('price', 0) / 2.205)}/lb, types: {', '.join(fd.get('types', []))}"
            )

    fish_tackle = []
    for fish in loc.get("fish", []):
        baits = [b["title"] for b in fish.get("baits", [])]
        lures = [l["title"] for l in fish.get("lures", [])]
        fish_tackle.append(
            f"- {fish['title']}: Baits=[{', '.join(baits[:8])}] Lures=[{', '.join(lures[:8])}]"
        )

    location_context = f"""
Location: {loc['title']} ({loc['locationName']})
Type: {loc['type']} | Base Level: {loc['baseLevel']} | Continent: {loc['continent']}
Travel Cost: ${loc['travelCost']} | Extend Cost: ${loc['extendCost']}

Fish at this location (with $/lb price):
{chr(10).join(fish_summary)}

Recommended tackle per fish:
{chr(10).join(fish_tackle)}

Spots: {', '.join(s['name'] for s in loc.get('spots', []))}
"""

    prompt = f"""You are an expert Fishing Planet (PC game) analyst. Analyze these screenshots of the player's current fishing loadout slots.

LOCATION DATA (from fp-collective.com):
{location_context}

For each screenshot:
1. Identify every item visible in each loadout slot (rod, reel, line, leader, hook/lure/rig, bait if applicable)
2. Note the setup type (float, spinning, bottom, casting, feeder, etc.)

Then provide a comprehensive analysis as a JSON object with these keys:
- "slots": array of objects, each with:
  - "slot_number": int
  - "screenshot": filename
  - "rod": string or null
  - "reel": string or null
  - "line": string or null
  - "leader": string or null
  - "terminal_tackle": string (hook, lure, rig description)
  - "bait": string or null
  - "setup_type": string (float/spinning/bottom/casting/feeder/etc)
  - "target_fish": array of strings (which fish at this location this setup can catch)
  - "effectiveness_rating": 1-10
  - "issues": array of strings (any problems with this setup)
  - "improvements": array of strings (specific upgrades recommended)

- "overall_analysis": object with:
  - "fish_coverage": object mapping each fish name at this location to whether the current loadout can target it (true/false)
  - "missing_setups": array of strings (setup types needed but not present)
  - "xp_optimization": array of strings (tips to maximize XP gain)
  - "income_optimization": array of strings (tips to maximize money/income)
  - "priority_changes": array of strings (most impactful changes, ordered by importance)
  - "spot_recommendations": object mapping spot names to recommended slot numbers

Return ONLY valid JSON, no markdown fencing or extra text."""

    content = image_blocks + [{"type": "text", "text": prompt}]

    print("  Sending screenshots to Claude Vision for analysis...")
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": content}],
    )

    response_text = response.content[0].text.strip()

    # Try to parse JSON from response
    try:
        # Handle potential markdown fencing
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0]
        analysis = json.loads(response_text)
    except json.JSONDecodeError:
        analysis = {"raw_response": response_text, "parse_error": True}

    return analysis


# ── Journal Loading ───────────────────────────────────────────────────────────
def load_journal_entries(location_slug):
    """Load all journal markdown files matching a location slug."""
    entries = []
    if not JOURNAL_DIR.exists():
        return entries
    # Match files like 2026-04-07_saint-croix-lake.md
    for md_file in sorted(JOURNAL_DIR.glob(f"*_{location_slug}.md")):
        text = md_file.read_text(encoding="utf-8")
        # Extract date from filename
        date_str = md_file.stem.split("_")[0]  # e.g. "2026-04-07"
        entries.append({"date": date_str, "filename": md_file.name, "content": text})
    return entries


def parse_journal_markdown(content):
    """Parse a journal markdown entry into structured sections."""
    sections = {}
    current_section = None
    current_lines = []

    for line in content.split("\n"):
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line[3:].strip()
            current_lines = []
        elif current_section:
            current_lines.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    # Extract header metadata
    meta = {}
    for line in content.split("\n"):
        if line.startswith("**Date:**"):
            meta["date"] = line.split("**Date:**")[1].strip()
        elif line.startswith("**Level:**"):
            meta["level"] = line.split("**Level:**")[1].strip()
        elif line.startswith("**Location Level:**"):
            meta["location_level"] = line.split("**Location Level:**")[1].strip()
        elif line.startswith("# Session:"):
            meta["title"] = line.split("# Session:")[1].strip()

    return {"meta": meta, "sections": sections}


def build_journal_data(location_slug):
    """Build journal data structure for embedding in reports."""
    import datetime
    entries = load_journal_entries(location_slug)
    generated_at = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
    parsed = []
    for entry in entries:
        p = parse_journal_markdown(entry["content"])
        p["date"] = entry["date"]
        p["filename"] = entry["filename"]
        p["generated_at"] = generated_at
        parsed.append(p)
    return parsed


# ── HTML Report Generation ─────────────────────────────────────────────────────
def generate_react_html(location_data, analysis, jpg_files, output_path, wiki_images=None):
    """Generate a self-contained interactive React SPA as a single HTML file."""

    loc = location_data["location"]

    # Encode loadout images as base64 for embedding
    embedded_images = {}
    for jpg in sorted(jpg_files):
        with open(jpg, "rb") as f:
            embedded_images[jpg.name] = base64.b64encode(f.read()).decode("utf-8")

    # Encode weather chart images as URLs (external)
    weather_charts = []
    for wp in loc.get("dayWeatherPatterns", []):
        weather_charts.append({
            "name": wp["name"],
            "type": "day",
            "icon": wp.get("icon", ""),
            "chart": wp.get("chart", ""),
        })
    for wp in loc.get("nightWeatherPatterns", []):
        weather_charts.append({
            "name": wp["name"],
            "type": "night",
            "icon": wp.get("icon", ""),
            "chart": wp.get("chart", ""),
        })

    # Build fish data for frontend
    # Fish activity/depth data — sourced from wiki.fishingplanet.com and in-game behavior
    fish_activity_db = {
        "Black Crappie": {
            "preferred_depth": "Mid-water to deep (6-13 ft)",
            "active_times": "Dawn, dusk, and late evening — most active during twilight",
            "habitat": "Clear, deeper water near structure and drop-offs. Prefers cooler, calmer areas.",
            "technique_tip": "Float fish at 6-10 ft depth near structure. Slow presentation works best.",
            "recommended_hook": "#1",
        },
        "Bluegill": {
            "preferred_depth": "Shallow to mid-water (2-7 ft)",
            "active_times": "Morning through midday — active throughout daylight hours",
            "habitat": "Among water plants and around underwater structures near shore.",
            "technique_tip": "Float fish near weed edges at 3-5 ft. Very aggressive biters — quick hook set needed.",
            "recommended_hook": "#1",
        },
        "Colorado Golden Trout": {
            "preferred_depth": "Mid-water to deep (7-13 ft)",
            "active_times": "Early morning and late evening — peak at dawn and dusk",
            "habitat": "Cold, clear mountain lake water. Holds near rocky bottom structure.",
            "technique_tip": "Float with Flies at 8-11 ft or slow-retrieve small spoons. Most valuable fish at $91/lb.",
            "recommended_hook": "#1/0",
        },
        "Cutthroat Trout": {
            "preferred_depth": "Mid-water (5-10 ft)",
            "active_times": "Morning and evening — most active during cooler periods",
            "habitat": "Clear water with gravel bottoms. Frequents shallow-to-moderate depth transitions.",
            "technique_tip": "Versatile — takes float rigs and lures equally well. Try near gravel/rock transitions.",
            "recommended_hook": "#3/0",
        },
        "Rainbow Trout": {
            "preferred_depth": "Mid-water to deep (7-13 ft), near bottom",
            "active_times": "Morning and evening — feeds near bottom in deeper water during midday",
            "habitat": "Oxygenated depths near rocky structure. Often found near the bottom in deeper holes.",
            "technique_tip": "Cast to deep holes and let lure sink near bottom. Ultra-light tackle recommended.",
            "recommended_hook": "#1/0",
        },
        "Golden Shiner": {
            "preferred_depth": "Shallow (2-5 ft)",
            "active_times": "Midday — active during warmer water periods",
            "habitat": "Shallow vegetated areas near shore. Schools near surface.",
            "technique_tip": "Float fish at 2-3 ft in weedy shallows. Small hook (#6-#10) essential.",
            "recommended_hook": "#4",
        },
        "White Bass": {
            "preferred_depth": "Mid-water (5-10 ft)",
            "active_times": "Dawn and dusk — aggressive feeders during twilight",
            "habitat": "Open water, often schooling. Chases baitfish actively.",
            "technique_tip": "Spinning with small spoons or spinners. Steady retrieve triggers strikes.",
            "recommended_hook": "#4/0",
        },
        "White Sucker": {
            "preferred_depth": "Bottom (7-13 ft)",
            "active_times": "Late evening and night — bottom feeder most active in low light",
            "habitat": "Sandy/muddy bottoms in deeper areas. Feeds by suction along the substrate.",
            "technique_tip": "Bottom/ledger rig with Marshmallows or Crickets. Let bait sit on bottom at 10-13 ft.",
            "recommended_hook": "#2",
        },
        "Smallmouth Buffalo": {
            "preferred_depth": "Bottom (7-16 ft)",
            "active_times": "Evening and night — most active in low light conditions",
            "habitat": "Deep water near muddy bottoms and vegetation.",
            "technique_tip": "Bottom rig with heavy bait. Patience required — slow biter.",
            "recommended_hook": "#1/0",
        },
        "Spotted Bass": {
            "preferred_depth": "Mid-water to deep (5-13 ft)",
            "active_times": "Morning and evening — ambush feeder near structure",
            "habitat": "Rocky structure, drop-offs, and submerged cover.",
            "technique_tip": "Jig or small spoon near rocky structure. Moderate retrieve with pauses.",
            "recommended_hook": "#4/0",
        },
        "Redear Sunfish": {
            "preferred_depth": "Shallow to mid-water (2-7 ft)",
            "active_times": "Morning through afternoon — active in warm water",
            "habitat": "Near vegetation and structure in shallow areas. Bottom feeder.",
            "technique_tip": "Float fish near weed beds at 3-7 ft. Prefers insect baits.",
            "recommended_hook": "#1",
        },
        "Channel Catfish": {
            "preferred_depth": "Bottom (7-20 ft)",
            "active_times": "Night and twilight — nocturnal feeder",
            "habitat": "Deep holes, channels, and areas with slow current near bottom.",
            "technique_tip": "Bottom rig at deepest available spots. Strong-smelling baits work best.",
            "recommended_hook": "#4/0",
        },
        "Grass Pickerel": {
            "preferred_depth": "Shallow to mid-water (2-7 ft)",
            "active_times": "Morning and late afternoon — ambush predator",
            "habitat": "Dense vegetation and weedy shallows.",
            "technique_tip": "Small lures or live bait near weed edges. Quick, darting retrieves.",
            "recommended_hook": "#1/0",
        },
        "Blacktail Shiner": {
            "preferred_depth": "Shallow (2-3 ft)",
            "active_times": "Midday — prefers flowing water and fast current areas",
            "habitat": "Areas with little vegetation and fast current.",
            "technique_tip": "Tiny hooks (#8-#12) with Dough Balls or Semolina Balls near current.",
            "recommended_hook": "#6",
        },
        "Green Sunfish": {
            "preferred_depth": "Shallow (2-5 ft)",
            "active_times": "Morning through afternoon — aggressive during warm periods",
            "habitat": "Near rocks, logs, and structure in shallow water.",
            "technique_tip": "Float fish near cover at 2-3 ft. Small hooks essential.",
            "recommended_hook": "#6",
        },
        "White Crappie": {
            "preferred_depth": "Mid-water (5-10 ft)",
            "active_times": "Dawn and dusk — schooling fish, most active at twilight",
            "habitat": "Brush piles, standing timber, and submerged structure.",
            "technique_tip": "Float or small jig near structure at 7 ft. Often found in schools.",
            "recommended_hook": "#1/0",
        },
        "Largemouth Bass": {
            "preferred_depth": "Shallow to mid-water (3-10 ft)",
            "active_times": "Early morning and late evening — ambush feeder",
            "habitat": "Near lily pads, fallen trees, docks, and weed lines.",
            "technique_tip": "Spinnerbaits, crankbaits, or soft plastics near cover. Vary retrieve speed.",
            "recommended_hook": "#4/0",
        },
        "Smallmouth Bass": {
            "preferred_depth": "Mid-water to deep (7-16 ft)",
            "active_times": "Morning and evening — more active in cooler water",
            "habitat": "Rocky points, gravel bars, and clear water structure.",
            "technique_tip": "Jigs, tubes, or small crankbaits near rocky structure.",
            "recommended_hook": "#1/0",
        },
        "Chain Pickerel": {
            "preferred_depth": "Shallow to mid-water (3-8 ft)",
            "active_times": "Morning and late afternoon — ambush predator",
            "habitat": "Weedy shallows and vegetated areas.",
            "technique_tip": "Spoons or spinners near weed edges. Wire leader recommended.",
            "recommended_hook": "#4/0",
        },
        "Walleye": {
            "preferred_depth": "Mid-water to deep (10-20 ft)",
            "active_times": "Dawn, dusk, and night — light-sensitive, most active in low light",
            "habitat": "Rocky reefs, sand bars, and deep structure.",
            "technique_tip": "Jig tipped with minnow near bottom. Slow, dragging retrieve.",
            "recommended_hook": "#4/0",
        },
        "Yellow Perch": {
            "preferred_depth": "Mid-water (5-10 ft)",
            "active_times": "Morning and late afternoon — schools actively during daylight",
            "habitat": "Near weed beds and structure. Schools in open water.",
            "technique_tip": "Small jigs or float with worms/minnows at 7 ft.",
            "recommended_hook": "#2/0",
        },
        "Rock Bass": {
            "preferred_depth": "Shallow to mid-water (3-10 ft)",
            "active_times": "Morning through evening — aggressive and easy to catch",
            "habitat": "Rocky areas, around boulders and fallen timber.",
            "technique_tip": "Small lures or bait near rocky structure. Not picky — will hit most offerings.",
            "recommended_hook": "#8",
        },
        "Brook Trout": {
            "preferred_depth": "Mid-water (5-10 ft)",
            "active_times": "Early morning and evening — prefers cold water",
            "habitat": "Cold, clear streams and spring-fed pools.",
            "technique_tip": "Small flies or spinners. Delicate presentation required.",
            "recommended_hook": "#4/0",
        },
        "Lake Trout": {
            "preferred_depth": "Deep (4-10m+)",
            "active_times": "Midday in cold weather, morning/evening in warm weather",
            "habitat": "Deep, cold lake water near bottom structure.",
            "technique_tip": "Deep trolling or heavy jigs. Target the deepest areas available.",
            "recommended_hook": "#4/0",
        },
        "Brown Trout": {
            "preferred_depth": "Mid-water to deep (7-16 ft)",
            "active_times": "Evening and night — more nocturnal than other trout",
            "habitat": "Undercut banks, deep pools, and shaded areas.",
            "technique_tip": "Larger lures than for other trout. Night fishing can be very productive.",
            "recommended_hook": "#4/0",
        },
        "Northern Pike": {
            "preferred_depth": "Shallow to mid-water (3-10 ft)",
            "active_times": "Morning and late afternoon — ambush predator",
            "habitat": "Weed edges, lily pad beds, and shallow bays.",
            "technique_tip": "Large spoons, spinnerbaits, or live bait. Wire leader essential.",
            "recommended_hook": "#6/0",
        },
        "Muskie": {
            "preferred_depth": "Mid-water to deep (7-20 ft)",
            "active_times": "Midday to afternoon — follows large prey fish",
            "habitat": "Deep weed edges, rock bars, and open water structure.",
            "technique_tip": "Large lures with erratic action. Requires patience — the 'fish of 10,000 casts'.",
            "recommended_hook": "#7/0",
        },
        "Common Carp": {
            "preferred_depth": "Bottom (3-13 ft)",
            "active_times": "Morning and evening — bottom feeder active in warm water",
            "habitat": "Muddy bottoms near vegetation. Often found in shallows during warm periods.",
            "technique_tip": "Bottom rig with boilies, corn, or bread. Groundbait helps concentrate fish.",
            "recommended_hook": "#6/0",
        },
        "Grass Carp": {
            "preferred_depth": "Mid-water to bottom (3-10 ft)",
            "active_times": "Morning through afternoon — herbivorous feeder",
            "habitat": "Vegetated areas with abundant plant growth.",
            "technique_tip": "Float or bottom rig with corn, peas, or bread near vegetation.",
            "recommended_hook": "#6/0",
        },
        "Mirror Carp": {
            "preferred_depth": "Bottom (7-16 ft)",
            "active_times": "Morning and evening — bottom feeder",
            "habitat": "Deep margins, silt bottoms, and near structure.",
            "technique_tip": "Hair rig with boilies. Pre-bait area with groundbait for best results.",
            "recommended_hook": "#6/0",
        },
    }

    fish_data = []
    for fish in loc.get("fish", []):
        detail = next(
            (fd for fd in loc.get("fishDetails", [])
             if isinstance(fd, dict) and fd.get("id") == fish["id"]),
            {}
        )
        activity = fish_activity_db.get(fish["title"], {})
        fish_data.append({
            "name": fish["title"],
            "image": fish.get("image", ""),
            "maxWeight": detail.get("max_weight", "?"),
            "price": detail.get("price", "?"),
            "types": detail.get("types", []),
            "baits": [b["title"] for b in fish.get("baits", [])],
            "lures": [{"title": l["title"], "color": l.get("color", ""), "type": l.get("lureType", "")} for l in fish.get("lures", [])[:20]],
            "preferredDepth": activity.get("preferred_depth", ""),
            "activeTimes": activity.get("active_times", ""),
            "habitat": activity.get("habitat", ""),
            "techniqueTip": activity.get("technique_tip", ""),
            "recommendedHook": activity.get("recommended_hook", ""),
            "ubersheetBaits": [b["title"] for b in fish.get("ubersheetBaits", [])],
            "ubersheetLures": [{"title": l["title"], "color": l.get("color", ""), "type": l.get("lureType", ""), "hookSize": l.get("hookSize", ""), "weight": l.get("weight", ""), "baseLevel": l.get("baseLevel", "")} for l in fish.get("ubersheetLures", [])[:15]],
            "ubersheetHooks": [{"title": h["title"], "size": h.get("size", ""), "type": h.get("type", "")} for h in fish.get("ubersheetHooks", [])],
            "ubersheetJigheads": [{"title": j["title"], "size": j.get("size", ""), "weight": j.get("weight", "")} for j in fish.get("ubersheetJigheads", [])],
        })

    spots_data = [
        {"name": s["name"], "image": s.get("image", ""), "lat": s.get("lat"), "lng": s.get("lng")}
        for s in loc.get("spots", [])
    ]

    # Transform fish-map markers already fetched upstream
    raw_markers = loc.get("fishMarkersRaw", []) or []
    fish_markers = []
    if raw_markers:
        for m in raw_markers:
            fish_info = m.get("fish") or {}
            lure_info = m.get("lure") or {}
            fish_markers.append({
                "lat": m.get("lat"),
                "lng": m.get("lng"),
                "x": m.get("x"),
                "y": m.get("y"),
                "fish": fish_info.get("title", ""),
                "fishImage": fish_info.get("image", ""),
                "type": m.get("type", ""),
                "weight": m.get("weight"),
                "time": m.get("time", ""),
                "bait": m.get("bait", ""),
                "hook": m.get("hook", ""),
                "lure": lure_info.get("title", ""),
                "lureImage": lure_info.get("image", ""),
                "lureColor": lure_info.get("color", ""),
                "jighead": m.get("jighead", ""),
                "sinker": m.get("sinker", ""),
                "technique": m.get("technique", ""),
                "fishingFrom": m.get("fishingFrom", ""),
                "depth": m.get("depth"),
                "caughtBy": m.get("caughtBy", ""),
                "weatherPattern": (m.get("weatherPattern") or {}).get("title", ""),
            })
        print(f"    Found {len(fish_markers)} fish markers.")

    license_data = {
        "basic": loc.get("basicLicense", {}),
        "advanced": loc.get("advancedLicense", {}),
    }

    # Prepare the data blob
    app_data = {
        "location": {
            "title": loc["title"],
            "locationName": loc.get("locationName", ""),
            "type": loc.get("type", ""),
            "baseLevel": loc.get("baseLevel", ""),
            "continent": loc.get("continent", ""),
            "travelCost": loc.get("travelCost", 0),
            "extendCost": loc.get("extendCost", 0),
            "description": loc.get("content", ""),
            "image": loc.get("image", ""),
            "map": loc.get("map", ""),
            "mapConfig": loc.get("mapConfig") or {},
        },
        "fish": fish_data,
        "spots": spots_data,
        "fishMarkers": fish_markers,
        "weather": weather_charts,
        "license": license_data,
        "analysis": analysis,
        "loadoutImages": embedded_images,
        "wikiImages": wiki_images or {},
        "journal": build_journal_data(loc.get("slug", "")),
    }

    data_json = json.dumps(app_data, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FP Analyzer - {loc['title']} (Level {loc.get('baseLevel', '?')})</title>
<script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {{
    --bg: #0f1923;
    --surface: #1a2634;
    --surface2: #243447;
    --accent: #00bcd4;
    --accent2: #4caf50;
    --gold: #ffc107;
    --text: #e0e0e0;
    --text2: #90a4ae;
    --danger: #f44336;
    --success: #4caf50;
    --warn: #ff9800;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }}
  .app {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
  .header {{
    background: linear-gradient(135deg, var(--surface) 0%, var(--surface2) 100%);
    border-radius: 16px;
    padding: 30px;
    margin-bottom: 24px;
    border: 1px solid rgba(0,188,212,0.2);
    display: flex;
    gap: 24px;
    align-items: center;
  }}
  .header img {{ width: 200px; border-radius: 12px; }}
  .header h1 {{ font-size: 2em; color: var(--accent); margin-bottom: 8px; }}
  .header .meta {{ color: var(--text2); font-size: 0.95em; }}
  .header .meta span {{ margin-right: 16px; }}
  .header .meta .tag {{
    display: inline-block;
    background: var(--surface2);
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.85em;
    border: 1px solid rgba(0,188,212,0.3);
    margin-right: 8px;
  }}

  .tabs {{
    display: flex;
    gap: 4px;
    margin-bottom: 24px;
    background: var(--surface);
    padding: 6px;
    border-radius: 12px;
    flex-wrap: wrap;
  }}
  .tab {{
    padding: 10px 20px;
    border-radius: 8px;
    cursor: pointer;
    border: none;
    background: transparent;
    color: var(--text2);
    font-size: 0.95em;
    font-weight: 500;
    transition: all 0.2s;
  }}
  .tab:hover {{ background: var(--surface2); color: var(--text); }}
  .tab.active {{ background: var(--accent); color: #fff; }}

  .panel {{
    background: var(--surface);
    border-radius: 16px;
    padding: 24px;
    border: 1px solid rgba(255,255,255,0.05);
  }}

  .grid {{ display: grid; gap: 16px; }}
  .grid-2 {{ grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }}
  .grid-3 {{ grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); }}

  .card {{
    background: var(--surface2);
    border-radius: 12px;
    padding: 16px;
    border: 1px solid rgba(255,255,255,0.05);
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  .card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.3); }}
  .card h3 {{ color: var(--accent); margin-bottom: 8px; font-size: 1.05em; }}
  .card .fish-img {{ width: 100%; max-width: 200px; margin: 0 auto 12px; display: block; }}
  .card .detail {{ color: var(--text2); font-size: 0.9em; margin: 4px 0; }}
  .card .detail strong {{ color: var(--text); }}

  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.8em;
    font-weight: 600;
    margin: 2px;
  }}
  .badge.common {{ background: rgba(76,175,80,0.2); color: var(--success); border: 1px solid rgba(76,175,80,0.3); }}
  .badge.trophy {{ background: rgba(255,193,7,0.2); color: var(--gold); border: 1px solid rgba(255,193,7,0.3); }}
  .badge.young {{ background: rgba(144,164,174,0.2); color: var(--text2); border: 1px solid rgba(144,164,174,0.3); }}
  .badge.monster {{ background: rgba(244,67,54,0.2); color: var(--danger); border: 1px solid rgba(244,67,54,0.3); }}
  .badge.bait {{ background: rgba(0,188,212,0.15); color: var(--accent); border: 1px solid rgba(0,188,212,0.2); }}

  .slot-card {{ position: relative; }}
  .slot-card .slot-num {{
    position: absolute;
    top: 12px; left: 12px;
    background: var(--accent);
    color: #fff;
    width: 32px; height: 32px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700;
    font-size: 0.95em;
    z-index: 2;
  }}
  .slot-img {{
    width: 100%;
    border-radius: 8px;
    margin-bottom: 12px;
    cursor: pointer;
    transition: transform 0.2s;
  }}
  .slot-img:hover {{ transform: scale(1.02); }}

  .rating {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 1.1em;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 8px;
    margin: 8px 0;
  }}
  .rating.high {{ background: rgba(76,175,80,0.2); color: var(--success); }}
  .rating.mid {{ background: rgba(255,152,0,0.2); color: var(--warn); }}
  .rating.low {{ background: rgba(244,67,54,0.2); color: var(--danger); }}

  .issue {{ color: var(--danger); font-size: 0.9em; padding: 4px 0; }}
  .improvement {{ color: var(--accent2); font-size: 0.9em; padding: 4px 0; }}
  .tip {{ color: var(--gold); font-size: 0.9em; padding: 4px 0; }}

  .coverage-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }}
  .coverage-item {{
    padding: 10px 14px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.9em;
  }}
  .coverage-item.covered {{ background: rgba(76,175,80,0.15); border: 1px solid rgba(76,175,80,0.3); }}
  .coverage-item.uncovered {{ background: rgba(244,67,54,0.15); border: 1px solid rgba(244,67,54,0.3); }}

  .weather-card img {{ max-width: 100%; border-radius: 8px; }}
  .weather-card .icon {{ width: 48px; height: 48px; vertical-align: middle; margin-right: 8px; }}

  .spot-card img {{ width: 100%; border-radius: 8px; margin-bottom: 8px; }}

  .license-table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
  .license-table th, .license-table td {{
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }}
  .license-table th {{ color: var(--accent); font-weight: 600; }}

  .priority-list {{ list-style: none; counter-reset: priority; }}
  .priority-list li {{
    counter-increment: priority;
    padding: 12px 16px;
    margin: 8px 0;
    background: var(--surface2);
    border-radius: 8px;
    border-left: 3px solid var(--gold);
    font-size: 0.95em;
  }}
  .priority-list li::before {{
    content: counter(priority) ".";
    font-weight: 700;
    color: var(--gold);
    margin-right: 8px;
  }}

  .lightbox {{
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.9);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    cursor: pointer;
  }}
  .lightbox img {{ max-width: 95vw; max-height: 95vh; border-radius: 8px; }}

  .collapsible-header {{
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    user-select: none;
  }}
  .collapsible-header:hover {{ color: var(--accent); }}
  .arrow {{ transition: transform 0.2s; display: inline-block; }}
  .arrow.open {{ transform: rotate(90deg); }}

  .money {{ color: var(--accent2); }}
  .xp {{ color: var(--accent); }}

  .section-title {{
    font-size: 1.3em;
    font-weight: 700;
    margin-bottom: 16px;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  @media (max-width: 768px) {{
    .header {{ flex-direction: column; text-align: center; }}
    .header img {{ width: 100%; max-width: 300px; }}
    .grid-2, .grid-3 {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<div id="root"></div>
<script>
  window.__FP_DATA__ = {data_json};
</script>
<script type="text/babel">
const {{ useState }} = React;
const D = window.__FP_DATA__;

function App() {{
  const [tab, setTab] = useState("loadout");
  const [lightbox, setLightbox] = useState(null);

  const tabs = [
    {{ id: "loadout", label: "Loadout Analysis" }},
    ...(D.analysis.mission ? [{{ id: "mission", label: "Mission Plan" }}] : []),
    {{ id: "recommended", label: "Recommended Loadout" }},
    {{ id: "priority", label: "Priority Actions" }},
    {{ id: "fish", label: "Fish & Tackle" }},
    {{ id: "spots", label: "Fishing Spots" }},
    ...(D.fishMarkers && D.fishMarkers.length > 0 ? [{{ id: "fishmap", label: "Fish Map" }}] : []),
    {{ id: "weather", label: "Bite Charts" }},
    {{ id: "license", label: "Licenses & Costs" }},
    {{ id: "passive", label: "Passive Fishing" }},
    {{ id: "gear", label: "Gear & Equipment" }},
    {{ id: "xp", label: "XP & Income Guide" }},
    ...(D.journal && D.journal.length > 0 ? [{{ id: "journal", label: "Journal" }}] : []),
  ];

  return (
    <div className="app">
      {{lightbox && (
        <div className="lightbox" onClick={{() => setLightbox(null)}}>
          <img src={{lightbox}} alt="Enlarged" />
        </div>
      )}}

      <Header />

      {{/* Progress banner */}}
      {{D.analysis.overall_analysis && D.analysis.overall_analysis.loadout_progress && (
        <div style={{{{background: "linear-gradient(135deg, rgba(76,175,80,0.15), rgba(0,188,212,0.15))",
                      border: "1px solid rgba(76,175,80,0.3)", borderRadius: "12px",
                      padding: "16px 24px", marginBottom: "24px", display: "flex",
                      alignItems: "center", gap: "20px", flexWrap: "wrap"}}}}>
          <div>
            <div style={{{{fontSize: "0.85em", color: "var(--text2)", marginBottom: "4px"}}}}>LOADOUT IMPROVEMENT</div>
            <div style={{{{fontSize: "1.8em", fontWeight: 700}}}}>
              <span style={{{{color: "var(--danger)"}}}}>{{"" + D.analysis.overall_analysis.loadout_progress.previous_average_rating}}</span>
              <span style={{{{color: "var(--text2)", margin: "0 8px"}}}}>→</span>
              <span style={{{{color: "var(--success)"}}}}>{{"" + D.analysis.overall_analysis.loadout_progress.current_average_rating}}</span>
              <span style={{{{fontSize: "0.5em", color: "var(--text2)", marginLeft: "4px"}}}}>/ 10</span>
            </div>
          </div>
          <div style={{{{flex: 1, minWidth: "200px", color: "var(--text2)", fontSize: "0.9em"}}}}>
            {{D.analysis.overall_analysis.loadout_progress.improvement_summary}}
          </div>
        </div>
      )}}

      <div className="tabs">
        {{tabs.map(t => (
          <button key={{t.id}} className={{"tab" + (tab === t.id ? " active" : "")}}
            onClick={{() => setTab(t.id)}}>{{t.label}}</button>
        ))}}
      </div>

      {{tab === "loadout" && <LoadoutTab setLightbox={{setLightbox}} />}}
      {{tab === "mission" && <MissionTab />}}
      {{tab === "recommended" && <RecommendedTab setLightbox={{setLightbox}} />}}
      {{tab === "priority" && <PriorityTab />}}
      {{tab === "passive" && <PassiveFishingTab />}}
      {{tab === "gear" && <GearTab setLightbox={{setLightbox}} />}}
      {{tab === "fish" && <FishTab />}}
      {{tab === "spots" && <SpotsTab />}}
      {{tab === "fishmap" && <FishMapTab />}}
      {{tab === "weather" && <WeatherTab />}}
      {{tab === "license" && <LicenseTab />}}
      {{tab === "xp" && <XPGuideTab />}}
      {{tab === "journal" && <JournalTab />}}
    </div>
  );
}}

function Header() {{
  const loc = D.location;
  return (
    <div className="header">
      {{loc.image && <img src={{loc.image}} alt={{loc.title}} />}}
      <div style={{{{flex: 1}}}}>
        <h1>{{loc.title}}</h1>
        <div className="meta">
          <span className="tag">{{loc.type}}</span>
          <span className="tag">Level {{loc.baseLevel}}+</span>
          <span className="tag">{{loc.continent}}</span>
          <span className="tag">{{loc.locationName}}</span>
        </div>
        <div className="meta" style={{{{marginTop: "8px"}}}}>
          <span>Travel: <strong className="money">${{loc.travelCost}}</strong></span>
          <span>Extend: <strong className="money">${{loc.extendCost}}</strong></span>
        </div>
      </div>
      <a href="/" style={{{{textDecoration: "none", background: "var(--surface2)",
                          border: "1px solid rgba(0,188,212,0.3)", borderRadius: "10px",
                          padding: "10px 20px", color: "var(--accent)", fontWeight: 600,
                          fontSize: "0.9em", whiteSpace: "nowrap", alignSelf: "flex-start",
                          transition: "background 0.2s"}}}}
         onMouseOver={{(e) => e.target.style.background = "rgba(0,188,212,0.15)"}}
         onMouseOut={{(e) => e.target.style.background = "var(--surface2)"}}>
        Reports Menu
      </a>
    </div>
  );
}}

function LoadoutTab({{ setLightbox }}) {{
  const a = D.analysis;
  if (a.error) return <div className="panel"><p style={{{{color:"var(--danger)"}}}}>{{a.error}}</p></div>;
  if (a.parse_error) return <div className="panel"><pre style={{{{whiteSpace:"pre-wrap"}}}}>{{a.raw_response}}</pre></div>;

  const slots = a.slots || [];
  const imageKeys = Object.keys(D.loadoutImages).sort();

  return (
    <div className="panel">
      <div className="section-title">Current Loadout Slots</div>
      <div className="grid grid-2">
        {{slots.map((slot, i) => {{
          const imgKey = slot.screenshot || imageKeys[i];
          const imgSrc = D.loadoutImages[imgKey]
            ? "data:image/jpeg;base64," + D.loadoutImages[imgKey]
            : null;
          const r = slot.effectiveness_rating || 0;
          const rClass = r >= 7 ? "high" : r >= 4 ? "mid" : "low";

          return (
            <div key={{i}} className="card slot-card">
              <div className="slot-num">{{slot.slot_number || i + 1}}</div>
              {{imgSrc && <img className="slot-img" src={{imgSrc}} alt={{"Slot " + (i+1)}}
                onClick={{() => setLightbox(imgSrc)}} />}}
              <div className="detail"><strong>Type:</strong> {{slot.setup_type}}</div>
              {{slot.rod && <div className="detail"><strong>Rod:</strong> {{slot.rod}}</div>}}
              {{slot.reel && <div className="detail"><strong>Reel:</strong> {{slot.reel}}</div>}}
              {{slot.line && <div className="detail"><strong>Line:</strong> {{slot.line}}</div>}}
              {{slot.leader && <div className="detail"><strong>Leader:</strong> {{slot.leader}}</div>}}
              {{slot.terminal_tackle && <div className="detail"><strong>Terminal:</strong> {{slot.terminal_tackle}}</div>}}
              {{slot.bait && <div className="detail"><strong>Bait:</strong> {{slot.bait}}</div>}}

              <div className={{"rating " + rClass}}>
                Effectiveness: {{r}}/10
              </div>

              {{slot.target_fish && slot.target_fish.length > 0 && (
                <div className="detail">
                  <strong>Targets:</strong> {{slot.target_fish.map((f,j) =>
                    <span key={{j}} className="badge common">{{f}}</span>)}}
                </div>
              )}}

              {{slot.leader_recommendation && (
                <div style={{{{background: "rgba(0,188,212,0.08)", border: "1px solid rgba(0,188,212,0.2)",
                              borderRadius: "8px", padding: "12px", margin: "10px 0"}}}}>
                  <div style={{{{fontWeight: 600, color: "var(--accent)", marginBottom: "6px", fontSize: "0.9em"}}}}>LEADER RECOMMENDATION</div>
                  <div className="detail"><strong>Material:</strong> {{slot.leader_recommendation.material}}</div>
                  <div className="detail"><strong>Test Weight:</strong> {{slot.leader_recommendation.test_weight}}</div>
                  <div className="detail"><strong>Length:</strong> {{slot.leader_recommendation.length}}</div>
                  <div className="detail"><strong>Float Depth:</strong> {{slot.leader_recommendation.depth_setting}}</div>
                  <div className="detail" style={{{{marginTop: "6px", color: "var(--text2)", fontSize: "0.85em"}}}}>{{slot.leader_recommendation.why}}</div>
                </div>
              )}}

              {{slot.issues && slot.issues.length > 0 && (
                <div>{{slot.issues.map((iss,j) => <div key={{j}} className="issue">⚠ {{iss}}</div>)}}</div>
              )}}
              {{slot.improvements && slot.improvements.length > 0 && (
                <div>{{slot.improvements.map((imp,j) => <div key={{j}} className="improvement">→ {{imp}}</div>)}}</div>
              )}}
            </div>
          );
        }})}}
      </div>

      {{a.overall_analysis && a.overall_analysis.fish_coverage && (
        <div style={{{{marginTop: "24px"}}}}>
          <div className="section-title">Fish Coverage</div>
          <div className="coverage-grid">
            {{Object.entries(a.overall_analysis.fish_coverage).map(([fish, covered]) => (
              <div key={{fish}} className={{"coverage-item " + (covered ? "covered" : "uncovered")}}>
                {{covered ? "✓" : "✗"}} {{fish}}
              </div>
            ))}}
          </div>
        </div>
      )}}
    </div>
  );
}}

function MissionTab() {{
  const m = D.analysis.mission;
  if (!m) return <div className="panel"><p>No mission data available.</p></div>;

  const strat = m.strategy || {{}};
  const wi = D.wikiImages || {{}};

  return (
    <div className="panel">
      {{/* Mission header */}}
      <div style={{{{background: "linear-gradient(135deg, rgba(255,193,7,0.15), rgba(244,67,54,0.1))",
                    border: "1px solid rgba(255,193,7,0.3)", borderRadius: "12px",
                    padding: "20px", marginBottom: "24px"}}}}>
        <div style={{{{fontSize: "1.4em", fontWeight: 700, color: "var(--gold)", marginBottom: "8px"}}}}>
          {{m.name || "Mission"}}
        </div>
        <div style={{{{display: "flex", gap: "8px", flexWrap: "wrap"}}}}>
          {{m.target_fish && m.target_fish.map((f,i) => (
            <span key={{i}} style={{{{background: "rgba(255,193,7,0.2)", border: "1px solid rgba(255,193,7,0.4)",
                                   borderRadius: "8px", padding: "4px 12px", fontSize: "0.95em",
                                   fontWeight: 600, color: "var(--gold)"}}}}>{{f}}</span>
          ))}}
        </div>
      </div>

      {{/* Required changes */}}
      {{m.required_changes && m.required_changes.length > 0 && (
        <div style={{{{marginBottom: "24px"}}}}>
          <div className="section-title" style={{{{color: "var(--danger)"}}}}>Required Loadout Changes</div>
          {{m.required_changes.map((c,i) => {{
            const isMust = c.startsWith("MUST");
            const isShould = c.startsWith("SHOULD");
            const color = isMust ? "var(--danger)" : isShould ? "var(--warn)" : "var(--text2)";
            return (
              <div key={{i}} style={{{{padding: "10px 14px", margin: "6px 0", borderRadius: "8px",
                                    background: "var(--surface2)",
                                    borderLeft: `3px solid ${{color}}`,
                                    fontSize: "0.95em"}}}}>
                {{c}}
              </div>
            );
          }})}}
        </div>
      )}}

      {{/* Per-fish strategy cards */}}
      <div className="section-title">Target Fish Strategy</div>
      <div className="grid grid-2">
        {{Object.entries(strat).map(([fishName, info], i) => {{
          const fishData = D.fish.find(f => f.name === fishName);
          return (
            <div key={{i}} className="card">
              <div style={{{{display: "flex", gap: "12px", alignItems: "center", marginBottom: "12px"}}}}>
                {{fishData && fishData.image && <img src={{fishData.image}} alt={{fishName}}
                  style={{{{width: "80px", borderRadius: "8px"}}}} />}}
                <div>
                  <h3 style={{{{margin: 0}}}}>{{fishName}}</h3>
                  {{fishData && (
                    <div className="detail">
                      {{fishData.maxWeight && <span>Max: <strong>{{(fishData.maxWeight * 2.205).toFixed(1)}} lb</strong></span>}}
                      {{fishData.price && <span style={{{{marginLeft: "12px"}}}}>Value: <strong className="money">${{(fishData.price / 2.205).toFixed(0)}}/lb</strong></span>}}
                    </div>
                  )}}
                </div>
              </div>

              <div style={{{{background: "rgba(0,188,212,0.08)", borderRadius: "8px", padding: "10px", marginBottom: "8px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--accent)", marginBottom: "4px"}}}}>BEST BAIT</div>
                <div style={{{{fontSize: "0.9em"}}}}>{{info.best_bait}}</div>
              </div>

              {{info.best_lure && (
                <div style={{{{background: "rgba(76,175,80,0.08)", borderRadius: "8px", padding: "10px", marginBottom: "8px"}}}}>
                  <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--accent2)", marginBottom: "4px"}}}}>BEST LURE</div>
                  <div style={{{{fontSize: "0.9em"}}}}>{{info.best_lure}}</div>
                </div>
              )}}

              <div style={{{{background: "rgba(255,193,7,0.08)", borderRadius: "8px", padding: "10px", marginBottom: "8px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--gold)", marginBottom: "4px"}}}}>RECOMMENDED SLOT</div>
                <div style={{{{fontSize: "0.9em"}}}}>{{info.best_slot}}</div>
              </div>

              <div className="detail"><strong>Best Spot:</strong> {{info.best_spot}}</div>
              {{info.notes && <div className="tip" style={{{{marginTop: "6px", fontSize: "0.85em"}}}}>{{info.notes}}</div>}}
            </div>
          );
        }})}}
      </div>

      {{/* Mission plan */}}
      {{m.mission_plan && m.mission_plan.length > 0 && (
        <div style={{{{marginTop: "24px"}}}}>
          <div className="section-title">Step-by-Step Mission Plan</div>
          <ol className="priority-list">
            {{m.mission_plan.map((step, i) => (
              <li key={{i}}>{{step.replace(/^\d+\.\s*/, "")}}</li>
            ))}}
          </ol>
        </div>
      )}}
    </div>
  );
}}

function RecommendedTab({{ setLightbox }}) {{
  const a = D.analysis;
  const wi = D.wikiImages || {{}};
  if (a.error || a.parse_error) return <div className="panel"><p>No analysis available.</p></div>;

  const slots = a.slots || [];

  // Build recommended loadout per slot based on improvements
  return (
    <div className="panel">
      <div className="section-title">Recommended Loadout Changes</div>
      <p style={{{{color: "var(--text2)", marginBottom: "20px"}}}}>
        Equipment images sourced from <a href="https://wiki.fishingplanet.com" target="_blank"
        style={{{{color: "var(--accent)"}}}}>wiki.fishingplanet.com</a>. Click any image to enlarge.
      </p>
      <div className="grid grid-2">
        {{slots.map((slot, i) => {{
          const r = slot.effectiveness_rating || 0;
          const rClass = r >= 7 ? "high" : r >= 4 ? "mid" : "low";

          // Find wiki images for items mentioned in this slot
          const slotImages = [];
          if (slot.bait && wi[slot.bait]) slotImages.push({{ name: "Current: " + slot.bait, url: wi[slot.bait] }});

          // Find recommended items from improvements
          const recImages = [];
          (slot.improvements || []).forEach(imp => {{
            Object.entries(wi).forEach(([name, url]) => {{
              if (imp.toLowerCase().includes(name.toLowerCase())) {{
                recImages.push({{ name, url }});
              }}
            }});
          }});

          return (
            <div key={{i}} className="card">
              <div style={{{{display: "flex", alignItems: "center", gap: "12px", marginBottom: "12px"}}}}>
                <div className="slot-num" style={{{{position: "relative", top: 0, left: 0}}}}>{{slot.slot_number || i + 1}}</div>
                <div>
                  <h3 style={{{{margin: 0}}}}>Slot {{slot.slot_number || i + 1}} — {{slot.setup_type}}</h3>
                  <div className={{"rating " + rClass}} style={{{{display: "inline-flex", margin: "4px 0"}}}}>
                    Current: {{r}}/10
                  </div>
                </div>
              </div>

              {{/* Current equipment summary */}}
              <div style={{{{background: "rgba(0,0,0,0.2)", borderRadius: "8px", padding: "12px", marginBottom: "12px"}}}}>
                <div style={{{{fontWeight: 600, color: "var(--text2)", marginBottom: "6px", fontSize: "0.85em"}}}}>CURRENT SETUP</div>
                {{slot.rod && <div className="detail">Rod: {{slot.rod}}</div>}}
                {{slot.reel && <div className="detail">Reel: {{slot.reel}}</div>}}
                {{slot.line && <div className="detail">Line: {{slot.line}}</div>}}
                {{slot.terminal_tackle && <div className="detail">Terminal: {{slot.terminal_tackle}}</div>}}
                {{slot.bait && <div className="detail">Bait: {{slot.bait}}</div>}}
              </div>

              {{/* Current bait/lure image */}}
              {{slotImages.length > 0 && (
                <div style={{{{marginBottom: "12px"}}}}>
                  <div style={{{{fontWeight: 600, color: "var(--text2)", marginBottom: "6px", fontSize: "0.85em"}}}}>CURRENT BAIT/LURE</div>
                  <div style={{{{display: "flex", gap: "8px", flexWrap: "wrap"}}}}>
                    {{slotImages.map((img, j) => (
                      <div key={{j}} style={{{{textAlign: "center"}}}}>
                        <img src={{img.url}} alt={{img.name}}
                          style={{{{width: "80px", height: "80px", objectFit: "contain", borderRadius: "8px",
                                  background: "rgba(255,255,255,0.05)", padding: "4px", cursor: "pointer"}}}}
                          onClick={{() => setLightbox(img.url)}} />
                        <div style={{{{fontSize: "0.75em", color: "var(--text2)", marginTop: "4px"}}}}>{{img.name}}</div>
                      </div>
                    ))}}
                  </div>
                </div>
              )}}

              {{/* Recommended changes */}}
              {{/* Leader recommendation */}}
              {{slot.leader_recommendation && (
                <div style={{{{background: "rgba(0,188,212,0.08)", border: "1px solid rgba(0,188,212,0.2)",
                              borderRadius: "8px", padding: "12px", marginBottom: "12px"}}}}>
                  <div style={{{{fontWeight: 600, color: "var(--accent)", marginBottom: "6px", fontSize: "0.85em"}}}}>LEADER RECOMMENDATION</div>
                  <div className="detail"><strong>Material:</strong> {{slot.leader_recommendation.material}}</div>
                  <div className="detail"><strong>Test Weight:</strong> {{slot.leader_recommendation.test_weight}}</div>
                  <div className="detail"><strong>Length:</strong> {{slot.leader_recommendation.length}}</div>
                  <div className="detail"><strong>Float Depth:</strong> {{slot.leader_recommendation.depth_setting}}</div>
                  <div className="detail" style={{{{marginTop: "6px", color: "var(--text2)", fontSize: "0.85em"}}}}>{{slot.leader_recommendation.why}}</div>
                </div>
              )}}

              <div style={{{{fontWeight: 600, color: "var(--accent2)", marginBottom: "6px", fontSize: "0.85em"}}}}>RECOMMENDED CHANGES</div>
              {{(slot.improvements || []).map((imp, j) => (
                <div key={{j}} className="improvement">→ {{imp}}</div>
              ))}}

              {{/* Recommended equipment images */}}
              {{recImages.length > 0 && (
                <div style={{{{marginTop: "12px"}}}}>
                  <div style={{{{fontWeight: 600, color: "var(--text2)", marginBottom: "6px", fontSize: "0.85em"}}}}>RECOMMENDED EQUIPMENT</div>
                  <div style={{{{display: "flex", gap: "10px", flexWrap: "wrap"}}}}>
                    {{recImages.map((img, j) => (
                      <div key={{j}} style={{{{textAlign: "center"}}}}>
                        <img src={{img.url}} alt={{img.name}}
                          style={{{{width: "90px", height: "90px", objectFit: "contain", borderRadius: "8px",
                                  background: "rgba(76,175,80,0.1)", border: "1px solid rgba(76,175,80,0.3)",
                                  padding: "6px", cursor: "pointer"}}}}
                          onClick={{() => setLightbox(img.url)}} />
                        <div style={{{{fontSize: "0.75em", color: "var(--accent2)", marginTop: "4px", maxWidth: "90px"}}}}>{{img.name}}</div>
                      </div>
                    ))}}
                  </div>
                </div>
              )}}
            </div>
          );
        }})}}
      </div>

      {{/* Fish bait/lure reference with images */}}
      <div style={{{{marginTop: "24px"}}}}>
        <div className="section-title">Bait & Lure Quick Reference</div>
        <p style={{{{color: "var(--text2)", marginBottom: "16px", fontSize: "0.9em"}}}}>
          All baits and lures effective at this location — images from the Fishing Planet Wiki.
        </p>
        <div style={{{{display: "flex", gap: "12px", flexWrap: "wrap"}}}}>
          {{Object.entries(wi).map(([name, url]) => (
            <div key={{name}} style={{{{textAlign: "center", width: "100px"}}}}>
              <img src={{url}} alt={{name}}
                style={{{{width: "80px", height: "80px", objectFit: "contain", borderRadius: "8px",
                        background: "rgba(255,255,255,0.05)", padding: "4px", cursor: "pointer"}}}}
                onClick={{() => setLightbox(url)}} />
              <div style={{{{fontSize: "0.75em", color: "var(--text)", marginTop: "4px"}}}}>{{name}}</div>
            </div>
          ))}}
        </div>
      </div>
    </div>
  );
}}

function PriorityTab() {{
  const a = D.analysis;
  if (a.error || a.parse_error) return <div className="panel"><p>No analysis available.</p></div>;
  const oa = a.overall_analysis || {{}};

  return (
    <div className="panel">
      {{oa.priority_changes && oa.priority_changes.length > 0 && (
        <div>
          <div className="section-title">Priority Changes (Most Impactful First)</div>
          <ol className="priority-list">
            {{oa.priority_changes.map((c,i) => <li key={{i}}>{{c}}</li>)}}
          </ol>
        </div>
      )}}

      {{oa.missing_setups && oa.missing_setups.length > 0 && (
        <div style={{{{marginTop: "24px"}}}}>
          <div className="section-title">Missing Setup Types</div>
          {{oa.missing_setups.map((s,i) => <div key={{i}} className="card" style={{{{marginBottom:"8px"}}}}>{{s}}</div>)}}
        </div>
      )}}

      {{oa.spot_recommendations && Object.keys(oa.spot_recommendations).length > 0 && (
        <div style={{{{marginTop: "24px"}}}}>
          <div className="section-title">Spot → Slot Recommendations</div>
          <div className="grid grid-3">
            {{Object.entries(oa.spot_recommendations).map(([spot, slots]) => (
              <div key={{spot}} className="card">
                <h3>{{spot}}</h3>
                <div className="detail">Use slot(s): <strong>{{Array.isArray(slots) ? slots.join(", ") : slots}}</strong></div>
              </div>
            ))}}
          </div>
        </div>
      )}}
    </div>
  );
}}

function FishTab() {{
  const [expanded, setExpanded] = useState(null);
  return (
    <div className="panel">
      <div className="section-title">Fish at this Location ({{D.fish.length}})</div>
      <div className="grid grid-2">
        {{D.fish.map((fish, i) => (
          <div key={{i}} className="card" onClick={{() => setExpanded(expanded === i ? null : i)}}
            style={{{{cursor: "pointer"}}}}>
            <div style={{{{display: "flex", gap: "16px", alignItems: "flex-start"}}}}>
              {{fish.image && <img src={{fish.image}} alt={{fish.name}}
                style={{{{width: "120px", minWidth: "120px", borderRadius: "8px"}}}} />}}
              <div style={{{{flex: 1}}}}>
                <h3>{{fish.name}}</h3>
                <div className="detail">
                  {{fish.types.map(t => <span key={{t}} className={{"badge " + t}}>{{t}}</span>)}}
                </div>
                <div className="detail">Max Weight: <strong>{{(fish.maxWeight * 2.205).toFixed(1)}} lb</strong></div>
                <div className="detail">Price: <strong className="money">${{(fish.price / 2.205).toFixed(0)}}/lb</strong></div>
              </div>
            </div>

            {{/* Activity, Depth & Hook info — always visible */}}
            {{(fish.activeTimes || fish.preferredDepth || fish.recommendedHook) && (
              <div style={{{{marginTop: "12px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px"}}}}>
                {{fish.activeTimes && (
                  <div style={{{{background: "rgba(255,193,7,0.08)", border: "1px solid rgba(255,193,7,0.2)",
                                borderRadius: "8px", padding: "10px"}}}}>
                    <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--gold)", marginBottom: "4px"}}}}>MOST ACTIVE</div>
                    <div style={{{{fontSize: "0.85em", color: "var(--text)"}}}}>{{fish.activeTimes}}</div>
                  </div>
                )}}
                {{fish.preferredDepth && (
                  <div style={{{{background: "rgba(0,188,212,0.08)", border: "1px solid rgba(0,188,212,0.2)",
                                borderRadius: "8px", padding: "10px"}}}}>
                    <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--accent)", marginBottom: "4px"}}}}>PREFERRED DEPTH</div>
                    <div style={{{{fontSize: "0.85em", color: "var(--text)"}}}}>{{fish.preferredDepth}}</div>
                  </div>
                )}}
                {{fish.recommendedHook && (
                  <div style={{{{background: "rgba(244,67,54,0.08)", border: "1px solid rgba(244,67,54,0.2)",
                                borderRadius: "8px", padding: "10px"}}}}>
                    <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--danger)", marginBottom: "4px"}}}}>RECOMMENDED HOOK</div>
                    <div style={{{{fontSize: "1.3em", fontWeight: 700, color: "var(--text)"}}}}>{{fish.recommendedHook}}</div>
                    <div style={{{{fontSize: "0.75em", color: "var(--text2)"}}}}>for unique/trophy</div>
                  </div>
                )}}
              </div>
            )}}

            {{fish.habitat && (
              <div style={{{{marginTop: "8px", fontSize: "0.85em", color: "var(--text2)"}}}}>
                <strong>Habitat:</strong> {{fish.habitat}}
              </div>
            )}}

            {{fish.techniqueTip && (
              <div className="tip" style={{{{marginTop: "6px", fontSize: "0.85em"}}}}>{{fish.techniqueTip}}</div>
            )}}

            {{/* Ubersheet recommended — curated best tackle */}}
            {{(fish.ubersheetBaits?.length > 0 || fish.ubersheetLures?.length > 0 || fish.ubersheetHooks?.length > 0) && (
              <div style={{{{marginTop: "10px", background: "rgba(255,193,7,0.06)", border: "1px solid rgba(255,193,7,0.2)",
                            borderRadius: "8px", padding: "10px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--gold)", marginBottom: "8px"}}}}>UBERSHEET RECOMMENDED (Community-Tested Best Tackle)</div>
                {{fish.ubersheetBaits?.length > 0 && (
                  <div style={{{{marginBottom: "6px"}}}}>
                    <span style={{{{fontSize: "0.75em", color: "var(--text2)", marginRight: "6px"}}}}>Baits:</span>
                    {{fish.ubersheetBaits.map((b,j) => {{
                      const imgUrl = D.wikiImages && D.wikiImages[b];
                      return (
                        <span key={{j}} style={{{{display: "inline-flex", alignItems: "center", gap: "3px",
                                              background: "rgba(255,193,7,0.12)", border: "1px solid rgba(255,193,7,0.25)",
                                              borderRadius: "6px", padding: "2px 8px 2px 2px", marginRight: "4px", marginBottom: "2px"}}}}>
                          {{imgUrl && <img src={{imgUrl}} alt={{b}} style={{{{width: "22px", height: "22px", objectFit: "contain"}}}} />}}
                          <span style={{{{fontSize: "0.8em", fontWeight: 600}}}}>{{b}}</span>
                        </span>
                      );
                    }})}}
                  </div>
                )}}
                {{fish.ubersheetHooks?.length > 0 && (
                  <div style={{{{marginBottom: "6px"}}}}>
                    <span style={{{{fontSize: "0.75em", color: "var(--text2)", marginRight: "6px"}}}}>Hooks:</span>
                    {{fish.ubersheetHooks.map((h,j) => (
                      <span key={{j}} style={{{{display: "inline-flex", alignItems: "center",
                                             background: "rgba(255,193,7,0.12)", border: "1px solid rgba(255,193,7,0.25)",
                                             borderRadius: "6px", padding: "2px 8px", marginRight: "4px", fontSize: "0.8em", fontWeight: 600}}}}>
                        {{h.title}} {{h.size ? `(${{h.size}})` : ""}}
                      </span>
                    ))}}
                  </div>
                )}}
                {{fish.ubersheetLures?.length > 0 && (
                  <div style={{{{marginBottom: "4px"}}}}>
                    <span style={{{{fontSize: "0.75em", color: "var(--text2)", marginRight: "6px"}}}}>Lures:</span>
                    <div style={{{{display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "4px"}}}}>
                      {{fish.ubersheetLures.map((l,j) => (
                        <span key={{j}} style={{{{display: "inline-block",
                                               background: "rgba(255,193,7,0.12)", border: "1px solid rgba(255,193,7,0.25)",
                                               borderRadius: "6px", padding: "2px 8px", fontSize: "0.75em"}}}}>
                          <strong>{{l.title}}</strong> {{l.color ? <span style={{{{color: "var(--text2)"}}}}>{{l.color}}</span> : ""}}
                          {{l.baseLevel ? <span style={{{{color: "var(--text2)", marginLeft: "4px"}}}}>Lv{{l.baseLevel}}</span> : ""}}
                        </span>
                      ))}}
                    </div>
                  </div>
                )}}
                {{fish.ubersheetJigheads?.length > 0 && (
                  <div>
                    <span style={{{{fontSize: "0.75em", color: "var(--text2)", marginRight: "6px"}}}}>Jigheads:</span>
                    {{fish.ubersheetJigheads.map((j,k) => (
                      <span key={{k}} style={{{{display: "inline-flex", alignItems: "center",
                                             background: "rgba(255,193,7,0.12)", border: "1px solid rgba(255,193,7,0.25)",
                                             borderRadius: "6px", padding: "2px 8px", marginRight: "4px", fontSize: "0.8em", fontWeight: 600}}}}>
                        {{j.title}}
                      </span>
                    ))}}
                  </div>
                )}}
              </div>
            )}}

            {{/* Preferred baits — always visible */}}
            {{fish.baits.length > 0 && (
              <div style={{{{marginTop: "10px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--accent)", marginBottom: "6px"}}}}>ALL EFFECTIVE BAITS</div>
                <div style={{{{display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center"}}}}>
                  {{fish.baits.map((b,j) => {{
                    const imgUrl = D.wikiImages && D.wikiImages[b];
                    return (
                      <div key={{j}} style={{{{display: "flex", alignItems: "center", gap: "4px",
                                            background: "rgba(0,188,212,0.1)", border: "1px solid rgba(0,188,212,0.2)",
                                            borderRadius: "6px", padding: "3px 8px 3px 3px"}}}}>
                        {{imgUrl && <img src={{imgUrl}} alt={{b}}
                          style={{{{width: "28px", height: "28px", objectFit: "contain", borderRadius: "4px"}}}} />}}
                        <span style={{{{fontSize: "0.8em", color: "var(--text)"}}}}>{{b}}</span>
                      </div>
                    );
                  }})}}
                </div>
              </div>
            )}}

            {{/* Preferred lure types — always visible */}}
            {{fish.lures.length > 0 && (() => {{
              const typeGroups = {{}};
              fish.lures.forEach(l => {{
                const t = l.type || "Other";
                if (!typeGroups[t]) typeGroups[t] = [];
                typeGroups[t].push(l);
              }});
              return (
                <div style={{{{marginTop: "8px"}}}}>
                  <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--accent2)", marginBottom: "6px"}}}}>PREFERRED LURE TYPES</div>
                  <div style={{{{display: "flex", gap: "6px", flexWrap: "wrap"}}}}>
                    {{Object.entries(typeGroups).map(([type, lures], j) => (
                      <div key={{j}} style={{{{background: "rgba(76,175,80,0.1)", border: "1px solid rgba(76,175,80,0.2)",
                                            borderRadius: "6px", padding: "4px 10px"}}}}>
                        <span style={{{{fontSize: "0.8em", color: "var(--accent2)", fontWeight: 600}}}}>{{type}}</span>
                        <span style={{{{fontSize: "0.75em", color: "var(--text2)", marginLeft: "4px"}}}}>
                          ({{lures.length}} {{lures.length === 1 ? "variant" : "variants"}})
                        </span>
                      </div>
                    ))}}
                  </div>
                </div>
              );
            }})()}}

            {{/* Expanded full bait/lure details */}}
            {{expanded === i && (
              <div style={{{{marginTop: "12px", borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: "12px"}}}}>
                {{fish.baits.length > 0 && (
                  <div className="detail">
                    <strong>All Baits:</strong><br/>
                    {{fish.baits.map((b,j) => <span key={{j}} className="badge bait">{{b}}</span>)}}
                  </div>
                )}}
                {{fish.lures.length > 0 && (
                  <div className="detail" style={{{{marginTop:"8px"}}}}>
                    <strong>All Lures (with colors):</strong><br/>
                    {{fish.lures.map((l,j) => <span key={{j}} className="badge bait">{{l.title}} {{l.color ? `(${{l.color}})` : ""}}</span>)}}
                  </div>
                )}}
              </div>
            )}}
          </div>
        ))}}
      </div>
    </div>
  );
}}

function SpotsTab() {{
  return (
    <div className="panel">
      <div className="section-title">Fishing Spots</div>
      <div className="grid grid-3">
        {{D.spots.map((spot, i) => (
          <div key={{i}} className="card spot-card">
            {{spot.image && <img src={{spot.image}} alt={{spot.name}} />}}
            <h3>{{spot.name}}</h3>
            <div className="detail">Coordinates: {{spot.lat?.toFixed(4)}}, {{spot.lng?.toFixed(4)}}</div>
          </div>
        ))}}
      </div>
    </div>
  );
}}

function FishMapTab() {{
  const mapRef = React.useRef(null);
  const mapInstanceRef = React.useRef(null);
  const layerRef = React.useRef(null);
  const [selectedFish, setSelectedFish] = React.useState("ALL");
  const [selectedType, setSelectedType] = React.useState("ALL");

  const markers = D.fishMarkers || [];
  const mapUrl = D.location.map;
  const mapConfig = D.location.mapConfig || {{}};
  // SVG aspect ratio drives Leaflet bounds so portrait/landscape SVGs render correctly
  const svgW = mapConfig.mapWidth || 100;
  const svgH = mapConfig.mapHeight || 100;
  // Normalize: longest edge = 100, other edge proportional
  const maxDim = Math.max(svgW, svgH);
  const boundsW = (svgW / maxDim) * 100;
  const boundsH = (svgH / maxDim) * 100;

  // Build fish list with counts
  const fishCounts = {{}};
  markers.forEach(m => {{
    if (m.fish) fishCounts[m.fish] = (fishCounts[m.fish] || 0) + 1;
  }});
  const fishList = Object.keys(fishCounts).sort((a, b) => fishCounts[b] - fishCounts[a]);

  const typeCounts = {{}};
  markers.forEach(m => {{
    const t = m.type || "common";
    typeCounts[t] = (typeCounts[t] || 0) + 1;
  }});

  // Color by fish type
  const typeColors = {{
    common: "#00bcd4", trophy: "#ffc107", unique: "#ff5252",
    young: "#90a4ae", "super trophy": "#ff9800",
  }};

  React.useEffect(() => {{
    if (typeof L === "undefined") return;
    if (!mapRef.current) return;

    if (!mapInstanceRef.current) {{
      const map = L.map(mapRef.current, {{
        crs: L.CRS.Simple, minZoom: -2, maxZoom: 4, zoomControl: true,
        attributionControl: false,
      }});
      mapInstanceRef.current = map;

      // Bounds match SVG aspect ratio so portrait maps don't stretch
      const bounds = [[0, 0], [boundsH, boundsW]];
      if (mapUrl) L.imageOverlay(mapUrl, bounds).addTo(map);
      map.fitBounds(bounds);
      map.setMaxBounds([[0 - boundsH * 0.5, 0 - boundsW * 0.5], [boundsH * 1.5, boundsW * 1.5]]);
    }}

    // Remove previous markers
    if (layerRef.current) {{
      mapInstanceRef.current.removeLayer(layerRef.current);
    }}

    // Filter markers — x/y are 0-100 percentages; reject outliers (bad data with huge negative coords)
    const filtered = markers.filter(m => {{
      if (selectedFish !== "ALL" && m.fish !== selectedFish) return false;
      if (selectedType !== "ALL" && (m.type || "common") !== selectedType) return false;
      if (m.x == null || m.y == null) return false;
      if (m.x < -5 || m.x > 105 || m.y < -5 || m.y > 105) return false;
      return true;
    }});

    // Add fresh marker layer
    const group = L.layerGroup();
    filtered.forEach(m => {{
      const color = typeColors[m.type] || "#00bcd4";
      // x/y are 0-100 percentages; scale to SVG aspect-corrected bounds. Flip y for Leaflet's bottom-up axis.
      const ly = (100 - m.y) * boundsH / 100;
      const lx = m.x * boundsW / 100;
      const marker = L.circleMarker([ly, lx], {{
        radius: m.type === "unique" ? 7 : (m.type === "trophy" ? 6 : 5),
        color: color, fillColor: color, fillOpacity: 0.7, weight: 1,
      }});
      const weightTxt = m.weight != null ? `${{(m.weight * 2.205).toFixed(1)}} lb` : "";
      const lureTxt = m.lure || m.bait || "-";
      marker.bindPopup(`
        <div style="font-family:Segoe UI,sans-serif;color:#1a2634;min-width:200px">
          <div style="font-weight:700;color:#00bcd4;margin-bottom:4px">${{m.fish}} ${{m.type && m.type !== 'common' ? '<span style=\\'color:'+color+'\\'>('+m.type+')</span>' : ''}}</div>
          ${{weightTxt ? '<div><strong>Weight:</strong> '+weightTxt+'</div>' : ''}}
          ${{m.time ? '<div><strong>Time:</strong> '+m.time+'</div>' : ''}}
          ${{m.weatherPattern ? '<div><strong>Weather:</strong> '+m.weatherPattern+'</div>' : ''}}
          <div><strong>Lure/Bait:</strong> ${{lureTxt}}</div>
          ${{m.hook ? '<div><strong>Hook:</strong> '+m.hook+'</div>' : ''}}
          ${{m.technique ? '<div><strong>Technique:</strong> '+m.technique+'</div>' : ''}}
          ${{m.fishingFrom ? '<div><strong>From:</strong> '+m.fishingFrom+'</div>' : ''}}
          ${{m.depth != null ? '<div><strong>Depth:</strong> '+m.depth+' m</div>' : ''}}
          ${{m.caughtBy ? '<div style="margin-top:4px;color:#666;font-size:0.85em">By: '+m.caughtBy+'</div>' : ''}}
        </div>
      `);
      group.addLayer(marker);
    }});
    group.addTo(mapInstanceRef.current);
    layerRef.current = group;
  }}, [selectedFish, selectedType, mapUrl]);

  return (
    <div className="panel">
      <div className="section-title">Fish Map — Crowdsourced Catch Locations</div>
      <p className="detail" style={{{{marginBottom:"12px"}}}}>
        {{markers.length}} catch markers from fp-collective.com. Click a marker to see what was caught — species, bait/lure, technique, weather, and more.
      </p>
      <div style={{{{display:"flex", gap:"12px", flexWrap:"wrap", marginBottom:"12px", alignItems:"center"}}}}>
        <label style={{{{color:"var(--text2)", fontSize:"0.85em"}}}}>Species:</label>
        <select value={{selectedFish}} onChange={{e => setSelectedFish(e.target.value)}}
          style={{{{background:"var(--surface2)", color:"var(--text)", border:"1px solid rgba(255,255,255,0.1)", borderRadius:"6px", padding:"6px 10px"}}}}>
          <option value="ALL">All ({{markers.length}})</option>
          {{fishList.map(f => <option key={{f}} value={{f}}>{{f}} ({{fishCounts[f]}})</option>)}}
        </select>
        <label style={{{{color:"var(--text2)", fontSize:"0.85em", marginLeft:"12px"}}}}>Type:</label>
        <select value={{selectedType}} onChange={{e => setSelectedType(e.target.value)}}
          style={{{{background:"var(--surface2)", color:"var(--text)", border:"1px solid rgba(255,255,255,0.1)", borderRadius:"6px", padding:"6px 10px"}}}}>
          <option value="ALL">All types</option>
          {{Object.keys(typeCounts).sort().map(t => <option key={{t}} value={{t}}>{{t}} ({{typeCounts[t]}})</option>)}}
        </select>
        <div style={{{{marginLeft:"auto", display:"flex", gap:"10px", fontSize:"0.8em", color:"var(--text2)"}}}}>
          <span><span style={{{{display:"inline-block",width:"10px",height:"10px",borderRadius:"50%",background:"#00bcd4",marginRight:"4px"}}}}></span>common</span>
          <span><span style={{{{display:"inline-block",width:"10px",height:"10px",borderRadius:"50%",background:"#ffc107",marginRight:"4px"}}}}></span>trophy</span>
          <span><span style={{{{display:"inline-block",width:"10px",height:"10px",borderRadius:"50%",background:"#ff5252",marginRight:"4px"}}}}></span>unique</span>
        </div>
      </div>
      <div ref={{mapRef}} style={{{{height:"650px", width:"100%", background:"var(--surface2)", borderRadius:"10px"}}}}></div>
    </div>
  );
}}

function WeatherTab() {{
  const day = D.weather.filter(w => w.type === "day");
  const night = D.weather.filter(w => w.type === "night");

  return (
    <div className="panel">
      <div className="section-title">Day Bite Charts</div>
      <div className="grid grid-3">
        {{day.map((w, i) => (
          <div key={{i}} className="card weather-card">
            <h3>{{w.icon && <img className="icon" src={{w.icon}} alt="" />}}{{w.name}}</h3>
            {{w.chart && <img src={{w.chart}} alt={{w.name + " bite chart"}} />}}
          </div>
        ))}}
      </div>
      <div className="section-title" style={{{{marginTop:"24px"}}}}>Night Bite Charts</div>
      <div className="grid grid-3">
        {{night.map((w, i) => (
          <div key={{i}} className="card weather-card">
            <h3>{{w.icon && <img className="icon" src={{w.icon}} alt="" />}}{{w.name}}</h3>
            {{w.chart && <img src={{w.chart}} alt={{w.name + " bite chart"}} />}}
          </div>
        ))}}
      </div>
    </div>
  );
}}

function LicenseTab() {{
  const b = D.license.basic || {{}};
  const a = D.license.advanced || {{}};

  return (
    <div className="panel">
      <div className="section-title">License & Cost Information</div>
      <table className="license-table">
        <thead>
          <tr><th>Duration</th><th>Basic</th><th>Advanced</th></tr>
        </thead>
        <tbody>
          <tr><td>1 Day</td><td className="money">${{b.oneDayCost}}</td><td className="money">${{a.oneDayCost}}</td></tr>
          <tr><td>3 Days</td><td className="money">${{b.threeDaysCost}}</td><td className="money">${{a.threeDaysCost}}</td></tr>
          <tr><td>1 Week</td><td className="money">${{b.weekCost}}</td><td className="money">${{a.weekCost}}</td></tr>
          <tr><td>1 Month</td><td className="money">${{b.monthCost}}</td><td className="money">${{a.monthCost}}</td></tr>
          <tr><td>Unlimited</td><td className="money">${{b.unlimitedCost}} BC</td><td className="money">${{a.unlimitedCost}} BC</td></tr>
          <tr><td>Violation Fine</td><td style={{{{color:"var(--danger)"}}}}>${{b.violationCost}}</td><td style={{{{color:"var(--danger)"}}}}>${{a.violationCost}}</td></tr>
        </tbody>
      </table>
      <div style={{{{marginTop:"16px"}}}}>
        <div className="detail">Night Fishing: <strong>{{a.isNightFishingAllowed ? "✓ Allowed (Advanced)" : "✗ Not allowed"}}</strong></div>
        <div className="detail">Boat Fishing: <strong>{{a.isBoatFishingAllowed ? "✓ Allowed (Advanced)" : "✗ Not allowed"}}</strong></div>
      </div>
      <div style={{{{marginTop:"16px"}}}}>
        <div className="detail">Travel Cost: <strong className="money">${{D.location.travelCost}}</strong></div>
        <div className="detail">Extend Stay: <strong className="money">${{D.location.extendCost}}</strong></div>
      </div>
    </div>
  );
}}

function PassiveFishingTab() {{
  const a = D.analysis;
  const pf = a.passive_fishing || {{}};
  const slots = a.slots || [];

  // Identify float/bottom rod slots suitable for rod stand
  const standSlots = slots.filter(s =>
    s.setup_type && (s.setup_type.toLowerCase().includes("float") || s.setup_type.toLowerCase().includes("bottom") || s.setup_type.toLowerCase().includes("feeder"))
  );
  const activeSlots = slots.filter(s =>
    s.setup_type && (s.setup_type.toLowerCase().includes("spinning") || s.setup_type.toLowerCase().includes("casting"))
  );

  return (
    <div className="panel">
      <div className="section-title">Passive Fishing Strategy</div>

      {{/* How it works */}}
      <div className="card" style={{{{marginBottom: "20px", borderLeft: "3px solid var(--accent)"}}}}>
        <h3 style={{{{color: "var(--accent)"}}}}>How Rod Stand Fishing Works</h3>
        <div style={{{{display: "grid", gap: "8px", marginTop: "10px"}}}}>
          {{[
            "Place your rod stand at a fishing spot — RodPod Trio holds 3 rods simultaneously",
            "Cast each float/bottom rod to a promising spot and set it on the stand",
            "Fish actively with a spinning or casting rod in your hands nearby",
            "When a fish bites a stand rod: the float dips/moves and you hear an audio cue",
            "Quickly switch to the biting rod (use Select Rod), set the hook, and reel in the fish",
            "Re-bait, cast back out, and return the rod to the stand — resume active fishing",
          ].map((step, i) => (
            <div key={{i}} style={{{{display: "flex", gap: "10px", alignItems: "flex-start"}}}}>
              <div style={{{{background: "var(--accent)", color: "#fff", width: "24px", height: "24px",
                           borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                           fontSize: "0.8em", fontWeight: 700, flexShrink: 0}}}}>{{i + 1}}</div>
              <div style={{{{fontSize: "0.9em"}}}}>{{step}}</div>
            </div>
          ))}}
        </div>
      </div>

      {{/* Key tips */}}
      <div className="card" style={{{{marginBottom: "20px", borderLeft: "3px solid var(--gold)"}}}}>
        <h3 style={{{{color: "var(--gold)"}}}}>Tips for Maximum Passive Income</h3>
        <div style={{{{marginTop: "8px"}}}}>
          {{[
            "Stay within visual range of your rod stand — if you wander too far, you'll miss bites and lose fish",
            "Use GLOWING floats (Pear-Shaped, Slim) for visibility at distance and during dawn/dusk/night",
            "Heavier floats are easier to see bite indications from further away",
            "Cast stand rods at different distances and angles to cover more water",
            "Set float depths at different levels (shallow, mid, deep) to find where fish are holding",
            "Re-check and re-bait stand rods every 5-10 minutes even without bites — bait degrades over time",
            "Active fish with your spinning rod NEAR the rod stand, not across the lake from it",
            "Sell your keepnet when it's full, then reset all stand rods — this is your income cycle",
          ].map((tip, i) => (
            <div key={{i}} className="tip" style={{{{padding: "4px 0"}}}}>{{tip}}</div>
          ))}}
        </div>
      </div>

      {{/* Recommended rod stand setup */}}
      <div className="section-title">Recommended Rod Stand Deployment</div>
      <div className="grid grid-2">
        <div className="card" style={{{{borderLeft: "3px solid var(--accent2)"}}}}>
          <h3 style={{{{color: "var(--accent2)"}}}}>Rods ON the Stand (Passive)</h3>
          <p style={{{{color: "var(--text2)", fontSize: "0.85em", marginBottom: "12px"}}}}>
            Float and bottom rigs that soak bait while you actively fish nearby.
          </p>
          {{standSlots.length > 0 ? standSlots.map((slot, i) => (
            <div key={{i}} style={{{{background: "rgba(76,175,80,0.08)", borderRadius: "8px",
                                  padding: "10px", marginBottom: "8px"}}}}>
              <div style={{{{fontWeight: 600}}}}>Slot {{slot.slot_number}} — {{slot.setup_type}}</div>
              <div className="detail">{{slot.rod}}</div>
              <div className="detail">{{slot.terminal_tackle}}</div>
              {{slot.bait && <div className="detail">Bait: <strong>{{slot.bait}}</strong></div>}}
              {{slot.target_fish && <div className="detail" style={{{{marginTop: "4px"}}}}>
                Targets: {{slot.target_fish.map((f,j) => <span key={{j}} className="badge common" style={{{{marginRight: "4px"}}}}>{{f}}</span>)}}
              </div>}}
            </div>
          )) : (
            <div className="detail" style={{{{color: "var(--text2)"}}}}>No float/bottom rods identified in current loadout.</div>
          )}}
        </div>

        <div className="card" style={{{{borderLeft: "3px solid var(--accent)"}}}}>
          <h3 style={{{{color: "var(--accent)"}}}}>Rods IN HAND (Active)</h3>
          <p style={{{{color: "var(--text2)", fontSize: "0.85em", marginBottom: "12px"}}}}>
            Spinning/casting rods to actively fish while stand rods soak.
          </p>
          {{activeSlots.length > 0 ? activeSlots.map((slot, i) => (
            <div key={{i}} style={{{{background: "rgba(0,188,212,0.08)", borderRadius: "8px",
                                  padding: "10px", marginBottom: "8px"}}}}>
              <div style={{{{fontWeight: 600}}}}>Slot {{slot.slot_number}} — {{slot.setup_type}}</div>
              <div className="detail">{{slot.rod}}</div>
              <div className="detail">{{slot.terminal_tackle}}</div>
              {{slot.target_fish && <div className="detail" style={{{{marginTop: "4px"}}}}>
                Targets: {{slot.target_fish.map((f,j) => <span key={{j}} className="badge common" style={{{{marginRight: "4px"}}}}>{{f}}</span>)}}
              </div>}}
            </div>
          )) : (
            <div className="detail" style={{{{color: "var(--text2)"}}}}>No spinning/casting rods identified in current loadout.</div>
          )}}
        </div>
      </div>

      {{/* Location-specific passive strategy */}}
      {{pf.strategy && (
        <div style={{{{marginTop: "24px"}}}}>
          <div className="section-title">Location Strategy</div>
          <div className="card">
            {{pf.best_stand_spot && (
              <div style={{{{marginBottom: "12px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--gold)", marginBottom: "4px"}}}}>BEST SPOT FOR ROD STAND</div>
                <div style={{{{fontSize: "1.05em", fontWeight: 600}}}}>{{pf.best_stand_spot}}</div>
                {{pf.stand_spot_why && <div className="detail" style={{{{color: "var(--text2)"}}}}>{{pf.stand_spot_why}}</div>}}
              </div>
            )}}
            {{pf.active_fishing_zone && (
              <div style={{{{marginBottom: "12px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--accent)", marginBottom: "4px"}}}}>ACTIVE FISHING ZONE</div>
                <div>{{pf.active_fishing_zone}}</div>
              </div>
            )}}
            {{pf.strategy.map((s, i) => (
              <div key={{i}} className="tip" style={{{{padding: "4px 0"}}}}>{{s}}</div>
            ))}}
          </div>
        </div>
      )}}

      {{/* Income estimate */}}
      {{pf.income_estimate && (
        <div style={{{{marginTop: "24px"}}}}>
          <div className="section-title">Estimated Passive Income</div>
          <div className="card" style={{{{borderLeft: "3px solid var(--accent2)"}}}}>
            {{pf.income_estimate.map((line, i) => (
              <div key={{i}} className="detail" style={{{{padding: "4px 0"}}}}>{{line}}</div>
            ))}}
          </div>
        </div>
      )}}

      {{/* Boat Trolling Strategy */}}
      {{pf.boat_trolling && (
        <div style={{{{marginTop: "24px"}}}}>
          <div className="section-title">🛥️ Boat Trolling Strategy</div>
          <div className="card" style={{{{borderLeft: "3px solid " + (pf.boat_trolling.recommended ? "var(--accent2)" : "var(--danger)")}}}}>
            <div style={{{{display: "flex", gap: "10px", alignItems: "center", marginBottom: "12px"}}}}>
              <span className={{"badge " + (pf.boat_trolling.recommended ? "trophy" : "common")}} style={{{{fontSize: "0.85em"}}}}>
                {{pf.boat_trolling.recommended ? "✅ RECOMMENDED" : "❌ NOT RECOMMENDED"}}
              </span>
              {{pf.boat_trolling.boat_required && <span className="detail" style={{{{color: "var(--text2)"}}}}>Boat: {{pf.boat_trolling.boat_required}}</span>}}
            </div>
            {{pf.boat_trolling.summary && <p style={{{{marginBottom: "12px"}}}}>{{pf.boat_trolling.summary}}</p>}}

            {{pf.boat_trolling.staging_spot && (
              <div style={{{{marginBottom: "10px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--gold)", marginBottom: "4px"}}}}>STAGING SPOT</div>
                <div style={{{{fontSize: "1em", fontWeight: 600}}}}>{{pf.boat_trolling.staging_spot}}</div>
                {{pf.boat_trolling.staging_why && <div className="detail" style={{{{color: "var(--text2)"}}}}>{{pf.boat_trolling.staging_why}}</div>}}
              </div>
            )}}

            {{pf.boat_trolling.route && (
              <div style={{{{marginBottom: "10px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--accent)", marginBottom: "4px"}}}}>TROLLING ROUTE</div>
                <div className="detail">{{pf.boat_trolling.route}}</div>
              </div>
            )}}

            {{pf.boat_trolling.target_fish && pf.boat_trolling.target_fish.length > 0 && (
              <div style={{{{marginBottom: "10px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--accent)", marginBottom: "4px"}}}}>TARGET FISH</div>
                <div>
                  {{pf.boat_trolling.target_fish.map((f, i) => (
                    <span key={{i}} className="badge trophy" style={{{{marginRight: "4px", marginBottom: "4px", display: "inline-block"}}}}>{{f}}</span>
                  ))}}
                </div>
              </div>
            )}}

            {{pf.boat_trolling.recommended_lures && pf.boat_trolling.recommended_lures.length > 0 && (
              <div style={{{{marginBottom: "10px"}}}}>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--accent)", marginBottom: "4px"}}}}>RECOMMENDED LURES / RIGS</div>
                {{pf.boat_trolling.recommended_lures.map((l, i) => (
                  <div key={{i}} className="detail">• {{l}}</div>
                ))}}
              </div>
            )}}

            {{pf.boat_trolling.notes && pf.boat_trolling.notes.length > 0 && (
              <div>
                <div style={{{{fontSize: "0.75em", fontWeight: 600, color: "var(--text2)", marginBottom: "4px"}}}}>NOTES</div>
                {{pf.boat_trolling.notes.map((n, i) => (
                  <div key={{i}} className="tip" style={{{{padding: "3px 0"}}}}>{{n}}</div>
                ))}}
              </div>
            )}}
          </div>
        </div>
      )}}
    </div>
  );
}}

function GearTab({{ setLightbox }}) {{
  const a = D.analysis;
  const gear = a.gear || {{}};
  const gb = a.groundbait || {{}};
  const imageKeys = Object.keys(D.loadoutImages).sort();

  // Find gear and groundbait screenshots
  const gearImgKey = gear.screenshot || imageKeys.find(k => k.includes("1704"));
  const gbImgKey = gb.screenshot || imageKeys.find(k => k.includes("1703"));
  const gearImgSrc = gearImgKey && D.loadoutImages[gearImgKey]
    ? "data:image/jpeg;base64," + D.loadoutImages[gearImgKey] : null;
  const gbImgSrc = gbImgKey && D.loadoutImages[gbImgKey]
    ? "data:image/jpeg;base64," + D.loadoutImages[gbImgKey] : null;

  if (!gear.hat && !gb.status) return <div className="panel"><p>No gear data available in this analysis.</p></div>;

  return (
    <div className="panel">
      <div className="section-title">Equipped Gear</div>
      <div className="grid grid-2">
        <div className="card">
          {{gearImgSrc && <img className="slot-img" src={{gearImgSrc}} alt="Gear"
            style={{{{cursor: "pointer"}}}} onClick={{() => setLightbox(gearImgSrc)}} />}}
          <h3>Player Equipment</h3>
          {{gear.hat && <div className="detail"><strong>Hat:</strong> {{gear.hat}}</div>}}
          {{gear.vest && <div className="detail"><strong>Vest:</strong> {{gear.vest}}</div>}}
          {{gear.tackle_box && <div className="detail"><strong>Tackle Box:</strong> {{gear.tackle_box}}</div>}}
          {{gear.rod_case && <div className="detail"><strong>Rod Case:</strong> {{gear.rod_case}}</div>}}
          {{gear.keepnet && <div className="detail"><strong>Keepnet:</strong> {{gear.keepnet}}</div>}}
          {{gear.rod_stand && <div className="detail"><strong>Rod Stand:</strong> {{gear.rod_stand}}</div>}}
        </div>

        <div className="card">
          {{gbImgSrc && <img className="slot-img" src={{gbImgSrc}} alt="Groundbait"
            style={{{{cursor: "pointer"}}}} onClick={{() => setLightbox(gbImgSrc)}} />}}
          <h3>Groundbait Mixing</h3>
          {{gb.status && <div className="detail" style={{{{marginBottom: "8px"}}}}>
            <strong>Status:</strong> {{gb.status}}
          </div>}}
        </div>
      </div>

      {{gear.notes && gear.notes.length > 0 && (
        <div style={{{{marginTop: "20px"}}}}>
          <div className="section-title">Gear Notes</div>
          {{gear.notes.map((note, i) => <div key={{i}} className="tip" style={{{{padding: "6px 0"}}}}>{{note}}</div>)}}
        </div>
      )}}

      {{gb.notes && gb.notes.length > 0 && (
        <div style={{{{marginTop: "20px"}}}}>
          <div className="section-title">Groundbait Tips</div>
          {{gb.notes.map((note, i) => <div key={{i}} className="tip" style={{{{padding: "6px 0"}}}}>{{note}}</div>)}}
        </div>
      )}}

      {{/* Boat section */}}
      {{a.boat && (
        <div style={{{{marginTop: "24px"}}}}>
          <div className="section-title">Boat Fishing</div>
          {{a.boat.location_allows_boats ? (
            <div>
              <div className="grid grid-2">
                {{/* Best purchasable option */}}
                {{a.boat.recommendation && (
                  <div className="card" style={{{{borderLeft: "3px solid var(--accent)"}}}}>
                    <h3 style={{{{color: "var(--accent)"}}}}>{{a.boat.recommendation.best_option}}</h3>
                    <div className="detail"><strong>Level:</strong> {{a.boat.recommendation.level}}</div>
                    <div className="detail"><strong>Price:</strong> <span className="money">{{a.boat.recommendation.price}}</span></div>
                    <div className="detail"><strong>Speed:</strong> {{a.boat.recommendation.speed}}</div>
                    <div className="detail"><strong>Weight:</strong> {{a.boat.recommendation.weight}}</div>
                    <div className="detail" style={{{{marginTop: "8px"}}}}>{{a.boat.recommendation.features}}</div>
                    <div className="tip" style={{{{marginTop: "8px", fontSize: "0.85em"}}}}>{{a.boat.recommendation.why}}</div>
                  </div>
                )}}

                {{/* DLC option */}}
                {{a.boat.dlc_option && (
                  <div className="card" style={{{{borderLeft: "3px solid var(--gold)", opacity: 0.85}}}}>
                    <h3 style={{{{color: "var(--gold)"}}}}>{{a.boat.dlc_option.name}} <span style={{{{fontSize: "0.7em", color: "var(--text2)"}}}}>(DLC)</span></h3>
                    <div className="detail"><strong>Level:</strong> {{a.boat.dlc_option.level}}</div>
                    <div className="detail"><strong>Price:</strong> {{a.boat.dlc_option.price}}</div>
                    <div className="detail"><strong>Power:</strong> {{a.boat.dlc_option.speed}}</div>
                    <div className="detail" style={{{{marginTop: "8px"}}}}>{{a.boat.dlc_option.features}}</div>
                    <div className="tip" style={{{{marginTop: "8px", fontSize: "0.85em"}}}}>{{a.boat.dlc_option.why}}</div>
                  </div>
                )}}
              </div>

              <div style={{{{marginTop: "12px", background: "var(--surface2)", borderRadius: "8px", padding: "12px"}}}}>
                <div className="detail"><strong>License Required:</strong> {{a.boat.license_required}}</div>
                {{a.boat.cost_analysis && <div className="detail" style={{{{marginTop: "6px"}}}}>
                  <strong>Cost Analysis:</strong> {{a.boat.cost_analysis}}
                </div>}}
              </div>

              {{a.boat.fishing_tips && a.boat.fishing_tips.length > 0 && (
                <div style={{{{marginTop: "16px"}}}}>
                  <div style={{{{fontWeight: 600, color: "var(--text)", marginBottom: "8px"}}}}>Boat Fishing Tips</div>
                  {{a.boat.fishing_tips.map((tip, i) => <div key={{i}} className="tip" style={{{{padding: "4px 0"}}}}>{{tip}}</div>)}}
                </div>
              )}}
            </div>
          ) : (
            <div className="card">
              <div className="detail" style={{{{color: "var(--text2)"}}}}>Boat fishing is not available at this location.</div>
            </div>
          )}}
        </div>
      )}}
    </div>
  );
}}

function XPGuideTab() {{
  const a = D.analysis;
  const oa = (a && !a.error && !a.parse_error) ? (a.overall_analysis || {{}}) : {{}};

  // Calculate best money fish
  const moneyFish = [...D.fish].sort((a,b) => (b.price || 0) - (a.price || 0));
  // Calculate best XP fish (heavier = more XP generally, trophies give bonus)
  const xpFish = [...D.fish].sort((a,b) => {{
    const aScore = (a.maxWeight || 0) * (a.types.includes("trophy") ? 1.5 : 1);
    const bScore = (b.maxWeight || 0) * (b.types.includes("trophy") ? 1.5 : 1);
    return bScore - aScore;
  }});

  return (
    <div className="panel">
      <div className="section-title">XP & Income Optimization Guide</div>

      <div className="grid grid-2">
        <div className="card">
          <h3 style={{{{color:"var(--accent)"}}}}> Top XP Fish</h3>
          <p className="detail" style={{{{marginBottom:"12px"}}}}>Heavier fish & trophies give more XP. Unique fish give first-catch bonuses.</p>
          {{xpFish.slice(0,5).map((f,i) => (
            <div key={{i}} className="detail">
              <strong>{{i+1}}. {{f.name}}</strong> — {{(f.maxWeight * 2.205).toFixed(1)}} lb max
              {{f.types.map(t => <span key={{t}} className={{"badge " + t}} style={{{{marginLeft:"4px"}}}}>{{t}}</span>)}}
            </div>
          ))}}
        </div>

        <div className="card">
          <h3 style={{{{color:"var(--accent2)"}}}}> Top Income Fish</h3>
          <p className="detail" style={{{{marginBottom:"12px"}}}}>Sorted by price per lb. Focus on these for maximum silver earnings.</p>
          {{moneyFish.slice(0,5).map((f,i) => (
            <div key={{i}} className="detail">
              <strong>{{i+1}}. {{f.name}}</strong> — <span className="money">${{(f.price / 2.205).toFixed(0)}}/lb</span> (max {{(f.maxWeight * 2.205).toFixed(1)}} lb)
            </div>
          ))}}
        </div>
      </div>

      {{oa.xp_optimization && oa.xp_optimization.length > 0 && (
        <div style={{{{marginTop:"24px"}}}}>
          <div className="section-title">XP Tips (Based on Your Loadout)</div>
          {{oa.xp_optimization.map((tip,i) => <div key={{i}} className="tip">💡 {{tip}}</div>)}}
        </div>
      )}}

      {{oa.income_optimization && oa.income_optimization.length > 0 && (
        <div style={{{{marginTop:"24px"}}}}>
          <div className="section-title">Income Tips (Based on Your Loadout)</div>
          {{oa.income_optimization.map((tip,i) => <div key={{i}} className="tip">💰 {{tip}}</div>)}}
        </div>
      )}}

      <div style={{{{marginTop:"24px"}}}} className="card">
        <h3>General Fishing Planet Tips</h3>
        <div className="tip">• Keep nets/stringers full before selling — bulk sells are more efficient time-wise</div>
        <div className="tip">• Trophy fish give 2-3x XP — always use tackle rated for trophies when possible</div>
        <div className="tip">• Match your hook size to the fish — oversized hooks reduce bite rate</div>
        <div className="tip">• Check bite charts above to fish during peak activity windows</div>
        <div className="tip">• Unique (first-time) catches give large XP bonuses — diversify species</div>
        <div className="tip">• Advanced license unlocks night fishing which often has better trophy rates</div>
        <div className="tip">• Use the cheapest effective bait to maximize profit margins</div>
      </div>
    </div>
  );
}}

function JournalTab() {{
  const entries = D.journal || [];
  const [openEntries, setOpenEntries] = React.useState({{}});
  const toggleEntry = (idx) => setOpenEntries(prev => ({{...prev, [idx]: !prev[idx]}}));

  function parseMarkdownTable(text) {{
    const lines = text.trim().split("\\n").filter(l => l.trim().startsWith("|"));
    if (lines.length < 2) return null;
    const headers = lines[0].split("|").map(h => h.trim()).filter(Boolean);
    const rows = lines.slice(2).map(row =>
      row.split("|").map(c => c.trim()).filter(Boolean)
    );
    return {{ headers, rows }};
  }}

  function parseList(text) {{
    return text.split("\\n")
      .map(l => l.replace(/^[-*\\[\\]x ]+/, "").trim())
      .filter(Boolean);
  }}

  function renderInline(str) {{
    let html = str
      .replace(/\*\*([^*]+)\*\*/g, '<strong style="color:var(--text)">$1</strong>')
      .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.08);padding:2px 6px;border-radius:3px;font-size:0.9em">$1</code>');
    return <span dangerouslySetInnerHTML={{{{__html: html}}}} />;
  }}

  function RenderTable({{ tableData }}) {{
    return (
      <div style={{{{overflowX: "auto", WebkitOverflowScrolling: "touch", marginBottom: "12px"}}}}>
        <table style={{{{width: "100%", minWidth: tableData.headers.length > 4 ? "600px" : "auto", borderCollapse: "collapse", fontSize: "0.9em"}}}}>
          <thead>
            <tr>
              {{tableData.headers.map((h, i) => (
                <th key={{i}} style={{{{textAlign: "left", padding: "8px 12px", borderBottom: "2px solid var(--accent)",
                  color: "var(--accent)", fontWeight: 600}}}}>{{renderInline(h)}}</th>
              ))}}
            </tr>
          </thead>
          <tbody>
            {{tableData.rows.map((row, ri) => (
              <tr key={{ri}} style={{{{borderBottom: "1px solid rgba(255,255,255,0.06)"}}}}>
                {{row.map((cell, ci) => (
                  <td key={{ci}} style={{{{padding: "8px 12px", color: ci === 0 ? "var(--text)" : "var(--text2)"}}}}>
                    {{cell.startsWith("$") || cell.startsWith("-$") || cell.startsWith("~")
                      ? <span className="money">{{cell}}</span>
                      : renderInline(cell)}}
                  </td>
                ))}}
              </tr>
            ))}}
          </tbody>
        </table>
      </div>
    );
  }}

  function RenderList({{ items }}) {{
    return (
      <ul style={{{{margin: 0, paddingLeft: "20px", marginBottom: "12px"}}}}>
        {{items.map((item, i) => (
          <li key={{i}} style={{{{color: "var(--text2)", marginBottom: "6px", lineHeight: 1.5}}}}>{{renderInline(item)}}</li>
        ))}}
      </ul>
    );
  }}

  function parseLoadout(lines) {{
    const rows = [];
    let noteRows = [];

    function categorize(parts) {{
      let reel = "", line = "", hook = "", lure = "", notes = [];
      for (const p of parts) {{
        const t = p.trim();
        if (!t) continue;
        if (!reel && /\d{{3,5}}/.test(t) && !/Fluoro|Braid|Mono|X-Series|Leader|Sinker|Feeder|Hook|Slider|Spoon|Runner|Cutbait|Minnow|Mussel|Jig|Boil|Worm|Finger|Slug|Swimbait|Lure|Float|Rig/i.test(t)) {{
          reel = t;
        }} else if (/Fluoro|Braid|Mono\s*\.|X-Series|Moustache Line/i.test(t) && !/Leader/i.test(t)) {{
          line = line ? line + ", " + t : t;
        }} else if (/Hook\s*#/i.test(t)) {{
          hook = t;
        }} else if (/Leader|Titanium\s*\./i.test(t)) {{
          line = line ? line + ", " + t : t;
        }} else if (/Sinker|Feeder|Slider|Float|Rig\s|Groundbait|Mix Grand/i.test(t)) {{
          notes.push(t);
        }} else if (/Spoon|Runner|Cutbait|Minnow|Mussel|Jig|Slug|Swimbait|Lure|Worm|Boil|Bait|Shrimp|Corn|Crawl|Finger|Golem|Fish Head|Horsehair/i.test(t)) {{
          lure = lure ? lure + ", " + t : t;
        }} else if (/#\d/i.test(t) && !hook) {{
          hook = t;
        }} else {{
          notes.push(t);
        }}
      }}
      return {{ reel, line, hook, lure, notes: notes.join(", ") }};
    }}

    for (const ln of lines) {{
      const trimmed = ln.trim();
      const slotMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
      if (slotMatch) {{
        const rest = slotMatch[2];
        const dashSplit = rest.split(/\s+[-\u2014]\s+/);
        const rodPart = dashSplit[0] || "";
        const setupStr = dashSplit.slice(1).join(" - ") || "";
        const parts = setupStr.split(/,\s*/);
        const cat = categorize(parts);
        rows.push({{ slot: slotMatch[1], rod: rodPart, ...cat }});
      }} else {{
        const cleaned = trimmed.replace(/^[-*\\[\\]x ]+/, "").trim();
        if (cleaned) noteRows.push(cleaned);
      }}
    }}
    return {{ rows, noteRows }};
  }}

  function RenderLoadout({{ lines }}) {{
    const {{ rows, noteRows }} = parseLoadout(lines);
    if (rows.length === 0) return null;
    const thStyle = {{textAlign: "left", padding: "8px 10px", borderBottom: "2px solid var(--accent)",
      color: "var(--accent)", fontWeight: 600, whiteSpace: "nowrap"}};
    const tdStyle = {{padding: "8px 10px", color: "var(--text2)", fontSize: "0.88em"}};
    return (
      <div>
        <div style={{{{overflowX: "auto", WebkitOverflowScrolling: "touch", marginBottom: "12px"}}}}>
          <table style={{{{width: "100%", borderCollapse: "collapse", fontSize: "0.9em"}}}}>
            <thead>
              <tr>
                <th style={{{{...thStyle, textAlign: "center", width: "40px"}}}}>Slot</th>
                <th style={{{{...thStyle}}}}>Rod</th>
                <th style={{{{...thStyle}}}}>Reel</th>
                <th style={{{{...thStyle}}}}>Line / Leader</th>
                <th style={{{{...thStyle}}}}>Hook</th>
                <th style={{{{...thStyle}}}}>Lure / Bait</th>
                <th style={{{{...thStyle}}}}>Notes</th>
              </tr>
            </thead>
            <tbody>
              {{rows.map((r, i) => (
                <tr key={{i}} style={{{{borderBottom: "1px solid rgba(255,255,255,0.06)"}}}}>
                  <td style={{{{...tdStyle, textAlign: "center", color: "var(--accent)", fontWeight: 700}}}}>{{r.slot}}</td>
                  <td style={{{{...tdStyle, color: "var(--text)"}}}}>{{renderInline(r.rod)}}</td>
                  <td style={{{{...tdStyle}}}}>{{renderInline(r.reel)}}</td>
                  <td style={{{{...tdStyle}}}}>{{renderInline(r.line)}}</td>
                  <td style={{{{...tdStyle}}}}>{{renderInline(r.hook)}}</td>
                  <td style={{{{...tdStyle}}}}>{{renderInline(r.lure)}}</td>
                  <td style={{{{...tdStyle, fontSize: "0.85em", opacity: 0.8}}}}>{{renderInline(r.notes)}}</td>
                </tr>
              ))}}
            </tbody>
          </table>
        </div>
        {{noteRows.length > 0 && <RenderList items={{noteRows}} />}}
      </div>
    );
  }}

  function SectionContent({{ text, sectionName }}) {{
    const lines = text.split("\\n");

    if (sectionName && /^Loadout/i.test(sectionName)) {{
      return <RenderLoadout lines={{lines}} />;
    }}

    const blocks = [];
    let currentList = [];
    let currentTable = [];

    function flushList() {{
      if (currentList.length > 0) {{
        blocks.push({{ type: "list", items: [...currentList] }});
        currentList = [];
      }}
    }}
    function flushTable() {{
      if (currentTable.length > 0) {{
        const parsed = parseMarkdownTable(currentTable.join("\\n"));
        if (parsed) blocks.push({{ type: "table", data: parsed }});
        currentTable = [];
      }}
    }}

    lines.forEach(line => {{
      const trimmed = line.trim();
      if (!trimmed) {{ flushList(); flushTable(); return; }}
      const isTableLine = trimmed.startsWith("|") && trimmed.endsWith("|");
      const isSeparator = /^\|[\s:|-]+\|$/.test(trimmed);

      if (isTableLine || isSeparator) {{
        flushList();
        currentTable.push(trimmed);
      }} else {{
        flushTable();
        const cleaned = trimmed.replace(/^[\d]+\.\s+/, "").replace(/^[-*\\[\\]x ]+/, "").trim();
        if (cleaned) currentList.push(cleaned);
      }}
    }});
    flushList();
    flushTable();

    if (blocks.length === 0) return null;
    return (
      <div>
        {{blocks.map((block, i) => (
          block.type === "table"
            ? <RenderTable key={{i}} tableData={{block.data}} />
            : <RenderList key={{i}} items={{block.items}} />
        ))}}
      </div>
    );
  }}

  function SectionTable({{ text, sectionName }}) {{
    return <SectionContent text={{text}} sectionName={{sectionName}} />;
  }}

  function SectionList({{ text, sectionName }}) {{
    return <SectionContent text={{text}} sectionName={{sectionName}} />;
  }}

  const sectionIcons = {{
    "Financials": "💰",
    "XP": "⭐",
    "Baitcoins": "🪙",
    "Loadout Used": "🎣",
    "What Worked": "✅",
    "What Didn't Work": "❌",
    "Fish Caught (Highlights)": "🐟",
    "Sturgeon Intel": "🔍",
    "Missions / Expeditions": "🎯",
    "Takeaways for Next Visit": "📝",
    "Notes": "📌",
    "Loadout (7 Slots)": "🎣",
  }};

  const tableSections = ["Financials", "XP", "Baitcoins", "Fish Caught (Highlights)", "Loadout (7 Slots)",
    "Baitcoins / Economy", "Baitcoins / Premium Bait", "Fish Keeper", "Fish Keeper (End of Session)"];

  const compactSections = ["Financials", "XP", "Baitcoins", "Baitcoins / Economy",
    "Baitcoins / Premium Bait", "Challenges Completed", "DLC / Pack Acquisitions Today"];

  const fullWidthPatterns = ["Loadout", "Fish Caught", "Fish Keeper", "Personal Bests"];
  const isFullWidth = (name) => fullWidthPatterns.some(p => name.startsWith(p));

  // Group entries by base date (strip trailing b/c/d suffixes from filenames like 2026-04-07b)
  const grouped = {{}};
  entries.forEach((entry, ei) => {{
    const baseDate = (entry.date || "").replace(/[a-z]$/, "");
    if (!grouped[baseDate]) grouped[baseDate] = [];
    grouped[baseDate].push({{ ...entry, _idx: ei }});
  }});

  function formatDateHeader(dateStr) {{
    try {{
      const [y, m, d] = dateStr.split("-").map(Number);
      const dt = new Date(y, m - 1, d);
      return dt.toLocaleDateString("en-US", {{ weekday: "long", year: "numeric", month: "long", day: "numeric" }});
    }} catch (e) {{
      return dateStr;
    }}
  }}

  return (
    <div className="panel">
      <div className="section-title">Fishing Journal</div>
      <p className="detail" style={{{{marginBottom: "24px"}}}}>
        Session notes, reflections, and progress tracking for this location.
      </p>

      {{Object.entries(grouped).map(([dateKey, dayEntries]) => (
        <div key={{dateKey}} style={{{{marginBottom: "28px"}}}}>
          <div style={{{{display: "flex", alignItems: "center", gap: "12px", marginBottom: "12px",
            paddingBottom: "8px", borderBottom: "2px solid rgba(0,188,212,0.3)"}}}}>
            <span style={{{{fontSize: "1.1em", color: "var(--accent)", fontWeight: 700}}}}>
              📅 {{formatDateHeader(dateKey)}}
            </span>
            <span style={{{{color: "var(--text2)", fontSize: "0.85em"}}}}>
              {{dayEntries.length}} session{{dayEntries.length > 1 ? "s" : ""}}
            </span>
          </div>

          {{dayEntries.map((entry) => {{
            const ei = entry._idx;
            const isOpen = !!openEntries[ei];
            return (
            <div key={{ei}} style={{{{marginBottom: "12px"}}}}>
              <div onClick={{() => toggleEntry(ei)}} style={{{{display: "flex", alignItems: "center", gap: "16px",
                padding: "12px 20px", background: "linear-gradient(135deg, rgba(0,188,212,0.12), rgba(76,175,80,0.08))",
                borderRadius: isOpen ? "10px 10px 0 0" : "10px", border: "1px solid rgba(0,188,212,0.25)",
                cursor: "pointer", userSelect: "none", transition: "background 0.2s"}}}}>
                <div style={{{{fontSize: "1.4em"}}}}>📓</div>
                <div style={{{{flex: 1}}}}>
                  <div style={{{{fontSize: "1.1em", fontWeight: 700}}}}>
                    {{entry.meta.title || "Session"}}
                  </div>
                  <div style={{{{color: "var(--text2)", fontSize: "0.85em", marginTop: "2px", display: "flex", gap: "16px", flexWrap: "wrap"}}}}>
                    {{entry.meta.level && <span>Level: <strong>{{entry.meta.level}}</strong></span>}}
                    {{entry.generated_at && <span style={{{{opacity: 0.7}}}}>Published: {{entry.generated_at}}</span>}}
                  </div>
                </div>
                <div style={{{{color: "var(--text2)", fontSize: "1.2em", transition: "transform 0.3s",
                  transform: isOpen ? "rotate(180deg)" : "rotate(0deg)"}}}}>▼</div>
              </div>

              {{isOpen && (
              <div style={{{{padding: "16px 0 0", borderLeft: "1px solid rgba(0,188,212,0.15)",
                borderRight: "1px solid rgba(0,188,212,0.15)", borderBottom: "1px solid rgba(0,188,212,0.15)",
                borderRadius: "0 0 10px 10px", paddingLeft: "8px", paddingRight: "8px"}}}}>
                {{/* Compact sections: Financials, XP, Baitcoins — 3 equal columns */}}
                {{(() => {{
                  const compact = Object.entries(entry.sections).filter(([name]) => compactSections.includes(name));
                  return compact.length > 0 && (
                    <div style={{{{display: "grid", gridTemplateColumns: `repeat(${{Math.min(compact.length, 3)}}, 1fr)`, gap: "12px"}}}}>
                      {{compact.map(([name, text], si) => (
                        <div key={{si}} className="card">
                          <h3 style={{{{color: "var(--accent)", marginBottom: "12px"}}}}>
                            {{(sectionIcons[name] || "📋") + " " + name}}
                          </h3>
                          <SectionTable text={{text}} sectionName={{name}} />
                        </div>
                      ))}}
                    </div>
                  );
                }})()}}

                {{/* Full-width sections: Loadout, Fish Keeper */}}
                {{Object.entries(entry.sections).filter(([name]) => isFullWidth(name)).map(([name, text], si) => (
                  <div key={{si}} className="card" style={{{{marginTop: "12px"}}}}>
                    <h3 style={{{{color: "var(--accent)", marginBottom: "12px"}}}}>
                      {{(sectionIcons[name] || "📋") + " " + name}}
                    </h3>
                    {{tableSections.includes(name)
                      ? <SectionTable text={{text}} sectionName={{name}} />
                      : <SectionList text={{text}} sectionName={{name}} />
                    }}
                  </div>
                ))}}

                {{/* Remaining sections: 2 columns (50% each) */}}
                <div style={{{{display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "12px", marginTop: "12px"}}}}>
                  {{Object.entries(entry.sections).filter(([name]) => !compactSections.includes(name) && !isFullWidth(name)).map(([name, text], si) => (
                    <div key={{si}} className="card">
                      <h3 style={{{{color: "var(--accent)", marginBottom: "12px"}}}}>
                        {{(sectionIcons[name] || "📋") + " " + name}}
                      </h3>
                      {{tableSections.includes(name)
                        ? <SectionTable text={{text}} sectionName={{name}} />
                        : <SectionList text={{text}} sectionName={{name}} />
                      }}
                    </div>
                  ))}}
                </div>
              </div>
              )}}
            </div>
            );
          }})}}
        </div>
      ))}}
    </div>
  );
}}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


# ── Directory Management ───────────────────────────────────────────────────────
def setup_directories():
    """Create directory structure and move HEIC files to current_loadout."""
    CURRENT_LOADOUT_DIR.mkdir(exist_ok=True)
    PAST_LOADOUTS_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Move any HEIC files from project root to current_loadout
    moved = 0
    for pattern in ["*.heic", "*.HEIC"]:
        for heic in PROJECT_DIR.glob(pattern):
            dest = CURRENT_LOADOUT_DIR / heic.name
            if not dest.exists():
                shutil.move(str(heic), str(dest))
                moved += 1
                print(f"  Moved {heic.name} -> current_loadout/")
            else:
                print(f"  {heic.name} already in current_loadout/")
    if moved:
        print(f"  Moved {moved} HEIC file(s) to current_loadout/")

    return CURRENT_LOADOUT_DIR


def archive_current_loadout():
    """Move current loadout JPGs to past_loadouts with timestamp."""
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = PAST_LOADOUTS_DIR / timestamp

    jpgs = list(CURRENT_LOADOUT_DIR.glob("*.jpg"))
    heics = list(CURRENT_LOADOUT_DIR.glob("*.heic")) + list(CURRENT_LOADOUT_DIR.glob("*.HEIC"))

    if not jpgs and not heics:
        print("  No loadout files to archive.")
        return

    archive_dir.mkdir(parents=True, exist_ok=True)
    for f in jpgs + heics:
        shutil.move(str(f), str(archive_dir / f.name))
    print(f"  Archived {len(jpgs) + len(heics)} file(s) to past_loadouts/{timestamp}/")


# ── AWS Deploy ─────────────────────────────────────────────────────────────────
AWS_BUCKET = "fp-reports-726138838993"
AWS_DISTRIBUTION_ID = "E3TOOZU85OXSCW"
AWS_DOMAIN = "fpreports.click"
AWS_PROFILE = "fp-deploy"


def deploy_to_aws():
    """Upload all reports to S3 and invalidate CloudFront cache."""
    import datetime

    report_files = sorted(OUTPUT_DIR.glob("fp_report_*.html"))
    if not report_files:
        print("No reports found in reports/ directory. Generate reports first.")
        return

    print(f"\nDeploying {len(report_files)} report(s) to AWS...")
    print(f"  Bucket: {AWS_BUCKET}")
    print(f"  URL: https://{AWS_DOMAIN}")

    # Build index page with report list
    report_entries = []
    for f in report_files:
        # Extract location name and level from report HTML
        name = f.stem.replace("fp_report_", "").replace("-", " ").title()
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
        # Parse level from the embedded JSON data in the report
        level = ""
        try:
            with open(f, "r", encoding="utf-8") as rh:
                content = rh.read()
            import re as _re
            m = _re.search(r'"baseLevel"\s*:\s*(\d+)', content)
            if m:
                level = m.group(1)
        except Exception:
            pass
        report_entries.append({
            "file": f.name,
            "name": name,
            "level": level,
            "date": mtime.strftime("%B %d, %Y at %I:%M %p"),
        })
    # Sort by level
    report_entries.sort(key=lambda r: int(r.get("level", 0) or 0))

    # Update index.html with report list
    index_path = OUTPUT_DIR / "index.html"
    with open(index_path, "r", encoding="utf-8") as fh:
        index_html = fh.read()

    import json as _json
    index_html = index_html.replace(
        "[/*REPORT_LIST*/]",
        _json.dumps(report_entries),
    )

    # Write updated index
    updated_index = OUTPUT_DIR / "_index_deploy.html"
    with open(updated_index, "w", encoding="utf-8") as fh:
        fh.write(index_html)

    # Build inventory page with embedded JSON data
    inventory_src = OUTPUT_DIR / "inventory.html"
    inventory_deploy = None
    if inventory_src.exists():
        inv_json_path = PROJECT_DIR / "player_inventory.json"
        if inv_json_path.exists():
            print("  Building inventory page...")
            inv_html = inventory_src.read_text(encoding="utf-8")
            inv_data = inv_json_path.read_text(encoding="utf-8")
            inv_html = inv_html.replace(
                "/*INVENTORY_DATA*/",
                f"window.__INV_DATA__ = {inv_data};",
            )
            inventory_deploy = OUTPUT_DIR / "_inventory_deploy.html"
            inventory_deploy.write_text(inv_html, encoding="utf-8")

    # Build loadouts page with embedded JSON data
    loadouts_src = OUTPUT_DIR / "loadouts.html"
    loadouts_deploy = None
    if loadouts_src.exists():
        lo_json_path = PROJECT_DIR / "player_loadouts.json"
        if lo_json_path.exists():
            print("  Building loadouts page...")
            lo_html = loadouts_src.read_text(encoding="utf-8")
            lo_data = lo_json_path.read_text(encoding="utf-8")
            lo_html = lo_html.replace(
                "/*LOADOUT_DATA*/",
                f"window.__LOADOUT_DATA__ = {lo_data};",
            )
            loadouts_deploy = OUTPUT_DIR / "_loadouts_deploy.html"
            loadouts_deploy.write_text(lo_html, encoding="utf-8")

    # Upload index
    print(f"  Uploading index.html...")
    result = subprocess.run(
        ["aws", "s3", "cp", str(updated_index), f"s3://{AWS_BUCKET}/index.html",
         "--content-type", "text/html; charset=utf-8", "--cache-control", "max-age=60",
         "--profile", AWS_PROFILE],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr}")
        return
    updated_index.unlink()

    # Upload inventory page
    if inventory_deploy and inventory_deploy.exists():
        print("  Uploading inventory.html...")
        result = subprocess.run(
            ["aws", "s3", "cp", str(inventory_deploy), f"s3://{AWS_BUCKET}/inventory.html",
             "--content-type", "text/html; charset=utf-8", "--cache-control", "max-age=300",
             "--profile", AWS_PROFILE],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR uploading inventory: {result.stderr}")
        inventory_deploy.unlink()

    # Upload standalone strategy/guide pages
    for guide_name in ["telescopic-strategy.html", "hook-reference.html"]:
        guide_path = OUTPUT_DIR / guide_name
        if guide_path.exists():
            print(f"  Uploading {guide_name}...")
            result = subprocess.run(
                ["aws", "s3", "cp", str(guide_path), f"s3://{AWS_BUCKET}/{guide_name}",
                 "--content-type", "text/html; charset=utf-8", "--cache-control", "max-age=300",
                 "--profile", AWS_PROFILE],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"  ERROR uploading {guide_name}: {result.stderr}")

    # Upload loadouts page
    if loadouts_deploy and loadouts_deploy.exists():
        print("  Uploading loadouts.html...")
        result = subprocess.run(
            ["aws", "s3", "cp", str(loadouts_deploy), f"s3://{AWS_BUCKET}/loadouts.html",
             "--content-type", "text/html; charset=utf-8", "--cache-control", "max-age=300",
             "--profile", AWS_PROFILE],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR uploading loadouts: {result.stderr}")
        loadouts_deploy.unlink()

    # Upload each report
    for f in report_files:
        print(f"  Uploading {f.name}...")
        result = subprocess.run(
            ["aws", "s3", "cp", str(f), f"s3://{AWS_BUCKET}/{f.name}",
             "--content-type", "text/html; charset=utf-8", "--cache-control", "max-age=300",
             "--profile", AWS_PROFILE],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR uploading {f.name}: {result.stderr}")

    # Invalidate CloudFront cache
    print("  Invalidating CloudFront cache...")
    result = subprocess.run(
        ["aws", "cloudfront", "create-invalidation",
         "--distribution-id", AWS_DISTRIBUTION_ID,
         "--paths", "/*",
         "--profile", AWS_PROFILE],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  WARNING: Cache invalidation failed: {result.stderr}")
    else:
        print("  Cache invalidated.")

    print(f"\n  Reports live at: https://{AWS_DOMAIN}")
    print(f"  Direct links:")
    for r in report_entries:
        print(f"    https://{AWS_DOMAIN}/{r['file']}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Fishing Planet Loadout Analyzer — scrapes fp-collective.com "
                    "and analyzes your loadout screenshots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all available locations
  python fp_analyzer.py --list-locations

  # Analyze loadout for Lone Star Lake
  python fp_analyzer.py --location lone-star-lake

  # Analyze without vision (just location data)
  python fp_analyzer.py --location lone-star-lake --no-vision

  # Archive current loadout before adding new screenshots
  python fp_analyzer.py --archive
        """,
    )
    parser.add_argument("--location", "-l", help="Location slug (e.g., lone-star-lake)")
    parser.add_argument("--list-locations", action="store_true", help="List all available locations")
    parser.add_argument("--no-vision", action="store_true", help="Skip screenshot analysis")
    parser.add_argument("--archive", action="store_true", help="Archive current loadout to past_loadouts")
    parser.add_argument("--analysis-file", help="Path to a pre-built analysis JSON file (skips vision API)")
    parser.add_argument("--output", "-o", help="Output HTML filename (default: auto-generated)")
    parser.add_argument("--deploy", action="store_true", help="Upload all reports to AWS S3/CloudFront")

    args = parser.parse_args()
    api = FPCollectiveAPI()

    if args.list_locations:
        print("\nFetching locations from fp-collective.com...\n")
        locations = api.get_locations()
        locations.sort(key=lambda x: x.get("baseLevel", 0))
        print(f"{'Slug':<35} {'Name':<30} {'Level':<8} {'Type':<10} {'Continent'}")
        print("-" * 100)
        for loc in locations:
            print(f"{loc['slug']:<35} {loc['title']:<30} {loc.get('baseLevel','?'):<8} "
                  f"{loc.get('type','?'):<10} {loc.get('continent','?')}")
        return

    if args.archive:
        setup_directories()
        archive_current_loadout()
        return

    if args.deploy:
        deploy_to_aws()
        return

    if not args.location:
        parser.print_help()
        print("\n\nERROR: --location is required (or use --list-locations to see options)")
        sys.exit(1)

    # 1. Setup directories
    print("\n[1/5] Setting up directories...")
    loadout_dir = setup_directories()

    # 2. Convert HEIC to JPG
    print("\n[2/5] Converting HEIC screenshots to JPG...")
    jpg_files = convert_heic_to_jpg(CURRENT_LOADOUT_DIR, CURRENT_LOADOUT_DIR)
    # Also pick up any existing JPGs
    all_jpgs = sorted(CURRENT_LOADOUT_DIR.glob("*.jpg"))
    if all_jpgs:
        print(f"  Found {len(all_jpgs)} JPG file(s) ready for analysis.")
    else:
        print("  No loadout screenshots found in current_loadout/")

    # 3. Fetch location data
    print(f"\n[3/5] Fetching data for '{args.location}' from fp-collective.com...")
    try:
        location_data = fetch_location_data(api, args.location)
    except requests.HTTPError as e:
        print(f"  ERROR: Could not fetch location '{args.location}': {e}")
        print("  Use --list-locations to see available locations.")
        sys.exit(1)

    # 4. Analyze screenshots
    print("\n[4/5] Analyzing loadout screenshots...")
    if args.analysis_file:
        print(f"  Loading pre-built analysis from {args.analysis_file}...")
        with open(args.analysis_file, "r") as f:
            analysis = json.load(f)
    elif args.no_vision or not all_jpgs:
        if not all_jpgs:
            print("  No screenshots to analyze.")
        analysis = {"error": "Vision analysis skipped." if args.no_vision
                    else "No loadout screenshots found in current_loadout/. Add .heic or .jpg files and re-run."}
    else:
        analysis = analyze_loadout_screenshots(list(all_jpgs), location_data)

    # 5. Fetch wiki equipment images
    print("\n[5/6] Fetching equipment images from wiki.fishingplanet.com...")
    wiki_images = {}
    if not args.no_vision or args.analysis_file:
        try:
            wiki = WikiScraper()
            wiki.build_equipment_index(categories=["baits", "lures", "hooks", "floats"])
            wiki_images = wiki.get_recommended_loadout_images(analysis)

            # Also resolve images for all baits used by fish at this location
            extra_names = {}
            for fish in location_data["location"].get("fish", []):
                for bait in fish.get("baits", []):
                    bname = bait["title"]
                    if bname not in wiki_images:
                        fn = bname.replace(" ", "_") + ".png"
                        extra_names[bname] = fn
            if extra_names:
                url_map = wiki.resolve_image_urls(list(extra_names.values()))
                for name, fn in extra_names.items():
                    url = url_map.get(fn)
                    if url:
                        wiki_images[name] = url

            print(f"  Found {len(wiki_images)} equipment images.")
        except Exception as e:
            print(f"  WARNING: Wiki scraping failed: {e}")
    else:
        print("  Skipped (no analysis to reference).")

    # 6. Generate report
    print("\n[6/6] Generating interactive HTML report...")
    slug = args.location
    output_name = args.output or f"fp_report_{slug}.html"
    output_path = OUTPUT_DIR / output_name
    result = generate_react_html(location_data, analysis, list(all_jpgs), output_path, wiki_images)
    print(f"\n  Report saved to: {result}")
    # Cross-platform file URL
    import platform as _platform
    if _platform.system() == "Windows":
        print(f"  Open in browser: file:///{str(result).replace(os.sep, '/')}")
    else:
        print(f"  Open in browser: file://{result}")


if __name__ == "__main__":
    main()
