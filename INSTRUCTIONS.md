# AI Tracker — Developer Instructions

Quick reference for working in this repo.

---

## Local setup (first time)

```bash
cd ~/Documents/ai-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Run locally

```bash
source venv/bin/activate
python3 app.py
```

Opens at **http://localhost:5000**. On startup it runs an initial crawl (seeds all 139 companies), then schedules an hourly crawl automatically.

---

## Trigger a manual crawl

```bash
curl -X POST http://localhost:5000/api/refresh
```

Or open http://localhost:5000/api/status to see the last crawl time and next scheduled run.

---

## Run the eval suite

```bash
source venv/bin/activate
python3 eval/eval_report.py      # scored report per agent (colour-coded)
python3 -m pytest eval/test_agents.py -v   # 27 unit tests
```

---

## Add new seed companies

Edit the `SEED_COMPANIES` list in `crawler.py`. Follow the existing pattern:

```python
Company(
    "company_id",          # snake_case, unique
    "Display Name",
    "One-sentence description of what they do.",
    ["Tag1", "Tag2"],      # from the 15 standard tags in ClassificationAgent
    "https://company.com",
    "Series B — $50M (Jan 2025)",   # last_funding
    "$500M",               # valuation (or "Undisclosed")
    2021,                  # founded year
    "San Francisco, CA",   # hq
    source="seed",
),
```

Valid tags: `LLM`, `Foundation Models`, `Generative AI`, `API`, `Image Generation`, `Video Generation`, `NLP / Speech`, `Audio AI`, `Computer Vision`, `AI Coding`, `AI Agents`, `Robotics`, `Autonomous Vehicles`, `AI Chips / Hardware`, `AI Infrastructure`, `MLOps / Infrastructure`, `Data & Labelling`, `AI Safety`, `Open Source`, `Enterprise AI`, `AI Search`, `AI for Healthcare`, `AI for Legal`, `AI for Finance`, `AI for HR`, `AI for Sales`, `AI for Education`, `Customer Service AI`, `Consumer AI`, `Research`, `Cloud AI`, `Automation`, `Hardware`, `Fintech`, `Drug Discovery`, `Genomics`, `AI Security`.

---

## Add new RSS feeds

Add the feed URL to the `RSS_FEEDS` list in `crawler.py`:

```python
RSS_FEEDS = [
    ...
    "https://yourstory.com/feed",   # example: Indian startup news
]
```

To improve **India coverage** specifically, add:
- `https://yourstory.com/feed`
- `https://inc42.com/feed/`
- `https://entrackr.com/feed/`

---

## API reference

| Endpoint | Method | Query params |
|---|---|---|
| `/api/companies` | GET | `?tag=Robotics`, `?q=search+term` |
| `/api/tags` | GET | — |
| `/api/status` | GET | — |
| `/api/refresh` | POST | — |

---

## Deploy to Railway

1. Push changes to `main` on GitHub — Railway auto-deploys.
2. Check build logs in the Railway dashboard.
3. To trigger a crawl immediately after deploy: `curl -X POST https://<your-railway-url>/api/refresh`

## Deploy to Oracle Cloud VM

```bash
ssh ubuntu@<your-vm-ip>
cd /home/ubuntu/ai-tracker
git pull
sudo systemctl restart ai-tracker
sudo systemctl status ai-tracker    # verify it's running
curl http://127.0.0.1:5000/api/status
```

First-time VM setup:
```bash
bash deploy/setup.sh
```

---

## Project structure

```
ai-tracker/
├── crawler.py          # All agents + seed data (edit this most often)
├── app.py              # Flask routes + scheduler
├── wsgi.py             # Gunicorn entry point
├── requirements.txt
├── Procfile            # Railway
├── runtime.txt         # Python version pin
├── static/
│   └── index.html      # Frontend (single file, no build step)
├── data/
│   └── companies.json  # Live data — gitignored
├── eval/
│   ├── eval_report.py
│   ├── test_agents.py
│   └── golden_dataset.json
└── deploy/
    ├── setup.sh
    ├── ai-tracker.service
    └── nginx.conf
```

---

## Common issues

**Port 5000 already in use**
```bash
lsof -ti:5000 | xargs kill -9
python3 app.py
```

**`data/companies.json` missing or corrupt**
```bash
rm -f data/companies.json
curl -X POST http://localhost:5000/api/refresh   # rebuilds from seeds
```

**Crawler finds 0 new companies**
- Check if RSS feeds are reachable: `curl -I https://techcrunch.com/category/artificial-intelligence/feed/`
- Run `eval_report.py` to check `DiscoveryAgent` score against fixtures
- Broaden `AI_KEYWORDS` or `FUNDING_RE` in `crawler.py` if regex is too strict
