import os
import time
import requests
import yfinance as yf
from datetime import datetime
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange

# =========================
# ENV VARIABLES (SAFE)
# =========================
BOT_TOKEN = os.getenv("8603336862:AAEUHtCOA-IYj8_VfhbObbJbLmacLYkiQ_c")
CHAT_ID = os.getenv("1450111449")

if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("Missing BOT_TOKEN or CHAT_ID")

# =========================
# TELEGRAM FUNCTION
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram Error:", e)

# =========================
# TIME FILTER (IST)
# =========================
def is_trading_time():
    now = datetime.now()
    current_time = now.hour + now.minute / 60

    # London + US sessions (IST)
    return (13 <= current_time <= 16.5) or (18.5 <= current_time <= 22)

# =========================
# PAIRS
# =========================
pairs = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY"
}

# =========================
# SIGNAL LOGIC
# =========================
def analyze_pair(symbol, name):
    try:
        df15 = yf.download(symbol, interval="15m", period="2d", progress=False)
        df1h = yf.download(symbol, interval="1h", period="5d", progress=False)

        if len(df15) < 200 or len(df1h) < 200:
            return None

        # ===== TREND (1H)
        df1h['ema50'] = EMAIndicator(df1h['Close'], window=50).ema_indicator()
        df1h['ema200'] = EMAIndicator(df1h['Close'], window=200).ema_indicator()

        trend_up = df1h['ema50'].iloc[-1] > df1h['ema200'].iloc[-1]
        trend_down = df1h['ema50'].iloc[-1] < df1h['ema200'].iloc[-1]

        trend_strength = abs(df1h['ema50'].iloc[-1] - df1h['ema200'].iloc[-1])
        if trend_strength < 0.0003:
            return None

        # ===== ENTRY (15M)
        df15['ema50'] = EMAIndicator(df15['Close'], window=50).ema_indicator()
        df15['rsi'] = RSIIndicator(df15['Close'], window=14).rsi()

        bb = BollingerBands(df15['Close'], window=20, window_dev=2)
        df15['bb_upper'] = bb.bollinger_hband()
        df15['bb_lower'] = bb.bollinger_lband()

        atr = AverageTrueRange(df15['High'], df15['Low'], df15['Close'], window=14)
        df15['atr'] = atr.average_true_range()

        last = df15.iloc[-1]
        prev = df15.iloc[-2]

        price = last['Close']
        ema50 = last['ema50']
        rsi = last['rsi']
        lower = last['bb_lower']
        upper = last['bb_upper']
        atr_val = last['atr']

        # ===== FILTERS
        if not (45 <= rsi <= 55):
            return None

        if atr_val < 0.0005:
            return None

        strong_green = last['Close'] > last['Open'] and last['Close'] > prev['Close']
        strong_red = last['Close'] < last['Open'] and last['Close'] < prev['Close']

        # ===== SIGNAL CONDITIONS
        signal = None

        if trend_up and (price <= ema50 or price <= lower) and strong_green:
            signal = "BUY"

        elif trend_down and (price >= ema50 or price >= upper) and strong_red:
            signal = "SELL"

        if not signal:
            return None

        # ===== SIGNAL STRENGTH
        score = 4  # all filters passed
        grade = "A+" if score == 4 else "A"

        # ===== SL / TP (ATR BASED)
        sl = atr_val * 1.5
        tp = sl * 2

        # ===== FINAL MESSAGE
        return f"""
🔥 {grade} SIGNAL – {name}

Type: {signal}
Price: {round(price,5)}
RSI: {round(rsi,2)}

SL: {round(sl,5)}
TP: {round(tp,5)}

⏰ IST Session
⚠️ Use 10–20x | Risk 2–3%
"""

    except Exception as e:
        print(f"{name} error:", e)
        return None

# =========================
# MAIN LOOP
# =========================
last_alert_time = 0
cooldown = 1800  # 30 minutes

send_telegram("🚀 PRO BOT STARTED (Multi-pair)")

while True:
    try:
        if is_trading_time():
            for symbol, name in pairs.items():
                signal = analyze_pair(symbol, name)

                if signal and time.time() - last_alert_time > cooldown:
                    print(signal)
                    send_telegram(signal)
                    last_alert_time = time.time()

        time.sleep(60)

    except Exception as e:
        print("Main Error:", e)
        time.sleep(60)