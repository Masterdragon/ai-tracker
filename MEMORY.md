# AI Tracker — Project Memory

Persistent context for Claude Code sessions working in this repo.

---

## What this project is

An autonomous crawler that discovers, enriches, classifies, and serves AI company data. The goal is comprehensive global coverage — especially India and the US — across all funding stages (pre-seed → IPO).

---

## Architecture decisions

### Why file-based storage (not a DB)
`data/companies.json` is intentionally simple — the dataset fits in memory, reads are fast, and it avoids a database dependency for a scraper that runs hourly. If the company count exceeds ~10k, migrate to SQLite.

### Why APScheduler (not cron)
The scheduler runs in-process with Gunicorn so the app is self-contained — no external cron daemon needed on Oracle Cloud or Railway.

### Why seed data is hardcoded in `crawler.py`
Seed companies have verified, hand-curated data (accurate valuations, HQ, founding year). Hardcoding them avoids accidental overwrite by stale RSS data. The `DeduplicationAgent` enforces this: **seed always beats RSS**.

### Why full-article fetch is capped at 8 per feed
Each article fetch adds ~6s timeout risk. 8 articles × 26 feeds × 6s worst case = ~12 min crawl. The cap keeps a full run under 15 minutes.

---

## Key numbers (as of Sep 2025)

| Metric | Value |
|---|---|
| Seed companies | 139 |
| RSS feeds | 26 |
| Tags / categories | 15 |
| Eval fixtures | 27 unit tests + golden dataset |
| Crawl frequency | Hourly (APScheduler) |

---

## File map

| File | Purpose |
|---|---|
| `crawler.py` | All four agents + seed data + orchestrator |
| `app.py` | Flask routes, APScheduler setup |
| `wsgi.py` | Gunicorn entry point — starts scheduler + initial crawl |
| `static/index.html` | Self-contained frontend (no build step) |
| `data/companies.json` | Live dataset — gitignored, rebuilt on deploy |
| `eval/eval_report.py` | Scored pipeline report |
| `eval/test_agents.py` | 27 unit tests |
| `eval/golden_dataset.json` | Ground-truth fixtures |
| `deploy/setup.sh` | One-shot Oracle Cloud Ubuntu setup |
| `Procfile` | Railway deployment |

---

## Known constraints & gotchas

- **`data/` is gitignored** — a fresh clone or Railway deploy will have no `companies.json`; `wsgi.py` handles this by running an initial crawl on startup.
- **Single Gunicorn worker** — APScheduler requires a single worker to avoid duplicate crawl jobs. Do not increase `--workers` without switching to an external scheduler.
- **RSS summaries truncate** — many feeds clip at ~200 chars, before funding figures appear. The `_fetch_article_text` fallback addresses this.
- **Indian AI companies are underrepresented** in current RSS feeds. The feeds are mostly US/EU-focused publications. To improve India coverage, add feeds from YourStory, Inc42, or The Ken.
- **Railway ephemeral filesystem** — `data/companies.json` resets on each new deploy; the startup crawl rebuilds from 139 seeds in ~30s. Add a Railway persistent volume at `/app/data` to avoid this.

---

## Deployment status

| Environment | Status | URL |
|---|---|---|
| Local | `python3 app.py` → `localhost:5000` | — |
| Oracle Cloud VM | Systemd + Nginx (configured, may need setup.sh) | Public IP via VM dashboard |
| Railway | GitHub auto-deploy via `Procfile` | Generated domain in Railway dashboard |

---

## Planned improvements (not yet built)

- Add Indian AI news sources (YourStory, Inc42, The Ken RSS feeds)
- Add Crunchbase / PitchBook API integration for structured funding data
- Persistent volume on Railway so data survives redeploys
- Company detail pages (individual pages per company)
- Funding stage filter backed by structured data (currently inferred from text)
