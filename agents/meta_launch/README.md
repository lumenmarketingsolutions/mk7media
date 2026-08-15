# Meta Campaign + Ad Set Launcher

Creates a campaign and an ad set on a client's Meta ad account from a JSON config.
The write-side companion to `../meta_audit`, which only reads.

## Use

1. `cp .env.example .env` — put an **`ads_management`** token and `act_<id>` in it (gitignored).
2. `cp campaign.example.json campaign.json` — set the objective, budget, and targeting.
3. `python3 launch.py` — dry run: validates the config, checks the account, prints the plan.
4. `python3 launch.py --go` — creates it, **PAUSED**.
5. Add creative and an ad in Ads Manager, then set it live there.

Zero pip dependencies (standard library only), same as `pull.py`.

## Safety

Because this one spends money, it is deliberately awkward to fire by accident:

- **Dry run is the default.** Nothing is created without `--go`.
- **Everything is created `PAUSED`.** `--activate` overrides that, and makes you retype the
  campaign name to confirm.
- **Preflight** confirms the token works and reports account status, currency, and whether a
  funding source exists — before creating anything.
- **Validation** runs before any API call, catching the mistakes that otherwise come back as an
  opaque HTTP 400: bad objective, budget on both campaign and ad set, lifetime budget with no
  end date, a conversion goal with no pixel.

Nothing here deletes or edits existing campaigns.

## Budgets

Give budgets in your account's currency — `50` means $50. The Graph API actually wants the
minor unit (5000 cents), and `launch.py` does that conversion after reading the real currency
off the account in preflight. Zero-decimal currencies like JPY and KRW are handled.

Budget goes on **either** the campaign (Advantage campaign budget / CBO) **or** the ad set,
never both — the validator rejects it if you set both.

## Special ad categories

`special_ad_categories` is required on every campaign. `[]` is correct for most advertising.
Ads about **credit, employment, housing, social issues, elections, or politics** must declare
the matching category — this is a legal requirement, not a Meta preference, and declaring one
restricts the targeting Meta will accept (no age or gender targeting, limited geo radius).
Getting it wrong is grounds for account restriction, so it is worth a second look.

## Scope

Creates the campaign shell and the ad set (targeting, budget, schedule, optimization). It does
**not** upload creative or create ads — those need image/video assets and a Page, and are
easier to review visually in Ads Manager. Extend the script if you want that automated too.
