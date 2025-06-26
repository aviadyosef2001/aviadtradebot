import os
import asyncio
import datetime
from pybit.unified_trading import HTTP
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from openai import OpenAI

# ======================== הגדרות ========================
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SYMBOLS = [
    "ETHUSDT", "SOLUSDT", "BTCUSDT", "AVAXUSDT",
    "LINKUSDT", "NEARUSDT", "DOGEUSDT"
]
TIMEFRAME = 15
RSI_PERIOD = 14
VOLUME_MULTIPLIER = 1.5

# הגדרת תזמון: ראשון–חמישי, 14:00–01:00, כל 30 דקות
ANALYSIS_DAYS = set(range(0, 5))  # 0=ראשון … 4=חמישי
ANALYSIS_HOURS = list(range(14, 24)) + list(range(0, 2))
CHECK_INTERVAL = 60 * 30

# אתחול לקוחות API
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
openai = OpenAI(api_key=OPENAI_API_KEY)
recent_signals = {}


async def send_alert(app, message: str):
    """שליחת התראה לטלגרם"""
    await app.bot.send_message(chat_id=CHAT_ID, text=message)


async def ask_gpt(prompt: str) -> str:
    """שולח prompt ל-GPT ומחזיר תשובה"""
    try:
        response = await openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "אתה אנליסט שוק קריפטו מומחה בויקוף, "
                        "מזהה תמיכות/התנגדויות, FVG, BOS, Springs, Order Blocks ומניפולציות."  
                    )
                },
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"שגיאה בבינה מלאכותית: {e}"


def fetch_data(symbol: str):
    """משיכת נרות מ-Bybit"""
    data = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=TIMEFRAME,
        limit=100
    )
    return data["result"]["list"]


def get_live_price(symbol: str) -> float:
    """משיכת מחיר חי M"""
    tk = session.get_tickers(category="linear", symbol=symbol)
    return float(tk["result"]["list"][0]["lastPrice"])


def generate_prompt(symbol: str) -> str:
    """בונה prompt לניתוח על ידי GPT"""
    candles = fetch_data(symbol)
    closes = [float(c[4]) for c in candles]
    volumes = [float(c[5]) for c in candles]
    price = get_live_price(symbol)
    # מחשבים RSI פשוט
    gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    avg_gain = sum(gains[-RSI_PERIOD:]) / RSI_PERIOD
    avg_loss = sum(losses[-RSI_PERIOD:]) / RSI_PERIOD
    rsi = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

    prompt = f"Analyze {symbol} using Wyckoff methodology and quality filters:\n"
    prompt += f"- Current price: {price}\n"
    prompt += f"- RSI({RSI_PERIOD}): {rsi:.2f}\n"
    prompt += f"- Last volume: {volumes[-1]} vs avg: {sum(volumes[-RSI_PERIOD:]) / RSI_PERIOD:.2f}\n"
    prompt += "- Identify key support and resistance levels\n"
    prompt += "- Detect Fair Value Gaps (FVG)\n"
    prompt += "- Spot Break of Structure (BOS) or Springs\n"
    prompt += "- Recognize Order Blocks or institutional footprints\n"
    prompt += "- Assess if this is a true move or manipulation\n"
    prompt += "Provide direction (Long/Short), entry price, stop loss, take profit, and confidence score out of 10."
    return prompt


async def analyze_market(app):
    """הרצת ניתוח על כל המטבעות לפי לוח הזמנים"""
    now = datetime.datetime.now().astimezone()
    if now.weekday() not in ANALYSIS_DAYS or now.hour not in ANALYSIS_HOURS:
        return

    for symbol in SYMBOLS:
        prompt = generate_prompt(symbol)
        ai_response = await ask_gpt(prompt)
        price = get_live_price(symbol)
        # מניעת סיגנל כפול
        last_price = recent_signals.get(symbol)
        if last_price and abs(price - last_price) < price * 0.003:
            continue
        recent_signals[symbol] = price

        message = f"🔎 {symbol} Analysis:\n{ai_response}"
        await send_alert(app, message)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מענה לשאלות ישירות"""
    question = update.message.text
    answer = await ask_gpt(question)
    await update.message.reply_text(answer)


async def run_bot(app):
    """לולאה מרכזית"""
    while True:
        await analyze_market(app)
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    asyncio.create_task(run_bot(app))
    app.run_polling()

