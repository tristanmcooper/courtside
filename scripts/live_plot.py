#!/usr/bin/env python3
"""Live 3-panel plot of the courtside node over serial: Mic, BME, IR.

Usage:
    python scripts/live_plot.py [PORT]

Default PORT = /dev/cu.wchusbserial210  (override with the arg or COURT_PORT env).

NOTE: close the Arduino IDE Serial Monitor (or any PlatformIO monitor) first —
only one program can hold the serial port at a time.
"""
import os
import sys
import time
from collections import deque

import matplotlib
# Try the backends most likely to pop a real window on macOS, in order.
for _b in ("macosx", "TkAgg", "Qt5Agg"):
    try:
        matplotlib.use(_b, force=True)
        break
    except Exception:
        continue
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

try:
    import serial
except ImportError:
    sys.exit("pyserial missing. Run:  .venv/bin/pip install pyserial")

PORT = sys.argv[1] if len(sys.argv) > 1 else os.getenv("COURT_PORT", "/dev/cu.wchusbserial10")
BAUD = 115200
WINDOW = 120  # samples shown (~2 min at 1 Hz)

COLS = ["millis", "temp_C", "humidity_pct",
        "ir_object_C", "ir_ambient_C", "sound_pp"]
col_idx = {c: i for i, c in enumerate(COLS)}  # default order; updated if header seen

print(f"Backend: {matplotlib.get_backend()}")
print(f"Opening {PORT} @ {BAUD} …  (close the window or Ctrl-C to quit)")
try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
except serial.SerialException as e:
    sys.exit(f"Could not open {PORT}: {e}\n"
             "- Close the Arduino IDE Serial Monitor / PlatformIO monitor.\n"
             "- List ports with:  ls /dev/cu.*")
time.sleep(2)  # let the board reset/boot after the port opens

t0 = None
elapsed = deque(maxlen=WINDOW)
buf = {c: deque(maxlen=WINDOW) for c in COLS}
seen_raw = 0


def parse_line(line):
    """Return {col: float} or None. Updates col_idx if a header row arrives."""
    global col_idx
    if not line or line.startswith("#"):
        return None
    if "millis" in line and "temp_C" in line:          # header
        names = [x.strip() for x in line.split(",")]
        col_idx = {n: i for i, n in enumerate(names)}
        return None
    parts = line.split(",")
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return None
    return {c: vals[i] for c, i in col_idx.items() if i < len(vals)}


fig, (axM, axB, axIR) = plt.subplots(3, 1, figsize=(8, 8), sharex=True)
fig.suptitle("Courtside node — live")

(lnSound,) = axM.plot([], [], color="#c05a3a", label="sound_pp")
axM.set_ylabel("Mic (peak-to-peak)")
axM.legend(loc="upper left")

axBh = axB.twinx()
(lnTemp,) = axB.plot([], [], color="tomato", label="temp °C")
(lnHum,) = axBh.plot([], [], color="steelblue", label="humidity %")
axB.set_ylabel("Temp (°C)", color="tomato")
axBh.set_ylabel("Humidity (%)", color="steelblue")
axB.legend(handles=[lnTemp, lnHum], loc="upper left")

(lnObj,) = axIR.plot([], [], color="#d97706", label="ir_object °C (sand)")
(lnAmb,) = axIR.plot([], [], color="#6b7280", label="ir_ambient °C")
axIR.set_ylabel("IR (°C)")
axIR.set_xlabel("Elapsed (s)")
axIR.legend(loc="upper left")


def update(_):
    global t0, seen_raw
    for _ in range(40):                # drain up to 40 lines/frame, stay current
        if not ser.in_waiting:
            break
        raw = ser.readline().decode(errors="ignore").strip()
        if seen_raw < 6:
            print("serial:", raw)
            seen_raw += 1
        row = parse_line(raw)
        if not row or "millis" not in row:
            continue
        ms = row["millis"]
        if t0 is None:
            t0 = ms
        elapsed.append((ms - t0) / 1000.0)
        for c in COLS:
            buf[c].append(row.get(c, float("nan")))
    xs = list(elapsed)
    if xs:
        lnSound.set_data(xs, list(buf["sound_pp"]))
        lnTemp.set_data(xs, list(buf["temp_C"]))
        lnHum.set_data(xs, list(buf["humidity_pct"]))
        lnObj.set_data(xs, list(buf["ir_object_C"]))
        lnAmb.set_data(xs, list(buf["ir_ambient_C"]))
        for a in (axM, axB, axBh, axIR):
            a.relim()
            a.autoscale_view()
    return lnSound, lnTemp, lnHum, lnObj, lnAmb


ani = FuncAnimation(fig, update, interval=300, cache_frame_data=False)
plt.tight_layout()
plt.show()
ser.close()
