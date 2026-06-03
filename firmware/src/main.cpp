// main.cpp — Courtside node firmware (ESP32-S3-WROOM, "Lonely Binary Gold")
//
// Sensors:
//   - DHT11   : air temp + humidity   (1-wire DATA on GPIO2)
//   - MLX90614: IR sand-surface temp  (I2C, SDA=21 SCL=20, addr 0x5A)
//   - Mic     : sound/wind proxy       (analog, GPIO4 = ADC1)
//
// Always prints one CSV row/sec over Serial @115200 (bench/offline fallback).
// If USE_WIFI (in secrets.h) is 1, it ALSO POSTs each reading as JSON to the
// backend's /ingest/court, which feeds the live web dashboard.
//
// CSV columns: millis,temp_C,humidity_pct,ir_object_C,ir_ambient_C,sound_pp
// (DHT11 has no pressure, so no pressure column.)

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_MLX90614.h>
#include <DHT.h>

#include "secrets.h"          // copy secrets.h.example -> secrets.h, then fill in
#ifndef USE_WIFI
#define USE_WIFI 0
#endif
#if USE_WIFI
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#endif

// ---- DHT11 (one-wire temp/humidity)
#define DHT_PIN  2
#define DHT_TYPE DHT11

// ---- I2C pins for the MLX90614. Match these to your actual wiring.
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

#if USE_WIFI
// JSON-safe number: NaN -> null (the backend's CourtIn fields are all optional).
static String jnum(float v, int dec) { return isnan(v) ? String("null") : String(v, dec); }

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("# WiFi: connecting to \"%s\" ", WIFI_SSID);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 12000) { delay(300); Serial.print("."); }
  if (WiFi.status() == WL_CONNECTED)
    Serial.printf("\n# WiFi: connected (IP %s) -> POSTing to %s\n",
                  WiFi.localIP().toString().c_str(), BACKEND_URL);
  else
    Serial.println("\n# WiFi: NOT connected — running serial-only");
}

void postReading(float t, float h, float irO, float irA, float snd) {
  if (WiFi.status() != WL_CONNECTED) return;

  String body = String("{\"node_id\":\"") + NODE_ID + "\","
              + "\"device_millis\":" + String(millis()) + ","
              + "\"temp_c\":"       + jnum(t, 1)   + ","
              + "\"humidity_pct\":" + jnum(h, 1)   + ","
              + "\"ir_object_c\":"  + jnum(irO, 2) + ","
              + "\"ir_ambient_c\":" + jnum(irA, 2) + ","
              + "\"sound_pp\":"     + jnum(snd, 0) + "}";

  String url = String(BACKEND_URL) + "/ingest/court";
  HTTPClient http;
  http.setConnectTimeout(1500);
  http.setTimeout(1500);

  WiFiClient plain;
  WiFiClientSecure secure;
  bool began;
  if (url.startsWith("https")) { secure.setInsecure(); began = http.begin(secure, url); }
  else                         { began = http.begin(plain, url); }

  if (began) {
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Node-Key", NODE_KEY);
    http.POST(body);     // fire-and-forget; ignore the response
    http.end();
  }
}
#endif  // USE_WIFI

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

#if USE_WIFI
  connectWiFi();
#else
  Serial.println("# WiFi disabled (USE_WIFI=0) — serial-only");
#endif

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

#if USE_WIFI
  postReading(lastTemp, lastHum, irObj, irAmb, sound);
#endif
}
