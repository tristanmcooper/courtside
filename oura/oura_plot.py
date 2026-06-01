from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).parent
CSV_DIR = SCRIPT_DIR / "oura_csvs"
PLOT_DIR = SCRIPT_DIR.parent / "plots"

PLOT_DIR.mkdir(exist_ok=True)

sleep_path = CSV_DIR / "oura_daily_sleep.csv"
readiness_path = CSV_DIR / "oura_daily_readiness.csv"
activity_path = CSV_DIR / "oura_daily_activity.csv"

sleep = pd.read_csv(sleep_path)
readiness = pd.read_csv(readiness_path)
activity = pd.read_csv(activity_path)

sleep["day"] = pd.to_datetime(sleep["day"])
readiness["day"] = pd.to_datetime(readiness["day"])
activity["day"] = pd.to_datetime(activity["day"])

df = sleep[["day", "score"]].rename(columns={"score": "sleep_score"})

df = df.merge(
    readiness[["day", "score"]].rename(columns={"score": "readiness_score"}),
    on="day",
    how="outer"
)

df = df.merge(
    activity[["day", "score"]].rename(columns={"score": "activity_score"}),
    on="day",
    how="outer"
)

df = df.sort_values("day")

plt.figure(figsize=(7, 3))
plt.plot(df["day"], df["sleep_score"], marker="o", label="Sleep score")
plt.plot(df["day"], df["readiness_score"], marker="o", label="Readiness score")
plt.plot(df["day"], df["activity_score"], marker="o", label="Activity score")

plt.xlabel("Date")
plt.ylabel("Oura daily score")
plt.title("Oura Recovery and Activity Data Pipeline Validation")
plt.xticks(rotation=30, ha="right")
plt.legend()
plt.tight_layout()

out_path = PLOT_DIR / "oura_daily_scores.png"
plt.savefig(out_path, dpi=200)

print(f"Saved plot to {out_path}")
print(df.tail())