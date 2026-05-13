# Lumen Lebanon Agent - Website Leads  (profile: `lumen_lebanon_website_leads`)

This profile runs as **Layla** — a sales-qualification agent for Lumen
Marketing, talking to Lebanese business owners who tap a WhatsApp link from a
Lumen ad on Meta. She qualifies in 2-3 short exchanges (business, problem,
website/ads status), books a discovery call inside her allowed windows, and
hands off to the human team. Distinct from `mk7_agent_v1_00`, which was an MK7
Media agent that just happened to run on the same Lumen-portfolio number.

## How it's wired
- Live on the same WABA as everything else: **+1 623 512 6504**
  (Phone Number ID `1082296231636502`, WABA `1457517218983357`).
- Selected as the live profile via
  `ACTIVE_PROFILE = "lumen_lebanon_website_leads"` in
  `agents/whatsapp_agent/__init__.py`.
- Uses the same routes (`/webhooks/whatsapp`, `/admin/whatsapp`, etc.) and the
  same env vars on the `mk7media` Railway service as MK7 V1.00 — see
  [`../mk7_agent_v1_00/README.md`](../mk7_agent_v1_00/README.md) for the full
  env-var list. Model: `claude-opus-4-7`. Default outreach template:
  `lumen_inbound_followup` / `en`. To give this profile its own SQLite DB so it
  doesn't share conversation history with the other profile, set
  `WHATSAPP_DB_PATH` to a different file before this profile is selected.

## Behaviour
The persona, qualification flow, pricing, booking windows, and handoff rules
all live in the `SYSTEM_PROMPT` constant at the top of `agent.py`. Edit it to
retune Layla. Key behaviours baked in by the prompt + code together:

- **Voice/tone** — Lebanese-direct, short, no American filler, no emojis
  unless the lead uses one first. Max 2-3 short lines per reply.
- **Qualification** — at most 3 exchanges before asking for the call; covers
  business, real problem, current website/ads status.
- **Pricing** — websites from $750, Meta ads from $600/mo (said directly if
  asked); anything project-specific punts to "easier to give you a real
  number on a quick call."
- **Booking windows** — primary: 6-11pm Beirut, Mon-Fri (= 9am-2pm MST).
  Secondary: 9-11am Beirut (= 12-2am MST). Outside both → handoff with
  `[[NEEDS_CUSTOM_TIME: ...]]`.
- **Reply timing** — random 5-15s for Layla's first reply in a conversation,
  10-25s for subsequent replies, implemented in `_reply_async`. (Spec called
  this "system-level, not in prompt." The 10-25s subsequent range is dialled
  back from the original 15-45s — felt too slow in live testing.)
- **Inbound filter** — reactions, system, ephemeral, unsupported are logged
  but not replied to (same as V1.00).
- **Non-text media** — Layla has no multimodal hookup yet. Voice messages get
  "Can't listen to voice messages here, can you type it?"; docs/images get
  "Can you type the key info? Easier to move from there." (Image vision is on
  the roadmap, see below.)

## Handoff tags and structured summaries
Layla ends replies with one or more `[[TAG: payload]]` tokens when a human
should pick up. `_reply_async` parses these out of her raw reply (helpers:
`_parse_handoff_tags`, `_parse_summary_block`, `_strip_meta_tokens`):

| Tag | Meaning |
|---|---|
| `[[HANDOFF]]` | Always present on any handoff. |
| `[[BOOKED: day, time Beirut, business, brief]]` | Call agreed; details in the trailing `---SUMMARY---` block. |
| `[[NEEDS_TRANSLATION]]` | Booked, but lead needs Arabic on the call. Always paired with `[[BOOKED: ...]]`. Bring a translator. |
| `[[ARABIC_SCRIPT]]` | Lead wrote in non-Latin Arabic — human decides. |
| `[[NEEDS_CUSTOM_TIME: window]]` | Time outside both booking windows. |
| `[[CUSTOM_PRICING]]` | Pricing question outside the $750 / $600/mo starting ranges. |
| `[[OUT_OF_SCOPE: what]]` | Service Lumen doesn't offer. |
| `[[HOSTILE]]` | Lead hostile/threatening; Layla replies once and stops. |
| `[[REQUESTED_HUMAN]]` | Lead explicitly asked for a person. |
| `[[UNKNOWN_QUESTION: what]]` | Layla doesn't know — flag for KB update. |

On a booking, Layla also emits a `---SUMMARY---\n key: value\n ---END---`
block at the end. That gets stripped from the WhatsApp reply and rendered as a
table at the top of the handoff email.

The handoff email subject is `New Lumen handoff — REASON — Business` (e.g.
`New Lumen handoff — BOOKED — Ecommerce, handmade leather bags, Lebanon`).

## Switching back to the MK7 agent
Change `ACTIVE_PROFILE` in `agents/whatsapp_agent/__init__.py` back to
`"mk7_agent_v1_00"`, commit, push. Nothing else moves.

## Not yet built (Layla spec roadmap)
The prompt instructs Layla to behave correctly on all of these; they hand off
or fall back gracefully today, but the supporting infrastructure isn't wired
yet:

- **Google Calendar booking** — currently a `[[BOOKED: ...]]` handoff puts the
  email + WhatsApp ping in the team's inbox so someone confirms the slot
  manually. The full OAuth + freebusy + events.insert flow (Section 6 of the
  spec) is a separate build.
- **4-6h soft follow-up on silent leads** — the prompt covers what Layla should
  say; there's no scheduler in this app to actually trigger it yet.
- **Image vision** — the Anthropic call doesn't pass image content through, so
  Layla can't actually "see" inbound images today. Right now they get the
  same brand-correct fallback as voice/docs.
- **Self-improvement logging enrichments** — `wa_messages` captures the full
  history; adding conversion-outcome / unknown-question flags as separate
  columns is a small follow-up.
