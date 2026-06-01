import matplotlib
matplotlib.use("TkAgg")

import serial
import csv
import time
from pathlib import Path
from collections import deque

import matplotlib.pyplot as plt

PORT = "/dev/cu.wchusbserial10"
BAUD = 115200

OUT_DIR = Path("esp32_csvs")
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "sound_live_log.csv"

window = 200
times = deque(maxlen=window)
wind_scores = deque(maxlen=window)

ser = serial.Serial(PORT, BAUD, timeout=2)
time.sleep(2)

plt.ion()
fig, ax = plt.subplots(figsize=(8, 4))
line, = ax.plot([], [])

ax.set_xlabel("Elapsed time (s)")
ax.set_ylabel("Wind noise score")
ax.set_title("Live ESP32 Acoustic Wind Proxy")

plt.show(block=False)

with open(OUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["elapsed_s", "temp_c", "humidity_pct", "wind_noise_score"])

    try:
        while True:
            raw_line = ser.readline().decode(errors="ignore").strip()

            if not raw_line:
                continue

            print(raw_line)

            if raw_line.startswith("elapsed_s"):
                continue

            parts = raw_line.split(",")

            if len(parts) != 4:
                continue

            try:
                elapsed_s = float(parts[0])
                temp_c = float(parts[1])
                humidity_pct = float(parts[2])
                wind_noise_score = float(parts[3])
            except ValueError:
                continue

            writer.writerow([elapsed_s, temp_c, humidity_pct, wind_noise_score])
            f.flush()

            times.append(elapsed_s)
            wind_scores.append(wind_noise_score)

            line.set_data(times, wind_scores)

            ax.relim()
            ax.autoscale_view()

            fig.canvas.draw()
            fig.canvas.flush_events()

            plt.pause(0.01)

    except KeyboardInterrupt:
        print("\nStopped logging.")
        ser.close()