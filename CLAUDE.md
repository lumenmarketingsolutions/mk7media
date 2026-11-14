# mk7media — rules for Claude

## How a change goes live
1. Edit source in `site/` (Next.js). Pages: `site/src/app/*`. Service copy: `site/src/lib/services.ts`.
   Blog posts: `site/content/blog/*.md`. Images/assets: `site/public/`.
2. Push to `main` → GitHub Action **"Build mk7media.com"** (`.github/workflows/build-site.yml`) builds the static
   export and commits it to `site_build/` as "Build site from <sha>".
3. Railway (project "Marykate", env production) auto-deploys every push to `main`. `app.py` (Flask, gunicorn)
   serves `site_build/`. Live in about 5 minutes.

## Rules
- Always `git pull --rebase origin main` first. Other people and the build bot push here.
- Change only files inside `site/` for website requests. Never hand-edit `site_build/`.
  The rest of the repo (`app.py`, `agents/`, `templates/`, `static/`) runs the WhatsApp bots, lead webhooks and
  client proposal pages — don't touch it unless MaryKate asks specifically.
- Before pushing: `cd site && npm ci` (first time) then `npm run build` must pass.
- Commit with a plain-English message describing the visible change, push to `main`.
- After pushing, check the deploy:
  `gh run list --workflow build-site.yml -L 1` (must be success), then
  `gh api repos/lumenmarketingsolutions/mk7media/deployments --jq '.[0]'` and its statuses for the Railway deploy.
- Tell MaryKate what changed, the commit link, and when it's live. If the build or deploy failed, say so and fix it.
- For bigger or risky changes, ask whether she wants a preview first (`npm run dev`, http://localhost:3000).
