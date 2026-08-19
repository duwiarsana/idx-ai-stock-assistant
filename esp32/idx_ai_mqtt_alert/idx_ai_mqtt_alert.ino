/*
 * IDX AI — Paper Trading MQTT Alert (ESP32-C3)
 *
 * Mendengarkan event paper trading dari bot (Mosquitto MQTT di VPS) lalu:
 *  - membunyikan buzzer pasif dengan pola beep berbeda tiap event
 *  - menampilkan info di OLED SSD1306 (128x64, I2C)
 *
 * ==============================================================
 *  SETUP WIFI (WiFiManager)
 * ==============================================================
 *  Setting MQTT sudah di-hardcode di bawah (tidak perlu diubah).
 *  Yang di-set lewat portal hanya SSID + password WiFi.
 *
 *  Saat pertama dinyalakan (atau WiFi tidak ketemu / tombol BOOT
 *  ditekan saat start), ESP32 membuka Access Point bernama:
 *
 *      IDX-AI-Setup
 *
 *  Hubungkan HP/laptop ke AP itu, lalu buka browser:
 *
 *      http://192.168.4.1
 *
 *  Isi Nama WiFi + Password WiFi → Save → ESP32 restart & konek.
 *
 *  Untuk RESET WiFi:
 *    1. Matikan ESP32
 *    2. Tahan tombol BOOT (GPIO9)
 *    3. Nyalakan ESP32 sambil tetap menahan BOOT
 *       selama 5 detik → buzzer berbunyi 2x → WiFi dihapus.
 *
 * Topic:
 *   crypto/trade/buy      → 1 beep pendek  (1000Hz)
 *   crypto/trade/profit   → 3 beep naik    (800→1400Hz)
 *   crypto/trade/loss     → 2 beep panjang (400Hz)
 *   crypto/trade/heartbeat→ tanpa suara, update watchdog + hitungan
 *
 * Wiring (ESP32-C3 Super Mini):
 *   OLED SDA → GPIO4, SCL → GPIO5, VCC → 3V3, GND → GND
 *   Buzzer (+) → GPIO3, (−) → GND
 *   Tombol BOOT ada di papan (GPIO9), dipakai untuk reset WiFi.
 *
 * Library (Arduino IDE Library Manager):
 *   PubSubClient, Adafruit SSD1306, Adafruit GFX, WiFiManager
 */

#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <Wire.h>

// ══════════════════════════════════════════════════════════════════
//  MQTT — HARDCODED (ubah di sini jika broker berganti)
// ══════════════════════════════════════════════════════════════════
const char *MQTT_HOST = "76.13.19.250"; // IP VPS
const int MQTT_PORT = 1883;
const char *MQTT_USER = "idxbot";
const char *MQTT_PASS = "62b97f2b443a64738c2bf04bab73933b";
const char *MQTT_TOPIC = "crypto/trade/#";

// ── Pin ──────────────────────────────────────────────────────────────
#define PIN_BUZZER 3 // GPIO3 — buzzer pasif (+)
#define OLED_SDA 4   // GPIO4
#define OLED_SCL 5   // GPIO5
#define PIN_BOOT 9   // GPIO9 — tombol BOOT (reset WiFi)

// ── OLED ─────────────────────────────────────────────────────────────
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_ADDR 0x3C
TwoWire I2C_OLED = TwoWire(0);
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &I2C_OLED);

// ── MQTT ─────────────────────────────────────────────────────────────
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

// ── Watchdog heartbeat ───────────────────────────────────────────────
const unsigned long WATCHDOG_MS = 3UL * 60UL * 1000UL; // 3 menit
unsigned long lastHeartbeat = 0;

// Status terakhir yang ditampilkan
String lastEvent = "";
String lastSymbol = "";
String lastExtra = "";
String lastBalance = "";
String lastPnl = "";
unsigned int heartbeatCount = 0;

// ── Prototipe ────────────────────────────────────────────────────────
void beep(int freq, int ms);
void beepBuy();
void beepProfit();
void beepLoss();
void beepReset();
void drawDisplay(const char *title, const char *line2, const char *line3,
                 const char *line4);
