# Meta Ad Account Audit Puller

Read-only snapshot of a client's Meta ad account via the Marketing API, for auditing
and strategy. Pulls structure + insights and writes them to `./out` (JSON + CSV).

## Use

1. `cp .env.example .env`
2. Put the client's **`ads_read`** token and `act_<id>` in `.env` (it's gitignored — never committed).
3. `python3 pull.py`

Output lands in `agents/meta_audit/out/`:
- `account.json`, `campaigns.json`, `adsets.json`, `ads.json` — structure
- `insights_{campaign,adset,ad}_{last_30d,last_90d}.{json,csv}` — performance

The script only ever reads. It never changes the account. For an audit, an `ads_read`
token is all you need — `ads_management` is only required later if we deliberately make changes.

Zero pip dependencies (uses the standard library).
