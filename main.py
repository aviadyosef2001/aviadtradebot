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

SYMBOLS          = ["ETHUSDT","SOLUSDT","BTCUSDT","AVAXUSDT","LINKUSDT","NEARUSDT","DOGEUSDT"]
TIMEFRAME        = 15
RSI_PERIOD       = 14
VOLUME_MULTIPLIER = 1.5

# תזמון: ראשון–חמישי, 14:00–01:00, כל 30 דקות
ANALYSIS_DAYS    = set(range(0,5))                       # 0=ראשון … 4=חמישי
ANALYSIS_HOURS   = list(range(14,24)) + list(range(0,2)) # 14–23 ו־0–1
CHECK_INTERVAL   = 30 * 60                               # שניות

# אתחול לקוחות API
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
openai  = OpenAI(api_key=OPENAI_API_KEY)
recent_signals = {}

async def send_alert(app, message: str):
    await app.bot.send_message(chat_id=CHAT_ID, text=message)

async def ask_gpt(prompt: str) -> str:
    resp = await openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role":"system",
                "content":"אתה אנליסט שוק קריפטו מומחה בויקוף, מזהה תמיכות/התנגדויות, FVG, BOS, Springs, Order Blocks ומניפולציות."
            },
            {"role":"user","content":prompt}
        ]
    )
    return resp.choices[0].message.content

async def fetch_data(symbol: str):
    data = session.get_kline(category="linear", symbol=symbol, interval=TIMEFRAME, limit=100)
    return data.get("result", {}).get("list", [])

async def get_live_price(symbol: str) -> float:
    tk = session.get_tickers(category="linear", symbol=symbol)
    lst = tk.get("result", {}).get("list", [])
    return float(lst[0]["lastPrice"]) if lst else 0.0

async def generate_prompt(symbol: str) -> str:
    candles = await fetch_data(symbol)
    closes = [float(c[4]) for c in candles]
    volumes = [float(c[5]) for c in candles]
    price = await get_live_price(symbol)

    gains  = [max(closes[i]-closes[i-1],0) for i in range(1,len(closes))]
    losses = [max(closes[i-1]-closes[i],0) for i in range(1,len(closes))]
    avg_gain = sum(gains[-RSI_PERIOD:])/RSI_PERIOD if len(gains)>=RSI_PERIOD else 0
    avg_loss = sum(losses[-RSI_PERIOD:])/RSI_PERIOD if len(losses)>=RSI_PERIOD else 0
    rsi = 100 if avg_loss==0 else 100-(100/(1+avg_gain/avg_loss))

    prompt = f"Analyze {symbol} with Wyckoff and quality filters:\n"
    prompt += f"- Price: {price}\n- RSI({RSI_PERIOD}): {rsi:.2f}\n"
    pro


