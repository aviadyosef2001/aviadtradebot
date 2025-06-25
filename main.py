import os
import time
import asyncio
from pybit.unified_trading import HTTP
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# קריאת משתנים מהסביבה
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = ["ETHUSDT", "SOLUSDT", "BTCUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT", "DOGEUSDT"]
TIMEFRAME = 15
VOLUME_MULTIPLIER = 1.5
RSI_PERIOD = 14
CHECK_INTERVAL = 60 * TIMEFRAME

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

async def send_alert(app, message: str):
    await app.bot.send_message(chat_id=CHAT_ID, text=message)

def fetch_data(symbol):
    candles = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=TIMEFRAME,
        limit=100
    )
    return candles["result"]["list"]

def get_live_price(symbol):
    tickers = session.get_tickers(category="linear", symbol=symbol)
    return float(tickers["result"]["list"][0]["lastPrice"])

def calculate_rsi(prices, period):
    gains, losses = [], []
    for i in range(1, len(prices)):
        delta = float(prices[i]) - float(prices[i - 1])
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def detect_fvg(candles):
    for i in range(2, len(candles)):
        high1 = float(candles[i - 2][2])
        low2 = float(candles[i - 1][3])
        low3 = float(candles[i][3])
        high2 = float(candles[i - 1][2])
        if low2 > high1:
            return "פער שווי הוגן שורי"
        elif high2 < low3:
            return "פער שווי הוגן דובי"
    return None

def detect_order_block(candles):
    for i in range(len(candles) - 2, 0, -1):
        open_price = float(candles[i][1])
        close_price = float(candles[i][4])
        high = float(candles[i][2])
        low = float(candles[i][3])
        body = abs(close_price - open_price)
        if body > (high - low) * 0.7:
            return f"יש Order Block חזק"
    return None

def detect_bos(candles):
    highs = [float(c[2]) for c in candles]
    for i in range(2, len(highs)):
        if highs[i - 1] < highs[i] > highs[i - 2]:
            return f"🧠 זיהיתי שבירת מבנה חזקה"
    return None

def detect_spring(candles):
    lows = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]
    for i in range(2, len(candles)):
        if lows[i] < lows[i - 1] and closes[i] > lows[i]:
            return f"🌱 זיהיתי תבנית Spring יפה"
    return None

def calculate_stop_loss(candles, direction):
    if direction == "לונג":
        recent_lows = [float(c[3]) for c in candles[-5:]]
        return min(recent_lows) * 0.997
    elif direction == "שורט":
        recent_highs = [float(c[2]) for c in candles[-5:]]
        return max(recent_highs) * 1.003
    return None

def calculate_take_profit(entry_price, stop_loss, direction):
    risk = abs(entry_price - stop_loss)
    reward = risk * 1.5
    if direction == "לונג":
        return entry_price + reward
    elif direction == "שורט":
        return entry_price - reward
    return None

async def analyze(app, symbol):
    data = fetch_data(symbol)
    if len(data) < RSI_PERIOD + 2:
        return
    closes = [float(candle[4]) for candle in data]
    volumes = [float(candle[5]) for candle in data]
    rsi = calculate_rsi(closes, RSI_PERIOD)
    avg_volume = sum(volumes[-RSI_PERIOD:]) / RSI_PERIOD
    current_price = get_live_price(symbol)

    score = 0
    reasons = []
    trend = None

    if rsi < 30:
        score += 1
        reasons.append(f"RSI נמוך: {rsi:.2f}")
        trend = "לונג"
    elif rsi > 70:
        score += 1
        reasons.append(f"RSI גבוה: {rsi:.2f}")
        trend = "שורט"

    if volumes[-1] > VOLUME_MULTIPLIER * avg_volume:
        score += 1
        reasons.append("Spike בווליום")

    fvg = detect_fvg(data)
    if fvg:
        score += 1
        reasons.append(fvg)

    ob = detect_order_block(data)
    if ob:
        score += 1
        reasons.append(ob)

    bos = detect_bos(data)
    if bos:
        score += 1
        reasons.append(bos)

    spring = detect_spring(data)
    if spring:
        score += 1
        reasons.append(spring)
        trend = "לונג"

    if score >= 3 and trend:
        stop_loss = calculate_stop_loss(data, trend)
        take_profit = calculate_take_profit(current_price, stop_loss, trend)
        message = f"📢 שים לב יאח! {'📈' if trend == 'לונג' else '📉'}\n"
        message += f"📊 יש אחלה כניסה ב-{symbol} (ציון: {score}/10) 🔥\n\n"
        for r in reasons:
            message += f"{r}\n"
        message += f"\n{ '🚀 לונג' if trend == 'לונג' else '📉 שורט' }"
        message += f"\n🎯 TP: {take_profit:.2f}\n🛑 SL: {stop_loss:.2f}\n💰 מחיר נוכחי: {current_price:.3f}"
        await send_alert(app, message)

async def run_bot(app):
    while True:
        for symbol in SYMBOLS:
            await analyze(app, symbol)
        await asyncio.sleep(CHECK_INTERVAL)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running!")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    asyncio.get_event_loop().create_task(run_bot(app))
    app.run_polling()
