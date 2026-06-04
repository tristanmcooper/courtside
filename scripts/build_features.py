#!/usr/bin/env python3
"""Build the per-session feature table from the Courtside backend.

For each logged session, aggregate the courtside node readings within the
session's [start_ts, end_ts] recording window (falling back to local-day
grouping for manually-logged sessions without timestamps), join daily wearable
recovery by date, attach Open-Meteo regional weather via lat/lon, and compute
outcomes. Writes features/session_features.csv for analysis.py.

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


def _agg_court(sub: pd.DataFrame) -> dict:
    if sub.empty:
        return {}
    sp = sub["sound_pp"].dropna()
    return {
        "env_temp_mean": sub["temp_c"].mean(), "env_temp_max": sub["temp_c"].max(),
        "humidity_mean": sub["humidity_pct"].mean(),
        "sand_temp_mean": sub["ir_object_c"].mean(), "sand_temp_max": sub["ir_object_c"].max(),
        "ir_ambient_mean": sub["ir_ambient_c"].mean(),
        "wind_sound_mean": sub["sound_pp"].mean(),
        "wind_sound_p95": float(np.percentile(sp, 95)) if len(sp) else np.nan,
        "n_court_samples": int(sub["sound_pp"].notna().sum()),
    }


def main():
    data = requests.get(f"{BACKEND_URL}/api/export", timeout=30).json()
    sessions = pd.DataFrame(data["sessions"])
    courts = pd.DataFrame(data["court_readings"])
    health = pd.DataFrame(data["health_daily"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if sessions.empty:
        print("No sessions yet — record/log at least one in the app, then re-run.")
        sessions.to_csv(OUT, index=False)
        return

    sessions["day"] = pd.to_datetime(sessions["day"]).dt.date

    # court timestamps: naive UTC (matches session start/end) + a local calendar date
    if not courts.empty:
        utc = pd.to_datetime(courts["server_ts"], format="ISO8601", utc=True)
        c_utc = utc.dt.tz_localize(None)
        c_localdate = utc.dt.tz_convert(LOCAL_TZ).dt.date

    # aggregate court readings per session (window first, else same local day)
    agg_rows = []
    for _, s in sessions.iterrows():
        if courts.empty:
            agg_rows.append({})
            continue
        if pd.notna(s.get("start_ts")) and pd.notna(s.get("end_ts")):
            start, end = pd.to_datetime(s["start_ts"]), pd.to_datetime(s["end_ts"])
            sub = courts[(c_utc >= start) & (c_utc <= end)]
        else:
            sub = courts[c_localdate == s["day"]]
        agg_rows.append(_agg_court(sub))
    sessions = pd.concat([sessions.reset_index(drop=True), pd.DataFrame(agg_rows)], axis=1)

    # daily wearable recovery (prefer apple, else oura) by date
    if not health.empty:
        health["day"] = pd.to_datetime(health["day"]).dt.date
        health["_rank"] = (health["source"] != "apple").astype(int)
        health = (health.sort_values(["day", "_rank"])
                        .groupby("day", as_index=False).first())
        sessions = sessions.merge(
            health[["day", "hrv_sdnn", "resting_hr", "sleep_hours"]], on="day", how="left")

    # regional weather (Open-Meteo) per session lat/lon, at ~mid-afternoon local
    wcols = ["weather_wind_ms", "weather_gust_ms", "weather_temp_c", "weather_humidity_pct"]
    wrows = []
    for _, s in sessions.iterrows():
        w = {}
        if pd.notna(s.get("lat")) and pd.notna(s.get("lon")):
            try:
                w = fetch_weather(float(s["lat"]), float(s["lon"]), f"{s['day']}T15:00")
            except Exception as e:
                print(f"  weather fetch failed {s['day']}: {e}")
        wrows.append({c: w.get(c) for c in wcols})
    sessions = pd.concat([sessions.reset_index(drop=True), pd.DataFrame(wrows)], axis=1)

    # outcomes
    if "kills" in sessions and "errors" in sessions:
        sessions["kill_err_diff"] = sessions["kills"] - sessions["errors"]

    sessions.to_csv(OUT, index=False)
    print(f"Wrote {len(sessions)} session rows × {sessions.shape[1]} cols -> {OUT}")
    print("Columns:", ", ".join(sessions.columns))


if __name__ == "__main__":
    main()
