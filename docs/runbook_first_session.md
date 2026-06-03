# First Data Collection — Runbook

Goal: capture one synchronized session (court sensors + Apple Watch + a logged
self-rating). Two connection options below — **use Option A for the first session**
(most reliable), move to Option B (Render) once it's proven.

---

## Pre-flight (do at home, before the beach)

**Hardware**
- [ ] MLX90614 header **soldered** (loose pins = no IR). Optional for first run —
      IR just logs `null` if absent; everything else still works.
- [ ] Sensors seated: DHT11 → GPIO2, mic OUT → GPIO4, MLX SDA→21 / SCL→20.
- [ ] Power bank charged.

**Firmware** (`firmware/include/secrets.h`)
- [ ] `USE_WIFI 1`
- [ ] `WIFI_SSID` / `WIFI_PASSWORD` = your **iPhone hotspot** name + password
- [ ] `BACKEND_URL` = `http://172.20.10.2:8000`  (typical laptop IP on an iPhone
      hotspot — confirm at the beach, see Option A step 2)
- [ ] Flash: `cd firmware && python3 -m platformio run -t upload` (in `.venv_pio`)
- [ ] Serial monitor sanity check (`platformio device monitor -b 115200`):
  - `#   found 0x5A` (if MLX soldered)
  - DHT temp/humidity look real, mic not stuck at 4095
  - `# WiFi: connected (IP ...) -> POSTing to ...`

**Backend** — confirm it runs (one command):
```bash
bash scripts/run_backend.sh        # prints the URL + your current IP
```
Open `http://localhost:8000` → dashboard loads. Ctrl-C to stop until the beach.
(To start the session with a clean DB: `rm ~/courtside_data.db` first.)

---

## Option A — laptop on the hotspot (use this first) ✅

No internet needed; laptop sits in a shaded bag.

1. **iPhone:** Settings → Personal Hotspot **ON**; turn **Maximize Compatibility ON**
   (forces 2.4 GHz — the ESP32-S3 is 2.4 GHz only).
2. **Laptop:** join the hotspot WiFi, then `bash scripts/run_backend.sh`. Note the
   printed hotspot IP (usually `172.20.10.2`). If it differs from `BACKEND_URL` in
   `secrets.h`, update it and reflash.
3. **Node:** plug into the power bank. It boots → joins the hotspot → starts POSTing.
4. **Phone:** open `http://<laptop-ip>:8000`. Status should turn green **online**.
5. **Position the tripod** using the live sand ring + wind trace.
6. **Apple Watch:** start a workout (Volleyball / Other) so in-session HR is recorded.
7. **Play.**
8. **Log it:** Log-session tab → rating, wind, kills/errors, partner, location
   (type it — geolocation needs https, which Option A lacks), Save.
9. **Stop** the Apple Watch workout.

## Option B — Render cloud (v2, no laptop) ☁️
Deploy once via `render.yaml` (see that file). Then set `BACKEND_URL` to the
`https://…onrender.com` URL and reflash. Beach flow is the same, minus the laptop:
node → iPhone hotspot → Render; phone opens the Render URL (geolocation works).
Open the dashboard first to wake the free service (~30–60 s cold start).

---

## Recovery data (Apple Watch → backend)
Health Auto Export → Automations → **REST API**:
- URL = `<BACKEND_URL>/ingest/health`  (Render URL, or the laptop IP on the hotspot)
- Data Type: Health Metrics · Format: JSON · Aggregate: Days · Batch: ON
- Metrics: HRV, Resting Heart Rate, Sleep Analysis, Respiratory Rate, Heart Rate
- Make a 2nd automation: Data Type **Workouts** (gets the in-session HR trace)
- Hit **Manual Export → today** after the session to push it now.

## After the session
- Data is in `~/courtside_data.db`. Confirm: session in the Log tab, court rows via
  the live view, and the health day arrived (HAE Activity Log shows a 200).
- That's one complete multi-modal session. Repeat to build N.

---

## Troubleshooting
| Symptom | Fix |
|---|---|
| Dashboard never goes "online" | node serial must say "WiFi connected"; `BACKEND_URL` IP must match the laptop's hotspot IP; both on the same hotspot |
| IR / sand stays blank (`null`) | MLX not soldered/detected — check serial for `0x5A` |
| `sound_pp` stuck at 4095 | mic OUT wire floating/shorted — reseat it |
| DHT/mic values flicker or drop | reseat Dupont jumpers; add tape/strain relief |
| node connects but no data on dash | backend must be started with `--host 0.0.0.0` (run_backend.sh does this) |
| node can't reach laptop at all | if macOS prompts "allow incoming connections to Python" → **Allow** (System Settings → Network → Firewall); otherwise it blocks the node |
