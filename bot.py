import os
import time
import sys
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

# ==============================
# ENV VARIABLES
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if BOT_TOKEN:
    BOT_TOKEN = BOT_TOKEN.strip()
if CHAT_ID:
    CHAT_ID = CHAT_ID.strip()

if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("Missing BOT_TOKEN or CHAT_ID")

# ==============================
# TELEGRAM FUNCTION
# ==============================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print("Telegram Error:", e)
        return False

# ==============================
# TIME + SESSION + NEWS FILTERS
# ==============================
def is_trading_time():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    t = now.hour + now.minute / 60
    return (13 <= t <= 16.5) or (18.5 <= t <= 22)

def is_news_time():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return now.hour in [12, 13, 17, 18, 19, 21]

def is_strong_session():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    hour = now.hour
    return (13 <= hour <= 17) or (18 <= hour <= 22)

# ==============================
# CONFIDENCE CALCULATION
# ==============================
def calculate_confidence(trend_strength, rsi, breakout, atr_val, price, ema50):
    score = 0

    if trend_strength > 0.001:
        score += 25
    elif trend_strength > 0.0005:
        score += 15

    if 55 <= rsi <= 65 or 35 <= rsi <= 45:
        score += 20
    elif 50 <= rsi <= 70 or 30 <= rsi <= 50:
        score += 10

    if breakout:
        score += 25

    if atr_val > 0.001:
        score += 15
    elif atr_val > 0.0005:
        score += 10

    if price > ema50 or price < ema50:
        score += 15

    return min(score, 95)

# ==============================
# LOT SIZE
# ==============================
def calculate_lot_size(balance, risk_percent, entry, sl):
    risk_amount = balance * (risk_percent / 100)
    pip_risk = abs(entry - sl)

    if pip_risk == 0:
        return 0

    lot = risk_amount / (pip_risk * 100000)
    return round(lot, 2)

# ==============================
# PAIRS
# ==============================
pairs = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY"
}

# ==============================
# TRADE TRACKING
# ==============================
active_trades = []
trade_history = []

# ==============================
# ANALYSIS
# ==============================
def analyze_pair(symbol, name):
    try:
        df15 = yf.download(symbol, interval="15m", period="2d", progress=False)
        df1h = yf.download(symbol, interval="1h", period="5d", progress=False)

        if len(df15) < 100 or len(df1h) < 100:
            return None

        # TREND
        df1h['ema50'] = EMAIndicator(df1h['Close'], 50).ema_indicator()
        df1h['ema200'] = EMAIndicator(df1h['Close'], 200).ema_indicator()

        ema50_1h = df1h['ema50'].iloc[-1]
        ema200_1h = df1h['ema200'].iloc[-1]

        trend_up = ema50_1h > ema200_1h
        trend_down = ema50_1h < ema200_1h

        trend_strength = abs(ema50_1h - ema200_1h)
        if trend_strength < 0.0003:
            return None

        # ENTRY
        df15['ema50'] = EMAIndicator(df15['Close'], 50).ema_indicator()
        df15['rsi'] = RSIIndicator(df15['Close'], 14).rsi()

        atr = AverageTrueRange(df15['High'], df15['Low'], df15['Close'], 14)
        df15['atr'] = atr.average_true_range()

        last = df15.iloc[-1]
        prev = df15.iloc[-2]

        price = last['Close']
        ema50 = last['ema50']
        rsi = last['rsi']
        atr_val = last['atr']

        prev_high = prev['High']
        prev_low = prev['Low']

        if atr_val < 0.0003:
            return None

        breakout_buy = price > prev_high
        breakout_sell = price < prev_low

        lot = calculate_lot_size(10000, 1, price, price - atr_val)

        # ======================
        # 🔥 A+ TRADE
        # ======================
        if trend_up and price > ema50 and breakout_buy and 55 <= rsi <= 65:
            sl = price - (atr_val * 1.5)
            tp = price + (atr_val * 3)

            confidence = calculate_confidence(trend_strength, rsi, True, atr_val, price, ema50)

            active_trades.append({"pair": name, "type": "BUY", "entry": price, "sl": sl, "tp": tp, "status": "OPEN"})

            return f"""
🔥 A+ TRADE BUY {name}

Price: {round(price,5)}
RSI: {round(rsi,2)}
ATR: {round(atr_val,5)}

SL: {round(sl,5)}
TP: {round(tp,5)}

📊 Confidence: {confidence}%
💰 Lot Size: {lot} (1% risk)
⏱ Entry Valid: 15–30 mins
"""

        if trend_down and price < ema50 and breakout_sell and 35 <= rsi <= 45:
            sl = price + (atr_val * 1.5)
            tp = price - (atr_val * 3)

            confidence = calculate_confidence(trend_strength, rsi, True, atr_val, price, ema50)

            active_trades.append({"pair": name, "type": "SELL", "entry": price, "sl": sl, "tp": tp, "status": "OPEN"})

            return f"""
🔥 A+ TRADE SELL {name}

Price: {round(price,5)}
RSI: {round(rsi,2)}
ATR: {round(atr_val,5)}

SL: {round(sl,5)}
TP: {round(tp,5)}

📊 Confidence: {confidence}%
💰 Lot Size: {lot} (1% risk)
⏱ Entry Valid: 15–30 mins
"""

        # ======================
        # ⚡ A TRADE
        # ======================
        if trend_up and price > ema50 and rsi >= 50:
            sl = price - (atr_val * 1.3)
            tp = price + (atr_val * 2.5)

            confidence = calculate_confidence(trend_strength, rsi, False, atr_val, price, ema50)

            active_trades.append({"pair": name, "type": "BUY", "entry": price, "sl": sl, "tp": tp, "status": "OPEN"})

            return f"""
⚡ A TRADE BUY {name}

Price: {round(price,5)}
RSI: {round(rsi,2)}
ATR: {round(atr_val,5)}

SL: {round(sl,5)}
TP: {round(tp,5)}

📊 Confidence: {confidence}%
💰 Lot Size: {lot} (1% risk)
⏱ Entry Valid: 15–45 mins
"""

        if trend_down and price < ema50 and rsi <= 50:
            sl = price + (atr_val * 1.3)
            tp = price - (atr_val * 2.5)

            confidence = calculate_confidence(trend_strength, rsi, False, atr_val, price, ema50)

            active_trades.append({"pair": name, "type": "SELL", "entry": price, "sl": sl, "tp": tp, "status": "OPEN"})

            return f"""
⚡ A TRADE SELL {name}

Price: {round(price,5)}
RSI: {round(rsi,2)}
ATR: {round(atr_val,5)}

SL: {round(sl,5)}
TP: {round(tp,5)}

📊 Confidence: {confidence}%
💰 Lot Size: {lot} (1% risk)
⏱ Entry Valid: 15–45 mins
"""

        return None

    except Exception as e:
        print("Error:", e)
        return None

