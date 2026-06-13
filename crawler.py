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
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "companies.json")

RSS_FEEDS = [
    # ── Funding & Startup News ────────────────────────────────────────────
    "https://news.crunchbase.com/feed/",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://techcrunch.com/tag/funding/feed/",
    "https://techcrunch.com/category/startups/feed/",

    # ── AI-Specific Publications ──────────────────────────────────────────
    "https://venturebeat.com/category/ai/feed/",
    "https://artificialintelligence-news.com/feed/",
    "https://aibusiness.com/rss.xml",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://www.technologyreview.com/feed/",
    "https://www.wired.com/feed/tag/ai/rss",

    # ── VC & Investor Blogs ───────────────────────────────────────────────
    "https://a16z.com/feed/",
    "https://www.ycombinator.com/blog/rss",
    "https://review.firstround.com/feed.xml",

    # ── General Tech (strong AI coverage) ────────────────────────────────
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://siliconangle.com/feed/",
    "https://feeds.reuters.com/reuters/technologyNews",

    # ── AI Research & Community ───────────────────────────────────────────
    "https://blog.research.google/feeds/posts/default",
    "https://huggingface.co/blog/feed.xml",

    # ── More AI-Focused News & Newsletters ──────────────────────────────────
    "https://www.unite.ai/feed/",
    "https://www.marktechpost.com/feed/",
    "https://syncedreview.com/feed/",
    "https://bdtechtalks.com/feed/",
    "https://www.maginative.com/feed/",
    "https://therundown.ai/feed",
    "https://www.therobotreport.com/feed/",
    "https://www.calcalistech.com/ct/rss/0,7340,L-3791,00.xml",
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

    # ── AI for Healthcare ─────────────────────────────────────────────────────
    Company("tempus_ai", "Tempus AI",
        "AI-enabled precision medicine platform that analyzes clinical and molecular data to personalize cancer care.",
        ["AI for Healthcare", "Genomics", "Data & Labelling"],
        "https://tempus.com", "IPO (Jun 2024)", "$8.1B", 2015, "Chicago, IL", source="seed"),
    Company("abridge", "Abridge",
        "AI medical scribe that turns patient-clinician conversations into structured clinical notes in real time.",
        ["AI for Healthcare", "NLP / Speech", "Enterprise AI"],
        "https://abridge.com", "Series E — $250M (Feb 2025)", "$2.75B", 2018, "Pittsburgh, PA", source="seed"),
    Company("hippocratic_ai", "Hippocratic AI",
        "Safety-focused LLM platform building generative AI healthcare agents for patient-facing, non-diagnostic tasks.",
        ["AI for Healthcare", "LLM", "AI Agents"],
        "https://hippocraticai.com", "Series B — $141M (Mar 2024)", "$1.6B", 2023, "Palo Alto, CA", source="seed"),
    Company("insitro", "Insitro",
        "Machine learning-driven drug discovery company combining biology and ML to industrialize therapeutic development.",
        ["AI for Healthcare", "Foundation Models", "Drug Discovery"],
        "https://insitro.com", "Series D — $400M (2021)", "$3.5B", 2018, "South San Francisco, CA", source="seed"),
    Company("xaira_therapeutics", "Xaira Therapeutics",
        "AI-driven drug discovery company applying generative models to design and develop novel therapeutics.",
        ["AI for Healthcare", "Foundation Models", "Drug Discovery"],
        "https://xaira.com", "Series A — $1B (Apr 2024)", "$1B+", 2024, "South San Francisco, CA", source="seed"),
    Company("isomorphic_labs", "Isomorphic Labs",
        "Alphabet spinout using AlphaFold-derived AI models to accelerate drug design and discovery.",
        ["AI for Healthcare", "Foundation Models", "Drug Discovery"],
        "https://isomorphiclabs.com", "Series A — $600M (Mar 2025)", "Undisclosed", 2021, "London, UK", source="seed"),
    Company("pathai", "PathAI",
        "AI-powered pathology platform that improves diagnostic accuracy and supports drug development with digital pathology.",
        ["AI for Healthcare", "Computer Vision"],
        "https://pathai.com", "Series D — $165M (2021)", "$1.5B", 2016, "Boston, MA", source="seed"),
    Company("ambience_healthcare", "Ambience Healthcare",
        "Ambient AI documentation platform that generates clinical notes and coding automatically during patient visits.",
        ["AI for Healthcare", "NLP / Speech", "Enterprise AI"],
        "https://ambiencehealthcare.com", "Series C — $243M (Apr 2025)", "$1.25B", 2020, "San Francisco, CA", source="seed"),
    Company("openevidence", "OpenEvidence",
        "AI-powered medical reference platform giving clinicians evidence-based answers grounded in peer-reviewed research.",
        ["AI for Healthcare", "LLM", "Enterprise AI"],
        "https://openevidence.com", "Series B — $210M (Feb 2025)", "$3.5B", 2023, "Miami, FL", source="seed"),

    # ── AI for Finance ────────────────────────────────────────────────────────
    Company("hebbia", "Hebbia",
        "AI platform for financial and legal research that lets analysts query large document sets in natural language.",
        ["AI for Finance", "Enterprise AI", "LLM"],
        "https://hebbia.ai", "Series B — $130M (2024)", "$700M", 2020, "New York, NY", source="seed"),
    Company("ramp", "Ramp",
        "AI-powered corporate card and spend management platform that automates expense tracking and finance operations.",
        ["AI for Finance", "Enterprise AI", "Fintech"],
        "https://ramp.com", "Series E — $150M (Mar 2025)", "$13B", 2019, "New York, NY", source="seed"),
    Company("alphasense", "AlphaSense",
        "AI-powered market intelligence search engine used by financial professionals to analyze company and market data.",
        ["AI for Finance", "AI Search", "Enterprise AI"],
        "https://alpha-sense.com", "Series F — $650M (Jun 2024)", "$4B", 2011, "New York, NY", source="seed"),
    Company("numerai", "Numerai",
        "AI hedge fund that crowdsources machine learning models from a global community of data scientists.",
        ["AI for Finance", "Data & Labelling"],
        "https://numer.ai", "Series A — $13M (2024)", "Undisclosed", 2015, "San Francisco, CA", source="seed"),
    Company("tractable", "Tractable",
        "AI that uses computer vision to assess vehicle and property damage for insurers, speeding up claims processing.",
        ["AI for Finance", "Computer Vision", "Enterprise AI"],
        "https://tractable.ai", "Series E — $65M (2024)", "$1B", 2014, "London, UK", source="seed"),

    # ── AI for Legal ──────────────────────────────────────────────────────────
    Company("ironclad", "Ironclad",
        "AI-powered contract lifecycle management platform used by enterprises to draft, negotiate, and manage contracts.",
        ["AI for Legal", "Enterprise AI"],
        "https://ironcladapp.com", "Series F — $150M (2021)", "$3.2B", 2014, "San Francisco, CA", source="seed"),
    Company("robin_ai", "Robin AI",
        "AI-powered contract review and drafting platform that helps legal teams negotiate agreements faster.",
        ["AI for Legal", "LLM", "Enterprise AI"],
        "https://robinai.com", "Series B — $26M (2023)", "Undisclosed", 2019, "London, UK", source="seed"),
    Company("spellbook", "Spellbook",
        "AI contract drafting and review assistant built for lawyers, integrated directly into Microsoft Word.",
        ["AI for Legal", "LLM", "Enterprise AI"],
        "https://spellbook.legal", "Series A — $20M (2024)", "Undisclosed", 2018, "Toronto, Canada", source="seed"),

    # ── AI Security ───────────────────────────────────────────────────────────
    Company("protect_ai", "Protect AI",
        "AI/ML security platform that helps enterprises secure machine learning models, pipelines, and supply chains.",
        ["AI Security", "Enterprise AI", "MLOps / Infrastructure"],
        "https://protectai.com", "Series B — $35M (2024)", "Undisclosed", 2022, "Seattle, WA", source="seed"),
    Company("hiddenlayer", "HiddenLayer",
        "Security platform for AI models, providing MLSecOps tooling to detect and prevent attacks on ML systems.",
        ["AI Security", "MLOps / Infrastructure"],
        "https://hiddenlayer.com", "Series A — $50M (2024)", "Undisclosed", 2022, "Austin, TX", source="seed"),
    Company("lakera", "Lakera",
        "AI security platform that protects LLM applications from prompt injection, data leakage, and abuse.",
        ["AI Security", "LLM", "Enterprise AI"],
        "https://lakera.ai", "Seed — $5.5M (2023)", "Undisclosed", 2021, "Zurich, Switzerland", source="seed"),
    Company("abnormal_security", "Abnormal Security",
        "AI-native email security platform that detects and stops sophisticated phishing and social engineering attacks.",
        ["AI Security", "Enterprise AI"],
        "https://abnormalsecurity.com", "Series D — $250M (Jul 2024)", "$5.1B", 2018, "San Francisco, CA", source="seed"),

    # ── AI Search & Web Agents ────────────────────────────────────────────────
    Company("glean", "Glean",
        "Enterprise AI search and assistant platform that connects to company knowledge sources to answer employee questions.",
        ["AI Search", "Enterprise AI", "LLM"],
        "https://glean.com", "Series F — $260M (Jun 2025)", "$7.2B", 2019, "Palo Alto, CA", source="seed"),
    Company("you_com", "You.com",
        "AI search engine that combines chat, web search, and generative AI into a single productivity platform.",
        ["AI Search", "LLM", "Consumer AI"],
        "https://you.com", "Series B — $50M (2024)", "$1.5B", 2020, "Palo Alto, CA", source="seed"),
    Company("exa", "Exa",
        "AI-native search API designed for LLMs and AI agents to retrieve high-quality web content.",
        ["AI Search", "AI Infrastructure", "AI Agents"],
        "https://exa.ai", "Series A — $17M (2024)", "Undisclosed", 2021, "San Francisco, CA", source="seed"),
    Company("browserbase", "Browserbase",
        "Headless browser infrastructure that lets AI agents reliably navigate and interact with websites.",
        ["AI Infrastructure", "AI Agents"],
        "https://browserbase.com", "Series B — $40M (2025)", "Undisclosed", 2023, "San Francisco, CA", source="seed"),
    Company("firecrawl", "Firecrawl",
        "Open-source web scraping API that turns websites into clean, LLM-ready data for AI applications.",
        ["AI Infrastructure", "AI Agents", "Open Source"],
        "https://firecrawl.dev", "Seed — $7M (2024)", "Undisclosed", 2023, "San Francisco, CA", source="seed"),
    Company("genspark", "Genspark",
        "AI agent platform that autonomously researches and completes tasks using multiple specialized AI agents.",
        ["AI Agents", "AI Search", "Consumer AI"],
        "https://genspark.ai", "Seed — $60M (2025)", "$530M", 2024, "Palo Alto, CA", source="seed"),

    # ── AI Coding ─────────────────────────────────────────────────────────────
    Company("replit", "Replit",
        "AI-powered collaborative coding platform that lets anyone build and deploy software from natural language.",
        ["AI Coding", "Enterprise AI", "LLM"],
        "https://replit.com", "Series B — $97M (2023)", "$1.16B", 2016, "San Francisco, CA", source="seed"),
    Company("magic_dev", "Magic AI",
        "AI research lab building long-context foundation models for fully autonomous software engineering.",
        ["AI Coding", "Foundation Models", "LLM"],
        "https://magic.dev", "Series B — $320M (Aug 2024)", "$1.5B", 2022, "San Francisco, CA", source="seed"),
    Company("codeium", "Codeium (Windsurf)",
        "AI coding assistant and AI-native IDE that helps developers write, refactor, and understand code faster.",
        ["AI Coding", "Enterprise AI", "LLM"],
        "https://codeium.com", "Series C — $150M (2024)", "$1.25B", 2021, "Mountain View, CA", source="seed"),
    Company("tabnine", "Tabnine",
        "AI code completion and assistant tool focused on private, enterprise-grade software development.",
        ["AI Coding", "Enterprise AI"],
        "https://tabnine.com", "Series B — $20M (2021)", "Undisclosed", 2013, "Tel Aviv, Israel", source="seed"),
    Company("augment_code", "Augment Code",
        "AI coding assistant designed to deeply understand large, complex enterprise codebases.",
        ["AI Coding", "Enterprise AI", "LLM"],
        "https://augmentcode.com", "Series B — $227M (2024)", "$977M", 2022, "Palo Alto, CA", source="seed"),
    Company("lovable", "Lovable",
        "AI app builder that lets anyone create and deploy full-stack web applications from natural language prompts.",
        ["AI Coding", "Enterprise AI", "Consumer AI"],
        "https://lovable.dev", "Series A — $15M (2024)", "$1.8B", 2023, "Stockholm, Sweden", source="seed"),

    # ── AI Agents ─────────────────────────────────────────────────────────────
    Company("adept_ai", "Adept AI",
        "AI research company building agents that can take actions in software by observing and operating UIs.",
        ["AI Agents", "Foundation Models", "LLM"],
        "https://adept.ai", "Series B — $350M (2023)", "$1B", 2022, "San Francisco, CA", source="seed"),
    Company("lindy_ai", "Lindy AI",
        "No-code platform for building AI agents that automate business workflows across email, calendar, and apps.",
        ["AI Agents", "Enterprise AI", "Automation"],
        "https://lindy.ai", "Series A — $50M (2024)", "Undisclosed", 2023, "San Francisco, CA", source="seed"),
    Company("decagon", "Decagon AI",
        "AI customer support agents that resolve complex customer issues across chat, email, and voice.",
        ["AI Agents", "Customer Service AI", "Enterprise AI"],
        "https://decagon.ai", "Series B — $131M (2025)", "$1.5B", 2023, "San Francisco, CA", source="seed"),
    Company("moveworks", "Moveworks",
        "Enterprise AI copilot and agent platform that automates IT, HR, and employee support workflows.",
        ["AI Agents", "Enterprise AI", "LLM"],
        "https://moveworks.com", "Series C — $200M (2021)", "$2.1B", 2016, "Mountain View, CA", source="seed"),
    Company("manus_ai", "Manus AI",
        "General-purpose AI agent that autonomously plans and executes multi-step tasks across the web and software.",
        ["AI Agents", "LLM"],
        "https://manus.im", "Series B — $75M (2025)", "$500M", 2024, "Singapore", source="seed"),
    Company("bland_ai", "Bland AI",
        "AI phone agent platform that automates inbound and outbound business calls with human-like voice agents.",
        ["AI Agents", "NLP / Speech", "Customer Service AI"],
        "https://bland.ai", "Series A — $40M (2024)", "$400M", 2023, "San Francisco, CA", source="seed"),
    Company("vapi", "Vapi",
        "Developer platform and infrastructure for building, testing, and deploying voice AI agents.",
        ["AI Infrastructure", "NLP / Speech", "AI Agents"],
        "https://vapi.ai", "Series A — $20M (2024)", "Undisclosed", 2023, "San Francisco, CA", source="seed"),
    Company("eleven_x", "11x",
        "AI-powered digital workers that autonomously perform outbound sales and go-to-market tasks for businesses.",
        ["AI Agents", "Enterprise AI"],
        "https://11x.ai", "Series B — $50M (2024)", "$350M", 2022, "London, UK", source="seed"),

    # ── Data & Labelling ──────────────────────────────────────────────────────
    Company("snorkel_ai", "Snorkel AI",
        "Data-centric AI platform that lets enterprises programmatically label and manage training data at scale.",
        ["Data & Labelling", "MLOps / Infrastructure", "Enterprise AI"],
        "https://snorkel.ai", "Series D — $85M (2022)", "$1B", 2019, "Redwood City, CA", source="seed"),
    Company("labelbox", "Labelbox",
        "Training data platform for building, managing, and improving datasets used to train AI models.",
        ["Data & Labelling", "MLOps / Infrastructure"],
        "https://labelbox.com", "Series D — $40M (2025)", "Undisclosed", 2018, "San Francisco, CA", source="seed"),
    Company("surge_ai", "Surge AI",
        "Data labelling platform specializing in high-quality human feedback (RLHF) for training large language models.",
        ["Data & Labelling", "MLOps / Infrastructure"],
        "https://surgehq.ai", "Bootstrapped — No VC", "$1B+", 2020, "San Francisco, CA", source="seed"),

    # ── AI Infrastructure & MLOps ─────────────────────────────────────────────
    Company("anyscale", "Anyscale",
        "Distributed computing platform built around the open-source Ray framework for scaling AI workloads.",
        ["AI Infrastructure", "MLOps / Infrastructure", "Open Source"],
        "https://anyscale.com", "Series D — $100M (2021)", "$1B", 2019, "San Francisco, CA", source="seed"),
    Company("baseten", "Baseten",
        "Infrastructure platform for deploying and serving custom AI models in production with low latency.",
        ["AI Infrastructure", "MLOps / Infrastructure"],
        "https://baseten.co", "Series B — $40M (2024)", "Undisclosed", 2019, "San Francisco, CA", source="seed"),
    Company("fireworks_ai", "Fireworks AI",
        "Generative AI inference platform offering fast, cost-efficient hosting for open-source and custom models.",
        ["AI Infrastructure", "MLOps / Infrastructure", "Open Source"],
        "https://fireworks.ai", "Series B — $52M (2024)", "$552M", 2022, "San Francisco, CA", source="seed"),
    Company("lambda_labs", "Lambda",
        "GPU cloud computing provider purpose-built for AI training and inference workloads.",
        ["AI Infrastructure", "Cloud AI", "AI Chips / Hardware"],
        "https://lambdalabs.com", "Series D — $480M (Feb 2025)", "$2.5B", 2012, "San Francisco, CA", source="seed"),
    Company("coreweave", "CoreWeave",
        "Specialized cloud provider delivering large-scale GPU infrastructure for AI training and inference.",
        ["AI Infrastructure", "Cloud AI", "AI Chips / Hardware"],
        "https://coreweave.com", "IPO (Mar 2025)", "$23B", 2017, "Roseland, NJ", source="seed"),
    Company("vast_ai", "Vast.ai",
        "Marketplace for renting GPU compute from data centers and individuals at low cost for AI workloads.",
        ["AI Infrastructure", "Cloud AI"],
        "https://vast.ai", "Series A — $15M (2024)", "Undisclosed", 2018, "New York, NY", source="seed"),
    Company("articul8", "Articul8 AI",
        "Enterprise generative AI platform that builds and deploys domain-specific AI models and agents.",
        ["Enterprise AI", "LLM", "Foundation Models"],
        "https://articul8.ai", "Series A — $22.5M (Mar 2025)", "Undisclosed", 2024, "Santa Clara, CA", source="seed"),

    # ── AI Chips & Hardware ───────────────────────────────────────────────────
    Company("sambanova", "SambaNova Systems",
        "AI chip and systems company providing full-stack hardware and software for enterprise model deployment.",
        ["AI Chips / Hardware", "AI Infrastructure"],
        "https://sambanova.ai", "Series D — $676M (2021)", "$5B", 2017, "Palo Alto, CA", source="seed"),
    Company("tenstorrent", "Tenstorrent",
        "AI processor design company building scalable, open RISC-V based AI accelerators.",
        ["AI Chips / Hardware", "AI Infrastructure"],
        "https://tenstorrent.com", "Series D — $693M (Dec 2024)", "$2.6B", 2016, "Toronto, Canada", source="seed"),
    Company("d_matrix", "d-Matrix",
        "AI chiplet and inference compute company designing hardware optimized for generative AI workloads.",
        ["AI Chips / Hardware", "AI Infrastructure"],
        "https://d-matrix.ai", "Series C — $110M (2024)", "$2B", 2019, "Santa Clara, CA", source="seed"),
    Company("etched", "Etched",
        "AI chip company building ASICs specialized exclusively for running transformer models.",
        ["AI Chips / Hardware", "AI Infrastructure"],
        "https://etched.com", "Series A — $120M (Jun 2024)", "$1.5B", 2022, "Cupertino, CA", source="seed"),
    Company("positron_ai", "Positron AI",
        "AI inference hardware company building energy-efficient accelerators for large language model serving.",
        ["AI Chips / Hardware", "AI Infrastructure"],
        "https://positron.ai", "Series A — $51M (2024)", "Undisclosed", 2023, "Palo Alto, CA", source="seed"),

    # ── Robotics & Autonomous Vehicles ────────────────────────────────────────
    Company("skild_ai", "Skild AI",
        "Building general-purpose robotics foundation models that can power any robot for any task.",
        ["Robotics", "Foundation Models", "AI Agents"],
        "https://skild.ai", "Series A — $300M (Jul 2024)", "$1.5B", 2023, "Pittsburgh, PA", source="seed"),
    Company("one_x_technologies", "1X Technologies",
        "Humanoid robotics company developing general-purpose androids for home and labor tasks.",
        ["Robotics", "Foundation Models", "Autonomous Systems"],
        "https://1x.tech", "Series B — $100M (Jan 2024)", "Undisclosed", 2014, "Moss, Norway", source="seed"),
    Company("apptronik", "Apptronik",
        "Humanoid robotics company building the Apollo robot for industrial and logistics applications.",
        ["Robotics", "Foundation Models", "Autonomous Systems"],
        "https://apptronik.com", "Series A — $350M (Feb 2025)", "Undisclosed", 2016, "Austin, TX", source="seed"),
    Company("covariant", "Covariant",
        "AI robotics company building foundation models that give warehouse robots human-like perception and dexterity.",
        ["Robotics", "Foundation Models", "Computer Vision"],
        "https://covariant.ai", "Series D — $222M (2022)", "$1.5B", 2017, "Berkeley, CA", source="seed"),
    Company("field_ai", "Field AI",
        "Robot foundation model company building field-deployable AI for industrial and infrastructure robots.",
        ["Robotics", "Foundation Models"],
        "https://fieldai.com", "Series A — $405M (2025)", "$2B", 2023, "Mission Viejo, CA", source="seed"),
    Company("waabi", "Waabi",
        "Generative AI company building a simulation-first approach to autonomous trucking technology.",
        ["Autonomous Vehicles", "Foundation Models", "Robotics"],
        "https://waabi.ai", "Series B — $200M (2024)", "Undisclosed", 2021, "Toronto, Canada", source="seed"),
    Company("nuro", "Nuro",
        "Autonomous vehicle company building self-driving delivery robots and licensing its driving technology.",
        ["Autonomous Vehicles", "Robotics", "Computer Vision"],
        "https://nuro.ai", "Series E — $106M (2024)", "$6B", 2016, "Mountain View, CA", source="seed"),
    Company("aurora_innovation", "Aurora Innovation",
        "Publicly traded self-driving technology company focused on autonomous trucking.",
        ["Autonomous Vehicles", "Foundation Models"],
        "https://aurora.tech", "Public (Nasdaq: AUR)", "$10B+", 2017, "Pittsburgh, PA", source="seed"),

    # ── Generative Media ──────────────────────────────────────────────────────
    Company("black_forest_labs", "Black Forest Labs",
        "AI research lab and creator of the FLUX family of open-weight image generation models.",
        ["Image Generation", "Generative AI", "Open Source"],
        "https://blackforestlabs.ai", "Seed — $31M (Aug 2024)", "Undisclosed", 2024, "Freiburg, Germany", source="seed"),
    Company("ideogram", "Ideogram",
        "AI image generation platform known for accurately rendering text and typography within images.",
        ["Image Generation", "Generative AI", "Creative AI"],
        "https://ideogram.ai", "Series A — $80M (2024)", "$1B+", 2022, "Toronto, Canada", source="seed"),
    Company("krea", "Krea AI",
        "Real-time AI tools for generating and editing images and video for designers and creators.",
        ["Image Generation", "Video Generation", "Creative AI"],
        "https://krea.ai", "Series A — $83M (2025)", "Undisclosed", 2022, "San Francisco, CA", source="seed"),
    Company("genmo", "Genmo",
        "AI research lab building open video generation models, including the Mochi model family.",
        ["Video Generation", "Generative AI", "Open Source"],
        "https://genmo.ai", "Seed — $28.4M (2024)", "Undisclosed", 2021, "San Francisco, CA", source="seed"),
    Company("stability_ai", "Stability AI",
        "Open generative AI company behind Stable Diffusion and other foundation models for image, audio, and video.",
        ["Image Generation", "Generative AI", "Open Source", "Foundation Models"],
        "https://stability.ai", "Series A — $101M (2023)", "$1B", 2019, "London, UK", source="seed"),
    Company("hume_ai", "Hume AI",
        "AI research company building emotionally intelligent voice interfaces that understand tone and expression.",
        ["NLP / Speech", "Generative AI", "AI Agents"],
        "https://hume.ai", "Series B — $50M (2024)", "$219M", 2021, "New York, NY", source="seed"),
    Company("tavus", "Tavus",
        "AI platform for generating realistic digital twins and personalized video at scale for businesses.",
        ["Video Generation", "AI Agents", "Creative AI"],
        "https://tavus.io", "Series A — $18M (2024)", "Undisclosed", 2020, "San Francisco, CA", source="seed"),
    Company("photoroom", "Photoroom",
        "AI-powered photo editing app that removes backgrounds and creates product photography for e-commerce.",
        ["Image Generation", "Creative AI", "Consumer AI"],
        "https://photoroom.com", "Series B — $43M (2023)", "Undisclosed", 2019, "Paris, France", source="seed"),
    Company("higgsfield_ai", "Higgsfield AI",
        "AI video generation platform focused on cinematic camera control for marketing and creative content.",
        ["Video Generation", "Generative AI", "Creative AI"],
        "https://higgsfield.ai", "Seed — $8M (2024)", "Undisclosed", 2024, "San Francisco, CA", source="seed"),

    # ── Consumer AI ───────────────────────────────────────────────────────────
    Company("inflection_ai", "Inflection AI",
        "AI company that built Pi, a personal AI designed to be supportive and emotionally intelligent.",
        ["LLM", "Consumer AI", "Generative AI"],
        "https://inflection.ai", "Series A — $1.3B (2023)", "$4B", 2022, "Palo Alto, CA", source="seed"),
    Company("rabbit_inc", "Rabbit Inc",
        "Consumer hardware and AI company that built the r1, a pocket AI assistant device.",
        ["Consumer AI", "AI Agents", "Hardware"],
        "https://rabbit.tech", "Series A — $30M (2024)", "Undisclosed", 2021, "Santa Monica, CA", source="seed"),

    # ── AI for Education, HR & Sales ──────────────────────────────────────────
    Company("speak", "Speak",
        "AI-powered language learning app that gives users real-time speaking practice and feedback.",
        ["AI for Education", "NLP / Speech", "Consumer AI"],
        "https://speak.com", "Series C — $78M (2024)", "$1B", 2016, "Seoul, South Korea", source="seed"),
    Company("sana_labs", "Sana Labs",
        "AI-powered learning and knowledge platform that personalizes training content for enterprises.",
        ["AI for Education", "Enterprise AI", "LLM"],
        "https://sanalabs.com", "Series C — $65M (2023)", "Undisclosed", 2016, "Stockholm, Sweden", source="seed"),
    Company("eightfold_ai", "Eightfold AI",
        "AI talent intelligence platform that helps enterprises with hiring, retention, and workforce planning.",
        ["AI for HR", "Enterprise AI", "LLM"],
        "https://eightfold.ai", "Series E — $220M (2021)", "$2.1B", 2016, "Mountain View, CA", source="seed"),
    Company("mercor", "Mercor",
        "AI-powered recruiting marketplace that matches vetted candidates with companies using AI evaluation.",
        ["AI for HR", "Enterprise AI", "AI Agents"],
        "https://mercor.com", "Series B — $100M (2025)", "$2B", 2023, "San Francisco, CA", source="seed"),
    Company("clay", "Clay",
        "AI-powered sales prospecting platform that enriches and personalizes outbound campaigns at scale.",
        ["AI for Sales", "Enterprise AI", "Automation"],
        "https://clay.com", "Series B — $46M (2024)", "$1.25B", 2017, "New York, NY", source="seed"),

    # ── Customer Service AI ───────────────────────────────────────────────────
    Company("ada_cx", "Ada",
        "AI customer service automation platform that resolves support inquiries across chat and messaging channels.",
        ["Customer Service AI", "Enterprise AI", "AI Agents"],
        "https://ada.cx", "Series C — $130M (2021)", "$1.2B", 2016, "Toronto, Canada", source="seed"),
    Company("forethought", "Forethought AI",
        "AI customer support platform that automates ticket resolution and triage for support teams.",
        ["Customer Service AI", "Enterprise AI", "AI Agents"],
        "https://forethought.ai", "Series D — $65M (2022)", "Undisclosed", 2018, "San Francisco, CA", source="seed"),
    Company("cresta", "Cresta",
        "AI platform for contact centers that coaches agents in real time and automates conversations.",
        ["Customer Service AI", "Enterprise AI", "LLM"],
        "https://cresta.com", "Series D — $125M (2024)", "$1.6B", 2017, "San Francisco, CA", source="seed"),

    # ── International Frontier Labs ───────────────────────────────────────────
    Company("deepseek", "DeepSeek",
        "Chinese AI lab developing open-weight frontier large language models known for efficient training techniques.",
        ["LLM", "Foundation Models", "Open Source"],
        "https://deepseek.com", "Backed by High-Flyer (no external VC disclosed)", "Undisclosed", 2023, "Hangzhou, China", source="seed"),
    Company("zhipu_ai", "Zhipu AI (Z.ai)",
        "Chinese foundation model company developing the GLM family of large language models.",
        ["LLM", "Foundation Models"],
        "https://z.ai", "Series E — $400M+ (2024)", "$3B+", 2019, "Beijing, China", source="seed"),
    Company("moonshot_ai", "Moonshot AI",
        "Chinese AI startup developing the Kimi family of long-context large language models.",
        ["LLM", "Foundation Models"],
        "https://moonshot.cn", "Series B — $1B (2024)", "$3.3B", 2023, "Beijing, China", source="seed"),
    Company("zero_one_ai", "01.AI",
        "Chinese foundation model startup founded by Kai-Fu Lee, developer of the open-weight Yi model series.",
        ["LLM", "Foundation Models", "Open Source"],
        "https://01.ai", "Seed — $200M (2023)", "$1B", 2023, "Beijing, China", source="seed"),
    Company("aleph_alpha", "Aleph Alpha",
        "European AI company building sovereign large language models for enterprise and government customers.",
        ["LLM", "Foundation Models", "Enterprise AI"],
        "https://aleph-alpha.com", "Series B — $500M (Nov 2023)", "Undisclosed", 2019, "Heidelberg, Germany", source="seed"),
    Company("h_company", "H Company",
        "European AI lab building foundation models and agents that can autonomously operate software.",
        ["AI Agents", "Foundation Models", "LLM"],
        "https://h.company", "Seed — $220M (May 2024)", "Undisclosed", 2024, "Paris, France", source="seed"),
    Company("sakana_ai", "Sakana AI",
        "Japanese AI research lab developing nature-inspired methods for building efficient foundation models.",
        ["Foundation Models", "Research", "LLM"],
        "https://sakana.ai", "Seed — $30M (2024)", "$1.5B", 2023, "Tokyo, Japan", source="seed"),

    # ── Spatial Intelligence ──────────────────────────────────────────────────
    Company("world_labs", "World Labs",
        "AI research lab founded by Fei-Fei Li building large world models for spatial intelligence and 3D understanding.",
        ["Foundation Models", "Computer Vision", "Research"],
        "https://worldlabs.ai", "Seed — $230M (Sep 2024)", "$1B", 2024, "San Francisco, CA", source="seed"),
    Company("synthflow_ai", "Synthflow AI",
        "No-code platform for building AI voice agents that handle business calls and customer interactions.",
        ["NLP / Speech", "AI Agents", "Enterprise AI"],
        "https://synthflow.ai", "Seed — $4M (2024)", "Undisclosed", 2023, "Berlin, Germany", source="seed"),
]


