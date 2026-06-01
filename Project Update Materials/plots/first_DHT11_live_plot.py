import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import serial

ser = serial.Serial('/dev/cu.wchusbserial10', 115200)
elapsed, temps, humids = [], [], []

fig, ax1 = plt.subplots(figsize=(8, 3.5))
ax2 = ax1.twinx()

def update(frame):
    line = ser.readline().decode().strip()
    try:
        e, t, h = line.split(',')
        elapsed.append(float(e)/60)
        temps.append(float(t))
        humids.append(float(h))
        ax1.cla(); ax2.cla()
        ax1.plot(elapsed, temps, color='tomato')
        ax1.set_ylabel('Temperature (°C)', color='tomato')
        ax2.plot(elapsed, humids, color='steelblue')
        ax2.set_ylabel('Humidity (%)', color='steelblue')
        ax1.set_xlabel('Time (min)')
        plt.title('ESP32-S3 + DHT11 live — courtside node bench test')
    except:
        pass

ani = animation.FuncAnimation(fig, update, interval=2000)
plt.tight_layout()
plt.show()