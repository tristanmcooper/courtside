# Courtside — Multi-Modal Beach Volleyball Performance Sensing

ECE 284 (hardware sensing for digital health). A personal-analytics instrument
that fuses three streams to explain day-to-day beach volleyball performance for a
single athlete:

1. **Courtside node** — ESP32-S3 logging air temp/humidity (DHT11),
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

### Firmware (PlatformIO via CLI)
PlatformIO lives in its **own** venv (`.venv_pio`), separate from the data/analysis
venv (`.venv`) — keep them apart (mixing them corrupted the original env).

```bash
cd "/Users/tristancooper/Desktop/ECE 284 Hardware Sensing"
source .venv_pio/bin/activate                       # PlatformIO env (NOT .venv)
cd firmware
python3 -m platformio run                           # compile
python3 -m platformio run -t upload                 # flash (board on UART USB-C port)
python3 -m platformio device monitor -b 115200      # serial monitor
```

Copy `include/secrets.h.example` → `include/secrets.h` before the WiFi build (Phase 2).
On boot the monitor prints a config summary + I2C scan, then a 1 Hz CSV stream:
`millis,temp_C,humidity_pct,ir_object_C,ir_ambient_C,sound_pp`.

**Hardware notes**
- **Solder the MLX90614 header before debugging IR.** Loose/touching I2C pins make
  the device vanish from the bus — `# I2C scan` must show `found 0x5A` for IR to read.
- If DHT11/mic readings jump (mic pegging to 4095) or drop to `nan`, **reseat the
  Dupont jumpers** — flaky connectors, not code, are the usual cause. Use a
  breadboard / screw terminals / tape for strain relief.

## Privacy
`oura/oura_csvs/` contains personal physiological data. Health exports and the
app database live under `data/` and are gitignored. Keep this repo **private**.

## Security note
The Oura token in `.env` was previously stored in plaintext — **rotate it** at
https://cloud.ouraring.com/personal-access-tokens. `.env` and
`firmware/include/secrets.h` are gitignored; never commit them.
