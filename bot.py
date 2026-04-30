import os
import time
import sys
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange

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
        if resp.status_code != 200:
            print("Telegram API error:", resp.status_code, resp.text)
            return False
        return True
    except Exception as e:
        print("Telegram Error:", e)
        return False

def telegram_get_me():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None

# ==============================
# TIME FILTER (IST)
# ==============================
def is_trading_time():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    t = now.hour + now.minute / 60
    return (13 <= t <= 16.5) or (18.5 <= t <= 22)

# ==============================
# PAIRS
# ==============================
pairs = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY"
}

# ==============================
# PRO ANALYSIS
# ==============================
def analyze_pair(symbol, name):
    try:
        df15 = yf.download(symbol, interval="15m", period="2d", progress=False)
        df1h = yf.download(symbol, interval="1h", period="5d", progress=False)

        if len(df15) < 200 or len(df1h) < 200:
            return None

        # ===== TREND (1H)
        df1h['ema50'] = EMAIndicator(df1h['Close'], 50).ema_indicator()
        df1h['ema200'] = EMAIndicator(df1h['Close'], 200).ema_indicator()

        ema50_1h = df1h['ema50'].iloc[-1]
        ema200_1h = df1h['ema200'].iloc[-1]

        trend_up = ema50_1h > ema200_1h
        trend_down = ema50_1h < ema200_1h

        trend_strength = abs(ema50_1h - ema200_1h)
        if trend_strength < 0.0005:
            return None

        # ===== ENTRY (15M)
        df15['ema50'] = EMAIndicator(df15['Close'], 50).ema_indicator()
        df15['rsi'] = RSIIndicator(df15['Close'], 14).rsi()

        bb = BollingerBands(df15['Close'], 20, 2)
        df15['bb_upper'] = bb.bollinger_hband()
        df15['bb_lower'] = bb.bollinger_lband()

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

        # ===== VOLATILITY FILTER
        if atr_val < 0:
            return None

        # ==========================
        # BUY (PRO)
        # ==========================
        if trend_up:
            breakout = price > prev_high
            rsi_ok = 55 <= rsi <= 65

            if price > ema50 and breakout and rsi_ok:

                sl = price - (atr_val * 1.5)
                tp = price + (atr_val * 3)

                return f"""
🔥 A+ BUY {name}

Price: {round(price,5)}
RSI: {round(rsi,2)}
ATR: {round(atr_val,5)}

SL: {round(sl,5)}
TP: {round(tp,5)}

📈 Trend Strong | Breakout Confirmed
"""

        # ==========================
        # SELL (PRO)
        # ==========================
        if trend_down:
            breakout = price < prev_low
            rsi_ok = 35 <= rsi <= 45

            if price < ema50 and breakout and rsi_ok:

                sl = price + (atr_val * 1.5)
                tp = price - (atr_val * 3)

                return f"""
🔥 A+ SELL {name}

Price: {round(price,5)}
RSI: {round(rsi,2)}
ATR: {round(atr_val,5)}

SL: {round(sl,5)}
TP: {round(tp,5)}

📉 Trend Strong | Breakdown Confirmed
"""

        return None

    except Exception as e:
        print(f"{name} error:", e)
        return None

# ==============================
# MAIN LOOP
# ==============================
last_alert_time = {}
cooldown = 900

print("🚀 BOT STARTED")

# TEST MODE
if len(sys.argv) > 1 and sys.argv[1] in ("test", "--test"):
    send_telegram("Bot test message ✅")
    sys.exit()

while True:
    try:
        if is_trading_time():
            for symbol, name in pairs.items():
                signal = analyze_pair(symbol, name)

                if signal:
                    now = time.time()

                    if symbol not in last_alert_time or now - last_alert_time[symbol] > cooldown:
                        send_telegram(signal)
                        print("Sent:", name)
                        last_alert_time[symbol] = now

        else:
            print("Outside trading time (IST)")

        # ✅ FIXED: always sleep
        time.sleep(120)

    except Exception as e:
        print("Main loop error:", e)
        time.sleep(120)