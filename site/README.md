# mk7media.com

Edit anything in this folder, commit and push to `main`. GitHub builds the site (Actions tab, "Build mk7media.com")
and updates `site_build/`, then Railway redeploys mk7media.com. Live in about 5 minutes.

- Preview locally: `npm install` once, then `npm run dev` and open http://localhost:3000
- Pages: `src/app/*`. Service copy: `src/lib/services.ts`. Blog posts: `content/blog/*.md`.
- Only change files inside `site/`. The rest of this repo runs the WhatsApp bots and lead webhooks.
- Pull first (GitHub Desktop: Fetch origin) so you never overwrite someone else's change.
