#!/usr/bin/env bash
# Starts API + serves the front end at http://localhost:8000  (camera needs https or localhost)
cd "$(dirname "$0")/backend" && pip install -r requirements.txt -q && DT_SECRET="${DT_SECRET:-dev-secret}" uvicorn app.main:app --host 0.0.0.0 --port 8000
