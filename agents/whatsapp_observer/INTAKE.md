# WhatsApp Pixel intake: the questions before we watch a single chat

The "win" is whatever the business counts as success: an order, a booked call, an appointment, a signup, a deposit. Every question about "the sale" below means the win.

Ask in order, on the onboarding call, with the client's phone open. Every time they
generalise, ask for the last real chat. Paste the answers into the client's context box
in the admin; the fields in brackets are what each answer becomes. Nothing here is about
how to reply to customers. Nothing replies.

## The shape of the business
1. In one breath, what do you sell, and who is the person on the other end of the chat? [business_description]
2. Walk me through the last sale you closed on WhatsApp, message by message. What did they say first, what did you say, how did it end? [how_fulfilment_works, committed_signals]
3. Where does the conversation go after WhatsApp? Nowhere, a call, a visit, a booking link, a payment link, a courier? [how_fulfilment_works, how_customers_pay]

## The moment it's sold (fires Purchase, the event ads optimise on)
4. In that chat, at which exact message did you know you had them? Not when the money arrived. The message. [sale_definition]
5. What does the customer have to hand you before you can act on it? An address, a slot, a name, a deposit, a photo of a transfer? [sale_definition, location_pin_is_commitment]
6. Does money ever move inside the chat (transfer screenshot, OMT, Whish, card link)? Before or after the thing in Q5? [how_customers_pay, settle_minutes]
7. If someone writes "ok, I'll take it" and then goes quiet, is that a sale to you? How often does that happen? [qualified_signals, context_notes]
8. After they commit, how long until it is really done? In that window, how often do they back out, and what do they say? [settle_minutes, lost_signals]
   Cash on delivery: 30 minutes. Bookings: 60. Anything with a deposit: 0.

## The lead before the sale (fires LeadSubmitted, reporting only)
9. What is the first question a serious buyer asks, and what does a time waster ask? Real examples of both. [qualified_signals]
10. What details do you always need before you can quote or book? [qualified_lead_definition]
11. List what you sell with a price on each, then tell me which one you'd most like the ads to bring more of. [what_is_sold, product_values, currency]

## What is not a customer (fires nothing)
12. What does a "no" look like in your chats? Real phrases, including the polite ones that don't say no. [lost_signals]
13. Who messages this number that will never buy? Wholesalers, suppliers, job seekers, influencers, people asking for a friend. [disqualify_signals]
14. What objections come up most, and what do you say back? Price ("mish 12?") and trust ("asli?") are different. [typical_objections]

## Plumbing
15. Which ad sets send people to this number, does anyone else reply from it, and which languages and scripts do customers write in? [languages, context_notes]
    Every WhatsApp ad set must point at this number or its clicks carry no id and can never be attributed.

| Conversation state | Event sent to Meta | Ads can optimise on it |
|---|---|---|
| QUALIFIED / INTENT (Q9, Q10) | LeadSubmitted | No, reporting only |
| COMMITTED (Q4, Q5) | Purchase, value from Q11 | Yes |
| LOST / DISQUALIFIED (Q12, Q13) | nothing | |

Purchase waits the settle window from Q8 and is cancelled if the customer walks away
inside it. The first week runs in dry run: every decision is logged with the customer's
exact words, and nothing reaches Meta until it is switched on.
