# Planning Detail: Sistem AI Stock Screener BEI + Telegram Signal

> Tujuan: membuat sistem seperti “AI IDX Stock Signal”, tetapi versi sendiri, transparan, bisa diaudit, dan tidak bergantung pada klaim marketing.
>
> Catatan penting: sistem ini **bukan mesin pasti cuan**. Posisikan sebagai **decision support / stock screener**, bukan auto-profit engine.

---

## 1. Gambaran Besar Sistem

Sistem akan melakukan screening saham BEI secara otomatis, menghitung indikator teknikal, memilih kandidat terbaik, lalu mengirim sinyal ke Telegram lengkap dengan entry, target profit, stop loss, risk reward, dan alasan teknikal.

```text
Data Saham BEI
    ↓
Database OHLCV
    ↓
Technical Indicator Engine
    ↓
Rule-Based Screener
    ↓
Risk Management Engine
    ↓
AI Reasoning / LLM Narrative
    ↓
Telegram Signal Bot
    ↓
Signal Log + Performance Tracker
```

---

## 2. Prinsip Desain

### 2.1 AI Jangan Jadi Dukun Saham

AI tidak boleh langsung menentukan beli/jual tanpa data dan aturan. AI hanya dipakai untuk:

- Menjelaskan alasan sinyal.
- Membuat rangkuman yang mudah dibaca.
- Memberi scoring tambahan berdasarkan data teknikal.
- Membantu menyaring sinyal yang terlalu lemah.

Keputusan utama tetap dari:

- Data harga.
- Volume.
- Indikator teknikal.
- Risk management.
- Backtest.

### 2.2 Semua Sinyal Harus Tercatat

Agar tidak seperti “jualan sinyal sulap”, semua sinyal harus disimpan:

- Tanggal sinyal.
- Kode saham.
- Harga entry.
- Stop loss.
- Target profit.
- Status: open, hit TP, hit SL, expired.
- Hasil akhir dalam persen.

Dengan ini performa bisa diaudit sendiri.

---

## 3. Fitur Utama

### 3.1 V1: Scanner Harian

Versi awal dibuat sederhana dulu.

Fitur:

- Scan saham BEI setelah market tutup.
- Pakai data harian OHLCV.
- Kirim 3 sampai 5 kandidat saham ke Telegram.
- Simpan semua sinyal ke database.
- Evaluasi hasil sinyal setiap hari.

Waktu jalan:

```text
Senin sampai Jumat
Jam 16:30 WIB / 17:30 WITA
Setelah market tutup
```

### 3.2 V2: Intraday Scanner

Setelah V1 stabil.

Fitur tambahan:

- Scan saat market berjalan.
- Timeframe 5 menit, 15 menit, 1 jam.
- Alert breakout.
- Alert volume spike.
- Alert saham mendekati entry.

### 3.3 V3: Dashboard Web

Fitur tambahan:

- Halaman daftar sinyal.
- Statistik win rate.
- Profit factor.
- Max drawdown.
- Equity curve.
- Filter saham berdasarkan sektor.

---

## 4. Stack Teknologi

### 4.1 Backend Utama

Rekomendasi:

```text
Python 3.11+
pandas
numpy
ta / pandas-ta
SQLAlchemy
PostgreSQL atau SQLite
APScheduler / cron
python-telegram-bot
FastAPI optional
```

### 4.2 Database

Untuk awal:

```text
SQLite
```

Untuk production:

```text
PostgreSQL
```

### 4.3 AI / LLM

Pilihan:

```text
OpenAI API
Claude API
Gemini API
Local LLM optional
```

Untuk awal, AI cukup dipakai pada 3 sampai 5 kandidat terbaik, bukan semua saham. Ini menghemat biaya.

### 4.4 Deployment

Cocok untuk:

```text
VPS Hostinger
Ubuntu Server
Docker Compose
Cron Job
Telegram Bot
```

---

## 5. Sumber Data Saham

Bagian ini paling penting. Kalau data jelek, sinyal ikut bengkok seperti penggaris kena panas.

