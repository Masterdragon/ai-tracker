# AI Companies Tracker — Skills & Capabilities

## What it does

Continuously discovers, enriches, classifies, and deduplicates AI companies worldwide — with a focus on India and the United States — across all funding stages from pre-seed to IPO. The dataset is served through a REST API and a filterable web frontend.

---

## Multi-Agent Crawler Pipeline

The core intelligence runs as four sequential agents, orchestrated by `CrawlerOrchestrator` (`crawler.py`).

### Agent 1 — DiscoveryAgent
Scans **26 RSS feeds** (TechCrunch, VentureBeat, a16z, Y Combinator, Hugging Face, Synced, Maginative, The Rundown AI, and more) and extracts AI companies from funding headlines.

- Matches headlines against an **AI keyword filter** (`AI`, `LLM`, `generative`, `neural`, `robotics`, etc.)
- Extracts company name + funding amount using a broad regex covering verbs like *raises, raised, secures, nets, scores, lands, bags, grabs, closed* and amounts in formats `$20M`, `$1.2B`, `$50 million`, `$2 billion`
- Falls back to **full article text fetch** (BeautifulSoup) when the title/summary doesn't contain a funding figure, up to 8 articles per feed
- Polite request pacing with delays between fetches

### Agent 2 — EnrichmentAgent
Fetches the **meta description / og:description** from each discovered company's homepage to replace the raw headline with a clean, informative description.

### Agent 3 — ClassificationAgent
Tags each company using **15 keyword rule sets** across categories:

| Category | Example keywords |
|---|---|
| Robotics | robot, humanoid, physical |
| Autonomous Vehicles | self-driving, waymo, AV |
| AI Chips / Hardware | chip, GPU, TPU, LPU, semiconductor |
| AI for Healthcare | health, medical, clinical, drug, radiology |
| AI for Legal | legal, contract, litigation, compliance |
| AI for Finance | finance, trading, risk, fraud, banking |
| Video Generation | video, film, cinematic, animation |
| NLP / Speech | voice, speech, TTS, audio |
| Computer Vision | image, vision, photo, diffusion |
| AI Coding | code, IDE, software engineer |
| AI Agents | agent, autonomous, workflow |
| AI Infrastructure | vector, embedding, RAG, search |
| AI Safety | safety, alignment, interpretability |
| Open Source | open-source, open weight |
| Enterprise AI | enterprise, B2B, business |

Each company is capped at 6 tags to stay focused.

### Agent 4 — DeduplicationAgent
Merges the incoming RSS-discovered records with the existing data store, with a clear priority rule: **seed data always wins over RSS data**. If a company already exists in the curated seed list, RSS updates can only enrich the description — never overwrite core fields.

---

## Seed Dataset

**139 curated companies** hand-verified with accurate funding, valuation, and HQ data, covering:

- **Foundation Model Labs** — OpenAI, Anthropic, Mistral, xAI, DeepSeek, Moonshot AI, Zhipu AI, 01.AI, Aleph Alpha, H Company, Sakana AI
- **AI Infrastructure** — CoreWeave, Lambda, Together AI, Anyscale, Baseten, Fireworks AI, Vast.ai, Pinecone, Weaviate
- **AI Chips** — Groq, Cerebras, SambaNova, Tenstorrent, d-Matrix, Etched, Positron AI
- **Robotics & AVs** — Physical Intelligence, Figure AI, 1X Technologies, Apptronik, Skild AI, Covariant, Field AI, Wayve, Waabi, Aurora, Nuro
- **Generative Media** — Runway, Pika, Luma AI, Suno, Udio, Black Forest Labs, Ideogram, Krea, ElevenLabs, Hume AI, Tavus
- **AI Coding** — Cursor, Replit, Codeium, Magic AI, Augment Code, Lovable, Tabnine
- **AI Agents** — Adept, Sierra, Cognition AI, Decagon, Lindy AI, Moveworks, Manus AI, 11x, Bland AI, Vapi
- **Vertical AI** — Harvey (legal), Hebbia (finance), Abridge/Ambience/Hippocratic/Tempus (healthcare), Glean/AlphaSense (search), Eightfold (HR)
- **International** — DeepSeek, Moonshot AI, Zhipu AI, 01.AI (China), Aleph Alpha (Germany), H Company (France), Sakana AI (Japan)
- **MLOps** — Weights & Biases, Scale AI, Hugging Face, LangChain, LlamaIndex, CrewAI, Snorkel AI, Labelbox

---

## REST API

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/companies` | GET | All companies. Filterable via `?tag=Robotics` and/or `?q=search+term` |
| `GET /api/tags` | GET | Sorted list of all unique tags in the dataset |
| `GET /api/status` | GET | Last crawl time, company count, next scheduled crawl |
| `POST /api/refresh` | POST | Manually trigger a full crawl cycle immediately |

---

## Frontend Features

- **Full-text search** across company name and description
- **Filter pills** for Category, Funding Stage, and Location
- **Active filter chips** showing current filters with individual remove buttons
- **Clear all filters** button
- **Tag colour coding** — each category has a consistent colour across cards
- Live company count reflecting active filters

---

## Eval Framework (`eval/`)

Three-layer quality gate for the crawler pipeline:

| File | What it checks |
|---|---|
| `test_agents.py` | 27 unit tests covering all four agents and edge cases |
| `golden_dataset.json` | Curated fixtures with known-good discovery and classification outputs |
| `eval_report.py` | Runs the pipeline end-to-end and prints a scored report per agent (colour-coded ✓/✗, percentage score) |

Run it with:
```bash
python3 eval/eval_report.py
```

---

## Scheduling

- **Hourly crawl** runs automatically via APScheduler in the background process
- **Startup crawl** runs once on boot if `data/companies.json` doesn't exist yet (handles fresh deploys)
- **Manual trigger** via `POST /api/refresh` for on-demand refreshes

---

## Deployment

| Target | Config | Notes |
|---|---|---|
| **Railway** (recommended) | `Procfile`, `runtime.txt` | Auto-deploys from GitHub; free tier covers ~500 hrs/month |
| **Oracle Cloud VM** | `deploy/ai-tracker.service`, `deploy/nginx.conf`, `deploy/setup.sh` | Systemd + Gunicorn + Nginx; run `bash deploy/setup.sh` on a fresh Ubuntu 22.04 VM |
| **Local** | `python3 app.py` | Starts crawl + scheduler + Flask on `localhost:5000` |

---

## Data Flow

```
RSS Feeds (26 sources)
       │
       ▼
 DiscoveryAgent ──── AI keyword filter ──── Funding regex ──── Article fetch fallback
       │
       ▼
EnrichmentAgent ──── Fetch homepage meta description
       │
       ▼
ClassificationAgent ── 15 keyword rules ── up to 6 tags per company
       │
       ▼
DeduplicationAgent ── Merge with existing store (seed > rss priority)
       │
       ▼
  companies.json ──── Flask API ──── Frontend
```
