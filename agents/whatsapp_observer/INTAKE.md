# Client intake: the questions that train the observer

Ask these on the onboarding call. The answers go straight into the client file. None
of them are about how to reply to customers, because nothing replies. They are about
one thing only: how this business knows a lead is real and a sale has happened.

## About the business (context the classifier reads)

1. **In one or two sentences, what do you sell and who buys it?**
   `business_description`
2. **List every product or service you'd want to see in reporting, with its price.**
   `what_is_sold`, `product_values` (the value Meta optimises toward), `currency`
3. **How does a customer pay?** Cash to the courier, card link, bank transfer, pay at the venue.
   `how_customers_pay`
4. **What happens after they say yes?** Courier, pickup, appointment, enrolment. How long does it take?
   `how_fulfilment_works`

## The lead (fires LeadSubmitted, for reporting)

5. **What does a customer have to tell you before you can actually do anything for them?**
   Item and quantity? Treatment and a day? Their child's level? `qualified_lead_definition`
6. **Give me three real messages from customers who turned out to be serious.**
   `qualified_signals`

## The sale (fires Purchase, what Meta optimises on)

7. **Inside the chat, what is the exact moment you consider it sold?**
   Not when the money arrives. The moment in the conversation. An address, a booked slot,
   a deposit screenshot, a name for the reservation. `sale_definition`
8. **Give me three real messages that were that moment.** `committed_signals`
9. **Do customers drop a location pin, and does that alone mean the order is on?**
   `location_pin_is_commitment`
10. **How often does someone commit and then back out within the hour, and what do they say?**
    Sets `settle_minutes`. Cash-on-delivery: 30. Bookings: 60. Anything with a deposit: 0.

## What is not a customer (never fires anything)

11. **What does a "no" sound like from your customers?** Real phrases, any language.
    `lost_signals`
12. **Who messages you that is not a customer?** Wholesalers, suppliers, job seekers, influencers.
    `disqualify_signals`
13. **What objections come up most, and what do you say back?** `typical_objections`
    This stops the classifier reading a haggle as a loss.

## Housekeeping

14. **Which languages and scripts do customers write in?** `languages`
15. **Which ad sets point at this WhatsApp number?** All of them must, or the click id never
    arrives and nothing can be attributed. Check it on the call, not after.

## What the answers become

| Milestone | Event sent to Meta | Ad sets can optimise on it |
|---|---|---|
| QUALIFIED / INTENT | LeadSubmitted | No, reporting only |
| COMMITTED (Q7) | Purchase, with the value from Q2 | Yes, for click-to-WhatsApp |
| LOST / DISQUALIFIED | nothing | |

Purchase waits the settle window from Q10 and is cancelled if the customer walks away
inside it. First week runs in dry run: the client sees every decision with its evidence
quote before a single event reaches Meta.
