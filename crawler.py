"""
Multi-agent crawler for AI company data.

Agent breakdown:
  DiscoveryAgent      — scans RSS feeds for AI company funding/launch news
  EnrichmentAgent     — fetches meta tags from company homepages
  ClassificationAgent — assigns subcategory tags based on keywords
  DeduplicationAgent  — merges incoming records with existing store
  CrawlerOrchestrator — runs the full pipeline and persists results
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
import re
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "companies.json")

RSS_FEEDS = [
    "https://news.crunchbase.com/feed/",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
]

# ─── Data Model ──────────────────────────────────────────────────────────────

@dataclass
class Company:
    id: str
    name: str
    description: str
    tags: list
    website: str
    last_funding: str
    valuation: str
    founded: Optional[int] = None
    hq: Optional[str] = None
    source: str = "seed"
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─── Seed Data (25 + companies with verified data) ───────────────────────────

SEED_COMPANIES: list[Company] = [
    Company("openai", "OpenAI",
        "AI research lab behind GPT-4, DALL-E, Sora, and ChatGPT — the world's most widely used AI platform.",
        ["LLM", "Foundation Models", "Generative AI", "API", "Image Generation"],
        "https://openai.com", "Series E — $6.6B (Oct 2024)", "$157B", 2015, "San Francisco, CA"),
    Company("anthropic", "Anthropic",
        "AI safety company and creator of the Claude family of large language models, focused on reliable and interpretable AI.",
        ["LLM", "AI Safety", "Foundation Models", "API"],
        "https://anthropic.com", "Series E — $2.5B (Mar 2024)", "$61.5B", 2021, "San Francisco, CA"),
    Company("xai", "xAI",
        "Elon Musk's AI company developing the Grok large language model, integrated with X (Twitter).",
        ["LLM", "Foundation Models", "Generative AI"],
        "https://x.ai", "Series B — $6B (May 2024)", "$50B", 2023, "San Francisco, CA"),
    Company("mistral", "Mistral AI",
        "European AI startup building open-weight and commercial LLMs known for efficiency and multilingual performance.",
        ["LLM", "Foundation Models", "Open Source", "API"],
        "https://mistral.ai", "Series B — $640M (Jun 2024)", "$6B", 2023, "Paris, France"),
    Company("perplexity", "Perplexity AI",
        "AI-powered answer engine that combines LLMs with real-time web search to deliver cited, conversational responses.",
        ["AI Search", "LLM", "Generative AI"],
        "https://perplexity.ai", "Series E — $500M (Jan 2025)", "$9B", 2022, "San Francisco, CA"),
    Company("cohere", "Cohere",
        "Enterprise AI platform offering LLMs, embeddings, and RAG tools optimised for business NLP applications.",
        ["LLM", "Foundation Models", "Enterprise AI", "NLP"],
        "https://cohere.com", "Series D — $500M (Jul 2024)", "$2.2B", 2019, "Toronto, Canada"),
    Company("scale_ai", "Scale AI",
        "Data labelling and AI evaluation platform that powers training pipelines for leading AI labs and enterprises.",
        ["Data & Labelling", "MLOps / Infrastructure", "AI Evaluation"],
        "https://scale.com", "Series F — $1B (May 2024)", "$14B", 2016, "San Francisco, CA"),
    Company("huggingface", "Hugging Face",
        "Open-source AI platform hosting 500k+ models and datasets; the GitHub of machine learning.",
        ["MLOps / Infrastructure", "Open Source", "Foundation Models", "NLP"],
        "https://huggingface.co", "Series D — $235M (Aug 2023)", "$4.5B", 2016, "New York, NY"),
    Company("runway", "Runway ML",
        "Generative AI video platform enabling creators to generate, edit, and transform video using AI models.",
        ["Generative AI", "Video Generation", "Creative AI"],
        "https://runwayml.com", "Series C — $141M (Jun 2023)", "$1.5B", 2018, "New York, NY"),
    Company("elevenlabs", "ElevenLabs",
        "AI voice synthesis platform offering ultra-realistic text-to-speech and voice cloning in 30+ languages.",
        ["NLP / Speech", "Generative AI", "Audio AI"],
        "https://elevenlabs.io", "Series C — $180M (Jan 2025)", "$3.3B", 2022, "New York, NY"),
    Company("groq", "Groq",
        "AI inference company building LPU (Language Processing Unit) chips for ultra-fast LLM inference.",
        ["AI Chips / Hardware", "AI Infrastructure", "LLM"],
        "https://groq.com", "Series D — $640M (Aug 2024)", "$2.8B", 2016, "Mountain View, CA"),
    Company("cerebras", "Cerebras Systems",
        "AI hardware company that builds the world's largest AI chips and wafer-scale processors for training at scale.",
        ["AI Chips / Hardware", "AI Infrastructure"],
        "https://cerebras.net", "Pre-IPO — $250M (Aug 2024)", "$7.2B", 2016, "Sunnyvale, CA"),
    Company("together_ai", "Together AI",
        "Cloud platform for running and fine-tuning open-source AI models at scale, with a developer-first API.",
        ["AI Infrastructure", "MLOps / Infrastructure", "Open Source", "LLM"],
        "https://together.ai", "Series A — $305M (May 2024)", "$1.25B", 2022, "San Francisco, CA"),
    Company("weights_biases", "Weights & Biases",
        "MLOps platform for experiment tracking, model versioning, and collaborative ML development.",
        ["MLOps / Infrastructure", "AI Evaluation"],
        "https://wandb.ai", "Series C — $250M (Oct 2023)", "$1.25B", 2017, "San Francisco, CA"),
    Company("pinecone", "Pinecone",
        "Managed vector database purpose-built for AI applications, powering similarity search and RAG pipelines.",
        ["AI Infrastructure", "Data & Labelling", "MLOps / Infrastructure"],
        "https://pinecone.io", "Series B — $100M (Apr 2023)", "$750M", 2019, "New York, NY"),
    Company("pika", "Pika Labs",
        "AI video generation startup that lets users create and edit cinematic videos from text or image prompts.",
        ["Video Generation", "Generative AI", "Creative AI"],
        "https://pika.art", "Series A — $80M (Apr 2024)", "$500M", 2023, "San Francisco, CA"),
    Company("character_ai", "Character.AI",
        "Consumer AI platform for creating and chatting with AI personas; one of the highest-traffic AI apps globally.",
        ["LLM", "Consumer AI", "Generative AI"],
        "https://character.ai", "Series A — $150M (Aug 2024)", "$5B", 2021, "Menlo Park, CA"),
    Company("harvey", "Harvey AI",
        "AI legal platform purpose-built for law firms, automating research, contract review, and litigation prep.",
        ["AI for Legal", "Enterprise AI", "LLM", "Generative AI"],
        "https://harvey.ai", "Series D — $300M (Dec 2024)", "$3B", 2022, "San Francisco, CA"),
    Company("sierra", "Sierra AI",
        "Enterprise conversational AI platform for building customer-facing AI agents with brand-specific personas.",
        ["AI Agents", "Enterprise AI", "LLM", "Customer Service AI"],
        "https://sierra.ai", "Series B — $175M (Feb 2025)", "$4.5B", 2023, "San Francisco, CA"),
    Company("physical_intelligence", "Physical Intelligence",
        "Robotics AI company (π) building general-purpose AI systems and foundation models for physical robots.",
        ["Robotics", "Foundation Models", "AI Agents"],
        "https://physicalintelligence.company", "Series A — $400M (Nov 2024)", "$2.4B", 2023, "San Francisco, CA"),
    Company("figure_ai", "Figure AI",
        "General-purpose humanoid robot company integrating multimodal AI for autonomous physical task execution.",
        ["Robotics", "Foundation Models", "Autonomous Systems"],
        "https://figure.ai", "Series B — $675M (Feb 2024)", "$2.6B", 2022, "Sunnyvale, CA"),
    Company("wayve", "Wayve",
        "Autonomous driving startup using end-to-end deep learning to train self-driving models across global fleets.",
        ["Autonomous Vehicles", "Foundation Models", "Computer Vision"],
        "https://wayve.ai", "Series C — $1.05B (May 2024)", "$5B", 2017, "London, UK"),
    Company("writer", "Writer",
        "Full-stack generative AI platform for enterprises — custom LLMs, Knowledge Graph, and AI workflow apps.",
        ["Enterprise AI", "LLM", "Generative AI", "Foundation Models"],
        "https://writer.com", "Series C — $200M (Sep 2024)", "$1.9B", 2020, "San Francisco, CA"),
    Company("weaviate", "Weaviate",
        "Open-source vector database with built-in ML models, enabling semantic search and RAG at scale.",
        ["AI Infrastructure", "Open Source", "MLOps / Infrastructure"],
        "https://weaviate.io", "Series B — $50M (Nov 2023)", "$400M", 2019, "Amsterdam, Netherlands"),
    Company("modal", "Modal Labs",
        "Serverless cloud platform for running AI inference and training workloads with sub-100ms cold starts.",
        ["AI Infrastructure", "MLOps / Infrastructure", "Cloud AI"],
        "https://modal.com", "Series B — $145M (2024)", "$2B", 2021, "New York, NY"),
    Company("imbue", "Imbue",
        "AI research lab building agents that can reason and code, aiming for practical AI with strong reliability.",
        ["AI Agents", "LLM", "AI Safety", "Research"],
        "https://imbue.com", "Series B — $200M (Sep 2023)", "$1B", 2021, "San Francisco, CA"),
    Company("poolside", "Poolside AI",
        "AI coding company building a foundation model trained via reinforcement learning from code execution.",
        ["AI Coding", "LLM", "Foundation Models"],
        "https://poolside.ai", "Series B — $500M (Aug 2024)", "$3B", 2023, "San Francisco, CA"),
    Company("cognition_ai", "Cognition AI",
        "Creator of Devin, the first fully autonomous AI software engineer capable of end-to-end coding tasks.",
        ["AI Coding", "AI Agents", "LLM"],
        "https://cognition.ai", "Series B — $175M (Apr 2024)", "$2B", 2023, "San Francisco, CA"),

    # ── Bootstrapped / No disclosed VC funding ────────────────────────────────
    Company("midjourney", "Midjourney",
        "Bootstrapped AI image generation platform with ~$200M ARR, no VC funding — one of the most profitable AI companies.",
        ["Image Generation", "Generative AI", "Creative AI"],
        "https://midjourney.com", "Bootstrapped — No VC", "Profitable (~$200M ARR)", 2021, "San Francisco, CA",
        source="seed"),
    Company("ollama", "Ollama",
        "Open-source tool to run LLMs (Llama, Mistral, Gemma) locally on any laptop — 80k+ GitHub stars, massive developer adoption.",
        ["Open Source", "LLM", "AI Infrastructure"],
        "https://ollama.com", "No disclosed funding", "N/A", 2023, "San Francisco, CA",
        source="seed"),
    Company("lmstudio", "LM Studio",
        "Desktop app for discovering, downloading and running open-source LLMs locally with a ChatGPT-like interface.",
        ["Open Source", "LLM", "Consumer AI"],
        "https://lmstudio.ai", "No disclosed funding", "N/A", 2023, "San Francisco, CA",
        source="seed"),

    # ── Seed Stage ────────────────────────────────────────────────────────────
    Company("hedra", "Hedra",
        "AI character video generation startup that animates any portrait with voice — viral for creating talking AI avatars.",
        ["Video Generation", "Generative AI", "Creative AI"],
        "https://hedra.com", "Seed — $10M (2024)", "Undisclosed", 2023, "San Francisco, CA",
        source="seed"),
    Company("udio", "Udio",
        "AI music generation platform that creates full songs with vocals and instrumentation from a text prompt.",
        ["Audio AI", "Generative AI", "Creative AI"],
        "https://udio.com", "Seed — $10M (Apr 2024)", "Undisclosed", 2024, "New York, NY",
        source="seed"),
    Company("cartesia", "Cartesia",
        "Real-time voice AI startup building ultra-low-latency speech synthesis models for interactive AI applications.",
        ["NLP / Speech", "AI Infrastructure", "Generative AI"],
        "https://cartesia.ai", "Series A — $36M (2024)", "Undisclosed", 2023, "San Francisco, CA",
        source="seed"),
    Company("nous_research", "Nous Research",
        "Open-source AI research collective building high-performance fine-tuned LLMs; known for Hermes and Capybara model series.",
        ["LLM", "Open Source", "Research", "Foundation Models"],
        "https://nousresearch.com", "No disclosed funding", "N/A", 2022, "San Francisco, CA",
        source="seed"),

    # ── Series A ──────────────────────────────────────────────────────────────
    Company("langchain", "LangChain",
        "Most widely used open-source framework for building LLM-powered applications, RAG pipelines, and AI agents.",
        ["AI Agents", "MLOps / Infrastructure", "Open Source", "LLM"],
        "https://langchain.com", "Series A — $25M (2023)", "$200M", 2022, "San Francisco, CA",
        source="seed"),
    Company("llamaindex", "LlamaIndex",
        "Data framework for connecting custom data sources to LLMs — the go-to tool for building RAG and agentic apps.",
        ["AI Infrastructure", "MLOps / Infrastructure", "Open Source", "LLM"],
        "https://llamaindex.ai", "Series A — $18.7M (2024)", "Undisclosed", 2022, "San Francisco, CA",
        source="seed"),
    Company("crewai", "CrewAI",
        "Open-source multi-agent orchestration framework for building collaborative AI agent teams to automate complex workflows.",
        ["AI Agents", "Open Source", "MLOps / Infrastructure"],
        "https://crewai.com", "Series A — $18M (2024)", "Undisclosed", 2023, "San Francisco, CA",
        source="seed"),
    Company("cursor", "Cursor",
        "AI-first code editor built on VSCode, with deep codebase understanding and multi-file editing — fastest-growing dev tool in 2024.",
        ["AI Coding", "AI Agents", "Enterprise AI"],
        "https://cursor.com", "Series B — $60M (Aug 2024)", "$400M", 2022, "San Francisco, CA",
        source="seed"),

    # ── Smaller Series B / C ──────────────────────────────────────────────────
    Company("heyg", "HeyGen",
        "AI video platform that creates personalised avatar videos from text — widely used for marketing, sales, and training content.",
        ["Video Generation", "Generative AI", "Enterprise AI"],
        "https://heygen.com", "Series A — $60M (Nov 2023)", "$500M", 2020, "Los Angeles, CA",
        source="seed"),
    Company("replicate", "Replicate",
        "Cloud platform for running open-source AI models via a simple API — supports Stable Diffusion, Llama, Whisper and thousands more.",
        ["AI Infrastructure", "Open Source", "MLOps / Infrastructure"],
        "https://replicate.com", "Series B — $40M (2023)", "$350M", 2019, "San Francisco, CA",
        source="seed"),
    Company("suno", "Suno AI",
        "AI music generation platform that creates radio-quality full songs with lyrics and vocals from a short text prompt.",
        ["Audio AI", "Generative AI", "Creative AI"],
        "https://suno.com", "Series B — $125M (May 2024)", "$500M", 2022, "Cambridge, MA",
        source="seed"),
    Company("luma_ai", "Luma AI",
        "AI video and 3D generation startup behind Dream Machine — creates cinematic video clips from text or image prompts.",
        ["Video Generation", "Generative AI", "Computer Vision"],
        "https://lumalabs.ai", "Series B — $43M (Jan 2024)", "$200M", 2021, "San Jose, CA",
        source="seed"),
    Company("synthesia", "Synthesia",
        "Enterprise AI video platform that generates professional presenter-led videos from text in 120+ languages — no camera needed.",
        ["Video Generation", "Enterprise AI", "NLP / Speech"],
        "https://synthesia.io", "Series C — $90M (Jun 2023)", "$1B", 2017, "London, UK",
        source="seed"),
    Company("descript", "Descript",
        "AI-powered audio and video editor where you edit media by editing text — used by podcasters, YouTubers, and marketers.",
        ["Audio AI", "Video Generation", "Creative AI"],
        "https://descript.com", "Series C — $100M (2022)", "Undisclosed", 2017, "San Francisco, CA",
        source="seed"),
    Company("assemblyai", "AssemblyAI",
        "Speech AI API platform offering transcription, speaker detection, sentiment analysis, and summarisation at scale.",
        ["NLP / Speech", "AI Infrastructure", "Enterprise AI"],
        "https://assemblyai.com", "Series C — $115M (2023)", "Undisclosed", 2017, "San Francisco, CA",
        source="seed"),
    Company("deepgram", "Deepgram",
        "AI speech recognition platform with best-in-class accuracy and speed, purpose-built for developers and enterprises.",
        ["NLP / Speech", "AI Infrastructure", "Foundation Models"],
        "https://deepgram.com", "Series B — $86M (2022)", "Undisclosed", 2015, "San Francisco, CA",
        source="seed"),
]


# ─── Agent 1: Discovery ───────────────────────────────────────────────────────

FUNDING_RE = re.compile(
    r"(?P<name>[A-Z][A-Za-z0-9 &.'-]{2,40}?)\s+"
    r"(?:raises?|secures?|closes?|lands?|bags?)\s+"
    r"\$(?P<amount>[\d,.]+)\s*(?P<unit>[MB])",
    re.IGNORECASE,
)
AI_KEYWORDS = re.compile(
    r"\b(AI|artificial intelligence|machine learning|LLM|neural|GPT|"
    r"generative|deep learning|foundation model|autonomous|robotics)\b",
    re.IGNORECASE,
)

class DiscoveryAgent:
    """Scans RSS feeds and extracts AI company funding mentions."""

    def run(self) -> list[Company]:
        discovered: list[Company] = []
        for feed_url in RSS_FEEDS:
            try:
                log.info(f"[DiscoveryAgent] Fetching {feed_url}")
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    text = (entry.get("title", "") + " " + entry.get("summary", ""))
                    if not AI_KEYWORDS.search(text):
                        continue
                    m = FUNDING_RE.search(text)
                    if m:
                        company_name = m.group("name").strip()
                        amount = m.group("amount")
                        unit = m.group("unit").upper()
                        company_id = re.sub(r"\W+", "_", company_name.lower()).strip("_")
                        link = entry.get("link", "")
                        c = Company(
                            id=company_id,
                            name=company_name,
                            description=f"AI company. Source: {entry.get('title', '')}",
                            tags=["Generative AI"],
                            website=link,
                            last_funding=f"${amount}{unit} (from news)",
                            valuation="Unknown",
                            source="rss",
                        )
                        discovered.append(c)
                        log.info(f"[DiscoveryAgent] Found: {company_name} — ${amount}{unit}")
            except Exception as e:
                log.warning(f"[DiscoveryAgent] Feed error {feed_url}: {e}")
        return discovered


# ─── Agent 2: Enrichment ─────────────────────────────────────────────────────

class EnrichmentAgent:
    """Fetches meta description from company homepage."""

    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AITrackerBot/1.0)"}
    TIMEOUT = 6

    def enrich(self, company: Company) -> Company:
        if company.source == "seed" or not company.website.startswith("http"):
            return company
        try:
            r = requests.get(company.website, headers=self.HEADERS,
                             timeout=self.TIMEOUT, allow_redirects=True)
            soup = BeautifulSoup(r.text, "html.parser")
            meta = (
                soup.find("meta", attrs={"name": "description"})
                or soup.find("meta", attrs={"property": "og:description"})
            )
            if meta and meta.get("content"):
                desc = meta["content"].strip()[:300]
                if len(desc) > 30:
                    company.description = desc
        except Exception as e:
            log.debug(f"[EnrichmentAgent] Could not enrich {company.name}: {e}")
        return company


# ─── Agent 3: Classification ─────────────────────────────────────────────────

TAG_RULES = [
    (re.compile(r"\b(robot|humanoid|physical)\b", re.I), "Robotics"),
    (re.compile(r"\b(driv|autonomous vehicle|self.driving|waymo)\b", re.I), "Autonomous Vehicles"),
    (re.compile(r"\b(chip|hardware|wafer|GPU|TPU|LPU|semiconductor)\b", re.I), "AI Chips / Hardware"),
    (re.compile(r"\b(health|medical|clinical|drug|radiology|genomic)\b", re.I), "AI for Healthcare"),
    (re.compile(r"\b(legal|law firm|contract|litigation|compliance)\b", re.I), "AI for Legal"),
    (re.compile(r"\b(financ|trading|risk|fraud|banking|insuranc)\b", re.I), "AI for Finance"),
    (re.compile(r"\b(video|film|cinematic|animation)\b", re.I), "Video Generation"),
    (re.compile(r"\b(voice|speech|text.to.speech|TTS|audio)\b", re.I), "NLP / Speech"),
    (re.compile(r"\b(image|vision|visual|photo|diffusion)\b", re.I), "Computer Vision"),
    (re.compile(r"\b(code|coding|software engineer|developer|IDE)\b", re.I), "AI Coding"),
    (re.compile(r"\b(agent|autonomous|workflow|task)\b", re.I), "AI Agents"),
    (re.compile(r"\b(vector|embedding|retrieval|RAG|search)\b", re.I), "AI Infrastructure"),
    (re.compile(r"\b(safety|alignment|interpretab|reliable)\b", re.I), "AI Safety"),
    (re.compile(r"\b(open.source|open weight|open model)\b", re.I), "Open Source"),
    (re.compile(r"\b(enterprise|B2B|business)\b", re.I), "Enterprise AI"),
]

class ClassificationAgent:
    """Adds/updates tags on a company based on its description."""

    def classify(self, company: Company) -> Company:
        text = company.description + " " + " ".join(company.tags)
        extra_tags = [tag for pattern, tag in TAG_RULES if pattern.search(text)]
        combined = list(dict.fromkeys(company.tags + extra_tags))  # deduplicate, preserve order
        company.tags = combined[:6]  # cap at 6 tags
        return company


# ─── Agent 4: Deduplication ──────────────────────────────────────────────────

class DeduplicationAgent:
    """Merges an incoming list with existing records, preferring seed data."""

    def merge(self, existing: list[Company], incoming: list[Company]) -> list[Company]:
        registry: dict[str, Company] = {c.id: c for c in existing}
        for c in incoming:
            if c.id in registry:
                existing_c = registry[c.id]
                # Prefer seed over rss; never downgrade
                if existing_c.source == "seed" and c.source == "rss":
                    continue
                # Update description if the incoming one is richer
                if len(c.description) > len(existing_c.description):
                    existing_c.description = c.description
            else:
                registry[c.id] = c
        return list(registry.values())


# ─── Orchestrator ────────────────────────────────────────────────────────────

class CrawlerOrchestrator:
    """Runs the full discovery → enrichment → classification → dedup pipeline."""

    def __init__(self):
        self.discovery = DiscoveryAgent()
        self.enrichment = EnrichmentAgent()
        self.classification = ClassificationAgent()
        self.dedup = DeduplicationAgent()

    def run(self):
        log.info("=== Crawl cycle started ===")
        existing = _load()
        if not existing:
            existing = SEED_COMPANIES[:]

        discovered = self.discovery.run()
        enriched = [self.enrichment.enrich(c) for c in discovered]
        classified_new = [self.classification.classify(c) for c in enriched]
        seed_classified = [self.classification.classify(c) for c in SEED_COMPANIES]

        merged = self.dedup.merge(seed_classified, classified_new)
        merged.sort(key=lambda c: c.name.lower())

        _save(merged)
        log.info(f"=== Crawl done — {len(merged)} companies ===")
        return merged


# ─── Storage helpers ─────────────────────────────────────────────────────────

def _load() -> list[Company]:
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE) as f:
        data = json.load(f)
    return [Company.from_dict(d) for d in data.get("companies", [])]


def _save(companies: list[Company]):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    payload = {
        "metadata": {
            "last_crawl": datetime.now(timezone.utc).isoformat(),
            "count": len(companies),
        },
        "companies": [c.to_dict() for c in companies],
    }
    with open(DATA_FILE, "w") as f:
        json.dump(payload, f, indent=2)


def load_all():
    """Public helper used by app.py."""
    if not os.path.exists(DATA_FILE):
        return {"metadata": {}, "companies": []}
    with open(DATA_FILE) as f:
        return json.load(f)
