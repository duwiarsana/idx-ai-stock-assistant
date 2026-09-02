# Lessons Learned - IDX AI Stock Assistant

**Dokumentasi ini wajib dibaca sebelum mengubah kode trading.**
**Terakhir diupdate: 2026-08-20**

---

## Ringkasan Kerugian & Perbaikan

| Masalah | Dampak | Status |
|---------|--------|--------|
| TP profit 0.00 di Telegram | User tidak tahu profit sebenarnya | FIXED |
| Market sell slippage 3.6% | Profit 4% jadi 0.05% | FIXED |
| R:R ratio selalu rendah | Tidak ada BUY signal | FIXED |
| PnL calculation bug | PnL salah dihitung | FIXED |
| IDX scanner tidak produce signal | Tidak ada alert saham | FIXED |

---

## 1. JANGAN PAKAI MARKET ORDER UNTUK TP EXIT

**Masalah:** Market sell di pair tipis (seperti POL) bisa slippage 3.6%.

**Contoh kasus:**
```
POL_USDT:
  Entry: 0.08188
  TP2 level: 0.0852 (+4.06% dari entry)
  Market sell fill: 0.08214 (bukan 0.0852!)
  Actual profit: +0.05% (bukan +4%)
  Slippage: 3.6%
```

**Penyebab:** Tokocrypto order book tipis untuk pair kecil. Harga spike ke TP level tapi market order fill di harga yang jauh lebih rendah.

**Solusi:**
```python
# JANGAN:
resp = await self.client.market_sell(symbol, qty)

# PAKAI:
limit_price = tp_level * 0.998  # 0.2% below TP
resp = await self.client.limit_sell(symbol, qty, limit_price)
```

**File:** `app/services/crypto_real.py:_close_position()`, `app/data/tokocrypto_trade_client.py:limit_sell()`

---

## 2. FILTER COIN TIPIS (MINIMUM VOLUME)

**Masalah:** Coin dengan 24h volume rendah punya order book tipis → slippage besar.

**Solusi:** Tambah minimum 24h quote volume filter.

```python
# Minimum 500K USDT 24h volume
quote_volume = float(ticker.get("quoteVolume", 0) or 0)
if quote_volume < 500_000:
    return False  # skip - too illiquid
```

**File:** `app/services/crypto_real.py:_passes_entry_gate()`

**Aturan:**
- Minimum 500K USDT 24h volume untuk real trading
- Minimum 1M USDT untuk scanner liquidity filter
- Jika pair tidak liquid, market order akan slippage

---

## 3. R:R RATIO HARUS PAKAI ATR-BASED TARGETS

**Masalah:** R:R ratio berdasarkan raw S/R sering terlalu rendah karena:
- Stock dekat resistance → upside kecil
- Stock jauh dari support → downside besar
- Hasil: R:R = 0.02 (mustahil profit)

**Contoh:**
```
AALI:
  Current price: 4500
  20-day high (resistance): 4510 (hanya 0.22% di atas)
  20-day low (support): 4400 (2.2% di bawah)
  R:R = 10/100 = 0.10 ← SANGAT RENDAH
```

**Solusi:** Pakai ATR-based targets ketika S/R R:R < 1.0

```python
# JANGAN:
upside = resistance - current_price
downside = current_price - support
rr_ratio = upside / downside

# PAKAI:
rr_sr = (resistance - current_price) / (current_price - support)
if rr_sr < 1.0:
    upside = atr * 2    # 2xATR sebagai target
    downside = atr       # 1xATR sebagai risk
else:
    upside = resistance - current_price
    downside = current_price - support
```

**File:** `app/services/analysis_engine.py:analyze()` baris ~468

---

## 4. PNL CALCULATION HARUS PROPORTIONAL

**Masalah:** PnL dihitung berdasarkan full invested amount, padahal qty yang dijual mungkin lebih kecil (fee/rounding).

**Contoh:**
```
Position: qty=61.3, invested=5.02 USDT
Sell: qty_sell=61.1 (fee mengurangi qty)
Wrong PnL: sell_value - 5.02 = -0.003 ( Salah! )
Correct PnL: sell_value - (61.1/61.3 * 5.02) = +0.013 (Benar!)
```

**Solusi:**
```python
# JANGAN:
pnl = proceeds - (pos.invested or 0)

# PAKAI:
cost_basis = (qty_sell / qty) * (pos.invested or 0) if qty else 0
pnl = proceeds - cost_basis
```

