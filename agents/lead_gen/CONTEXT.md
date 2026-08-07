# MK7 Lead-Gen Agent — Context

Built for Marykate to source high-quality MK7 outreach leads across Beirut (priority), GCC (Dubai, Riyadh, Kuwait City, Doha), and Yerevan, Armenia.

## Purpose

Produce a clean, manually-outreach-ready spreadsheet of legitimate businesses that:
- Are active (recent IG presence, recent reviews)
- Fall into MK7's ideal-client verticals: e-commerce, restaurants/cafés, real estate, service businesses (medspas, salons, clinics)
- Have a real reason to need MK7 services: Meta ads, websites/ecom, content/Reels, social management, AI agents/automation, WhatsApp + lead nurture
- Can actually be contacted (WhatsApp number + Instagram handle both verified)

## MK7 services (informs lead-fit)

From mk7media.com homepage (extracted from local templates/index.html):
1. Meta Advertising (FB/IG ads)
2. Websites + E-Commerce
3. Content + Reels
4. Social Media Management
5. AI Agents + Automation
6. Lead Nurture + WhatsApp

## Sourcing strategy (not random)

A "good lead" is a business where MK7's services solve a visible gap AND there's evidence they'll pay. Filtering tiers used:

**Tier 1 — Intent signals:**
- Already runs Meta ads (Meta Ad Library verifiable)
- Just opened in 2025–2026 or expanding (fresh budget, actively looking)
- Pre-vetted by editorial lists (Lebanon Traveler, Beirut.com "What's New," Time Out Doha, FACT KSA, Grazia ME, Wanderlog)

**Tier 2 — Gap signals (the pitch hook):**
- High follower count with static-only feed = Reels pitch
- Active IG, weak/no website = website + funnel pitch
- Manually handling WhatsApp orders = WhatsApp + AI agent pitch
- Slow DM responses = lead nurture automation pitch

**Tier 3 — Disqualifiers (skipped):**
- Megabrands with in-house teams or known agency (Aïshti, Namshi, Ounass, Bloomingdale's, Hanayen mall chain, Cartier, Chanel, Versace, BVLGARI, etc.)
- Aggregator/directory IG accounts (e.g. "Beirut Food Official," "New In Doha") — not businesses
- Defunct or inactive (last IG post >90 days)

**Channels used (in priority order):**
1. Editorial "best of 2026" and "what's new" lists per city
2. Cross-referenced IG handles for activity / follower count
3. Website fetches to verify WhatsApp + phone
4. Filtered out megabrands and aggregator accounts

## Verification rules (strict)

Every row in the deliverable must have **both**:
- A real `@instagram_handle` (no "search for handle" stubs)
- A real phone number (which equals WhatsApp in Beirut / GCC / Armenia)

If both can't be confirmed from public sources, the lead is dropped.

## CSV schema

`leads_v1.csv` (snapshot stored in this folder; live working copy at `~/mk7-leads-beirut-gcc-armenia.csv`):

| Column | Purpose |
|---|---|
| region | Country |
| city | City |
| category | E-commerce / Restaurant / Service / Real Estate |
| business_name | Display name |
| instagram | Verified @handle |
| website | URL if exists |
| whatsapp | Verified phone (= WhatsApp) |
| email | If published |
| address | Street + neighborhood |
| notes | Factual context only (follower count, founding year, location color). NO pitch language. |

**Intentionally not included** (and why):
- `outreach_angle` — Marykate doesn't want AI-written DMs signed with her name. Outreach copy gets layered into v2 only after she sends real reply data so it's grounded in what's actually working.
- `priority` — Kendall didn't want priority tiers on the operator-facing list.
- `needs_signal`, `why_legit`, `ig_size` — too much noise for manual outreach.

See also: `~/.claude/projects/-Users-kendalldavis/memory/feedback_lead_list_iteration.md`

## Current state — v1 (2026-05-14)

**81 fully verified leads** across 6 regions:

| Region | Count | Categories |
|---|---|---|
| Lebanon (Beirut) | 45 | 21 restaurants, 14 e-com, 5 service, 5 real estate |
| Qatar (Doha) | 11 | 6 restaurants, 3 e-com, 1 service, 1 real estate |
| Armenia (Yerevan) | 8 | 6 e-com, 1 restaurant, 1 service |
| Kuwait (Kuwait City) | 7 | 6 e-com, 1 restaurant |
| UAE (Dubai) | 5 | 5 e-com |
| Saudi Arabia (Riyadh) | 5 | 3 restaurants, 1 e-com, 1 service |

## Known gaps / next sweep targets

To get to the 10x volume Kendall asked for (~400 leads), do a v2 sweep focused on:

1. **Local business directories** — indexoflebanon.com, doha.directory, kuwait yellowpages, propertyfinder.qa, byootna.com (Lebanon). High volume of phones + business names; cross-look IG.
2. **Riyadh restaurants** — most new openings publish IG but not phone in any indexable source. Pull SevenRooms reservation phones individually.
3. **Pure-IG Kuwaiti boutiques** — phone is usually in the IG bio (not the website). Manually paginate the StarNgage Kuwait clothing-store ranking.
4. **Beirut hair salons, dental, fitness** — only one or two of each in v1; Lebanon has dozens. Pull from the961 listicles and Beirut.com directory.
5. **Doha restaurants beyond the new-openings list** — Time Out Doha was blocked (403). Use Tripadvisor + visitqatar.com + iloveqatar.net instead.
6. **Yerevan service businesses** — armeniayp.com has 28 verified beauty salons.

## v2 workflow (when Marykate sends replies back)

1. Get reply data from Marykate: which leads replied, which DMs landed, what objections came up.
2. Cluster the wins by pattern (e.g., "new restaurants reply at 3x the rate" or "WhatsApp-mention opening line works").
3. Add `outreach_angle` column to v2 with copy derived from real-reply patterns. Apply copywriting standard: direct, human, no em dashes, no AI voice, no audience filters.
4. Continue verifying new candidates against the same strict IG + phone rule.

## File locations

- **Live working CSV:** `~/mk7-leads-beirut-gcc-armenia.csv`
- **Snapshot for this agent:** `~/mk7media/agents/lead_gen/leads_v1.csv`
- **This context doc:** `~/mk7media/agents/lead_gen/CONTEXT.md`