### 5.1 Data Minimal yang Dibutuhkan

Untuk setiap saham:

```text
Tanggal
Open
High
Low
Close
Volume
```

Disebut juga OHLCV.

### 5.2 Sumber Data yang Bisa Dipakai

Pilihan sumber data:

1. API market data berbayar.
2. Data dari broker/sekuritas jika ada akses.
3. Yahoo Finance melalui yfinance untuk tahap eksperimen.
4. Scraping website finansial, tetapi harus hati-hati terhadap aturan penggunaan.
5. Export manual CSV untuk uji awal.

### 5.3 Rekomendasi Untuk V1

Untuk prototype:

```text
Gunakan yfinance atau CSV historis.
```

Untuk sistem serius:

```text
Gunakan API data resmi / berbayar.
```

---

## 6. Struktur Folder Project

```text
ai-idx-stock-screener/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── scheduler.py
│   │
│   ├── data/
│   │   ├── fetcher.py
│   │   ├── cleaner.py
│   │   └── symbols.py
│   │
│   ├── indicators/
│   │   ├── trend.py
│   │   ├── momentum.py
│   │   ├── volume.py
│   │   └── volatility.py
│   │
│   ├── screener/
│   │   ├── rules.py
│   │   ├── scoring.py
│   │   └── selector.py
│   │
│   ├── risk/
│   │   ├── entry.py
│   │   ├── stop_loss.py
│   │   └── take_profit.py
│   │
│   ├── ai/
│   │   ├── prompt_builder.py
│   │   └── llm_client.py
│   │
│   ├── telegram/
│   │   ├── bot.py
│   │   └── templates.py
│   │
│   ├── database/
│   │   ├── models.py
│   │   ├── db.py
│   │   └── migrations.py
│   │
│   └── performance/
│       ├── evaluator.py
│       └── report.py
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── symbols.csv
│
├── tests/
│
├── .env
├── requirements.txt
├── docker-compose.yml
└── README.md
```

---

## 7. Database Design

### 7.1 Table: symbols

```sql
CREATE TABLE symbols (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) UNIQUE NOT NULL,
    name TEXT,
    sector TEXT,
    is_active BOOLEAN DEFAULT TRUE
);
```

Contoh ticker:

```text
BBCA.JK
BMRI.JK
ANTM.JK
TLKM.JK
```

### 7.2 Table: ohlcv_daily

```sql
CREATE TABLE ohlcv_daily (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT,
    UNIQUE(ticker, date)
);
```

### 7.3 Table: signals

