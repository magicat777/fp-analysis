---
name: Club-series gear economy + FP currency model
description: FP has three currencies — Credits (free, abundant), Baitcoins (premium, real-money $2.99-$29.99 packs ~$0.05/BC), and Club Tokens (earned ONLY via club activity, NO direct real-money purchase). Club Tokens are the actual scarcity bottleneck. Club-series spoons/spinners 35-52 tokens/5x pack; heavy club-series reels 5050-7703 tokens. Reserve Club Token spending for missions/competitions/monster zones — rocky locations like Kaniq with mismatched line burn tokens to snags.
metadata:
  type: feedback
---

**Rule:** Treat **Club Tokens** as the truly finite, un-purchasable currency in FP. Only deploy Club-Series gear on high-value events (missions, challenges, competitions, marked unique zones) — NOT on general discovery or volume fishing.

---

## The three FP currencies (sourced from wiki + community + user observation)

### 1. Credits
- **Earned by:** Selling caught fish at end of session, tournament/competition rewards, missions, 5-day login bonus (300-1500 credits over 5 days)
- **Spent on:** Travel, bait, tackle, equipment, licenses — almost all routine purchases
- **Real-money purchase:** No (but can be obtained indirectly by converting Baitcoins)
- **Conversion:** 1 Baitcoin = 100 Credits (one-way only — credits cannot be converted back)
- **Abundance:** This is the ABUNDANT currency. User balance 2026-05-28 = **24,394,969 credits**

### 2. Baitcoins
- **Earned by:** Achievements + missions (small amounts), tournament/competition rewards, **Day-5 consecutive-login bonus (1 BC)**, real-money purchase
- **Spent on:** Exclusive premium tackle, baits, equipment (the "P" suffix items in the shop)
- **Real-money purchase:** YES — official tiered pricing (user-verified 2026-05-28):

  | Pack | USD | $/BC |
  |---|---|---|
  | 50 BC | $2.99 | $0.060 |
  | 100 BC | $5.99 | $0.060 |
  | 300 BC | $14.99 | $0.050 |
  | 600 BC | $29.99 | $0.050 |
  | (wiki lists larger packs: 1090, 2330 — not user-verified) | | |

- **Effective rate:** ~$0.05-0.06 per BC (cheaper at 300+ packs)
- **Abundance:** Moderate. User balance 2026-05-28 = **419 BC** (≈ $21-25 USD retail)

### 3. Club Tokens / "Club Points" (the scarce currency — system not fully implemented yet)
**IMPORTANT — current state vs. planned state (user observation 2026-05-28):**

The community/wiki sources describe a Club Leagues + CLUB-mode fishing earning model. **That system is still "coming soon" — NOT active in the current FP build.** What the wiki/community describes is the PLANNED implementation; what actually works today is much narrower.

- **Currently active earning methods (the only real paths):**
  - **"Club daily" mission** — rewards a small number of Club Points each day. **NOT actually club-social** despite the name — you don't need clubmates, group, or any club room mode to complete it. It's just a solo daily that happens to pay in Club Points.
  - **Club Enthusiast Pack DLC** — one-time ~1500 Club Points bonus (user recollection; not independently verified)
  - **Top-3 competition finishes** — reward Club-Series LURE DROPS directly (not Club Points). This is the fast track for the actual large spoons.

- **NOT currently active (planned/coming-soon):**
  - Club Leagues (7-day league finishes paying tokens) — wiki describes this but it's not live
  - "Fishing Together" group sessions at yacht locations (user expected this would reward Club Points; observed it does NOT currently)
  - CLUB-room-mode fishing as a points multiplier — not active