**File:** `app/services/crypto_real.py:_close_position()` baris ~326

---

## 5. TP LEVELS HARUS MINIMUM 2% DIATAS ENTRY

**Masalah:** Untuk coin dengan ATR kecil, TP1 bisa sangat dekat dengan entry, sehingga profit tidak cukup untuk cover trading fees (0.2%).

**Solusi:**
```python
# Ensure TP1 minimal 2% di atas entry untuk cover fee
min_tp1 = price * 1.02
if tp1_price < min_tp1:
    tp1_price = min_tp1
```

**File:** `app/services/crypto_levels.py:compute_price_levels()`

---

## 6. SLIPPAGE GUARD: JANGAN JUAL JIKA HARGA TURUN DARI TP

**Masalah:** Price bisa spike ke TP level lalu langsung crash. Jika bot langsung jual, fill di harga rendah.

**Solusi:** Cek apakah price masih di atas TP level saat akan jual:

```python
if tp2 is not None and price >= tp2:
    # Cek slippage
    slippage_pct = (tp2 - price) / tp2 * 100
    if slippage_pct > 1.0:
        # Price turun >1% dari TP level, skip sell
        return None
    return EXIT_TP2
```

**File:** `app/services/crypto_real.py:_decide_exit()`

---

## 7. TELEGRAM PNL FORMAT

**Masalah:** Format `:.2f` membulatkan profit kecil jadi 0.00.

```
# Sebelum:
f"PnL: {pnl:+.2f}"  # +0.0027 → "+0.00"

# Sesudah:
pnl_str = f"{pnl:+.4f}" if abs(pnl) < 1 else f"{pnl:+.2f}"
f"PnL: {pnl_str} ({pnl_pct:+.2f}%)"  # +0.0027 → "+0.0027 (+0.05%)"
```

**File:** `app/services/crypto_real.py:_notify_close()`, `app/services/crypto_paper.py:_notify_close()`

---

## 8. IDX SCANNER: THRESHOLD DAN LIQUIDITY

**Masalah:** Scanner threshold terlalu tinggi (70) dan liquidity filter terlalu ketat (1B IDR).

**Perubahan:**
| Parameter | Sebelum | Sesudah | Alasan |
|-----------|---------|---------|--------|
| Scan threshold | 70 | 55 | Lebih banyak signal |
| R:R minimum | 2.0 | 1.5 | Lebih realistis |
| Liquidity filter | 1B IDR | 500M IDR | Sertakan mid-cap |
| Alert cooldown | 24h | 4h | Lebih responsif |

**File:** `app/scheduler/jobs.py`, `app/services/analysis_engine.py`

---

## 9. JANGAN OVERWRITE DATABASE DENGAN DATA SALAH

**Masalah:** PnL salah dihitung lalu disimpan ke database, sulit dikoreksi.

**Solusi:**
1. Selalu verifikasi PnL calculation sebelum commit ke DB
2. Gunakan proportional cost basis
3. Test dengan data sebelum deploy

---

## 10. RATE LIMITING TOKOCRYPTO

**Masalah:** Tokocrypto API sangat aggressive rate limiting (429 error).

**Solusi yang sudah diterapkan:**
- Cache prices 15 detik (bot) / 60 detik (dashboard)
- Quick TP/SL check interval: 5 detik
- Semaphore untuk parallel requests
- Retry with backoff

**Yang masih perlu diperhatikan:**
- Jangan fetch price terlalu sering
- Gunakan cache yang sudah ada
- Jangan bypass rate limit dengan multiple connections

---

## Checklist Sebelum Deploy

- [ ] PnL calculation sudah pakai proportional cost basis?
- [ ] TP exit sudah pakai limit order?
- [ ] Volume filter sudah aktif (min 500K USDT)?
- [ ] R:R ratio sudah pakai ATR-based fallback?
- [ ] TP1 minimum 2% di atas entry?
- [ ] Slippage guard sudah aktif?
- [ ] Telegram notification format sudah benar?
- [ ] Tidak ada debug print yang tertinggal?
- [ ] Database migration sudah dijalankan?
- [ ] Semua test passing?

---

## 11. DUST TRAP: JANGAN SIZE POSISI PAS DI MINIMUM NOTIONAL BURSA

**Masalah (ditemukan 2026-08-23):** Posisi di-size ~5.02 USDT (persis min_notional
bursa 5 USDT). Fee taker dipotong dari koin + turun harga sedikit → nilai posisi
< 5 USDT → sell ditolak bursa (error 3210) → bot force-close sebagai `SL_DUST`.