```sql
CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    signal_date DATE NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    entry_price NUMERIC NOT NULL,
    stop_loss NUMERIC NOT NULL,
    take_profit_1 NUMERIC,
    take_profit_2 NUMERIC,
    risk_reward NUMERIC,
    score NUMERIC,
    reason TEXT,
    ai_summary TEXT,
    status VARCHAR(20) DEFAULT 'open',
    result_percent NUMERIC,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 7.4 Table: signal_tracking

```sql
CREATE TABLE signal_tracking (
    id SERIAL PRIMARY KEY,
    signal_id INT,
    check_date DATE,
    close_price NUMERIC,
    high_price NUMERIC,
    low_price NUMERIC,
    status VARCHAR(20),
    note TEXT
);
```

---

## 8. Indikator Teknikal

### 8.1 Trend Indicator

Gunakan:

```text
EMA20
EMA50
EMA100
EMA200
```

Contoh rule:

```text
close > EMA20
EMA20 > EMA50
EMA50 mulai naik
```

Artinya saham sedang berada dalam struktur naik.

### 8.2 Momentum Indicator

Gunakan:

```text
RSI14
MACD
Stochastic optional
```

Contoh rule:

```text
RSI antara 45 sampai 70
MACD histogram mulai naik
```

Hindari RSI terlalu tinggi karena rawan sudah telat masuk.

### 8.3 Volume Indicator

Gunakan:

```text
Volume MA20
Relative Volume
```

Contoh:

```text
volume_today > 1.5 x average_volume_20
```

Ini membantu mendeteksi minat pasar.

### 8.4 Volatility Indicator

Gunakan:

```text
ATR14
```

ATR dipakai untuk menentukan stop loss yang lebih realistis.

---

## 9. Rule Screener V1

### 9.1 Syarat Likuiditas

Agar tidak terjebak saham yang tipis:

```text
Average volume 20 hari > 1.000.000 lembar
Average transaction value > Rp1 miliar per hari
Harga saham > Rp50
```

### 9.2 Syarat Trend

```text
Close > EMA20
EMA20 > EMA50
Close tidak terlalu jauh dari EMA20
```

Contoh batas:

```text
Jarak close ke EMA20 < 8%
```

### 9.3 Syarat Momentum

```text
RSI14 > 45
RSI14 < 70
MACD histogram naik dibanding hari sebelumnya
```

### 9.4 Syarat Volume

```text
Volume hari ini > 1.5 x Volume MA20
```

### 9.5 Syarat Candle

Untuk sinyal bullish:

```text
Close > Open
Close mendekati High
Body candle tidak terlalu kecil
```

---

## 10. Scoring System

Setiap saham diberi skor 0 sampai 100.

Contoh bobot:

```text
Trend:       30 poin
Momentum:    25 poin
Volume:      25 poin
Risk Reward: 20 poin
```

### 10.1 Contoh Scoring

```text
Trend kuat:              +30
RSI sehat:               +10
MACD bullish:            +15
Volume spike:            +25
Risk reward > 1:2:       +20
```

Sinyal hanya dikirim jika:

```text
Score >= 70
```

---

## 11. Entry, Stop Loss, Take Profit

### 11.1 Entry Price

Untuk V1 gunakan:

```text
Entry = close hari ini
```

Atau lebih konservatif:

```text
Entry = area pullback dekat EMA20
```

### 11.2 Stop Loss

Pilihan stop loss:

```text
SL = low candle terakhir
SL = entry - 1.5 x ATR14
SL = support terdekat
```

Untuk awal:

```text
SL = entry - 1.5 x ATR14
```

### 11.3 Take Profit

Gunakan risk reward.

```text
Risk = Entry - Stop Loss
TP1 = Entry + 2 x Risk
TP2 = Entry + 3 x Risk
```

Minimal:

```text
Risk Reward >= 1:2
```

---

## 12. AI Prompt Design

### 12.1 Input ke AI

Jangan kirim data mentah terlalu banyak. Kirim ringkasan hasil indikator.

Contoh JSON:

```json
{
  "ticker": "ABCD.JK",
  "close": 1250,
  "ema20": 1180,
  "ema50": 1100,
  "rsi14": 58,
  "macd_histogram": 12.5,
  "volume_ratio": 2.1,
  "atr14": 45,
  "entry": 1250,
  "stop_loss": 1180,
  "tp1": 1390,
  "tp2": 1460,
  "risk_reward": 2.0,
  "score": 82
}
```

### 12.2 Prompt Untuk AI

```text
Kamu adalah asisten analis teknikal saham Indonesia.
Tugasmu bukan memberi kepastian profit, tetapi menjelaskan alasan teknikal dari sinyal yang sudah difilter sistem.

Buat ringkasan singkat dalam bahasa Indonesia.
Jangan menjanjikan profit pasti.
Jelaskan risiko utama.
Gunakan data berikut:
{data_json}

Format jawaban:
- Kesimpulan
- Alasan teknikal
- Risiko
- Catatan disiplin trading
```

### 12.3 Output AI yang Diinginkan

```text
Kesimpulan:
ABCD masuk kandidat karena trend jangka pendek masih positif dan volume naik di atas rata-rata.

Alasan teknikal:
Harga berada di atas EMA20 dan EMA50. RSI masih sehat di area 58, belum terlalu panas. Volume 2.1x rata-rata 20 hari menunjukkan ada peningkatan minat.

Risiko:
Jika harga turun menembus area stop loss, setup dianggap gagal.

