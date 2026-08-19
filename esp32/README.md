# ESP32-C3 — MQTT Sound + Display Alert

Firmware untuk ESP32-C3 yang mendengarkan event paper trading dari bot (via MQTT)
lalu membunyikan buzzer dan menampilkan info di layar OLED SSD1306.

## Setup WiFi tanpa kabel (WiFiManager)

Tidak perlu mengubah kode / upload ulang untuk ganti WiFi atau MQTT.

1. Nyalakan ESP32 — jika belum ada config (atau WiFi tidak ketemu), muncul
   Access Point bernama **`IDX-AI-Setup`**.
2. Hubungkan HP/laptop ke AP `IDX-AI-Setup`, buka browser
   `http://192.168.4.1`.
3. Isi form: **WiFi SSID + Password**, lalu **MQTT Host, Port, User, Password,
   Topic**. Klik Save → ESP32 restart dan konek sendiri.
4. Config tersimpan di flash (EEPROM/LittleFS) — tetap ada setelah mati listrik.

**Reset penuh** (hapus config, buka portal lagi):
1. Matikan ESP32.
2. Tahan tombol **BOOT** (GPIO9), nyalakan, tahan 5 detik
   → buzzer berbunyi 2x → config terhapus.

> Konfigurasi default jika field MQTT dikosongkan:
> Host `76.13.19.250`, Topic `crypto/trade/#`.

## Topik MQTT yang didengarkan

| Topic | Arti | Bunyi | OLED |
|-------|------|-------|------|
| `crypto/trade/buy` | Posisi dibuka | 1 beep pendek (200ms, 1000Hz) | 🟢 BUY + symbol + harga |
| `crypto/trade/profit` | TP1/TP2 tercapai | 3 beep naik (800→1400Hz) | ✅ PROFIT + pnl |
| `crypto/trade/loss` | SL tercapai (cut loss) | 2 beep panjang (400Hz) | 🔻 LOSS + pnl |
| `crypto/trade/heartbeat` | Bot hidup (60s) | tanpa suara | ⏱ heartbeat count |

Heartbeat dipakai juga sebagai **watchdog**: jika tidak ada heartbeat selama
`WATCHDOG_MS` (default 3 menit), layar menampilkan "⚠️ BOT OFFLINE".

## Wiring (ESP32-C3 Super Mini)

| Komponen | GPIO |
|----------|------|
| OLED SDA | GPIO4 |
| OLED SCL | GPIO5 |
| Buzzer (pasif) (+) | GPIO3 |
| Buzzer (−) | GND |
| OLED VCC | 3V3 |
| OLED GND | GND |

> Ganti pin di `#define` jika papan kamu memakai wiring lain.

## Cara upload

1. Buka Arduino IDE → **File → Preferences** → tambah board manager URL:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
2. **Tools → Board → Boards Manager** → cari "esp32" → install **esp32 by Espressif Systems**.
3. Pilih board **ESP32C3 Dev Module**.
4. Install library via **Library Manager**:
   - `PubSubClient` (Nick O'Leary)
   - `Adafruit SSD1306`
   - `Adafruit GFX`
   - `WiFiManager` (tzapu)
5. **Tidak perlu mengisi kredensial di kode** — semua di-set lewat portal
   WiFiManager. Kode hanya berisi default MQTT host/topic.
6. Upload.

## Kredensial MQTT (VPS)

Diisi lewat portal WiFiManager. Nilai referensi:

```
Host : 76.13.19.250
Port : 1883
User : idxbot
Pass : lihat file .env di VPS (MQTT_PASSWORD)
```

> Jangan commit kredensial asli ke git. Simpan lewat portal WiFiManager saja.

## Struktur file

```
esp32/
├── README.md              ← file ini
└── idx_ai_mqtt_alert/
    └── idx_ai_mqtt_alert.ino   ← sketsa Arduino
```

## Catatan

- ESP32-C3 mendukung WiFi 2.4GHz saja (bukan 5GHz).
- Broker Mosquitto di VPS memakai port 1883 (non-TLS). Jika ESP32 diakses dari
  jaringan publik, sebaiknya batasi akses ke port 1883 di firewall atau aktifkan
  TLS di Mosquitto.
- Buzzer pasif memakai `tone()` — aktifkan **Arduino Core ESP32 versi terbaru**
  yang sudah mendukung `tone()` pada pin random.