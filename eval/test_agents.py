"""
Unit evals for each agent in the AI Companies Tracker pipeline.

Run with:
    cd ai-tracker
    python3 -m pytest eval/test_agents.py -v
"""

import json
import os
import sys
import pytest

# Make sure crawler.py is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crawler import (
    Company, DiscoveryAgent, EnrichmentAgent,
    ClassificationAgent, DeduplicationAgent, FUNDING_RE, AI_KEYWORDS
)

GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "golden_dataset.json")))


# ─── Helper ──────────────────────────────────────────────────────────────────

def make_company(**kwargs):
    defaults = dict(
        id="test_co", name="Test Co", description="An AI company.",
        tags=["Generative AI"], website="https://example.com",
        last_funding="Series A — $10M", valuation="$100M",
        source="seed"
    )
    defaults.update(kwargs)
    return Company(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 1 — DiscoveryAgent
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscoveryAgent:

    @pytest.mark.parametrize("fixture", [f for f in GOLDEN["discovery_fixtures"] if f["should_match"]])
    def test_extracts_known_funding_headlines(self, fixture):
        """FUNDING_RE must capture company name + amount from real-world headlines."""
        text = fixture["title"] + " " + fixture["summary"]
        m = FUNDING_RE.search(text)
        assert m is not None, f"Pattern missed: '{fixture['title']}'"
        assert m.group("amount") == fixture["expected_amount"], \
            f"Amount mismatch — got {m.group('amount')}, expected {fixture['expected_amount']}"
        assert m.group("unit").upper() == fixture["expected_unit"]

    @pytest.mark.parametrize("fixture", [f for f in GOLDEN["discovery_fixtures"] if not f["should_match"]])
    def test_ignores_non_ai_articles(self, fixture):
        """Articles with no AI keywords must be filtered out."""
        text = fixture["title"] + " " + fixture["summary"]
        has_ai = bool(AI_KEYWORDS.search(text))
        assert not has_ai, f"False positive — non-AI article was flagged: '{fixture['title']}'"

    def test_run_returns_list(self, monkeypatch):
        """DiscoveryAgent.run() must always return a list even if all feeds fail."""
        import feedparser
        monkeypatch.setattr(feedparser, "parse", lambda url: type("F", (), {"entries": []})())
        agent = DiscoveryAgent()
        result = agent.run()
        assert isinstance(result, list)

    def test_feed_failure_does_not_crash(self, monkeypatch):
        """A broken feed URL must not raise an exception."""
        import feedparser
        def boom(url):
            raise ConnectionError("Network down")
        monkeypatch.setattr(feedparser, "parse", boom)
        agent = DiscoveryAgent()
        result = agent.run()
        assert result == []

    def test_no_non_ai_companies_in_output(self, monkeypatch):
        """All companies returned must have passed the AI keyword filter."""
        import feedparser
        fake_entries = [
            {"title": "Apple launches new MacBook",  "summary": "Better battery life.", "link": ""},
            {"title": "Tesla announces new car",      "summary": "EV range improved.",   "link": ""},
        ]
        monkeypatch.setattr(feedparser, "parse",
            lambda url: type("F", (), {"entries": [type("E", (), e)() for e in fake_entries]})())
        agent = DiscoveryAgent()
        result = agent.run()
        assert len(result) == 0, "Non-AI articles leaked into output"


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 2 — EnrichmentAgent
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnrichmentAgent:

    def test_seed_company_skipped(self):
        """Seed companies must never be sent to the enrichment HTTP request."""
        agent = EnrichmentAgent()
        c = make_company(source="seed", description="Original description.")
        result = agent.enrich(c)
        assert result.description == "Original description.", "Seed company description was overwritten"

    def test_rss_company_with_bad_url_unchanged(self):
        """If the website URL is not http/https, company must be returned unchanged."""
        agent = EnrichmentAgent()
        c = make_company(source="rss", website="not-a-url", description="Original.")
        result = agent.enrich(c)
        assert result.description == "Original."

    def test_rss_company_enriched_on_good_response(self, monkeypatch):
        """Enrichment must update description when a valid og:description is found."""
        import requests
        fake_html = '<html><head><meta property="og:description" content="We build AI agents for enterprises."></head></html>'
        monkeypatch.setattr(requests, "get",
            lambda *a, **kw: type("R", (), {"text": fake_html, "status_code": 200})())
        agent = EnrichmentAgent()
        c = make_company(source="rss", website="https://real-company.ai", description="AI company.")
        result = agent.enrich(c)
        assert "AI agents" in result.description

    def test_network_error_does_not_crash(self, monkeypatch):
        """HTTP failure must not raise — company returned unchanged."""
        import requests
        monkeypatch.setattr(requests, "get", lambda *a, **kw: (_ for _ in ()).throw(Exception("Timeout")))
        agent = EnrichmentAgent()
        c = make_company(source="rss", website="https://broken.ai", description="Original.")
        result = agent.enrich(c)
        assert result.description == "Original."

    def test_short_meta_description_ignored(self, monkeypatch):
        """Meta descriptions shorter than 30 chars must not replace existing description."""
        import requests
        fake_html = '<html><head><meta name="description" content="Short."></head></html>'
        monkeypatch.setattr(requests, "get",
            lambda *a, **kw: type("R", (), {"text": fake_html})())
        agent = EnrichmentAgent()
        c = make_company(source="rss", website="https://example.ai", description="Original good description.")
        result = agent.enrich(c)
        assert result.description == "Original good description."


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 3 — ClassificationAgent
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassificationAgent:

    @pytest.mark.parametrize("fixture", GOLDEN["classification_fixtures"])
    def test_expected_tags_assigned(self, fixture):
        """ClassificationAgent must assign each expected tag for known descriptions."""
        agent = ClassificationAgent()
        c = make_company(description=fixture["description"], tags=[])
        result = agent.classify(c)
        for expected_tag in fixture["expected_tags"]:
            assert expected_tag in result.tags, \
                f"Missing tag '{expected_tag}' for description: '{fixture['description']}'"

    def test_tags_capped_at_six(self):
        """No company should have more than 6 tags."""
        agent = ClassificationAgent()
        long_desc = (
            "We build robots with computer vision, NLP speech, AI chips, "
            "autonomous vehicles, healthcare AI, legal AI, and financial AI tools."
        )
        c = make_company(description=long_desc, tags=["LLM", "Foundation Models", "Generative AI"])
        result = agent.classify(c)
        assert len(result.tags) <= 6, f"Tag cap exceeded: {result.tags}"

    def test_no_duplicate_tags(self):
        """Output tags must not contain duplicates."""
        agent = ClassificationAgent()
        c = make_company(description="LLM and machine learning platform", tags=["LLM", "LLM"])
        result = agent.classify(c)
        assert len(result.tags) == len(set(result.tags)), f"Duplicate tags found: {result.tags}"

    def test_empty_description_does_not_crash(self):
        agent = ClassificationAgent()
        c = make_company(description="", tags=[])
        result = agent.classify(c)
        assert isinstance(result.tags, list)


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 4 — DeduplicationAgent
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeduplicationAgent:

    def test_seed_beats_rss(self):
        """Seed data must always win over RSS when merging the same company."""
        f = next(x for x in GOLDEN["deduplication_fixtures"] if x["scenario"] == "seed beats rss")
        agent = DeduplicationAgent()
        seed = [make_company(**{**f["seed"], "description": "seed desc", "tags": []})]
        rss  = [make_company(**{**f["incoming"], "description": "rss desc", "tags": []})]
        result = agent.merge(seed, rss)
        match = next(c for c in result if c.id == "openai")
        assert match.valuation == f["expected_valuation"]

    def test_richer_description_wins(self):
        """When both are RSS, the longer description must win."""
        f = next(x for x in GOLDEN["deduplication_fixtures"] if x["scenario"] == "richer description wins")
        agent = DeduplicationAgent()
        existing = [make_company(**{**f["seed"], "tags": []})]
        incoming = [make_company(**{**f["incoming"], "tags": []})]
        result = agent.merge(existing, incoming)
        match = next(c for c in result if c.id == f["seed"]["id"])
        assert len(match.description) >= f["expected_description_min_len"]

    def test_no_duplicates_in_output(self):
        """Output must never contain two companies with the same id."""
        agent = DeduplicationAgent()
        companies = [
            make_company(id="openai", name="OpenAI"),
            make_company(id="openai", name="OpenAI"),
            make_company(id="anthropic", name="Anthropic"),
        ]
        result = agent.merge(companies, [])
        ids = [c.id for c in result]
        assert len(ids) == len(set(ids)), f"Duplicate ids found: {ids}"

    def test_new_company_added(self):
        """A brand-new company in incoming must appear in the output."""
        agent = DeduplicationAgent()
        existing = [make_company(id="openai", name="OpenAI")]
        incoming = [make_company(id="new_co", name="New Co", source="rss")]
        result = agent.merge(existing, incoming)
        ids = [c.id for c in result]
        assert "new_co" in ids


# ═══════════════════════════════════════════════════════════════════════════════
# End-to-end — Golden company coverage
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoldenCoverage:

    def test_all_golden_companies_present_in_seed(self):
        """Every company in golden_dataset must exist in SEED_COMPANIES."""
        from crawler import SEED_COMPANIES
        seed_names_lower = {c.name.lower() for c in SEED_COMPANIES}
        missing = []
        for entry in GOLDEN["known_companies"]:
            if entry["name"].lower() not in seed_names_lower:
                missing.append(entry["name"])
        assert not missing, f"Missing from SEED_COMPANIES: {missing}"

    def test_golden_companies_have_required_tags(self):
        """Each golden company must carry all its required tags."""
        from crawler import SEED_COMPANIES, ClassificationAgent
        agent = ClassificationAgent()
        seed_map = {c.name: agent.classify(c) for c in SEED_COMPANIES}
        failures = []
        for entry in GOLDEN["known_companies"]:
            company = seed_map.get(entry["name"])
            if not company:
                continue
            for tag in entry["required_tags"]:
                if tag not in company.tags:
                    failures.append(f"{entry['name']} missing tag '{tag}' (has: {company.tags})")
        assert not failures, "\n".join(failures)

    def test_golden_companies_have_required_fields(self):
        """Each golden company must have all required fields populated."""
        from crawler import SEED_COMPANIES
        seed_map = {c.name: c for c in SEED_COMPANIES}
        failures = []
        for entry in GOLDEN["known_companies"]:
            company = seed_map.get(entry["name"])
            if not company:
                continue
            for field in entry["required_fields"]:
                val = getattr(company, field, None)
                if not val or val in ("Unknown", "N/A", "Undisclosed", ""):
                    failures.append(f"{entry['name']}.{field} = '{val}'")
        assert not failures, "\n".join(failures)
