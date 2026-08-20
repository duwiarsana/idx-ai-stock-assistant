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
