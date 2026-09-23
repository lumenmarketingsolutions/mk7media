# Lumen Ai Agent V1.00

The WhatsApp agent for **Lumen itself**, on **+961 70 836 908**.

It is two things at once: the live demo a prospect meets after clicking an ad,
and the agent that books the call. Those are not in tension — the demo IS the
reply, so reply quality is the product.

## Identity

| | |
|---|---|
| Number | +961 70 836 908 ("Lumen Ai") |
| phone_number_id | `1386086784582081` |
| WABA | `1041685491957098` (owned by Lumen V2, partner-shared to Lumen Marketing) |
| Subscribed app | MK7 messaging `2107067100091646` — verified, sole subscriber |
| CAPI dataset | `1552802522839666` |

## The objective is a booked call

Not a sale, not an address, not a location. The agent is finished when the
prospect has given **a day AND a time**, and only then does it hand off.

Applying the taxonomy rule — *the first moment the customer hands over something
that costs them if they walk away* — a named slot is the commitment here. "Sounds
good" is not. "Send me info" is not. The trap this profile has to avoid is firing
on interest, which is the same trap as `"do you have anything Thursday?"` in the
salon preset.

## What was removed from the FGC base

This started as a copy of `fgc_agent_v1_00` and the entire commerce layer is gone:

- `product_map.json` deleted, product resolution stripped out of the context line
- `_maybe_log_agent_order()` is now a no-op — there is no order and no Shopify
- No prices for goods, no delivery, no COD, no location capture as a conversion

The context line now carries only **which ad they clicked**, because that is the
promise already in their head.

## Voice

Lebanese, human, short. One to three lines, never more than ~35 words. Mirrors
the customer's language including arabizi. No emojis, no corporate vocabulary,
no em dashes. It talks about **their** business, not about us — Lumen only comes
up when asked, and then in one line from their side.

## Safety

`LUMENAI_AUTO_REPLY` defaults to **0** — shadow mode. The agent logs and emails
every conversation but sends nothing until that is set to `1` on Railway.

## Env

All knobs are `LUMENAI_*` so nothing collides with the FGC profile:
`LUMENAI_AUTO_REPLY`, `LUMENAI_GREETING_TEXT`, `LUMENAI_GREETING_MODE`,
`LUMENAI_DB_PATH`, `LUMENAI_NOTIFY_EMAILS`, `LUMENAI_MONITOR_WA`,
`LUMENAI_HANDOFF_WA`, `LUMENAI_REPLY_DELAY`, `LUMENAI_REENGAGE`.

## Routing

`app.py` splits the webhook by `phone_number_id` before the ACTIVE_PROFILE
fallthrough. Without that split the Lumen Lebanon profile would answer our own
prospects from the wrong number.
