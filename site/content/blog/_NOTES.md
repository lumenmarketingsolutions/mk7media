# Blog fact check notes

Claims the owner should double check before publishing. All example numbers in the posts are labeled as examples and are not client results.

## meta-ads-lebanon-guide
- "Ad costs are usually lower than in the Gulf or the US." Matches general experience, but confirm against your own account data before publishing.
- Advantage+ naming: Meta renamed and merged Advantage+ shopping campaigns into Advantage+ sales campaigns in 2025. The post refers to "Advantage+ options" generally. Check current Ads Manager wording.
- "Adding a hashed phone number usually helps Event Match Quality a lot in Lebanon." Reasonable, but it is our experience, not a published Meta stat.
- Cash on delivery being very common locally: widely true, keep as is unless you disagree.

## track-whatsapp-sales-meta-ads
- The click ID (ctwa_clid) arrives in the referral object of the first inbound message on the WhatsApp Business Platform (Cloud API). Confirm this is still how it works and that your provider/GHL setup exposes it.
- Conversions API for business messaging: events tied to the WhatsApp Business Account's dataset. Confirm current setup steps in Meta docs (field names like action_source "business_messaging" and messaging_channel "whatsapp" are intentionally not in the post).
- Statement that the free WhatsApp Business app does not expose ad referral data to your systems. Check whether Meta has added any purchase or event reporting inside the Business app recently.
- "A number used on the platform generally cannot also be used in the regular phone app in the same way." Meta has rolled out coexistence (using the Business app and the platform on one number) in some markets. Verify current availability for Lebanon/Gulf numbers and soften or update the line if needed.
- "Upload sales by phone number ... through the Conversions API." Meta retired the old Offline Conversions API in 2025 in favor of the Conversions API. Confirm wording matches the current method.

## choosing-marketing-agency-beirut
- "A three month minimum is common and reasonable." Opinion; make sure it matches MK7's own contract terms.
- Example proposals are hypothetical. Make sure MK7's real pricing does not contradict the framing.

## shopify-store-lebanon
- Card payment options for Lebanese businesses on Shopify: the post deliberately does not name any gateway. Verify which providers work for Lebanese registered businesses if you want to add specifics. Shopify Payments is generally not available in Lebanon, but the post does not state this.
- Shopify supports cash on delivery as a manual payment method: true as of 2025, confirm.
- "Facebook and Instagram sales channel app sets up pixel and Conversions API." True for Shopify's Meta app as of 2025; confirm the app name.
- Shopify reports a purchase when a COD order is placed (even if later refused). Accurate for standard pixel and Meta app behavior; confirm.
- Address/postcode handling for Lebanon at checkout: test on a live store.

## meta-ads-for-beginners
- Six campaign objectives (Awareness, Traffic, Engagement, Leads, App promotion, Sales): current as of 2025.
- "Around 50 optimization events in a week to exit learning": Meta's long standing guidance; confirm it has not changed.
- Deduplication requires matching event name and event ID between pixel and server: correct as of 2025.
- "Advantage+ placements" name: confirm current label.

## google-ads-basics
- Match type definitions (exact, phrase, broad) reflect Google's current meaning based matching.
- Performance Max channel list (Search, YouTube, Display, Gmail, Maps, Discover). Google has been rebranding Discover as Demand Gen inventory; consider checking the current list.
- "In smaller markets like Lebanon, search volumes for some terms can be low, and many searches are in a mix of English, Arabic and French, or Arabic written in Latin letters." Widely true, but worth a quick Keyword Planner check.
- Example CPC of about $2 for AC repair in Dubai is invented; confirm it is not wildly off before publishing, or keep the "illustrative" framing.

## how-to-build-an-offer
- "Before and after results (where that is allowed for your industry)." Meta restricts before and after imagery in some categories (health, weight loss, cosmetic). Keep the caveat.
- "Many people pick the middle option" is a common pricing observation, not a cited study. Keep the soft wording.

## how-to-promote-your-business-online
- WhatsApp Business app features (catalog, greeting message, quick replies): true as of 2025.
- Google Business Profile accepting a WhatsApp link: GBP supports chat/messaging links in some forms; confirm what the profile allows in Lebanon.
- Example of $2 per WhatsApp conversation and 20 percent order rate is invented and labeled; sanity check it against your own accounts so it does not overpromise.

## when-to-automate-your-business
- WhatsApp rule: business initiated messages outside the customer service window (24 hours) need approved templates. Correct as of 2025; the post phrases it generally.
- Tool names (Zapier, Make, n8n) are mentioned as examples only.
- Dental clinic numbers are invented and labeled.

## website-that-converts
- PageSpeed Insights and WebP recommendations: stable.
- Heatmap tools mentioned generically (Microsoft Clarity is a free option if you want to name one).
- "Logos of clients or partners (with permission)": keep the caveat.

## General
- All posts are dated 2026-11-13 as requested.
- Internal links used only the allowed /services/* paths and /contact. The Meta Lebanon guide mentions the WhatsApp tracking post by name without linking, since /blog paths were not on the allowed list. Add a link once blog URLs are final if you want it.