- **Spent on:** Club-Series gear (lures + rods + reels) in the Club Store
- **Real-money purchase:** NO direct path. Only the one-time Club Enthusiast Pack DLC bundles any injection.
- **Abundance:** EXTREMELY SCARCE. User balance 2026-05-28 = **447** (described as "club points" in user's UI/parlance)
- **Terminology:** User says **"Club Points"** or **"club coins"** or **"club dollars"** interchangeably. The official wiki uses "Club Tokens." All refer to the same spendable currency (the light blue/grey icon). When future-me sees "Club Points" or "Club Tokens" in either documentation or chat, they're the same thing. There MAY be a separate competitive-score "Club Points" system in the wiki (penalty for oversized tackle on small fish), but the user has not observed it as a separate UI element — likely also coming-soon, or it's the same number used two ways.

---

## Icon identification (in-game UI vs wiki)

Wiki description for Credits says "Gold-colored coin" and Baitcoins "Teal/blue-colored coin" — this **contradicts** the user's in-game observation (2026-05-28):
- Gold round coins = Baitcoins (user)
- Silver bill stacks = Credits (user)
- Light blue/grey rounded = Club Tokens (user)

**Trust the user's in-game observation** — the 419 (gold) balance fits Baitcoins (premium, ~$25 worth) while 24M (silver) fits the abundant Credits currency. Wiki icon descriptions are likely outdated.

---

## Verified Club-Series shop pricing (2026-05-28 shop snapshot)

### Spoons & Spinners (the Kaniq/salmon tier — Club Tokens)
| Item | Pack | Club Tokens |
|---|---|---|
| Glow&Holo Medium Spoon 1 Oz #4/0 (night) | x5 | 35 |
| Casting Spoon 3/4 Oz #3/0 | x5 | 37 |
| Barbless Nano Spoon 1/5 Oz #1/0 | x5 | 42 |
| Barbless Medium Spoon 1/2 Oz #3/0 | x5 | 45 |
| Barbless Spinner 1/2 Oz #3/0 | x5 | 45 |
| Glow&Holo Casting Spoon 1 Oz #4/0 (night) | x5 | 46 |
| **Medium Spoon 2 Oz #6/0** | x5 | **47** |
| Barbless Nano Spinner 1/5 Oz #1/0 | x5 | 47 |
| Single Spoon 1 1/2 Oz #4/0 | x5 | 52 |
| Spinner 1/2 Oz #3/0 | x5 | 52 |

Larger Flat Spoons (e.g., the **Flat Spoon 1 1/2 Oz #6/0** = Kaniq Loki+Black Needle MVP) sit deeper in the page list — pricing TBD on next inventory pass, expected ~35-60 Club Tokens / 5x.

### Soft Plastics (Club Tokens)
| Item | Pack | Club Tokens |
|---|---|---|
| Club-Series Shad 4" | x10 | 25 |
| Club-Series Grub 3" | x10 | 25 |
| Club-Series Worm 6" | x10 | 27 |
| Club-Series Glow Shad 6" (night) | x5 | 33 |
| Club-Series Craw 6" | x5 | 35 |
| Club-Series Twin Tail Spider Grub 2.7" | x10 | 37 |

### Hard Lures (currency UNVERIFIED — flagged for next shop pass)
Frog/Walker/Triple Runner/Mini Crank/Glow&Holo Crankbait/Jerkbait/Frog-popper/Hunched Runner/Topper/Major Popper = 300-433 each. My earlier read identified these as Credits, but the icon was not verified against the user's icon-identification scheme. **Treat as scarcity-bucket until re-verified.**

### Reels — Club-Series spinning (Club Tokens, 10000-13000 class)
| Item | Max Drag | Club Tokens |
|---|---|---|
| Club-Series Carpzilla 10000 | 57.7 Lb | 5,050 |
| Club-Series HeroThrust 10000 | — | 6,607 |
| Club-Series FireStorm 13000 | — | 6,991 |
| Club-Series QuantumSpeed 10000 | — | 7,703 |

### Reels — Club-Series casting (Club Tokens)
| Item | Club Tokens |
|---|---|
| Club-Series TurboTwist 8000 | 5,890 |

### Reels — Premium "P" tier (Baitcoins, real-money-accessible)
| Item | Baitcoins | USD equivalent (@ $0.05/BC) |
|---|---|---|
| LowDex 1500 P SE | 37 | ~$2.21 |
| LowDex 1500 P | 3,700 | ~$185 |
| Attorney 2000 P | 5,800 | ~$290 |
| LowDexMG 1000 P | 7,500 | ~$375 |

---

## Strategic implications

1. **Club Points are the actual bottleneck**, and the bottleneck is WORSE than the wiki implies because Club Leagues isn't live. Only the daily "club daily" mission + competition lure drops are functional earning paths right now. Baitcoins are paywalled but bulk-buyable for reasonable sums.

2. **The user's 447-Point balance** buys ~9-12 spoon packs OR <10% of one heavy reel. Don't recommend single-purchases that wipe the balance. With only the daily-mission earn path, recovery to current balance is **weeks-to-months of dailies**.

3. **Premium "P" reels are realistically purchasable** — $185-375 for a top-tier reel is real-money but accessible, not luxury-only. If user wants to step past the Black Needle for the 80-90 lb Kaniq monster class, a baitcoin-tier reel is a viable real-money upgrade path.

4. **Top-3 competition finishes = the ONLY practical path to large Club-Series spoons** (lure drops, not points). With Club Leagues coming-soon and "Fishing Together" not yet rewarding points, competition is functionally the sole acquisition route for the apex-class gear. Per [[feedback_xclass_competition_progression]].

5. **Watch for when Club Leagues goes live** — the earning rate will jump materially when 7-day league finishes start paying points. Strategy and recommendations should be revisited at that point.

5. **Kaniq rock-snag incident pattern (2026-05-28):**
   - User has lost **4-6 Club-Series lures** total at Kaniq across sessions
   - Last night: **2 lures in one session on the Loki** (one to a monster salmon snapping 20 Lb mono, one to a rock snag)
   - Pattern: **rocky bottom + 20 Lb mono + big fish or aggressive snag-clearing = high lure-loss rate**

---

## Snag-resistance ranking (Kaniq context, user observation)
- **Club-Series Flat Spoon** = least snag-prone, bounces off bottom — IDEAL for rocky bottom
- Other club-series spoons = more snag-prone
- Bullet spinners / spinnertails = mid-range
- Soft plastics / jigs = highest snag rate on rocky bottom

## Risk-management rules for Club Token items
1. **Use them on high-value targets only:** mission completions, challenge progression, monster-unique markers, competitions
2. **AVOID using on:** general discovery, volume/income farming, exploratory casting in unknown terrain
3. **Match the line class to the lure value:** a ~50-Token Flat Spoon on 20 Lb mono in rocky water = snap-loss risk; step up to fluoro that lets you horse the lure free of snags
4. **Snag-clearing technique:** Steady pressure, walk the angle. Don't jerk hard + release tension — that's the snap sequence.
5. **Flat Spoons over other spoons** in any rocky-bottom location
6. **Currency identification matters:** always verify the icon (gold = Baitcoin, silver bills = Credits, light blue/grey = Club Token) before assuming a price is "expensive" or "scarce."

---

## Cross-references
- [[feedback_xclass_competition_progression]] — X-class large spoons are above Club-Series, unlocked via top-3 finishes
- [[feedback_kaniq_monster_unique_tackle]] — Kaniq specifically combines rock snag + monster-unique class = fastest token-bleed location
- [[feedback_marker_pattern_recognition]] — pre-rigging at marked monster zones is the high-value event Club-Series gear is for
- [[feedback_undersized_rod_reel_wear]] — line/leader weight mismatch is a self-inflicted cost
- [[feedback_repair_cost_percentage]] — sibling concept; brute-force fights eat reel durability the way rock snags + 20 Lb mono eat Club-Series lures
