# Apple Watch → Backend (Health Auto Export) setup

Goal: your daily recovery metrics (HRV, resting HR, sleep) upload automatically to
the Courtside backend's `/ingest/health`, landing in the `health_daily` table that
the analysis joins to each session by date. You already have HAE Premium.

> Endpoint = `<BACKEND_URL>/ingest/health`
> - Cloud (recommended): `https://<your-app>.onrender.com/ingest/health`
> - Local test on hotspot: `http://<laptop-ip>:8000/ingest/health`

## Automation 1 — Health Metrics (the important one)
In the Health Auto Export app:
1. **Automations tab → New Automation**.
2. **Automation Type:** REST API.
3. **Name:** `Courtside health`.
4. **URL:** `<BACKEND_URL>/ingest/health`
5. **HTTP Headers:** none required. (Later, if you set a backend `NODE_KEY`, you'd
   add a matching header — skip for now.)
6. **Data Type:** Health Metrics → **Select Health Metrics:**
   - Heart Rate Variability
   - Resting Heart Rate
   - Sleep Analysis
   - Respiratory Rate
   - Heart Rate
7. **Export Format:** JSON
8. **Summarize Data:** ON
9. **Time Grouping:** Days
10. **Batch Requests:** ON
11. **Date Range:** start with **Previous 7 Days** (backfills history); after the
    first run, switch to **Since Last Sync**.
12. **Sync Cadence:** every 1 hour (or daily — these are daily metrics).
13. **Tap Update** to save.

### Test it now
- Tap **Manual Export → pick today (or last 7 days) → Export**.
- **View Activity Logs** in the automation → you want an **HTTP 200** with a summary.
- The backend replies `{"ok":true,"days_written":N,"metrics_seen":[...]}` — that's success.

## Automation 2 — Workouts (optional, for in-session HR)
Make a second REST API automation, same URL, **Data Type: Workouts**, Include
Workout Metrics ON. This carries the heart-rate trace from each Apple Watch
workout you start courtside. (Note: the backend currently stores the daily metrics;
parsing the workout HR trace is a small future add — set this up now so the data
is captured server-side regardless.)

## During a session
Start an Apple Watch **workout** when you start playing (Volleyball or Other) and
stop it when you finish — that's what produces the in-session HR.

## iOS limitations (why a sync might be late)
- Automations only run while the **iPhone is unlocked** (Apple rule). Tip: keep it
  charging / use iPhone Mirroring to let them run more reliably.
- Background App Refresh must be ON for HAE; Low Power Mode delays runs.
- If a day looks missing, open HAE and run a **Manual Export** for that date.

## How it maps into the pipeline
| HAE metric | backend field (`health_daily`) |
|---|---|
| heart_rate_variability | `hrv_sdnn` |
| resting_heart_rate | `resting_hr` |
| sleep_analysis | `sleep_hours` |

Joined to each session by **date**. Oura can backfill the same table
(`source="oura"`) for days before you switched to Apple Watch.
