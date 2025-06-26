import os
import asyncio
import datetime
from pybit.unified_trading import HTTP
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from openai import OpenAI

# ======================== הגדרות ========================
BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID          = os.getenv("CHAT_ID")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")

SYMBOLS       = ["ETHUSDT","SOLUSDT","BTCUSDT","AVAXUSDT","LINKUSDT","NEARUSDT","DOGEUSDT"]
TIMEFRAME     = 15
RSI_PERIOD    = 14
VOLUME_MULTIPLIER = 1.5

# שעות הרצה: ראשון עד חמישי, 14:00–01:00
ANALYSIS_DAYS  = set(range(0,5))
ANALYSIS_HOURS = list(range(14,24)) + list(range(0,2))
CHECK_INTERVAL = 60 * 30

# אתחול לקוחות
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
openai  = OpenAI(api_key=OPENAI_API_KEY)
recent_signals = {}

# שליחת התראות
async def send_alert(app, message: str):
    await app.bot.send_message(chat_id=CHAT_ID, text=message)

# שאילת GPT
async def ask_gpt(prompt: str) -> str:
    resp = await openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role":"system","content":"אתה אנליסט שוק קריפטו מומחה בויקוף, מחפש תמיכה, התנגדות, FVG, שבירות מבנה, order blocks ומניפולציות."},
            {"role":"user","content":prompt}
        ]
    )
    return resp.choices[0].message.content

# נתוני שוק
def fetch_data(symbol):
    return session.get_kline(category="linear",symbol=symbol,interval=TIMEFRAME,limit=100)["result"]["list"]

def get_live_price(symbol):
    tk = session.get_tickers(category="linear",symbol=symbol)
    return float(tk["result"]["list"][0]["lastPrice"])

# בניית prompt עם פרמטרים איכותיים
async def analyze_symbol(symbol):
    candles = fetch_data(symbol)
    closes = [float(c[4]) for c in candles]
    volumes = [float(c[5]) for c in candles]
    price = get_live_price(symbol)
    rsi = round(sum(max(closes[i]-closes[i-1],0) for i in range(1,len(closes)))[-RSI_PERIOD:]/RSI_PERIOD,2)
    # מחשיבים תמיכה/התנגדות, FVG, BOS, order blocks בקצרה
    prompt = f"Analyze {symbol} using Wyckoff methodology:\n"
    prompt += f"- Current price: {price}\n"
    prompt += f"- RSI({RSI_PERIOD}): {rsi}\n"
    prompt += f"- Latest volume spike: {volumes[-1]} vs avg\n"
    prompt += "- Identify key support and resistance levels\n"
    prompt += "- Detect any Fair Value Gaps (FVG)\n"
    prompt += "- Spot any Break of Structure (BOS) or Springs\n"
    prompt += "- Recognize Order Blocks or institutional footprints\n"
    prompt += "- Assess if this is a true move or manipulation\n"
    prompt += "Provide direction (Long/Short), entry, stop loss, take profit, and confidence score out of 10."
    return await ask_gpt(prompt)

# הרצת ניתוח שוק מחזורית
async def analyze_market(app):
    now = datetime.datetime.now().astimezone()
    if now.weekday() not in ANALYSIS_DAYS or now.hour not in ANALYSIS_HOURS:
        return
    for symbol in SYMBOLS:
        content = await analyze_symbol(symbol)
        # מניעת סיגנל כפול
        price = get_live_price(symbol)
        last = recent_signals.get(symbol)
        if last and abs(price - last) < price*0.003:
            continue
        recent_signals[symbol] = price
        message = f"🔎 {symbol} Analysis:\n{content}"
        await send_alert(app,message)

# טיפול בשאלות חיות
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.message.text
    ans = await ask_gpt(q)
    await update.message.reply_text(ans)

# לולאה מרכזית
async def run_bot(app):
    while True:
        await analyze_market(app)
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    asyncio.create_task(run_bot(app))
    app.run_polling()
 app.run_polling()