void drawHeartbeat();
void drawOffline();
void connectMQTT();
void mqttCallback(char *topic, byte *payload, unsigned int length);
String getJsonField(String json, String key);

// ── Setup ────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_BOOT, INPUT_PULLUP);

  // Inisialisasi OLED
  I2C_OLED.begin(OLED_SDA, OLED_SCL, 400000);
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println("OLED gagal init!");
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  drawDisplay("IDX AI ALERT", "Memuat...", "", "");

  // Reset paksa: tahan tombol BOOT 5 detik saat start → hapus WiFi
  unsigned long holdStart = millis();
  while (digitalRead(PIN_BOOT) == LOW) {
    delay(50);
    if (millis() - holdStart > 5000) {
      WiFiManager wm;
      wm.resetSettings();
      beepReset();
      drawDisplay("WIFI DIHAPUS", "Portal akan buka...", "", "");
      delay(2000);
      break;
    }
  }

  // Setup WiFiManager (hanya WiFi — MQTT sudah hardcoded)
  WiFi.mode(WIFI_STA);
  WiFiManager wm;
  wm.setTitle("IDX AI Alert Setup");

  drawDisplay("IDX AI ALERT", "Konek WiFi...", "", "");
  Serial.println("Menghubungi WiFi (atau portal setup)...");

  // autoConnect: coba WiFi tersimpan → jika gagal buka AP "IDX-AI-Setup"
  if (!wm.autoConnect("IDX-AI-Setup")) {
    Serial.println("Gagal setup WiFi — restart 30s");
    drawDisplay("SETUP GAGAL", "Restart dalam 30s...", "", "");
    delay(30000);
    ESP.restart();
  }

  Serial.println("WiFi OK: " + WiFi.localIP().toString());

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(512);

  connectMQTT();
  lastHeartbeat = millis();
}

// ── Loop ─────────────────────────────────────────────────────────────
void loop() {
  if (!mqtt.connected()) {
    connectMQTT();
  }
  mqtt.loop();

  // Watchdog: tidak ada heartbeat dalam WATCHDOG_MS → tampilkan offline
  if (millis() - lastHeartbeat > WATCHDOG_MS) {
    drawOffline();
  }
}

// ── MQTT koneksi (reconnect otomatis) ────────────────────────────────
void connectMQTT() {
  while (!mqtt.connected()) {
    Serial.print("MQTT connect " + String(MQTT_HOST) + ":");
    Serial.println(MQTT_PORT);
    if (mqtt.connect("esp32-idx-alert", MQTT_USER, MQTT_PASS)) {
      Serial.println("MQTT OK");
      mqtt.subscribe(MQTT_TOPIC);
      drawDisplay("MQTT OK", MQTT_HOST, "Menunggu heartbeat...", "");
    } else {
      Serial.print(" gagal, rc=");
      Serial.print(mqtt.state());
      Serial.println(" coba lagi 3s");
      drawDisplay("MQTT", "Gagal konek broker", MQTT_HOST, "coba 3 detik...");
      delay(3000);
    }
  }
}

// ── Callback pesan MQTT ──────────────────────────────────────────────
void mqttCallback(char *topic, byte *payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++)
    msg += (char)payload[i];

  String t = String(topic);

  if (t.endsWith("/heartbeat")) {
    lastHeartbeat = millis();
    heartbeatCount++;
    drawHeartbeat();
    return;
  }

  // Parse JSON sederhana: ambil field symbol & pnl (jika ada)
  String symbol = getJsonField(msg, "display");
  if (symbol.length() == 0)
    symbol = getJsonField(msg, "symbol");
  String pnl = getJsonField(msg, "pnl");
  String pnlPct = getJsonField(msg, "pnl_percent");
  String balance = getJsonField(msg, "balance");
  String realized = getJsonField(msg, "realized_pnl");

  if (t.endsWith("/buy")) {
    lastEvent = "BUY";
    lastSymbol = symbol;
    lastExtra = "Entry: " + getJsonField(msg, "entry_price");
    lastBalance = balance;
    lastPnl = realized;
    beepBuy();
    drawDisplay("** PAPER BUY **", symbol.c_str(), lastExtra.c_str(),
                balance.length() ? ("Cash: " + balance).c_str() : "");
    Serial.println("BUY: " + symbol + " " + lastExtra);
  } else if (t.endsWith("/profit")) {
    lastEvent = "PROFIT";
    lastSymbol = symbol;
    lastExtra = "PnL: " + pnl + " (" + pnlPct + "%)";
    lastBalance = balance;
    lastPnl = realized;
    beepProfit();
    drawDisplay("*** PROFIT ***", symbol.c_str(), lastExtra.c_str(),
                realized.length() ? ("Total: " + realized).c_str() : "");
    Serial.println("PROFIT: " + symbol + " " + lastExtra);
  } else if (t.endsWith("/loss")) {
    lastEvent = "LOSS";
    lastSymbol = symbol;
    lastExtra = "PnL: " + pnl + " (" + pnlPct + "%)";
    lastBalance = balance;
    lastPnl = realized;
    beepLoss();
    drawDisplay("** CUT LOSS **", symbol.c_str(), lastExtra.c_str(),
                realized.length() ? ("Total: " + realized).c_str() : "");
    Serial.println("LOSS: " + symbol + " " + lastExtra);
  }
}

// ── Pola beep ────────────────────────────────────────────────────────
void beep(int freq, int ms) {
  tone(PIN_BUZZER, freq, ms);
  delay(ms + 50); // jeda antar beep
  noTone(PIN_BUZZER);
}

void beepBuy() { beep(1000, 200); }

void beepProfit() {
  beep(800, 120);
  beep(1100, 120);
  beep(1400, 200);
}

void beepLoss() {
  beep(400, 300);
  delay(100);
  beep(400, 300);
}

void beepReset() {
  beep(2000, 300);
  beep(2000, 300);
}

// ── Helper: ambil field JSON sederhana ───────────────────────────────
String getJsonField(String json, String key) {
  String k = "\"" + key + "\":";
  int idx = json.indexOf(k);
  if (idx < 0)
    return "";
  idx += k.length();
  while (idx < (int)json.length() && (json[idx] == ' ' || json[idx] == '"'))
    idx++;
  String val = "";
  while (idx < (int)json.length() && json[idx] != '"' && json[idx] != ',' &&
         json[idx] != '}' && json[idx] != ' ') {
    val += json[idx];
    idx++;
  }
  return val;
}

// ── OLED helpers ─────────────────────────────────────────────────────
void drawDisplay(const char *title, const char *line2, const char *line3,
                 const char *line4) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println(title);
  display.drawFastHLine(0, 10, OLED_WIDTH, SSD1306_WHITE);
  display.setCursor(0, 16);
  display.println(line2);
  display.setCursor(0, 26);
  display.println(line3);
  display.setCursor(0, 36);
  display.println(line4);
  display.setCursor(0, 52);
  display.print("HB:");
  display.print(heartbeatCount);
  display.display();
}

void drawHeartbeat() {
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println(">> BOT AKTIF <<");
  display.drawFastHLine(0, 10, OLED_WIDTH, SSD1306_WHITE);
  display.setCursor(0, 20);
  display.print("Heartbeat #");
  display.println(heartbeatCount);
  display.setCursor(0, 36);
  display.print("Event terakhir: ");
  display.println(lastEvent);
  display.setCursor(0, 48);
  display.println(lastSymbol);
  if (lastPnl.length() > 0) {
    display.setCursor(0, 56);
    display.print("Total PnL: ");
    display.println(lastPnl);
  }
  display.display();
}

void drawOffline() {
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println("!! BOT OFFLINE !!");
  display.drawFastHLine(0, 10, OLED_WIDTH, SSD1306_WHITE);
  display.setCursor(0, 24);
  display.println("Tidak ada heartbeat");
  display.setCursor(0, 36);
  display.println("> 3 menit");
  display.setCursor(0, 52);
  display.print("HB terakhir: ");
  display.print(heartbeatCount);
  display.display();
}