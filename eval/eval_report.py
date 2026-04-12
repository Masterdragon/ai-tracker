"""
Eval report — runs the full crawler pipeline and scores each agent.

Usage:
    cd ai-tracker
    python3 eval/eval_report.py

Prints a scorecard showing how well each agent is performing.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crawler import (
    SEED_COMPANIES, CrawlerOrchestrator,
    ClassificationAgent, DeduplicationAgent,
    FUNDING_RE, AI_KEYWORDS, load_all
)

GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "golden_dataset.json")))

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}~{RESET} {msg}")

def score_label(pct):
    if pct >= 0.9: return f"{GREEN}{pct*100:.0f}%{RESET}"
    if pct >= 0.7: return f"{YELLOW}{pct*100:.0f}%{RESET}"
    return f"{RED}{pct*100:.0f}%{RESET}"


# ═══════════════════════════════════════════════════════════════════════════════
# 1 — DiscoveryAgent eval
# ═══════════════════════════════════════════════════════════════════════════════

def eval_discovery():
    print(f"\n{BOLD}── Agent 1: DiscoveryAgent ──────────────────────────────{RESET}")
    passed = total = 0

    for f in GOLDEN["discovery_fixtures"]:
        total += 1
        text = f["title"] + " " + f["summary"]
        has_ai = bool(AI_KEYWORDS.search(text))
        m = FUNDING_RE.search(text) if has_ai else None

        if f["should_match"]:
            if m and m.group("amount") == f["expected_amount"]:
                ok(f"Detected: '{f['title'][:60]}…'")
                passed += 1
            else:
                fail(f"Missed:   '{f['title'][:60]}…'")
        else:
            if not has_ai:
                ok(f"Correctly ignored: '{f['title'][:60]}…'")
                passed += 1
            else:
                fail(f"False positive:   '{f['title'][:60]}…'")

    pct = passed / total
    print(f"  Score: {score_label(pct)}  ({passed}/{total} fixtures)")
    return pct


# ═══════════════════════════════════════════════════════════════════════════════
# 2 — ClassificationAgent eval
# ═══════════════════════════════════════════════════════════════════════════════

def eval_classification():
    print(f"\n{BOLD}── Agent 3: ClassificationAgent ─────────────────────────{RESET}")
    agent = ClassificationAgent()
    passed = total = 0

    for f in GOLDEN["classification_fixtures"]:
        from crawler import Company
        c = Company("t","T", f["description"], [], "https://t.com", "Seed","N/A")
        result = agent.classify(c)
        missing = [t for t in f["expected_tags"] if t not in result.tags]
        total += len(f["expected_tags"])
        if not missing:
            ok(f"All tags correct for: '{f['description'][:55]}…'")
            passed += len(f["expected_tags"])
        else:
            fail(f"Missing {missing} for: '{f['description'][:55]}…'")
            passed += len(f["expected_tags"]) - len(missing)

    pct = passed / total
    print(f"  Score: {score_label(pct)}  ({passed}/{total} tag assignments correct)")
    return pct


# ═══════════════════════════════════════════════════════════════════════════════
# 3 — DeduplicationAgent eval
# ═══════════════════════════════════════════════════════════════════════════════

def eval_deduplication():
    print(f"\n{BOLD}── Agent 4: DeduplicationAgent ──────────────────────────{RESET}")
    agent = DeduplicationAgent()
    passed = total = 0

    for f in GOLDEN["deduplication_fixtures"]:
        total += 1
        from crawler import Company
        def make(d):
            return Company(d["id"], d["name"], d.get("description","desc"),
                           [], "https://x.com", "Seed", d.get("valuation","N/A"),
                           source=d["source"])
        seed = [make(f["seed"])]
        incoming = [make(f["incoming"])]
        result = agent.merge(seed, incoming)
        merged = next((c for c in result if c.id == f["seed"]["id"]), None)

        if f["scenario"] == "seed beats rss":
            if merged and merged.valuation == f["expected_valuation"]:
                ok(f"Seed correctly preserved for '{merged.name}'")
                passed += 1
            else:
                fail(f"Seed lost for '{f['seed']['name']}' — got {merged.valuation if merged else 'None'}")

        elif f["scenario"] == "richer description wins":
            if merged and len(merged.description) >= f["expected_description_min_len"]:
                ok(f"Richer description kept for '{merged.name}'")
                passed += 1
            else:
                fail(f"Short description kept — len={len(merged.description) if merged else 0}")

    pct = passed / total
    print(f"  Score: {score_label(pct)}  ({passed}/{total} scenarios correct)")
    return pct


# ═══════════════════════════════════════════════════════════════════════════════
# 4 — End-to-end golden coverage
# ═══════════════════════════════════════════════════════════════════════════════

def eval_golden_coverage():
    print(f"\n{BOLD}── End-to-End: Golden Company Coverage ──────────────────{RESET}")
    agent = ClassificationAgent()
    seed_map = {c.name: agent.classify(c) for c in SEED_COMPANIES}

    present = tag_pass = field_pass = 0
    total = len(GOLDEN["known_companies"])

    for entry in GOLDEN["known_companies"]:
        company = seed_map.get(entry["name"])
        if not company:
            fail(f"{entry['name']} NOT FOUND in seed data")
            continue
        present += 1

        missing_tags = [t for t in entry["required_tags"] if t not in company.tags]
        if not missing_tags:
            ok(f"{entry['name']} — tags OK {company.tags}")
            tag_pass += 1
        else:
            warn(f"{entry['name']} — missing tags: {missing_tags} (has {company.tags})")

        missing_fields = [
            f for f in entry["required_fields"]
            if not getattr(company, f, None) or getattr(company, f) in ("Unknown", "N/A", "Undisclosed", "")
        ]
        if not missing_fields:
            field_pass += 1
        else:
            warn(f"{entry['name']} — empty fields: {missing_fields}")

    coverage = present / total
    tag_score = tag_pass / total
    field_score = field_pass / total
    print(f"  Company coverage:  {score_label(coverage)}  ({present}/{total} found)")
    print(f"  Tag accuracy:      {score_label(tag_score)}  ({tag_pass}/{total} correct)")
    print(f"  Field completeness:{score_label(field_score)}  ({field_pass}/{total} complete)")
    return (coverage + tag_score + field_score) / 3


# ═══════════════════════════════════════════════════════════════════════════════
# 5 — Data health check (runs against live data/companies.json)
# ═══════════════════════════════════════════════════════════════════════════════

def eval_data_health():
    print(f"\n{BOLD}── Live Data Health (companies.json) ────────────────────{RESET}")
    data = load_all()
    companies = data.get("companies", [])

    if not companies:
        fail("No data file found — run the server first")
        return 0.0

    total = len(companies)
    no_desc   = sum(1 for c in companies if not c.get("description") or len(c["description"]) < 30)
    no_tags   = sum(1 for c in companies if not c.get("tags"))
    no_site   = sum(1 for c in companies if not c.get("website","").startswith("http"))
    no_fund   = sum(1 for c in companies if not c.get("last_funding"))
    dup_ids   = total - len({c["id"] for c in companies})

    print(f"  Total companies:   {BOLD}{total}{RESET}")
    (ok if no_desc  == 0 else warn)(f"Short/missing descriptions: {no_desc}")
    (ok if no_tags  == 0 else warn)(f"Missing tags:               {no_tags}")
    (ok if no_site  == 0 else warn)(f"Missing website:            {no_site}")
    (ok if no_fund  == 0 else warn)(f"Missing funding info:       {no_fund}")
    (ok if dup_ids  == 0 else fail)(f"Duplicate IDs:              {dup_ids}")

    issues = no_desc + no_tags + no_site + no_fund + dup_ids
    health = max(0, 1 - (issues / (total * 5)))
    print(f"  Health score:      {score_label(health)}")
    return health


# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{BOLD}{'═'*54}")
    print("  AI Companies Tracker — Agent Eval Report")
    print(f"{'═'*54}{RESET}")

    scores = {
        "DiscoveryAgent":    eval_discovery(),
        "ClassificationAgent": eval_classification(),
        "DeduplicationAgent":  eval_deduplication(),
        "Golden Coverage":     eval_golden_coverage(),
        "Data Health":         eval_data_health(),
    }

    print(f"\n{BOLD}── Overall Scorecard ────────────────────────────────────{RESET}")
    for name, score in scores.items():
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  {name:<25} {bar} {score_label(score)}")

    overall = sum(scores.values()) / len(scores)
    print(f"\n  {BOLD}Overall pipeline score: {score_label(overall)}{RESET}\n")
