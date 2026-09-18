"""/start and /help command handlers."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = """
🤖 **Selamat datang di IDX AI Stock Assistant! [FIXED-V3]**

Saya adalah asisten analisis saham Indonesia (IDX) berbasis AI. Saya dapat membantu Anda memahami kondisi saham dengan data real-time dan analisis teknikal.

━━━━━━━━━━━━━━━━━━━━━━
📋 **Perintah yang tersedia:**

📊 **Crypto Bot & Portofolio (Real Tokocrypto):**
💼 `/portofolio` — Ringkasan saldo, PnL & posisi
📈 `/posisi` — Posisi crypto real yang aktif berjalan
📜 `/riwayat` — 10 transaksi real terakhir
🪙 `/crypto` — Status scanner koin & sinyal

📈 **Saham IDX:**
📊 `/stock BBCA` — Cek harga saham
🔍 `/analyze BBCA` — Analisis AI lengkap saham
🎯 `/stocks` — Saham potensial dari scanner IDX

❓ `/help` — Tampilkan panduan lengkap
━━━━━━━━━━━━━━━━━━━━━━

💡 **Tips:** Anda juga bisa langsung ketik kode saham (contoh: `BBCA`)
━━━━━━━━━━━━━━━━━━━━━━

⚠️ *Disclaimer: Informasi yang diberikan bukan merupakan saran investasi. Selalu lakukan riset mandiri sebelum mengambil keputusan investasi.*
"""

HELP_MESSAGE = """
📖 **Panduan IDX AI Stock & Crypto Assistant**

━━━━━━━━━━━━━━━━━━━━━━
📋 **Semua Perintah:**

/start — Mulai & sambutan
/help — Bantuan ini

💼 **Crypto Bot (Real Trading):**
/portofolio (atau /porto) — Total saldo, modal terpakai & PnL
/posisi — Detail koin yang sedang di-hold, floating PnL, TP, SL
/riwayat — 10 riwayat transaksi sell/buy terakhir
/crypto — Status scanner Tokocrypto
/crypto scan — Jalankan scan momentum manual
/crypto alerts — Riwayat alert sinyal masuk

📊 **Saham IDX:**
/stock BBCA — Cek harga saham (alias: /s BBCA)
/analyze BBCA — Analisis AI lengkap (alias: /a BBCA)
/stocks — Saham potensial IDX
Ketik langsung `BBCA` — Info harga otomatis

━━━━━━━━━━━━━━━━━━━━━━
📊 **Contoh Saham Populer:**
   BBCA, BBRI, TLKM, ASII, BMRI,
   UNVR, GOTO, BRIS, ACES, ICBP

━━━━━━━━━━━━━━━━━━━━━━
🤖 **Tentang AI:**
   • Menggunakan data real-time dari pasar
   • Menghitung RSI, MACD, SMA otomatis
   • Menjelaskan analisis dengan bahasa mudah
   • TIDAK memberikan saran beli/jual

━━━━━━━━━━━━━━━━━━━━━━
⚠️ *Informasi bukan saran investasi.*
"""


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"New user: {user.id} (@{user.username})")

    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode="Markdown",
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.message.reply_text(
        HELP_MESSAGE,
        parse_mode="Markdown",
    )
