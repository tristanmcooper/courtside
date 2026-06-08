#!/usr/bin/env python3
"""4-stage factor-ranking analysis — the project's primary deliverable.

Input : features/session_features.csv (from build_features.py)
Output: features/factor_rankings_modeled.csv + .png

Stages (descriptive / exploratory — NOT confirmatory, given small N):
  1. Pearson + Spearman of each feature vs the outcome.
  2. Lasso (standardized) with leave-one-out CV for sparse selection.
  3. Random Forest + Gradient Boosting feature importances.
  4. SHAP values from the gradient-boosting model.
Plus leave-one-session-out stability of the top-3 features.

Everything degrades gracefully on tiny N: stages that need more rows are skipped
with an honest note, but correlations + the ranking artifact are always produced.

Usage:
    python scripts/analysis.py [--input features/session_features.csv]
                               [--outcome subjective_rating_1_10]
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LassoCV
from sklearn.model_selection import LeaveOneOut
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "features" / "session_features.csv"

# Candidate predictors (only those present + usable are kept).
CANDIDATES = [
    "sand_temp_mean", "sand_temp_max", "env_temp_mean", "env_temp_max",
    "humidity_mean", "ir_ambient_mean", "wind_sound_mean", "wind_sound_p95",
    "hrv_sdnn", "resting_hr", "sleep_hours", "respiratory_rate",
    "oura_hrv", "oura_resting_hr", "oura_sleep_hours", "oura_readiness",
    "insession_hr_avg", "insession_hr_max", "insession_energy", "load_7d_energy",
    "weather_wind_ms", "weather_gust_ms", "weather_temp_c", "weather_humidity_pct",
    "wind_self_report",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_IN))
    ap.add_argument("--outcome", default="subjective_rating_1_10")
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    out_dir = Path(args.input).resolve().parent
    out = args.outcome
    if out not in df.columns:
        print(f"Outcome '{out}' not in table. Columns: {list(df.columns)}")
        return

    df = df[df[out].notna()].copy()
    n = len(df)
    print(f"N = {n} sessions with outcome '{out}'")

    # keep usable features: present, >=2 distinct non-NaN values
    feats = [c for c in CANDIDATES if c in df.columns
             and df[c].notna().sum() >= 3 and df[c].nunique(dropna=True) >= 2]
    if not feats:
        print("No usable features yet (need >=3 sessions with varying sensor/wearable data).")
        return
    print(f"Features ({len(feats)}): {feats}")

    y = df[out].to_numpy(dtype=float)
    rank = pd.DataFrame({"feature": feats}).set_index("feature")

    # --- Stage 1: correlations ---
    for f in feats:
        pair = df[[f, out]].dropna()
        if len(pair) >= 3:
            rank.loc[f, "pearson_r"] = stats.pearsonr(pair[f], pair[out])[0]
            rank.loc[f, "spearman_r"] = stats.spearmanr(pair[f], pair[out])[0]

    # Impute for model stages
    X_raw = df[feats].to_numpy(dtype=float)
    X = SimpleImputer(strategy="mean").fit_transform(X_raw)

    # --- Stage 2: Lasso + LOOCV ---
    if n >= 5 and len(feats) >= 2:
        try:
            Xs = StandardScaler().fit_transform(X)
            lasso = LassoCV(cv=LeaveOneOut(), max_iter=100000).fit(Xs, y)
            rank["lasso_coef"] = lasso.coef_
            print(f"Lasso alpha={lasso.alpha_:.4g}; "
                  f"selected={[f for f, c in zip(feats, lasso.coef_) if abs(c) > 1e-8]}")
        except Exception as e:
            print(f"Lasso skipped: {e}")
    else:
        print(f"Lasso/LOOCV skipped (need >=5 sessions, have {n}).")

    # --- Stage 3: RF + GBM importances ---
    if n >= 4:
        rf = RandomForestRegressor(n_estimators=400, random_state=0).fit(X, y)
        gbm = GradientBoostingRegressor(random_state=0).fit(X, y)
        rank["rf_importance"] = rf.feature_importances_
        rank["gbm_importance"] = gbm.feature_importances_

        # --- Stage 4: SHAP on GBM ---
        try:
            import shap
            sv = shap.TreeExplainer(gbm).shap_values(X)
            rank["mean_abs_shap"] = np.abs(sv).mean(axis=0)
        except Exception as e:
            print(f"SHAP skipped: {e}")

        # --- leave-one-session-out top-3 stability ---
        top3_counts = {f: 0 for f in feats}
        loo = LeaveOneOut()
        for tr, _ in loo.split(X):
            g = GradientBoostingRegressor(random_state=0).fit(X[tr], y[tr])
            top3 = [feats[i] for i in np.argsort(g.feature_importances_)[::-1][:3]]
            for f in top3:
                top3_counts[f] += 1
        rank["top3_stability"] = [top3_counts[f] / n for f in feats]
    else:
        print(f"RF/GBM/SHAP/stability skipped (need >=4 sessions, have {n}).")

    # --- rank + write ---
    sort_col = next((c for c in ["mean_abs_shap", "gbm_importance", "rf_importance", "pearson_r"]
                     if c in rank.columns), None)
    if sort_col:
        rank = rank.reindex(rank[sort_col].abs().sort_values(ascending=False).index)

    out_csv = out_dir / "factor_rankings_modeled.csv"
    rank.to_csv(out_csv)
    print(f"\nFactor rankings -> {out_csv}\n{rank.round(3)}")

    # --- plot (high-res for the report) ---
    plot_col = sort_col or "pearson_r"
    vals = rank[plot_col].abs() if plot_col == "pearson_r" else rank[plot_col]
    fig, ax = plt.subplots(figsize=(8, max(3, 0.45 * len(rank))))
    ax.barh(rank.index[::-1], vals[::-1], color="#c05a3a", edgecolor="black", lw=0.4)
    ax.set_xlabel(f"{plot_col}  (modeled importance)")
    ax.set_title(f"Modeled factor importance for {out}  (N={n}, exploratory)")
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    plt.tight_layout()
    out_png = out_dir / "factor_rankings_modeled.png"
    plt.savefig(out_png, dpi=300, bbox_inches="tight")
    print(f"Plot -> {out_png}")
    if n < 6:
        print(f"\nNOTE: N={n} is very small — treat rankings as exploratory/descriptive, "
              "not statistically confirmatory (see top3_stability column).")


if __name__ == "__main__":
    main()
