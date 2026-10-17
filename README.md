# JobPilot

**Open-source job discovery, semantic matching, notifications and application tracking.** A self-hosted, single-owner portfolio project with a dark dashboard inspired by Dokploy.

## Working MVP

- Private owner login (HTTP-only signed cookie, no public registration).
- Fetch jobs from **Arbeitnow** and optionally **Greenhouse** / **Lever** public job-board APIs. No prohibited LinkedIn scraping.
- **ML-based matching:** TF-IDF + cosine similarity, weighted against job keywords, location and remote preferences. Scores are heuristic relevance indicators, **not** hiring probabilities. ChatGPT is **not** powering the server in this release.
- Personal profile and pasted resume text; exclusions, remote-only preference and matching threshold.
- Search, filter, save/ignore jobs; manual application tracker.
- Export a basic, editable cover-letter template to clipboard. **No automatic submissions yet.**
- Optional Telegram alerts, automated polling every 30 minutes, SQLite persistence.
- Responsive Next.js dashboard, FastAPI backend, Docker Compose setup.

## Deploy to Dokploy

1. Create a **Compose** service and connect `blaszkaaa/JobPilot`, branch `main`.
2. Set Compose Path to `./docker-compose.yml`.
3. In **Environment**, add:
   - `JOBPILOT_ADMIN_EMAIL` — your email.
   - `JOBPILOT_ADMIN_PASSWORD` — random password (minimum 12 characters).
   - `JOBPILOT_SESSION_SECRET` — random secret (minimum 32 characters).
   - `COOKIE_SECURE=true` — use HTTPS for the public domain.
4. Optional: set `GREENHOUSE_BOARDS` and/or `LEVER_SITES` to comma-separated employer board identifiers. `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` enable alerts.
5. Deploy. Under **Domains**, expose the **web** service on **container port 3000** and enable HTTPS. The API service remains internal, no external port.
6. Sign in using the configured owner credentials. Open **Ustawienia** and enter keywords, location and resume text. Click **Skanuj oferty**.

The Compose file joins the frontend to the existing Dokploy `dokploy-network` network. If you use custom Traefik labels instead of the Dokploy Domains UI, configure them for `web:3000`. Keep the mounted `jobpilot-data` Docker volume to persist your database across deployments.

### Local development

```bash
cp .env.example .env
# Edit .env: use your own secret, password, email; set COOKIE_SECURE=false for HTTP localhost.
docker network create dokploy-network 2>/dev/null || true
docker compose up --build
```

To access the web service locally, use `docker compose -f docker-compose.yml -f docker-compose.local.yml up --build`, then visit http://localhost:3000. The local override binds only frontend port 3000.

### Technical layout

```
web/             Next.js app, Polish UI, proxy /api → api service
api/app/main.py  FastAPI, auth, matching, fetchers, background sync
api/tests/       Matching and API tests
docker-compose.yml
```

### ChatGPT account / plan integration

This web release **does not** claim to use your ChatGPT Plus plan. The earlier Hearthstone desktop app used an official Sign in with ChatGPT open-source flow, but a remotely hosted or paid app has different onboarding requirements. SIWC credentials must not be pooled or persistently stored on a remote managed server. This repository deliberately does not collect ChatGPT passwords, browser cookies or OAuth tokens.

Potential next milestone: a **user-controlled local companion** providing SIWC authentication and inference requests from the user's device, subject to OpenAI authorization and eligibility. This needs separate implementation, not a fake “connect” button. Alternatively, a separately billed OpenAI API integration could be added as an optional provider.

References: [OpenAI SIWC OSS docs](https://developers.openai.com/siwc/token-sharing-open-source), [SIWC terms](https://openai.com/policies/sign-in-with-chatgpt-terms/), [Dokploy Compose tutorial](https://docs.dokploy.com/docs/core/docker-compose/example).

### Limitations / roadmap

This is a **real MVP**, not a production multi-tenant SaaS. One owner per deployment, no self-registration. Job-board providers may restrict volume, use and availability. Company-specific Greenhouse and Lever boards must be configured. Job postings are external content and may be inaccurate.

Upcoming features:
1. Better deduplication and location parsing (currently deduplication by provider ID).
2. Per-company boards configuration from UI, real notification preferences, scheduled job queues.
3. CV PDF import; user-labeled ranking dataset and learned reranker.
4. Draft assistant and optional approved provider with user-controlled credentials.
5. Website application adapters with explicit user consent, visible review screen, per-source compliance checks, rate limits and audit trail.

**JobPilot does not submit job applications automatically in v0.1.** Only the user can mark an application as sent.

## Security notes

Use HTTPS on Dokploy; keep `.env` out of version control. Never publish personal CVs or real secrets in issues. The application stores pasted CV text in the self-hosted database. Do not expose port 8000 publicly. Do not run multiple API worker processes with the embedded polling loop. Backup the Docker volume before destructive upgrades.

## Development

```bash
cd api && pip install -r requirements.txt && python -m unittest discover -s tests -v
cd ../web && npm install && npm run typecheck && npm run build
```

MIT License.