# ==============================
# TRADE RESULT CHECK
# ==============================
def check_trade_results():
    global active_trades, trade_history

    for trade in active_trades[:]:
        symbol = [k for k, v in pairs.items() if v == trade["pair"]][0]

        df = yf.download(symbol, interval="5m", period="1d", progress=False)
        if df.empty:
            continue

        price = df['Close'].iloc[-1]

        if trade["type"] == "BUY":
            if price >= trade["tp"]:
                trade["status"] = "WIN"
            elif price <= trade["sl"]:
                trade["status"] = "LOSS"

        if trade["type"] == "SELL":
            if price <= trade["tp"]:
                trade["status"] = "WIN"
            elif price >= trade["sl"]:
                trade["status"] = "LOSS"

        if trade["status"] in ["WIN", "LOSS"]:
            trade_history.append(trade)
            active_trades.remove(trade)

# ==============================
# PERFORMANCE REPORT
# ==============================
def get_performance():
    wins = sum(1 for t in trade_history if t["status"] == "WIN")
    losses = sum(1 for t in trade_history if t["status"] == "LOSS")

    total = wins + losses
    if total == 0:
        return "No trades yet"

    winrate = (wins / total) * 100

    return f"""
📊 Performance

Trades: {total}
Wins: {wins}
Losses: {losses}
Winrate: {round(winrate,2)}%
"""

# ==============================
# MAIN LOOP
# ==============================
last_alert = {}
cooldown = 900

print("🚀 BOT STARTED")

if len(sys.argv) > 1 and sys.argv[1] == "test":
    send_telegram("Bot working ✅")
    sys.exit()

while True:
    try:
        check_trade_results()

        if is_trading_time() and not is_news_time() and is_strong_session():

            for symbol, name in pairs.items():
                signal = analyze_pair(symbol, name)

                if signal:
                    now = time.time()

                    if symbol not in last_alert or now - last_alert[symbol] > cooldown:
                        send_telegram(signal)
                        print("Sent:", name)
                        last_alert[symbol] = now

        else:
            print("⏸ Skipping (time/news/session filter)")

        time.sleep(120)

    except Exception as e:
        print("Main error:", e)
        time.sleep(120)