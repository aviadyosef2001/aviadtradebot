async def analyze_market(app):
    now = datetime.datetime.now().astimezone()
    if now.weekday() not in ANALYSIS_DAYS or now.hour not in ANALYSIS_HOURS:
        return

    for symbol in SYMBOLS:
        price = get_live_price(symbol)
        candles = fetch_data(symbol)
        # בונים prompt הכולל את המחיר האמיתי
        prompt = (
            f"אנליזה של {symbol} לפי Wyckoff ופילטרים איכותיים.\n"
            f"- מחיר נוכחי אמיתי: {price}\n"
            f"- RSI({RSI_PERIOD}): {compute_rsi(candles):.2f}\n"
            f"- ווליום אחרון vs ממוצע ...\n"
            "זיהוי תמיכות/התנגדויות, FVG, BOS/Spring, Order Blocks ומניפולציות.\n"
            "אנא ספק בתגובה בלבד: כיוון (לונג/שורט), מחיר כניסה (קרוב למחיר הנוכחי), SL, TP וציון איכות (1–10)."
        )
        ai_response = ask_gpt(prompt)

        # פרסינג כמו קודם
        m_dir = re.search(r'כיוון[: ]+(\w+)', ai_response)
        m_ent = re.search(r'כניסה[: ]+([0-9\\.]+)', ai_response)
        m_sl  = re.search(r'SL[: ]+([0-9\\.]+)', ai_response)
        m_tp  = re.search(r'TP[: ]+([0-9\\.]+)', ai_response)
        if all([m_dir, m_ent, m_sl, m_tp]):
            direction = m_dir.group(1)
            entry     = float(m_ent.group(1))
            sl_price  = float(m_sl.group(1))
            tp_price  = float(m_tp.group(1))

            # שליחה רק אם יש סיגנל חדש או שינוי מהותי
            prev = active_trades.get(symbol)
            if not prev or prev['direction'] != direction or abs(prev['entry']-entry)>price*0.005:
                active_trades[symbol] = {
                    'direction': direction,
                    'entry': entry,
                    'sl': sl_price,
                    'tp': tp_price
                }
                await send_alert(app, f"📢 {symbol}: {ai_response}")
