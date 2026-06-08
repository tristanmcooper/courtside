#!/usr/bin/env python3
"""Illustrative (SIMULATED) relationship plots for the report/demo.

Two panels: (1) actual effort (Apple-Watch in-session avg HR, paired to the ESP32
session window by timestamp overlap) vs self-rated performance; (2) sleep vs
performance. Data is simulated with a plausible planted structure to show the
analyses the instrument enables once enough real sessions are collected. NOT real.

    python scripts/demo_plots.py
"""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Project Update Materials" / "ECE_284_Project_Report" / "demo_relationships.png"
SAND, AQUA, INK, GRID = "#e08a3c", "#1f9e8f", "#22303f", "#dfe6ee"


def panel(ax, x, y, xlabel, title, color):
    ax.scatter(x, y, s=70, c=color, edgecolors="white", linewidths=1.0, zorder=3, alpha=0.9)
    b, a = np.polyfit(x, y, 1)
    xs = np.linspace(x.min(), x.max(), 50)
    ax.plot(xs, a + b * xs, color=INK, lw=1.8, ls="--", zorder=2)
    r = stats.pearsonr(x, y)[0]
    ax.text(0.04, 0.93, f"r = {r:+.2f}", transform=ax.transAxes, fontsize=12,
            fontweight="bold", va="top", color=INK,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GRID))
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel("Self-rated performance (1–10)", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold", color=INK)
    ax.set_ylim(0.5, 10.5)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def main():
    rng = np.random.default_rng(11)
    n = 20
    sleep = np.clip(rng.normal(7.0, 1.1, n), 4.8, 9.3)
    effort_hr = np.clip(rng.normal(152, 14, n), 120, 184)   # actual effort (watch)
    # performance: strongly helped by sleep; mild inverted-U in effort (too hard = worse)
    rating = (6 + 0.95 * (sleep - 7) - 0.0016 * (effort_hr - 150) ** 2
              + rng.normal(0, 0.7, n))
    rating = np.clip(np.round(rating), 1, 10)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))
    panel(ax1, effort_hr, rating, "Actual effort — in-session avg HR (bpm)",
          "Actual effort vs performance", SAND)
    panel(ax2, sleep, rating, "Sleep the night before (hours)",
          "Sleep vs performance", AQUA)
    fig.suptitle("Illustrative relationships (SIMULATED, N=20) — analyses the instrument enables",
                 fontsize=11, style="italic", color="#5a6b7b", y=1.02)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=300, bbox_inches="tight")
    print(f"Wrote {OUT}")
    print(f"  effort–performance r = {stats.pearsonr(effort_hr, rating)[0]:+.2f}")
    print(f"  sleep–performance  r = {stats.pearsonr(sleep, rating)[0]:+.2f}")


if __name__ == "__main__":
    main()