Catatan:
Gunakan position sizing kecil dan disiplin pada stop loss.
```

---

## 13. Format Pesan Telegram

```text
📈 IDX AI SIGNAL

Ticker: ABCD.JK
Score: 82/100

Entry: Rp1.250
TP1: Rp1.390
TP2: Rp1.460
SL: Rp1.180
Risk Reward: 1:2.0

Alasan:
Trend EMA positif, RSI sehat, volume naik 2.1x rata-rata.

Risiko:
Setup batal jika harga menembus SL.

Disclaimer:
Bukan ajakan beli. Gunakan analisa dan manajemen risiko sendiri.
```

---

## 14. Workflow Harian

### 14.1 Setelah Market Tutup

```text
1. Ambil data OHLCV terbaru.
2. Update database.
3. Hitung indikator semua saham.
4. Jalankan rule screener.
5. Hitung skor.
6. Ambil top 3 sampai 5 saham.
7. Hitung entry, SL, TP.
8. Minta AI membuat narasi.
9. Simpan sinyal ke database.
10. Kirim sinyal ke Telegram.
```

### 14.2 Pagi Sebelum Market Buka

Opsional:

```text
1. Kirim reminder sinyal kemarin.
2. Beri catatan: pantau area entry.
3. Jangan kirim sinyal baru jika data belum update.
```

### 14.3 Evaluasi Harian

```text
1. Cek sinyal open.
2. Apakah harga menyentuh TP1?
3. Apakah harga menyentuh TP2?
4. Apakah harga menyentuh SL?
5. Update status.
6. Kirim performance report mingguan.
```

---

## 15. Performance Tracking

### 15.1 Metrik Penting

Jangan hanya pakai win rate.

Metrik yang perlu dihitung:

```text
Win rate
Average win
Average loss
Profit factor
Max drawdown
Expectancy
Jumlah sinyal
Rata-rata holding period
```

### 15.2 Rumus Dasar

```text
Win Rate = jumlah menang / total sinyal

Profit Factor = total profit dari sinyal menang / total loss dari sinyal kalah

