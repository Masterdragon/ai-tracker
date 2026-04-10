"""
Flask server for the AI Companies Tracker.
Serves the frontend and exposes a REST API backed by the crawler pipeline.
APScheduler triggers a full crawl every hour in the background.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, request, send_from_directory

from crawler import CrawlerOrchestrator, load_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static")
orchestrator = CrawlerOrchestrator()
scheduler = BackgroundScheduler(timezone="UTC")


# ─── Background job ───────────────────────────────────────────────────────────

def scheduled_crawl():
    log.info("[Scheduler] Hourly crawl triggered")
    orchestrator.run()


scheduler.add_job(scheduled_crawl, "interval", hours=1, id="crawl_job",
                  max_instances=1, coalesce=True)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/companies")
def get_companies():
    tag = request.args.get("tag")
    q = request.args.get("q", "").lower()
    data = load_all()
    companies = data.get("companies", [])

    if tag:
        companies = [c for c in companies if tag in c.get("tags", [])]
    if q:
        companies = [
            c for c in companies
            if q in c.get("name", "").lower() or q in c.get("description", "").lower()
        ]

    return jsonify({
        "metadata": data.get("metadata", {}),
        "companies": companies,
    })


@app.route("/api/refresh", methods=["POST"])
def manual_refresh():
    log.info("[API] Manual refresh requested")
    companies = orchestrator.run()
    return jsonify({"status": "ok", "count": len(companies)})


@app.route("/api/status")
def status():
    data = load_all()
    job = scheduler.get_job("crawl_job")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    return jsonify({
        "last_crawl": data.get("metadata", {}).get("last_crawl"),
        "count": data.get("metadata", {}).get("count", 0),
        "next_crawl": next_run,
        "server_time": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/tags")
def get_tags():
    data = load_all()
    tags: set[str] = set()
    for c in data.get("companies", []):
        tags.update(c.get("tags", []))
    return jsonify(sorted(tags))


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Running initial crawl on startup …")
    orchestrator.run()
    scheduler.start()
    log.info("Scheduler started — crawl every 60 minutes")
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    finally:
        scheduler.shutdown()
