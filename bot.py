import os
import time
import sys
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands

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
        resp = requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
        # surface Telegram API errors for easier debugging
        if resp.status_code != 200:
            print("Telegram API error:", resp.status_code, resp.text)
            return False
        return True
    except Exception as e:
        print("Telegram Error:", e)
        return False

# ==============================
# TIME FILTER (IST)
# ==============================
def is_trading_time():
    # use IST explicitly
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    current_time = now.hour + now.minute / 60

    # London + US sessions (IST)
    return (13 <= current_time <= 16.5) or (18.5 <= current_time <= 22)

# ==============================
# PAIRS
# ==============================
pairs = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY"
}

# ==============================
# ANALYSIS FUNCTION
# ==============================
def analyze_pair(symbol, name):
    try:
        # DATA
        df15 = yf.download(symbol, interval="15m", period="2d", progress=False)
        df1h = yf.download(symbol, interval="1h", period="5d", progress=False)

        if len(df15) < 200 or len(df1h) < 200:
            return None

        # ==========================
        # 1H TREND
        # ==========================
        df1h['ema50'] = EMAIndicator(df1h['Close'], 50).ema_indicator()
        df1h['ema200'] = EMAIndicator(df1h['Close'], 200).ema_indicator()

        trend_up = df1h['ema50'].iloc[-1] > df1h['ema200'].iloc[-1]
        trend_down = df1h['ema50'].iloc[-1] < df1h['ema200'].iloc[-1]

        trend_strength = abs(df1h['ema50'].iloc[-1] - df1h['ema200'].iloc[-1])

        if trend_strength < 0.0003:
            return None

        # ==========================
        # 15M ENTRY
        # ==========================
        df15['ema50'] = EMAIndicator(df15['Close'], 50).ema_indicator()
        df15['rsi'] = RSIIndicator(df15['Close'], 14).rsi()

        bb = BollingerBands(df15['Close'], window=20, window_dev=2)
        df15['bb_upper'] = bb.bollinger_hband()
        df15['bb_lower'] = bb.bollinger_lband()

        price = df15['Close'].iloc[-1]
        ema50 = df15['ema50'].iloc[-1]
        rsi = df15['rsi'].iloc[-1]
        upper = df15['bb_upper'].iloc[-1]
        lower = df15['bb_lower'].iloc[-1]

        # ==========================
        # BUY SIGNAL
        # ==========================
        if trend_up:
            if price > ema50 and rsi > 55 and price < upper:
                sl = price - 0.0020
                tp = price + 0.0040

                return f"""
🟢 STRONG BUY {name}

Price: {round(price,5)}
RSI: {round(rsi,2)}

SL: {round(sl,5)}
TP: {round(tp,5)}

⏰ IST Session
⚠ Use 10–20x | Risk 2–3%
"""

        # ==========================
        # SELL SIGNAL
        # ==========================
        if trend_down:
            if price < ema50 and rsi < 45 and price > lower:
                sl = price + 0.0020
                tp = price - 0.0040

                return f"""
🔴 STRONG SELL {name}

Price: {round(price,5)}
RSI: {round(rsi,2)}

SL: {round(sl,5)}
TP: {round(tp,5)}

⏰ IST Session
⚠ Use 10–20x | Risk 2–3%
"""

        return None

    except Exception as e:
        print(f"{name} error:", e)
        return None


# ==============================
# MAIN LOOP
# ==============================
last_alert_time = 0
cooldown = 900  # 15 minutes

print("🚀 BOT STARTED")

# quick verification: if script called with --test, send one test message and exit
if len(sys.argv) > 1 and sys.argv[1] in ("--test", "test"):
    ok = send_telegram("Test message from Forex bot. If you see this, BOT_TOKEN and CHAT_ID are correct.")
    if ok:
        print("Test message sent successfully.")
    else:
        print("Test message failed — check BOT_TOKEN / CHAT_ID and bot permissions.")
    sys.exit(0)

while True:
    try:
        if is_trading_time():
            for symbol, name in pairs.items():
                signal = analyze_pair(symbol, name)

                if signal:
                    now = time.time()

                    if now - last_alert_time > cooldown:
                        send_telegram(signal)
                        print("Sent:", name)
                        last_alert_time = now

        else:
            print("Outside trading time (IST)")

        time.sleep(60)

    except Exception as e:
        print("Main loop error:", e)
        time.sleep(60)