# ─── Agent 1: Discovery ───────────────────────────────────────────────────────

FUNDING_RE = re.compile(
    r"(?P<name>[A-Z][A-Za-z0-9&.,'-]{1,40}(?:\s+[A-Z][A-Za-z0-9&.,'-]{1,40}){0,3})\s+"
    r"(?:raises?|raised|secures?|secured|closes?|closed|lands?|landed|"
    r"bags?|bagged|nets?|netted|scores?|scored|grabs?|grabbed|"
    r"gets?|got|banks?|pulls? in)\s+"
    r"(?:an?\s+)?(?:additional\s+)?\$(?P<amount>[\d,.]+)\s*"
    r"(?P<unit>million|billion|[MB])\b",
)
AI_KEYWORDS = re.compile(
    r"\b(AI|artificial intelligence|machine learning|LLM|neural|GPT|"
    r"generative|deep learning|foundation model|autonomous|robotics)\b",
    re.IGNORECASE,
)

class DiscoveryAgent:
    """Scans RSS feeds and extracts AI company funding mentions."""

    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AITrackerBot/1.0)"}
    ARTICLE_TIMEOUT = 6
    ARTICLE_TEXT_LIMIT = 4000

    def _fetch_article_text(self, link: str) -> str:
        """Fetch the article body so the funding regex has more text to match against."""
        if not link.startswith("http"):
            return ""
        try:
            r = requests.get(link, headers=self.HEADERS, timeout=self.ARTICLE_TIMEOUT)
            soup = BeautifulSoup(r.text, "html.parser")
            paragraphs = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
            return paragraphs[:self.ARTICLE_TEXT_LIMIT]
        except Exception as e:
            log.debug(f"[DiscoveryAgent] Could not fetch article {link}: {e}")
            return ""

    def run(self) -> list[Company]:
        discovered: list[Company] = []
        total_entries = 0
        total_matched = 0

        for feed_url in RSS_FEEDS:
            try:
                log.info(f"[DiscoveryAgent] Fetching {feed_url}")
                feed = feedparser.parse(feed_url)
                feed_found = 0
                article_fetches = 0
                MAX_ARTICLE_FETCHES = 8

                for entry in feed.entries:
                    total_entries += 1
                    text = (entry.get("title", "") + " " + entry.get("summary", ""))
                    if not AI_KEYWORDS.search(text):
                        continue
                    m = FUNDING_RE.search(text)
                    if not m and article_fetches < MAX_ARTICLE_FETCHES:
                        # Title/summary didn't have a funding figure — check the full article.
                        article_text = self._fetch_article_text(entry.get("link", ""))
                        article_fetches += 1
                        if article_text:
                            m = FUNDING_RE.search(text + " " + article_text)
                        time.sleep(0.3)  # polite delay between article fetches
                    if m:
                        company_name = m.group("name").strip()
                        amount = m.group("amount")
                        unit_raw = m.group("unit").lower()
                        unit = "B" if unit_raw.startswith("b") else "M"
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
                        feed_found += 1
                        total_matched += 1

                log.info(f"[DiscoveryAgent] {feed_url.split('/')[2]} → {len(feed.entries)} entries, {feed_found} AI companies found")
                time.sleep(0.5)  # polite delay between feeds
            except Exception as e:
                log.warning(f"[DiscoveryAgent] Feed error {feed_url}: {e}")

        log.info(f"[DiscoveryAgent] Done — scanned {total_entries} entries across {len(RSS_FEEDS)} feeds, found {total_matched} AI companies")
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
