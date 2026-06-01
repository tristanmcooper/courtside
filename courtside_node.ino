#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <Adafruit_MLX90614.h>
#include <DHT.h>

// ---------- Pin setup ----------
#define I2C_SDA 21
#define I2C_SCL 20

#define MIC_PIN 4
#define DHT_PIN 2

// If your one-wire temp/humidity sensor is DHT11, change this to DHT11.
#define DHT_TYPE DHT22

#define MIC_WINDOW_MS 50
#define LOG_INTERVAL_MS 1000

Adafruit_BME280 bme;
Adafruit_MLX90614 mlx = Adafruit_MLX90614();
DHT dht(DHT_PIN, DHT_TYPE);

bool bmeOK = false;
bool mlxOK = false;
bool dhtOK = true;

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

  return (float)(sigMax - sigMin);
}

void scanI2C() {
  Serial.println("# I2C scan starting...");

  int count = 0;

  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("# I2C device found at 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
      count++;
    }
  }

  if (count == 0) {
    Serial.println("# No I2C devices found");
  }

  Serial.println("# I2C scan done");
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  analogReadResolution(12);

  Wire.begin(I2C_SDA, I2C_SCL);
  dht.begin();

  scanI2C();

  bmeOK = bme.begin(0x76) || bme.begin(0x77);
  mlxOK = mlx.begin();

  if (!bmeOK) {
    Serial.println("# WARNING: BME280 not found on I2C");
  }

  if (!mlxOK) {
    Serial.println("# WARNING: MLX90614 not found on I2C");
  }

  Serial.println("millis,dht_temp_C,dht_humidity_pct,bme_temp_C,bme_humidity_pct,bme_pressure_hPa,ir_object_C,ir_ambient_C,sound_pp");
}

void loop() {
  if (millis() - lastLog < LOG_INTERVAL_MS) {
    return;
  }

  lastLog = millis();

  float dhtTemp = dht.readTemperature();
  float dhtHum = dht.readHumidity();

  if (isnan(dhtTemp) || isnan(dhtHum)) {
    dhtTemp = NAN;
    dhtHum = NAN;
  }

  float bmeTemp = bmeOK ? bme.readTemperature() : NAN;
  float bmeHum = bmeOK ? bme.readHumidity() : NAN;
  float bmePress = bmeOK ? bme.readPressure() / 100.0F : NAN;

  float irObj = mlxOK ? mlx.readObjectTempC() : NAN;
  float irAmb = mlxOK ? mlx.readAmbientTempC() : NAN;

  float sound = readSoundLevel();

  Serial.print(millis());
  Serial.print(",");

  Serial.print(dhtTemp, 2);
  Serial.print(",");
  Serial.print(dhtHum, 2);
  Serial.print(",");

  Serial.print(bmeTemp, 2);
  Serial.print(",");
  Serial.print(bmeHum, 2);
  Serial.print(",");
  Serial.print(bmePress, 2);
  Serial.print(",");

  Serial.print(irObj, 2);
  Serial.print(",");
  Serial.print(irAmb, 2);
  Serial.print(",");

  Serial.println(sound, 0);
}