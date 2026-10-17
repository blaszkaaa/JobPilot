# JobPilot

**Open-source job discovery, semantic matching, notifications and application tracking.** A self-hosted, single-owner portfolio project with a dark dashboard inspired by Dokploy.

## Release v0.4 — Dokploy-inspired interface

The dashboard is redesigned using a **neutral black / zinc theme** inspired by Dokploy's project and deployment screens, rather than the earlier purple SaaS theme. JobPilot uses its own name, logo and content.

- Narrow graphite navigation rail with **Home and Settings sections** and collapsible desktop sidebar (remembers your preference).
- **Project header and compact horizontal tabs** consistent across workspace views.
- Compact statistics and configurable **provider status tiles**; indicators show **configured** sources, not guaranteed live API reachability.
- Global `Ctrl+K` command search: quickly open a workspace page or a matching job. `Esc` closes the search.
- Job listings have **list and grid views**; search, filters, feedback and application actions remain available in both.
- Consistent neutral buttons, forms, panels, states and responsive mobile layout.
- No API or database changes required for the design migration.

## Release v0.3 — feedback-driven matching and reliable inbox

- Click **Pasuje** / **Nie pasuje** on a listing. Explicit like/dislike feedback is stored in SQLite and immediately reranks other listings using TF-IDF content similarity to examples. This is a **simple content-based adaptive ML ranking**, not an LLM, a fine-tuned model, or probability of getting hired. Undo a vote by clicking it again.
- Learn from individual votes, without making negative assumptions about ignored/saved items.
- **History of scans** (up to 500 records retained), with fetched counts, new matches and provider errors.
- **Inbox read/unread state**, individual marking and mark-all, unread badges.
- Deploy to Dokploy as before; schema migrations preserve existing listings, applications, and user profile.

## Release v0.2 — search watchers & application workspace\n\nThis version extends the first MVP with managed search queries, PDF CV parsing, and a full application pipeline. No third-party recruiter sites are automated or posted to by JobPilot.\n\n## Working MVP

- Private owner login (HTTP-only signed cookie, no public registration).
- Fetch jobs from **Arbeitnow** and optionally **Greenhouse**, **Lever** and **Adzuna (Poland)** official job APIs. No prohibited LinkedIn scraping.
- **ML-based matching:** TF-IDF + cosine similarity, weighted against job keywords, location and remote preferences. Scores are heuristic relevance indicators, **not** hiring probabilities. ChatGPT is **not** powering the server in this release.
- Personal profile, pasted resume text **or PDF CV import (2 MB, 12 pages)**; exclusions, remote-only preference and matching threshold. Raw PDF is processed transiently in the backend, and its extracted text is saved only when you confirm. Scanned PDFs require OCR (not implemented).
- Search, filter, save/ignore jobs; **up to five saved searches** (query, location, enable/disable) for official Adzuna API; previous single-query fallback stays available until any search is created. Other provider feeds are unaffected.\n- **Application pipeline**: draft → applied → interview → offer/rejected/withdrawn, notes, editable cover-letter draft, follow-up date, stage history, CSV export, and reminder notifications (one per due date). Status ‘applied’ is **manual confirmation**, not evidence of platform submission.
- Create and edit truthful, reusable application draft and copy it to clipboard. **No automatic submissions yet.**
- Optional Telegram alerts, automated polling every 30 minutes, SQLite persistence.
- Responsive Next.js dashboard, FastAPI backend, Docker Compose setup.

## Deploy to Dokploy\n\n**Existing installation:** Pull latest `main` and redeploy. The SQLite schema migration runs automatically at startup; preserve your existing `jobpilot-data` volume. Back it up first.

1. Create a **Compose** service and connect `blaszkaaa/JobPilot`, branch `main`.
2. Set Compose Path to `./docker-compose.yml`.
3. In **Environment**, add:
   - `JOBPILOT_ADMIN_EMAIL` — your email.
   - `JOBPILOT_ADMIN_PASSWORD` — random password (minimum 12 characters).
   - `JOBPILOT_SESSION_SECRET` — random secret (minimum 32 characters).
   - `COOKIE_SECURE=true` — use HTTPS for the public domain.
