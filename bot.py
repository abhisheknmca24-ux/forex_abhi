import os
import time
import requests
import yfinance as yf
from datetime import datetime
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands

# =====================
# ENV VARIABLES
# =====================
BOT_TOKEN = os.getenv("8603336862:AAEUHtCOA-IYj8_VfhbObbJbLmacLYkiQ_c")
CHAT_ID = os.getenv("1450111449")

if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("❌ BOT_TOKEN or CHAT_ID not set")

# =====================
# TELEGRAM FUNCTION
# =====================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram Error:", e)

# =====================
# INDIA TIME FILTER (IST)
# =====================
def is_trading_time():
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    current_time = hour + minute/60

    # London + US sessions (IST)
    return (
        (12.5 <= current_time <= 16.5) or   # London
        (18.5 <= current_time <= 21.5)      # US overlap
    )

# =====================
# SIGNAL FUNCTION
# =====================
def check_signal():
    try:
        df_15m = yf.download("EURUSD=X", interval="15m", period="2d", progress=False)
        df_1h = yf.download("EURUSD=X", interval="1h", period="5d", progress=False)

        if len(df_15m) < 200 or len(df_1h) < 200:
            return "WAIT"

        # ===== 1H TREND =====
        df_1h['ema50'] = EMAIndicator(df_1h['Close'], window=50).ema_indicator()
        df_1h['ema200'] = EMAIndicator(df_1h['Close'], window=200).ema_indicator()

        trend_up = df_1h['ema50'].iloc[-1] > df_1h['ema200'].iloc[-1]
        trend_down = df_1h['ema50'].iloc[-1] < df_1h['ema200'].iloc[-1]

        # ===== 15M ENTRY =====
        df_15m['ema50'] = EMAIndicator(df_15m['Close'], window=50).ema_indicator()
        df_15m['rsi'] = RSIIndicator(df_15m['Close'], window=14).rsi()

        bb = BollingerBands(df_15m['Close'], window=20, window_dev=2)
        df_15m['bb_upper'] = bb.bollinger_hband()
        df_15m['bb_lower'] = bb.bollinger_lband()

        last = df_15m.iloc[-1]
        prev = df_15m.iloc[-2]

        price = last['Close']
        ema50 = last['ema50']
        rsi = last['rsi']
        lower = last['bb_lower']
        upper = last['bb_upper']

        # Candle strength
        strong_green = last['Close'] > last['Open'] and last['Close'] > prev['Close']
        strong_red = last['Close'] < last['Open'] and last['Close'] < prev['Close']

        # ===== BUY =====
        if trend_up:
            if (price <= ema50 or price <= lower) and (45 <= rsi <= 55) and strong_green:
                return f"🔥 STRONG BUY EUR/USD\nPrice: {round(price,5)}\nRSI: {round(rsi,2)}\nSession: IST"

        # ===== SELL =====
        if trend_down:
            if (price >= ema50 or price >= upper) and (45 <= rsi <= 55) and strong_red:
                return f"🔻 STRONG SELL EUR/USD\nPrice: {round(price,5)}\nRSI: {round(rsi,2)}\nSession: IST"

        return "WAIT"

    except Exception as e:
        print("Signal Error:", e)
        return "WAIT"

# =====================
# MAIN LOOP
# =====================
last_signal = ""
last_alert_time = 0
cooldown = 1800  # 30 minutes

# Startup message
send_telegram("🤖 Bot started (India time filter ON 🇮🇳)")

while True:
    try:
        if is_trading_time():
            signal = check_signal()
        else:
            signal = "WAIT"

        if signal != "WAIT" and signal != last_signal:
            if time.time() - last_alert_time > cooldown:
                print("Signal:", signal)
                send_telegram(signal)
                last_signal = signal
                last_alert_time = time.time()

        time.sleep(60)

    except Exception as e:
        print("Main Loop Error:", e)
        time.sleep(60)