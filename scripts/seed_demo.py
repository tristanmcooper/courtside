#!/usr/bin/env python3
"""Populate the dashboard with LABELED simulated sessions for a demo.

These are clearly marked (session_id prefix 'sim-demo-', partner '(simulated)',
notes flag) and only add session ratings/context (NOT wearable or sensor data),
so they enrich the Summary chart/trend/history without contaminating real
recovery data. Fully reversible:

    python scripts/seed_demo.py            # add ~10 simulated sessions
    python scripts/seed_demo.py --clear    # delete all sim-demo sessions
"""
import argparse
import datetime as dt
import numpy as np
import requests

BACKEND = "https://courtside-yr2r.onrender.com"
PREFIX = "sim-demo-"
FELT = ["loose", "tired", "dialed-in", "flat", "sore", "energized", "rushed", "calm"]


def clear():
    rows = requests.get(f"{BACKEND}/api/sessions", timeout=60).json()
    n = 0
    for s in rows:
        if str(s["session_id"]).startswith(PREFIX):
            requests.delete(f"{BACKEND}/api/sessions/{s['session_id']}", timeout=30)
            n += 1
    print(f"Deleted {n} simulated demo sessions.")


def seed(n):
    rng = np.random.default_rng(3)
    today = dt.date.today()
    for i in range(n):
        day = today - dt.timedelta(days=(i + 2) * 2)
        sleep = float(np.clip(rng.normal(7, 1), 5, 9))
        rating = int(np.clip(round(6 + 0.8 * (sleep - 7) + rng.normal(0, 1)), 1, 10))
        body = {
            "session_id": f"{PREFIX}{day.isoformat()}",
            "day": day.isoformat(),
            "subjective_rating_1_10": rating,
            "peer_rating_1_10": int(np.clip(rating + rng.integers(-1, 2), 1, 10)),
            "wind_self_report": int(rng.integers(0, 6)),
            "kills": int(rng.integers(6, 18)), "errors": int(rng.integers(3, 12)),
            "partner": "(simulated)", "location": "Demo Beach",
            "felt_state": FELT[i % len(FELT)],
            "notes": "[simulated demo session — clear with: python scripts/seed_demo.py --clear]",
        }
        r = requests.post(f"{BACKEND}/api/sessions", json=body, timeout=30)
        print(f"  {day} rating {rating}: {r.status_code}")
    print(f"Seeded {n} labeled simulated sessions.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    clear() if a.clear else seed(a.n)
