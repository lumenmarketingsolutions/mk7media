# agents/

Self-contained agents that run inside this app. Each agent gets its own folder.
`agents/<name>/__init__.py` re-exports the live agent on a stable path
(`from agents.<name> import agent`) so the rest of the app doesn't care which
underlying implementation is wired up.

- **`whatsapp_agent/`** — Claude-powered WhatsApp Cloud API agent for the
  +1 623 512 6504 number. It runs **one of several agent _profiles_** at a time;
  each profile under `whatsapp_agent/profiles/<name>/` is a fully independent
  copy of the agent (own persona/prompt, model, templates, behaviour). Which one
  is live is decided by the single `ACTIVE_PROFILE` constant in
  `whatsapp_agent/__init__.py` — changing that string + pushing is the entire
  switch. Current profiles:
  - `mk7_agent_v1_00` — "MK7 Agent V1.00", the original agent we built and
    shipped. **Preserved; don't edit.**
  - `lumen_lebanon_website_leads` — "Lumen Lebanon Agent - Website Leads", a
    full-on Lumen agent (started as a copy of V1.00). **Currently live.**
  See `whatsapp_agent/profiles/<name>/README.md` for each.

The HTTP routes for an agent (webhooks, admin views) stay in `app.py` and the
Jinja templates stay in `templates/` — only the agent's own logic lives here,
and those routes work against whichever profile is live.
