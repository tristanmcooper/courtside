import os
import requests
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

TOKEN = os.getenv("OURA_TOKEN")
headers = {"Authorization": f"Bearer {TOKEN}"}

BASE = "https://api.ouraring.com/v2/usercollection"

end_date = date.today()
start_date = end_date - timedelta(days=21)

params = {
    "start_date": start_date.isoformat(),
    "end_date": end_date.isoformat()
}

endpoints = {
    "daily_sleep": "daily_sleep",
    "daily_readiness": "daily_readiness",
    "daily_activity": "daily_activity",
    "sleep_periods": "sleep",
    "workouts": "workout"
}
CSV_DIR = Path(__file__).parent / "oura_csvs"
CSV_DIR.mkdir(exist_ok=True)

for name, endpoint in endpoints.items():
    url = f"{BASE}/{endpoint}"
    r = requests.get(url, headers=headers, params=params)

    print(f"\n{name}: {r.status_code}")

    if r.status_code != 200:
        print(r.text)
        continue

    data = r.json().get("data", [])
    df = pd.json_normalize(data)

    out = CSV_DIR / f"oura_{name}.csv"
    df.to_csv(out, index=False)

    print(f"Saved {len(df)} rows to {out}")
    print(df.head())