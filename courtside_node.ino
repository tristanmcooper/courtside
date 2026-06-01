// courtside_node.ino
// ESP32-S3-WROOM (Lonely Binary Gold Edition)
// Reads BME280 (temp/humidity/pressure), MLX90614 (IR surface + ambient temp),
// and an analog mic, then prints one CSV row per second over Serial @115200.
//
// Libraries needed (Tools > Manage Libraries):
//   - Adafruit BME280 Library
//   - Adafruit MLX90614 Library
//   - Adafruit Unified Sensor   (already installed)
//
// I2C addresses: BME280 = 0x76 or 0x77, MLX90614 = 0x5A. Both share one bus.

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <Adafruit_MLX90614.h>

// ---- I2C pins. Lonely Binary S3 default Qwiic/STEMMA is SDA=8, SCL=9.
// If sensors don't init, try swapping or check the silkscreen next to your wired pins.
#define I2C_SDA 8
#define I2C_SCL 9

// ---- Mic: analog-capable GPIO. Change to whichever pin the mic OUT is wired to.
#define MIC_PIN 4
#define MIC_WINDOW_MS 50      // sampling window for peak-to-peak amplitude

// ---- Logging cadence
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

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(I2C_SDA, I2C_SCL);
  analogReadResolution(12);          // 0..4095

  bmeOK = bme.begin(0x76) || bme.begin(0x77);
  mlxOK = mlx.begin();

  if (!bmeOK) Serial.println("# WARNING: BME280 not found");
  if (!mlxOK) Serial.println("# WARNING: MLX90614 not found");

  // CSV header — keep column names stable for the Python pipeline
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