4. Optional: set `GREENHOUSE_BOARDS` and/or `LEVER_SITES` to comma-separated employer board identifiers. For Polish listings obtain `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` from [Adzuna Developer](https://developer.adzuna.com/overview), with `ADZUNA_COUNTRY=pl` and optional `ADZUNA_QUERY=Python`. `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` enable alerts.
5. Deploy. Under **Domains**, expose the **web** service on **container port 3000** and enable HTTPS. The API service remains internal, no external port.\n6. Open **Wyszukiwania** to add up to five search rules. The new rules affect Adzuna only; without Adzuna credentials, they will be stored but not executed.\n7. Under **Ustawienia**, import a textual PDF CV if you prefer, review extracted text and click **Zapisz zmiany**. Under **Oferty pracy**, choose **Przygotuj aplikację** to open the application pipeline.
8. Sign in using the configured owner credentials. Open **Ustawienia** and enter keywords, location and resume text. Click **Skanuj oferty**.

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
api/app/main.py  FastAPI, auth, matching, fetchers, background sync\napi/app/features.py  Search-watch CRUD, applications pipeline, migration, PDF import, CSV export\napi/app/intelligence.py  TF-IDF matching, explicit vote similarity, ranking reasons\napi/app/learning.py  User feedback API, scan history, inbox read/unread\nweb/app/workspaces.tsx  UI for watch lists, pipeline, CV importer
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
2. Per-company boards configuration from UI, real notification preferences, scheduled job queues and configurable follow-up reminders (currently queued on each scan and optionally delivered through Telegram; no instant scheduler).
3. Exportable user-labeled ranking dataset and supervised reranker: current adaptive relevance is TF-IDF with explicit feedback similarity, not a trained supervised neural model.
4. Draft assistant and optional approved provider with user-controlled credentials.
5. Permitted website application adapters with explicit user consent, visible review screen, per-source compliance checks, rate limits and audit trail.

**JobPilot does not submit job applications automatically in v0.3.** Only the user can confirm that an application was sent.

## Security notes

Use HTTPS on Dokploy; keep `.env` out of version control. Never publish personal CVs or real secrets in issues. The application stores pasted CV text in the self-hosted database. Do not expose port 8000 publicly. Do not run multiple API worker processes with the embedded polling loop. Backup the Docker volume before destructive upgrades.

## Development

```bash
cd api && pip install -r requirements.txt && python -m unittest discover -s tests -v
cd ../web && npm install && npm run typecheck && npm run build
```

MIT License.

### Using the application workflow

1. Pick a job, select **Przygotuj aplikację**. This creates an editable draft — no information is sent to the employer.
2. Open **Moje aplikacje**, choose the draft, review/edit the message and optionally add notes and a follow-up date.
3. Open the job offer and apply directly at the employer's site. Only then change the stage to **Wysłane** and save; JobPilot records this manual confirmation.
4. Advance the stage as the hiring process progresses. Use **Eksport CSV** for a local backup of your pipeline.

Search watches consume Adzuna API quota: with five enabled queries and 30-minute polls, this release can issue up to 240 Adzuna searches per day (not counting manual scans). Configure fewer watches or increase `SYNC_INTERVAL_SECONDS` to fit your plan.

### Adaptive matching scores\n\nA liked or disliked listing becomes a labelled example (kept locally). For each other job, its TF-IDF vector is compared to liked/disliked examples. Similarity can adjust the original profile-fit score by up to +22 points or −27 points. Saved jobs do **not** count as positive feedback automatically. All content-based adjustments can be cleared by undoing votes. This is a heuristic ranking scale between 0–100, not a calibrated probability of interviews or hiring.\n

### UI development notes

Design tokens and layout styles live in `web/app/dokploy.css`; the original styles remain in `globals.css` and `workspaces.css` for compatibility. UI functionality lives in `web/app/page.tsx` and `web/app/workspaces.tsx`. Do not copy Dokploy trademarks or logo.
