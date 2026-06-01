# Courtside — Multi-Modal Beach Volleyball Performance Sensing

ECE 284 (hardware sensing for digital health). A personal-analytics instrument
that fuses three streams to explain day-to-day beach volleyball performance for a
single athlete:

1. **Courtside node** — ESP32-S3 logging air temp/humidity/pressure (BME280),
   sand-surface temp (MLX90614 IR), and a sound/wind proxy (electret mic).
2. **Recovery** — wearable physiology: Apple Watch (primary) + Oura (secondary).
3. **Performance** — per-session subjective rating + objective outcomes.

The node streams readings over the athlete's iPhone hotspot to a small web app
(FastAPI + database) that shows **live data on the phone** (for tripod setup),
auto-ingests Apple Watch data, and lets the athlete **log each session**. A
4-stage analysis (correlation → Lasso/LOOCV → RF/GBM → SHAP) then ranks which
factors best explain performance.

## Layout

```
firmware/     ESP32-S3 PlatformIO project (sensors + I2C scanner; WiFi POST added Phase 2)
backend/      FastAPI web app + dashboard (Phase 1+)
scripts/      Python data pipeline (wearable parse, feature merge, analysis)
oura/         Oura API pull + plots (existing, working)
plots/        Player survey analysis (user-need validation; N≈19)
docs/         enclosure / design notes
data/         local raw exports + db (gitignored)
```

## Setup

```bash
# Python (venv already exists at .venv)
source .venv/bin/activate
pip install -r requirements.txt

# Secrets
cp .env.example .env          # add your OURA_TOKEN
```

### Firmware (VS Code + PlatformIO)
1. Install the **PlatformIO IDE** extension in VS Code.
2. Open the `firmware/` folder. PlatformIO reads `platformio.ini`.
3. `cp firmware/include/secrets.h.example firmware/include/secrets.h` (Phase 2).
4. Plug the board into the **UART USB-C port**; Build → Upload → Monitor from the
   PlatformIO toolbar. The monitor should show an I2C scan then a 1 Hz CSV stream.

## Privacy
`oura/oura_csvs/` contains personal physiological data. Health exports and the
app database live under `data/` and are gitignored. Keep this repo **private**.

## Security note
The Oura token in `.env` was previously stored in plaintext — **rotate it** at
https://cloud.ouraring.com/personal-access-tokens. `.env` and
`firmware/include/secrets.h` are gitignored; never commit them.
