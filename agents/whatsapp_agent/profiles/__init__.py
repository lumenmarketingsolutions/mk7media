"""Agent profiles for the WhatsApp agent.

Each subfolder is a self-contained agent (its own SYSTEM_PROMPT, model,
templates, behaviour) that can be made live on the +1 623 512 6504 WABA by
pointing ACTIVE_PROFILE in `agents/whatsapp_agent/__init__.py` at its name.

Don't edit `lumen/` — that's the preserved original. To make a new agent,
copy a profile folder to a new name and edit `agent.py` in the copy.
"""
