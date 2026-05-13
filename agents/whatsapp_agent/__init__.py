"""WhatsApp agent — one WABA (+1 623 512 6504), swappable agent profiles.

`agent` always points at whichever profile is currently LIVE on the number.
Each profile under `profiles/<name>/` is a fully self-contained copy of the
agent: its own SYSTEM_PROMPT, model, default template, behaviour. The rest of
the app only ever does `from agents.whatsapp_agent import agent as wa`, so
swapping profiles never touches app.py, the routes, or the Meta webhook config.

┌──────────────────────────────────────────────────────────────────────────┐
│  TO SWITCH WHICH AGENT ANSWERS WHATSAPP:                                   │
│  change ACTIVE_PROFILE below to one of the folder names in `profiles/`,    │
│  commit, push. That is the entire switch. (Switching back = change it      │
│  back and push — one line, always.)                                       │
└──────────────────────────────────────────────────────────────────────────┘

Profiles (see profiles/<name>/README.md for each):
  • "mk7_agent_v1_00"  — "MK7 Agent V1.00": the ORIGINAL agent we built
                         (MK7 Media outreach, speaking as "Kendall from
                         Lumen" since the number lives in the Lumen
                         portfolio). PRESERVED — do not edit this folder.
                         To iterate, copy it to a new profile and edit the
                         copy.
  • "lumen_lebanon_website_leads"
                       — "Lumen Lebanon Agent - Website Leads": a full-on
                         Lumen agent. Started as a verbatim copy of MK7
                         Agent V1.00; this is the one we change.

To add another profile: copy any `profiles/<name>/` folder to a new name,
edit `agent.py` in the copy, add a line above, then (when ready) point
ACTIVE_PROFILE at it.
"""
import importlib

# ── THE SWITCH ──────────────────────────────────────────────────────────────
ACTIVE_PROFILE = "lumen_lebanon_website_leads"   # ← change this one string to switch profiles
# ────────────────────────────────────────────────────────────────────────────

agent = importlib.import_module(f"{__name__}.profiles.{ACTIVE_PROFILE}.agent")
