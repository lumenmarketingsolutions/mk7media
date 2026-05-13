# Lumen Lebanon Agent - Website Leads  (profile: `lumen_lebanon_website_leads`)

A full-on Lumen agent — distinct from `mk7_agent_v1_00`, which was an MK7 Media
agent that just happened to run on a Lumen-portfolio number.

This profile started as a **verbatim copy** of `mk7_agent_v1_00`. Edits to its
behaviour (persona, qualifying questions, what counts as a handoff, model,
default template, etc.) happen in *this folder's* `agent.py` — the `mk7` folder
is preserved untouched.

## How it's wired
- Live on the same WABA as everything else: **+1 623 512 6504**
  (Phone Number ID `1082296231636502`, WABA `1457517218983357`).
- Selected as the live profile via `ACTIVE_PROFILE = "lumen_lebanon_website_leads"`
  in `agents/whatsapp_agent/__init__.py`.
- Uses the same routes (`/webhooks/whatsapp`, `/admin/whatsapp`, etc.) and the
  same env vars on the `mk7media` Railway service — see
  [`../mk7_agent_v1_00/README.md`](../mk7_agent_v1_00/README.md) for the full
  list. To give this profile its own SQLite DB (so it doesn't share conversation
  history with the other profile) set `WHATSAPP_DB_PATH` to a different file
  before this profile is selected.

## Where to make changes
Everything specific to this agent lives in `agent.py` in this folder. Most
edits will be in `SYSTEM_PROMPT` near the top. Other knobs:
- `DEFAULT_TEMPLATE` / `DEFAULT_TEMPLATE_LANG` — the approved Meta template the
  agent kicks outreach off with (default `lumen_inbound_followup` / `en`).
- `WHATSAPP_AGENT_MODEL` env var — the Claude model id.
- `_handle_inbound_message` / `generate_reply` — message filtering and reply
  generation. Override at the function level for behaviour that differs from
  the MK7 baseline.

## Switching back to the MK7 agent
Change `ACTIVE_PROFILE` in `agents/whatsapp_agent/__init__.py` back to
`"mk7_agent_v1_00"`, commit, push. Nothing else moves.
