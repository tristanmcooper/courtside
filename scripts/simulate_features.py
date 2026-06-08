#!/usr/bin/env python3
"""Generate a SIMULATED multi-modal session feature table to demonstrate the
analysis pipeline at a realistic sample size.

This is NOT real data. It plants a plausible structure (better sleep/HRV +
cooler, calmer conditions + lighter recent load -> higher self-rating) so the
factor-ranking pipeline produces an interpretable, story-consistent output. Use
ONLY to illustrate what the instrument produces once enough real sessions are
collected; never report these as findings.

    python scripts/simulate_features.py --n 16 --out features/session_features_sim.csv
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--out", default=str(ROOT / "features" / "session_features_sim.csv"))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    n = args.n

    # latent recovery & conditions
    sleep = np.clip(rng.normal(7.0, 1.1, n), 4.5, 9.5)
    hrv = np.clip(rng.normal(70, 18, n), 30, 120)
    readiness = np.clip(0.6 * (hrv - 70) + rng.normal(78, 8, n), 40, 99)
    rhr = np.clip(58 - 0.15 * (hrv - 70) + rng.normal(0, 2, n), 44, 70)
    sand = np.clip(rng.normal(38, 7, n), 22, 55)
    air = np.clip(0.3 * sand + rng.normal(20, 2, n), 18, 32)
    humidity = np.clip(rng.normal(55, 12, n), 30, 85)
    wind = np.clip(rng.normal(160, 90, n), 20, 600)
    insession_hr = np.clip(rng.normal(150, 12, n), 120, 185)
    load7d = np.clip(rng.normal(1400, 700, n), 0, 3500)
    wmet = np.clip(wind / 60 + rng.normal(0, 0.6, n), 0.5, 9)

    # planted outcome: sleep+, hrv+, readiness+ ; sand-, wind-, load-
    z = (0.7 * (sleep - 7) + 0.03 * (hrv - 70) + 0.02 * (readiness - 78)
         - 0.06 * (sand - 38) - 0.004 * (wind - 160) - 0.0006 * (load7d - 1400)
         + rng.normal(0, 0.6, n))
    rating = np.clip(np.round(6 + z), 1, 10)

    df = pd.DataFrame({
        "session_id": [f"sim-{i:02d}" for i in range(n)],
        "day": pd.date_range("2026-04-15", periods=n, freq="3D").date,
        "subjective_rating_1_10": rating,
        "sand_temp_mean": sand.round(1), "sand_temp_max": (sand + rng.uniform(1, 4, n)).round(1),
        "env_temp_mean": air.round(1), "humidity_mean": humidity.round(0),
        "wind_sound_mean": wind.round(0), "wind_sound_p95": (wind * 1.4).round(0),
        "hrv_sdnn": hrv.round(1), "resting_hr": rhr.round(0), "sleep_hours": sleep.round(2),
        "respiratory_rate": np.clip(rng.normal(14.5, 1.0, n), 11, 18).round(1),
        "oura_hrv": (hrv * 0.9 + rng.normal(0, 5, n)).round(1),
        "oura_resting_hr": rhr.round(0), "oura_sleep_hours": (sleep + rng.normal(0, 0.3, n)).round(2),
        "oura_readiness": readiness.round(0),
        "insession_hr_avg": insession_hr.round(0), "insession_hr_max": (insession_hr + rng.uniform(10, 25, n)).round(0),
        "insession_energy": (insession_hr * 2.6 + rng.normal(0, 40, n)).round(0),
        "load_7d_energy": load7d.round(0),
        "weather_wind_ms": wmet.round(1), "weather_gust_ms": (wmet * 1.3).round(1),
        "weather_temp_c": (air - 2 + rng.normal(0, 1, n)).round(1),
        "weather_humidity_pct": (humidity + rng.normal(0, 4, n)).round(0),
        "wind_self_report": np.clip((wind / 110).round(), 0, 5).astype(int),
    })
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {n} SIMULATED sessions -> {args.out}")


if __name__ == "__main__":
    main()
