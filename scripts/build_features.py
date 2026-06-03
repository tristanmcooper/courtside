#!/usr/bin/env python3
"""Build the per-session feature table from the Courtside backend.

Pulls <BACKEND_URL>/api/export, then for each logged session:
  - aggregates the courtside node readings from that day (mean/max sand temp,
    mean/p95 wind-sound, air temp, humidity),
  - joins daily wearable recovery by date (HRV, resting HR, sleep; Apple Watch
    preferred, Oura as fallback),
  - attaches Open-Meteo regional weather via the session's logged lat/lon,
  - computes outcomes (subjective rating; kills-errors differential).

Writes features/session_features.csv (one row per session) for analysis.py.

LIMITATION (N=1 pilot): court readings are attributed to a session by *local
date* (assumes one main session/day). Multiple sessions in one day would need
explicit per-session start/end times — a future enhancement.

Usage:
    BACKEND_URL=https://courtside-yr2r.onrender.com python scripts/build_features.py
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weather_pull import fetch_weather  # noqa: E402

BACKEND_URL = os.getenv("BACKEND_URL", "https://courtside-yr2r.onrender.com").rstrip("/")
LOCAL_TZ = "America/Los_Angeles"
OUT = Path(__file__).resolve().parent.parent / "features" / "session_features.csv"


def _p95(s):
    s = s.dropna()
    return float(np.percentile(s, 95)) if len(s) else np.nan


def main():
    data = requests.get(f"{BACKEND_URL}/api/export", timeout=30).json()
    sessions = pd.DataFrame(data["sessions"])
    courts = pd.DataFrame(data["court_readings"])
    health = pd.DataFrame(data["health_daily"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if sessions.empty:
        print("No sessions yet — log at least one in the app, then re-run.")
        sessions.to_csv(OUT, index=False)
        return

    sessions["day"] = pd.to_datetime(sessions["day"]).dt.date

    # --- courtside node readings aggregated per local day ---
    if not courts.empty and courts["sound_pp"].notna().any():
        ts = pd.to_datetime(courts["server_ts"], format="ISO8601", utc=True)
        courts["day"] = ts.dt.tz_convert(LOCAL_TZ).dt.date
        agg = courts.groupby("day").agg(
            env_temp_mean=("temp_c", "mean"),
            env_temp_max=("temp_c", "max"),
            humidity_mean=("humidity_pct", "mean"),
            sand_temp_mean=("ir_object_c", "mean"),
            sand_temp_max=("ir_object_c", "max"),
            ir_ambient_mean=("ir_ambient_c", "mean"),
            wind_sound_mean=("sound_pp", "mean"),
            wind_sound_p95=("sound_pp", _p95),
            n_court_samples=("sound_pp", "count"),
        ).reset_index()
        sessions = sessions.merge(agg, on="day", how="left")

    # --- daily wearable recovery (prefer apple, else oura) joined by date ---
    if not health.empty:
        health["day"] = pd.to_datetime(health["day"]).dt.date
        health["_rank"] = (health["source"] != "apple").astype(int)
        health = (health.sort_values(["day", "_rank"])
                        .groupby("day", as_index=False).first())
        sessions = sessions.merge(
            health[["day", "hrv_sdnn", "resting_hr", "sleep_hours"]], on="day", how="left")

    # --- regional weather (Open-Meteo) per session lat/lon ---
    wcols = ["weather_wind_ms", "weather_gust_ms", "weather_temp_c", "weather_humidity_pct"]
    wrows = []
    for _, s in sessions.iterrows():
        w = {}
        if pd.notna(s.get("lat")) and pd.notna(s.get("lon")):
            when = s.get("start_ts") or f"{s['day']}T15:00"
            try:
                w = fetch_weather(float(s["lat"]), float(s["lon"]), str(when)[:19])
            except Exception as e:
                print(f"  weather fetch failed for {s['day']}: {e}")
        wrows.append({c: w.get(c) for c in wcols})
    sessions = pd.concat([sessions.reset_index(drop=True), pd.DataFrame(wrows)], axis=1)

    # --- outcomes ---
    if "kills" in sessions and "errors" in sessions:
        sessions["kill_err_diff"] = sessions["kills"] - sessions["errors"]

    sessions.to_csv(OUT, index=False)
    print(f"Wrote {len(sessions)} session rows × {sessions.shape[1]} cols -> {OUT}")
    print("Columns:", ", ".join(sessions.columns))


if __name__ == "__main__":
    main()