Expectancy = (win_rate x average_win) - (loss_rate x average_loss)
```

Contoh:

```text
Win rate 80% belum tentu bagus jika:
Menang rata-rata +1%
Kalah rata-rata -8%
```

Lebih sehat:

```text
Win rate 45%-60%
Risk reward bagus
Profit factor > 1.5
Drawdown terkendali
```

---

## 16. Backtest

### 16.1 Tujuan Backtest

Backtest dipakai untuk mengecek apakah rule screener punya kemungkinan edge.

### 16.2 Hal yang Harus Dihindari

```text
Look-ahead bias
Survivorship bias
Memilih hanya saham yang sudah naik
Menghapus sinyal rugi
Overfitting indikator
```

### 16.3 Backtest Sederhana

Untuk setiap hari historis:

```text
1. Gunakan data sampai hari itu saja.
2. Hitung indikator.
3. Jika rule lolos, buat sinyal.
4. Simulasikan entry besok.
5. Cek apakah TP/SL kena dalam maksimal 10 hari.
6. Catat hasil.
```

### 16.4 Parameter Awal Backtest

```text
Holding period maksimal: 10 hari trading
Risk reward minimal: 1:2
SL: 1.5 x ATR14
TP1: 2 x risk
TP2: 3 x risk
Minimum score: 70
```

---

## 17. Roadmap Pengerjaan

### Phase 1: Prototype Lokal

Target waktu: 3 sampai 5 hari.

Checklist:

- [ ] Buat struktur project.
- [ ] Ambil list saham BEI.
- [ ] Ambil data OHLCV harian.
- [ ] Simpan ke SQLite.
- [ ] Hitung EMA, RSI, MACD, ATR, volume ratio.
- [ ] Jalankan rule screener.
- [ ] Tampilkan top 5 di terminal.

Output:

```text
Sistem bisa scan saham dan menampilkan kandidat.
```

### Phase 2: Telegram Bot

Target waktu: 1 sampai 2 hari.

Checklist:

- [ ] Buat bot Telegram via BotFather.
- [ ] Simpan BOT_TOKEN di .env.
- [ ] Ambil CHAT_ID.
- [ ] Buat template pesan.
- [ ] Kirim sinyal otomatis.

Output:

```text
Sinyal masuk ke Telegram.
```

### Phase 3: AI Narrative

Target waktu: 1 sampai 2 hari.

Checklist:

- [ ] Buat prompt builder.
- [ ] Integrasi OpenAI/Claude/Gemini API.
- [ ] Kirim hanya top 5 kandidat ke AI.
- [ ] Simpan ringkasan AI ke database.
- [ ] Kirim ringkasan AI ke Telegram.

Output:

```text
Sinyal punya penjelasan yang rapi.
```

### Phase 4: Signal Tracking

Target waktu: 3 sampai 5 hari.

Checklist:

- [ ] Buat table signals.
- [ ] Simpan semua sinyal.
- [ ] Buat evaluator harian.
- [ ] Update status TP/SL.
- [ ] Buat report mingguan.

Output:

```text
Performa sinyal bisa diaudit.
```

### Phase 5: Backtest

Target waktu: 1 sampai 2 minggu.

Checklist:

- [ ] Buat engine backtest.
- [ ] Test rule di data historis.
- [ ] Hitung win rate, profit factor, drawdown.
- [ ] Cari parameter yang stabil, bukan yang cuma terlihat bagus.

Output:

```text
Rule yang dipakai punya bukti historis.
```

### Phase 6: Deploy VPS

Target waktu: 1 sampai 2 hari.

Checklist:

- [ ] Setup VPS Ubuntu.
- [ ] Install Docker.
- [ ] Setup PostgreSQL.
- [ ] Setup cron job.
- [ ] Setup logging.
- [ ] Backup database.

Output:

```text
Sistem jalan otomatis setiap hari.
```

### Phase 7: Dashboard Web

Target waktu: 1 sampai 3 minggu.

Checklist:

- [ ] Buat API dengan FastAPI.
- [ ] Buat frontend Next.js.
- [ ] Halaman daftar sinyal.
- [ ] Halaman performa.
- [ ] Chart equity curve.
- [ ] Login admin.

Output:

```text
Sistem terlihat seperti platform profesional.
```

---

## 18. Contoh Pseudocode Scanner

```python
for ticker in symbols:
    df = load_ohlcv(ticker)
    df = calculate_indicators(df)

    latest = df.iloc[-1]

    if latest.close <= latest.ema20:
        continue

    if latest.ema20 <= latest.ema50:
        continue

    if latest.rsi14 < 45 or latest.rsi14 > 70:
        continue

    if latest.volume_ratio < 1.5:
        continue

    entry = latest.close
    stop_loss = entry - (1.5 * latest.atr14)
    risk = entry - stop_loss
    tp1 = entry + (2 * risk)
    tp2 = entry + (3 * risk)

    score = calculate_score(latest, entry, stop_loss, tp1)

    if score >= 70:
        save_candidate(ticker, entry, stop_loss, tp1, tp2, score)
```

---

## 19. Contoh .env

```env
APP_ENV=development
DATABASE_URL=sqlite:///data/app.db

TELEGRAM_BOT_TOKEN=isi_token_bot
TELEGRAM_CHAT_ID=isi_chat_id

LLM_PROVIDER=openai
OPENAI_API_KEY=isi_api_key

TIMEZONE=Asia/Makassar
RUN_TIME=17:30
```

---

## 20. Contoh requirements.txt

```text
pandas
numpy
SQLAlchemy
python-dotenv
requests
yfinance
ta
python-telegram-bot
APScheduler
openai
fastapi
uvicorn
psycopg2-binary
```

---

## 21. Contoh docker-compose.yml

```yaml
services:
  app:
    build: .
    container_name: ai_idx_screener
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    depends_on:
      - postgres
    restart: unless-stopped

  postgres:
    image: postgres:16
    container_name: ai_idx_postgres
    environment:
      POSTGRES_USER: screener
      POSTGRES_PASSWORD: screener_password
      POSTGRES_DB: screener_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

