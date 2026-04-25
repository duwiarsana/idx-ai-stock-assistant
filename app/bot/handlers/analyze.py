"""/analyze command handler — full AI stock analysis with score card."""

import logging
import os
from telegram import Update
from telegram.ext import ContextTypes

from app.services.ai_service import ai_service
from app.services.chart_service import chart_service

logger = logging.getLogger(__name__)

MAX_TELEGRAM_MSG_LENGTH = 4096


async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /analyze <TICKER> [question] command.
    Provides full AI-powered stock analysis with deterministic score card.
    """
    if not context.args:
        await update.message.reply_text(
            "❓ Cara penggunaan: `/analyze BBCA`\n\n"
            "Anda juga bisa menambahkan pertanyaan:\n"
            "`/analyze BBCA Bagaimana tren jangka panjang?`\n\n"
            "Contoh saham: BBCA, BBRI, TLKM, ASII",
            parse_mode="Markdown",
        )
        return

    ticker = context.args[0].upper().strip()
    # Optional: user can add a specific question after the ticker
    user_question = " ".join(context.args[1:]) if len(context.args) > 1 else None

    logger.info(
        f"Analysis request: {ticker} by user {update.effective_user.id}"
        f"{f' question: {user_question}' if user_question else ''}"
    )

    # Send "typing" indicator — analysis takes time
    await update.message.chat.send_action("typing")

    # Notify user that analysis is in progress
    status_msg = await update.message.reply_text(
        f"🔍 Menganalisis **{ticker}**...\n"
        f"_Mengambil data pasar, menghitung skor, dan menjalankan analisis AI..._",
        parse_mode="Markdown",
    )

    try:
        result = await ai_service.analyze_stock(ticker, user_question=user_question)
        analysis_text = result.get("analysis", "Tidak ada analisis tersedia.")
        history = result.get("history", [])
        score_card = result.get("score_card", "")

        # 1. Generate Chart
        chart_path = await chart_service.generate_candlestick_chart(ticker, history)

        # Delete the "analyzing..." status message
        try:
            await status_msg.delete()
        except Exception:
            pass

        # 2. Send Chart if generated
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"📈 Grafik Candlestick **{ticker}** (90 Hari Terakhir)",
                    parse_mode="Markdown"
                )
            # Cleanup
            try:
                os.remove(chart_path)
            except:
                pass

        # 3. Send Score Card (deterministic results)
        if score_card:
            try:
                await update.message.reply_text(
                    f"```\n{score_card}\n```",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning(f"Score card markdown failed, sending as plain text: {e}")
                await update.message.reply_text(f"SCORE CARD {ticker}:\n{score_card}")

        # 4. Send the analysis (handle Telegram's 4096 char limit)
        chunks = _split_message(analysis_text, MAX_TELEGRAM_MSG_LENGTH)
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            try:
                await update.message.reply_text(
                    chunk,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning(f"Analysis chunk {i} markdown failed, sending as plain text: {e}")
                # Fallback to plain text if Telegram rejects the markdown
                await update.message.reply_text(chunk, parse_mode=None)

    except Exception as e:
        logger.error(f"Analyze handler error for {ticker}: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(
            f"❌ Terjadi kesalahan saat menganalisis {ticker}.\n"
            f"Silakan coba lagi dalam beberapa saat.\n\n"
            f"Error: {str(e)[:200]}",
        )


def _split_message(text: str, max_length: int) -> list[str]:
    """Split a long message into chunks at paragraph boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""

    for paragraph in text.split("\n\n"):
        if len(current_chunk) + len(paragraph) + 2 <= max_length:
            current_chunk += paragraph + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = paragraph + "\n\n"

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks
