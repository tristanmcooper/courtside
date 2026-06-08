#!/usr/bin/env python3
"""Seed the deployment with demo sessions, courts, and people for a live demo.

Populates real-looking sessions across five San Diego courts with four partners
and four opponents, self-rated abilities, and a coherent performance story
(you click with Maya, struggle with Leo; Daniel is a tough matchup, you handle
Tess) so the Map tab, People rankings, relationship signals, and ability
estimates all light up.

Demo entities are id-prefixed ("demo-") and removable. This data is for
*demonstrating functionality* — clear it before exporting real sessions for the
report's analysis so it never mixes into reported results.

    python scripts/seed_demo.py                 # seed the production deployment
    python scripts/seed_demo.py --clear         # remove demo sessions + people
    python scripts/seed_demo.py --url http://127.0.0.1:8000   # target local
"""
import argparse
import re

import requests

DEFAULT_URL = "https://courtside-yr2r.onrender.com"
PREFIX = "demo-"
OLD_PREFIXES = ("demo-", "sim-demo-")  # also clean up the older demo scheme

COURTS = {
    "South Mission Beach Challenge Courts": (32.760463, -117.251987),
    "La Jolla Shores North Courts":         (32.859614, -117.255954),
    "Del Mar Dog Beach Pickup Courts":      (32.976829, -117.269656),
    "Wave Volleyball Club":                 (32.976435, -117.253476),
    "Ocean Beach Courts":                   (32.751411, -117.251921),
}
SMB, LJS, DMD, WVC, OB = COURTS  # dict preserves insertion order

# name -> (kind, your self-rated ability 1-10)
PEOPLE = {
    "Maya":   ("partner", 8), "Sofia": ("partner", 9), "Jordan": ("partner", 6), "Leo": ("partner", 5),
    "Daniel": ("opponent", 9), "Marcus": ("opponent", 8), "Kai": ("opponent", 6), "Tess": ("opponent", 5),
}

# (date, court, partner, your self-rating, [opponents])
# Story: you click with Maya (boost) and struggle with Leo (drag); Daniel is a
# consistently tough matchup (drag) while you handle Tess well (favorable).
SESSIONS = [
    ("2026-03-07", SMB, "Maya",   9, ["Tess", "Kai"]),
    ("2026-03-12", DMD, "Leo",    4, ["Daniel", "Kai"]),
    ("2026-03-15", OB,  "Sofia",  8, ["Tess", "Marcus"]),
    ("2026-03-20", LJS, "Maya",   9, ["Tess", "Marcus"]),
    ("2026-03-26", WVC, "Jordan", 6, ["Daniel", "Kai"]),
    ("2026-04-02", OB,  "Maya",   8, ["Kai", "Tess"]),
    ("2026-04-06", SMB, "Leo",    4, ["Daniel", "Marcus"]),
    ("2026-04-11", DMD, "Sofia",  8, ["Tess", "Kai"]),
    ("2026-04-15", LJS, "Jordan", 7, ["Kai", "Marcus"]),
    ("2026-04-20", WVC, "Maya",   8, ["Marcus", "Kai"]),
    ("2026-04-25", OB,  "Leo",    5, ["Daniel", "Marcus"]),
    ("2026-05-01", SMB, "Sofia",  7, ["Tess", "Kai"]),
    ("2026-05-05", DMD, "Leo",    3, ["Daniel", "Kai"]),
    ("2026-05-10", LJS, "Jordan", 6, ["Daniel", "Marcus"]),
    ("2026-05-15", WVC, "Sofia",  8, ["Tess", "Kai"]),
]


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def seed(base):
    for i, (day, court, partner, rating, opps) in enumerate(SESSIONS, 1):
        lat, lon = COURTS[court]
        body = {
            "session_id": f"{PREFIX}{i:02d}", "day": day, "location": court,
            "lat": lat, "lon": lon, "partner": partner, "opponents": opps,
            "subjective_rating_1_10": rating,
            "start_ts": f"{day}T17:00:00", "end_ts": f"{day}T18:30:00",
        }
        requests.post(f"{base}/api/sessions", json=body, timeout=60).raise_for_status()
    for name, (kind, abil) in PEOPLE.items():
        requests.post(f"{base}/api/people",
                      json={"name": name, "kind": kind, "ability_self": abil}, timeout=30).raise_for_status()
    print(f"Seeded {len(SESSIONS)} sessions, {len(COURTS)} courts, {len(PEOPLE)} people -> {base}")


def clear(base):
    rows = requests.get(f"{base}/api/sessions", timeout=60).json()
    n = 0
    for s in rows:
        if str(s["session_id"]).startswith(OLD_PREFIXES):
            requests.delete(f"{base}/api/sessions/{s['session_id']}", timeout=30)
            n += 1
    for name in PEOPLE:
        requests.delete(f"{base}/api/people/{_slug(name)}", timeout=30)
    print(f"Removed {n} demo sessions and {len(PEOPLE)} demo people from {base}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--clear", action="store_true")
    args = ap.parse_args()
    (clear if args.clear else seed)(args.url.rstrip("/"))
