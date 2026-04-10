"""
WSGI entry point for Gunicorn (production).
Starts the APScheduler and runs an initial crawl if no data exists.
"""

import os
from app import app, orchestrator, scheduler

# Run initial crawl if data file doesn't exist yet
data_file = os.path.join(os.path.dirname(__file__), "data", "companies.json")
if not os.path.exists(data_file):
    orchestrator.run()

# Start background scheduler (hourly crawl)
if not scheduler.running:
    scheduler.start()
