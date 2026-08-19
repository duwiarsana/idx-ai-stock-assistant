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

📊 `/stock BBCA` — Cek harga saham
🔍 `/analyze BBCA` — Analisis AI lengkap
🪙 `/crypto` — Scanner crypto Tokocrypto
❓ `/help` — Tampilkan bantuan

💡 **Tips:** Anda juga bisa langsung ketik kode saham (contoh: `BBCA`)
━━━━━━━━━━━━━━━━━━━━━━

⚠️ *Disclaimer: Informasi yang diberikan bukan merupakan saran investasi. Selalu lakukan riset mandiri sebelum mengambil keputusan investasi.*
"""

HELP_MESSAGE = """
📖 **Panduan IDX AI Stock Assistant**

━━━━━━━━━━━━━━━━━━━━━━
📋 **Semua Perintah:**

/start — Mulai & sambutan
/help — Bantuan ini

/stock BBCA — Cek harga saham
   (alias: /s BBCA)

/analyze BBCA — Analisis AI lengkap
   (alias: /a BBCA)

/crypto — Status scanner crypto Tokocrypto
/crypto scan — Jalankan scan crypto manual
/crypto alerts — Riwayat alert crypto
   (opsi: /crypto scan --dry untuk simulasi)

Ketik `BBCA` — Info harga otomatis
   (tanpa perintah)

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
