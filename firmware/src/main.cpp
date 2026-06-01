// main.cpp — Courtside node firmware (ESP32-S3-WROOM, "Lonely Binary Gold")
//
// Sensors:
//   - DHT11   : air temp + humidity   (1-wire DATA on GPIO2)
//   - MLX90614: IR sand-surface temp  (I2C, SDA=21 SCL=20, addr 0x5A)
//   - Mic     : sound/wind proxy       (analog, GPIO4 = ADC1)
//
// Prints one CSV row per second over Serial @115200. Phase 2 adds WiFi + HTTP
// POST to the backend; this Serial CSV stays as a bench/offline fallback.
//
// NOTE: DHT11 has no barometric pressure, so the pressure column is gone vs the
// old BME280 schema. CSV columns are now:
//   millis,temp_C,humidity_pct,ir_object_C,ir_ambient_C,sound_pp

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_MLX90614.h>
#include <DHT.h>

// ---- DHT11 (one-wire temp/humidity)
#define DHT_PIN  2
#define DHT_TYPE DHT11

// ---- I2C pins for the MLX90614. Match these to your actual wiring (see #defines).
#define I2C_SDA 21
#define I2C_SCL 20

// ---- Mic: GPIO4 = ADC1_CH3. ADC1 is safe to read while WiFi is active.
#define MIC_PIN 4
#define MIC_WINDOW_MS 50      // window for peak-to-peak amplitude

#define LOG_INTERVAL_MS 1000

DHT dht(DHT_PIN, DHT_TYPE);
Adafruit_MLX90614 mlx = Adafruit_MLX90614();

bool mlxOK = false;
unsigned long lastLog = 0;
float lastTemp = NAN, lastHum = NAN;   // cache last good DHT read (it occasionally NaNs)

float readSoundLevel() {
  unsigned long start = millis();
  int sigMax = 0;
  int sigMin = 4095;
  while (millis() - start < MIC_WINDOW_MS) {
    int s = analogRead(MIC_PIN);
    if (s > sigMax) sigMax = s;
    if (s < sigMin) sigMin = s;
  }
  return (float)(sigMax - sigMin);   // peak-to-peak amplitude (raw ADC units)
}

// Prints every responding I2C address — use this to confirm the MLX90614 (0x5A)
// is on the bus when wiring.
void scanI2C() {
  Serial.println("# I2C scan:");
  uint8_t found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("#   found 0x%02X\n", addr);
      found++;
    }
  }
  if (found == 0) Serial.println("#   (none found — check wiring / pull-ups)");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  dht.begin();
  Wire.begin(I2C_SDA, I2C_SCL);
  analogReadResolution(12);          // 0..4095

  // --- startup config summary (lines starting with # are ignored by the pipeline)
  Serial.printf("# DHT11 configured on GPIO%d\n", DHT_PIN);
  Serial.printf("# MLX90614 I2C configured SDA=%d SCL=%d\n", I2C_SDA, I2C_SCL);
  Serial.printf("# Mic configured on GPIO%d\n", MIC_PIN);

  scanI2C();
  mlxOK = mlx.begin();
  if (!mlxOK) Serial.println("# WARNING: MLX90614 not found (solder the header — see README)");

  // CSV header — keep column names stable for the pipeline / backend.
  Serial.println("millis,temp_C,humidity_pct,ir_object_C,ir_ambient_C,sound_pp");
}

void loop() {
  if (millis() - lastLog < LOG_INTERVAL_MS) return;
  lastLog = millis();

  float t = dht.readTemperature();   // °C
  float h = dht.readHumidity();      // %RH
  if (!isnan(t)) lastTemp = t;
  if (!isnan(h)) lastHum = h;

  float irObj = mlxOK ? mlx.readObjectTempC()  : NAN;   // sand surface temp
  float irAmb = mlxOK ? mlx.readAmbientTempC() : NAN;
  float sound = readSoundLevel();

  Serial.print(millis());     Serial.print(",");
  Serial.print(lastTemp, 1);  Serial.print(",");   // DHT11 is ±2°C, 1 decimal is plenty
  Serial.print(lastHum, 1);   Serial.print(",");
  Serial.print(irObj, 2);     Serial.print(",");
  Serial.print(irAmb, 2);     Serial.print(",");
  Serial.println(sound, 0);
}
