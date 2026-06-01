// main.cpp — Courtside node firmware (PlatformIO port of courtside_node.ino)
// ESP32-S3-WROOM (Lonely Binary Gold Edition)
//
// Reads BME280 (temp/humidity/pressure), MLX90614 (IR surface + ambient temp),
// and an analog mic, then prints one CSV row per second over Serial @115200.
// Sensor logic is unchanged from the validated .ino. Phase 2 adds WiFi + HTTP
// POST to the backend; the Serial CSV stays as a bench/offline fallback.
//
// I2C: BME280 = 0x76 or 0x77, MLX90614 = 0x5A, both on one bus (SDA=8, SCL=9).

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <Adafruit_MLX90614.h>

// ---- I2C pins. Lonely Binary S3 default Qwiic/STEMMA is SDA=8, SCL=9.
#define I2C_SDA 8
#define I2C_SCL 9

// ---- Mic: GPIO4 = ADC1_CH3. ADC1 is safe to read while WiFi is active
//      (ADC2 pins are not — keep the mic on an ADC1 pin once WiFi is added).
#define MIC_PIN 4
#define MIC_WINDOW_MS 50      // sampling window for peak-to-peak amplitude

#define LOG_INTERVAL_MS 1000

Adafruit_BME280 bme;
Adafruit_MLX90614 mlx = Adafruit_MLX90614();

bool bmeOK = false;
bool mlxOK = false;
unsigned long lastLog = 0;

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

// Prints every responding I2C address. Use this when wiring to confirm the
// BME280 (0x76/0x77) and MLX90614 (0x5A) are on the bus before trusting data.
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

  Wire.begin(I2C_SDA, I2C_SCL);
  analogReadResolution(12);          // 0..4095

  scanI2C();

  bmeOK = bme.begin(0x76) || bme.begin(0x77);
  mlxOK = mlx.begin();

  if (!bmeOK) Serial.println("# WARNING: BME280 not found");
  if (!mlxOK) Serial.println("# WARNING: MLX90614 not found");

  // CSV header — keep column names stable for the pipeline / backend.
  Serial.println("millis,temp_C,humidity_pct,pressure_hPa,ir_object_C,ir_ambient_C,sound_pp");
}

void loop() {
  if (millis() - lastLog < LOG_INTERVAL_MS) return;
  lastLog = millis();

  float t     = bmeOK ? bme.readTemperature()        : NAN;
  float h     = bmeOK ? bme.readHumidity()           : NAN;
  float p     = bmeOK ? bme.readPressure() / 100.0F  : NAN;   // hPa
  float irObj = mlxOK ? mlx.readObjectTempC()        : NAN;   // surface (sand) temp
  float irAmb = mlxOK ? mlx.readAmbientTempC()       : NAN;
  float sound = readSoundLevel();

  Serial.print(millis());  Serial.print(",");
  Serial.print(t, 2);      Serial.print(",");
  Serial.print(h, 2);      Serial.print(",");
  Serial.print(p, 2);      Serial.print(",");
  Serial.print(irObj, 2);  Serial.print(",");
  Serial.print(irAmb, 2);  Serial.print(",");
  Serial.println(sound, 0);
}
