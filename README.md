# SAI Agency

**Launch · Acquire · Own.** 18 free, privacy-first browser tools for the new entrepreneur. Runs entirely on your device — no signup, no email, no cookies.

Live: https://sai-agency.netlify.app

Built by [Desired Solutions](https://desiredsolutions.me).

---

## What this repo contains

This repo was reconstructed from the deployed Netlify bundle (originally pushed via `netlify deploy` from a local machine). It has two layers:

1. **`dist/`** — the current production build served by Netlify. Keeps the live site working while the source is rebuilt tool-by-tool.
2. **`src/`** — a fresh Vite + React + TypeScript + Tailwind scaffold. The 18 tools from the sitemap are registered in `src/tools.ts`; each will be re-implemented from the bundle in future PRs.

The `netlify.toml` currently publishes `dist/`. Once a tool is ported to `src/`, its chunk can be removed from `dist/` and the SPA will fall through to the new source.

## Tool catalog

| Category    | Tools                                                                                                     |
| ----------- | --------------------------------------------------------------------------------------------------------- |
| 🚀 Launch   | Business Launcher · Niche Selector · Service Pricing · Outreach Gen · Discovery Script · Proposal · 60-Day Dashboard |
| 🏪 Acquire  | Small-Biz Scanner · Due Diligence · Revenue Calculator · Saved Deals                                      |
| 🧩 Own      | Funding Engine · Fractional Ownership                                                                     |
| 📈 GTM      | Marketing Agent · Sales Agent · GTM Planner · Outreach Automation                                         |
| 📊 Insights | Analytics                                                                                                 |

Routes are query-string driven: `?cat=launch&tab=launcher`.

## Local development

```bash
npm install
npm run dev     # Vite dev server
npm run build   # Build into dist/ (preserves existing bundle files via emptyOutDir: false)
npm run preview
```

## Deploy

Netlify is configured to publish `dist/`. Future workflow:

1. Push changes to the development branch.
2. Open a PR against `main`.
3. Netlify builds & posts a deploy preview on the PR.
4. Merge → production deploy.

To link this repo to the Netlify site (one-time, in the Netlify UI):

1. Netlify → **sai-agency** site → **Site configuration → Build & deploy → Continuous deployment**.
2. Click **Link repository** and pick `dnzengou/sai-agency`.
3. Build command: `npm run build` · Publish directory: `dist` · Base: _(empty)_.
4. Save. Trigger a deploy to confirm parity.

## Brand

Theme color `#9333ea` · background `#030712` · dark mode only. See `tailwind.config.js` for the `brand` palette.

## License

See [`LICENSE`](./LICENSE).