volumes:
  postgres_data:
```

---

## 22. Risiko dan Batasan

### 22.1 Risiko Teknis

- Data telat update.
- Data tidak lengkap.
- API berubah.
- Saham suspend.
- Corporate action tidak ter-adjust.
- Sinyal terlalu banyak saat market euforia.

### 22.2 Risiko Trading

- False breakout.
- Gap down.
- Saham tidak likuid.
- Market merah ekstrem.
- Bandar / gorengan.
- SL tidak bisa dieksekusi sesuai harga.

### 22.3 Risiko Legal dan Etika

Kalau sistem hanya dipakai pribadi:

```text
Risiko lebih kecil.
```

Kalau mau dijual sebagai layanan:

```text
Harus hati-hati.
Jangan klaim pasti profit.
Jangan tampilkan win rate tanpa data lengkap.
Jangan memberi kesan sebagai nasihat investasi resmi jika tidak berizin.
Tambahkan disclaimer jelas.
```

---

## 23. Disclaimer yang Disarankan

```text
Disclaimer:
Sinyal ini adalah hasil screening otomatis berbasis data historis dan indikator teknikal.
Bukan ajakan membeli atau menjual saham.
Keputusan investasi sepenuhnya menjadi tanggung jawab pengguna.
Selalu gunakan manajemen risiko dan dana dingin.
```

---

## 24. Strategi Validasi

Sebelum dipakai serius:

```text
1. Jalankan paper trading minimal 1 sampai 3 bulan.
2. Jangan pakai uang asli dulu.
3. Bandingkan sinyal dengan hasil aktual.
4. Catat semua sinyal, termasuk yang gagal.
5. Evaluasi mingguan.
6. Ubah rule hanya setelah punya data cukup.
```

---

## 25. Minimum Viable Product

MVP paling sederhana:

```text
Python script
Data harian dari yfinance / CSV
Indikator EMA, RSI, MACD, ATR, Volume Ratio
Filter rule-based
Top 5 saham
Telegram bot
SQLite log
```

Target MVP:

```text
Dalam 1 minggu sudah bisa jalan otomatis.
```

---

## 26. Prompt Untuk AI Code Editor

Gunakan prompt ini di AI code editor:

```text
Saya ingin membuat sistem AI IDX Stock Screener berbasis Python.

Buatkan project dengan struktur modular:
- data fetcher untuk mengambil data OHLCV saham BEI
- database SQLite untuk menyimpan symbols, ohlcv_daily, dan signals
- indicator engine untuk EMA20, EMA50, RSI14, MACD, ATR14, volume ratio
- screener rule-based untuk memilih saham kandidat
- scoring system 0-100
- risk engine untuk menghitung entry, stop loss, TP1, TP2, risk reward
- Telegram bot untuk mengirim hasil sinyal
- optional LLM module untuk membuat narasi sinyal

Untuk versi awal:
- gunakan yfinance sebagai sumber data
- gunakan SQLite
- gunakan file .env untuk konfigurasi
- buat main.py yang bisa menjalankan scan manual
- buat kode yang rapi, mudah dikembangkan, dan ada logging
- jangan buat auto trading
- tambahkan disclaimer pada pesan Telegram

Output yang saya inginkan:
1. Struktur folder lengkap.
2. Semua file Python utama.
3. requirements.txt.
4. README.md berisi cara install dan menjalankan.
```

---

## 27. Kesimpulan

Sistem seperti Zeta AI bisa dibuat sendiri dengan pendekatan yang lebih jujur dan transparan.

Kunci utamanya bukan pada kata “AI”, tetapi pada:

```text
Data yang bersih
Rule yang jelas
Risk management
Backtest
Tracking performa
Disiplin eksekusi
```

AI hanya menjadi lapisan penjelas dan perapih analisa, bukan mesin ramalan.