**Dampak:** `pnl = -abs(invested)` mencatat **-100%** padahal koin masih di wallet
dan harga hanya turun 1-4% (bahkan ada yang positif!). 5 trade SL_DUST = -25 USDT,
menghapus semua profit TP1 (+1.4 USDT).

**Solusi yang diterapkan:**
1. PnL dust = nilai pasar riil (`qty_sell * price - cost_basis`), bukan `-invested`
2. Floor ukuran posisi: `CRYPTO_REAL_MIN_POSITION_QUOTE=7` (buffer ~29% di atas minimum)
3. Blacklist aset pegged: stablecoin/gold/wrapped tidak pernah ditradingkan
   (`CRYPTO_REAL_SYMBOL_BLACKLIST`) — harga flat, TP/SL tidak berarti
4. Cooldown SL sekarang mencakup `SL_DUST`, bukan hanya `SL`

**Pelajaran:** Selalu ukur posisi dengan buffer di atas batas minimum bursa.
Aset pegged lolos filter volatilitas (ATR rendah!) — harus diblacklist eksplisit.

---

## 12. KENAPA BOT SERING KENA SL: ENTRY PULLBACK vs EXIT YANG ASIMETRIS

**Gejala (data review 111 closed REAL):** 52 exit SL rata-rata hanya -1.24%, dan 5
di antaranya exit justru *di atas* entry. Artinya koin sering sempat naik lalu
di-stop sebelum sempat ke TP1 (+1.8%) — bukan sinyal BUY yang salah total, tapi
exit yang kepotong oleh noise.

**Akar masalah yang diperbaiki di sesi ini:**

| Masalah | Sebelum | Sesudah |
|---------|---------|---------|
| Paper engine pakai trailing 1.2×ATR (bug lama) padahal real sudah 2.2×ATR | paper tampak kalah lebih sering SL | paper ikut 2.2×ATR (sama dengan real) |
| Harga lewat SL 0.0x% sekali tapi langsung market-sell di titik terendah wick | SL langsung eksekusi | wick guard `SL_EXIT_TOLERANCE_PCT=0.5` — hold, exit saat benar-benar tembus |
| Gate entry minta R:R≥1.5 tapi breakout branch TP1=2.5×ATR & SL=2×ATR → R:R=1.25 (gagal) | kontradiksi, TP1 dekat-entry kepotong trailing | TP1=3.0×ATR & SL=2.0×ATR → R:R 1.5 konsisten |
| Beli pullback saat 15m masih bearish (falling knife) | langsung entry | gate `ENTRY_CONFIRM_15M=true` menunggu 15m berhenti jatuh |
| Paper SL exit membukukan `stop_loss` dasar (bukan harga yang memicu) | paper rugi -5.38% rata-rata vs real -1.31% (dihitung overstate) | paper SL membukukan harga trigger, mirror fill real |

**Pelajaran:** Mulai selalu selidiki apakah "sering SL" itu masalah *entry* atau
*exit* — kalau kerugian SL rata-rata jauh lebih kecil dari jarak SL asli, itu
adalah exit yang terlalu ketat, bukan entry yang salah. Ukur dulu, lalu ubah.

## File Penting yang Sering Diubah

| File | Fungsi | Yang Perlu Diperhatikan |
|------|--------|------------------------|
| `app/services/crypto_real.py` | Real trading engine | PnL calc, limit orders, slippage guard |
| `app/services/analysis_engine.py` | IDX stock analysis | R:R calculation, thresholds |
| `app/services/crypto_levels.py` | TP/SL levels | ATR multipliers, min TP% |
| `app/scheduler/jobs.py` | Scheduled jobs | Scanner thresholds, cooldowns |
| `app/data/tokocrypto_trade_client.py` | Exchange API | Limit orders, rate limiting |
| `app/config.py` | Configuration | Semua parameter trading |

---

## Catatan Penting

1. **JANGAN pernah market sell di pair tipis** - pakai limit order
2. **JANGAN trust R:R dari raw S/R** - pakai ATR-based
3. **JANGAN pakai full invested untuk PnL** - pakai proportional
4. **SELALU test di paper mode dulu** sebelum real
5. **SELALU cek database** sebelum claim PnL benar
6. **cek volume** sebelum entry - min 500K USDT
