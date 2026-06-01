#!/usr/bin/env python3
"""Pull regional weather (wind, temp, humidity) from Open-Meteo — free, no API key.

Two uses:
  1. Validation — correlate the courtside node's acoustic wind proxy (sound_pp)
     and DHT11 against a regional reference.
  2. Feature / framing — Open-Meteo is a ~10 m grid-scale model that deliberately
     MISSES the court-level microclimate the node measures. Treat it as a coarse
     reference, not ground truth; the gap between them is part of the thesis.

Usage:
    python scripts/weather_pull.py [--lat LAT] [--lon LON] [--when ISO8601]
    # default: La Jolla, CA, right now

Importable (used later by build_features.py):
    from weather_pull import fetch_weather
    w = fetch_weather(lat, lon, "2026-06-01T15:00")
"""
import argparse
from datetime import datetime
from typing import Optional

import requests

# Default court location — CHANGE to your usual beach/court.
DEFAULT_LAT = 32.857   # La Jolla Shores, CA
DEFAULT_LON = -117.257

HOURLY = ["temperature_2m", "relative_humidity_2m",
          "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m"]


def fetch_weather(lat: float, lon: float, when_iso: Optional[str] = None) -> dict:
    """Regional weather for the hour nearest `when_iso` (local time). past_days=7
    covers the data-collection window; for older dates swap to the archive API."""
    target = datetime.fromisoformat(when_iso) if when_iso else datetime.now()
    target = target.replace(tzinfo=None)
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat, "longitude": lon,
            "hourly": ",".join(HOURLY),
            "wind_speed_unit": "ms",
            "past_days": 7, "forecast_days": 1,
            "timezone": "auto",
        },
        timeout=20,
    )
    r.raise_for_status()
    h = r.json()["hourly"]
    times = [datetime.fromisoformat(t) for t in h["time"]]
    i = min(range(len(times)), key=lambda k: abs(times[k] - target))
    return {
        "weather_time": h["time"][i],
        "weather_temp_c": h["temperature_2m"][i],
        "weather_humidity_pct": h["relative_humidity_2m"][i],
        "weather_wind_ms": h["wind_speed_10m"][i],
        "weather_gust_ms": h["wind_gusts_10m"][i],
        "weather_wind_dir_deg": h["wind_direction_10m"][i],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=DEFAULT_LAT)
    ap.add_argument("--lon", type=float, default=DEFAULT_LON)
    ap.add_argument("--when", default=None, help="ISO8601 local datetime; default now")
    args = ap.parse_args()
    w = fetch_weather(args.lat, args.lon, args.when)
    print(f"Nearest hour: {w['weather_time']}")
    print(f"  wind     {w['weather_wind_ms']:.1f} m/s (gust {w['weather_gust_ms']:.1f}), "
          f"dir {w['weather_wind_dir_deg']}°")
    print(f"  temp     {w['weather_temp_c']:.1f} °C")
    print(f"  humidity {w['weather_humidity_pct']:.0f} %")


if __name__ == "__main__":
    main()
