import os
import time
from datetime import datetime, time as dt_time
import pytz
import yfinance as yf
import requests
import pandas as pd
import numpy as np

# Credentials
BOT_TOKEN = "8969458120:AAHPn7fb95a8wDDD4XYlpkLcIe5lWoXhumo"
CHAT_ID = "8333484358"

# 19 High-Beta Nifty Heavyweights Watchlist
TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "ITC.NS", "LT.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "AXISBANK.NS", "TATAMOTORS.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "TITAN.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "HCLTECH.NS", "WIPRO.NS"
]

IST = pytz.timezone('Asia/Kolkata')
START_TIME = dt_time(9, 30)
END_TIME = dt_time(14, 0)

alerted_today = set()

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            print(f"Telegram API Error: {res.text}")
    except Exception as e:
        print(f"Telegram Connection Error: {e}")

def fetch_stock_data(ticker):
    try:
        intra = yf.download(ticker, period="5d", interval="5m", progress=False)
        daily = yf.download(ticker, period="1mo", interval="1d", progress=False)

        if intra.empty or daily.empty:
            return pd.DataFrame(), pd.DataFrame()

        if isinstance(intra.columns, pd.MultiIndex):
            intra.columns = intra.columns.get_level_values(0)
        if isinstance(daily.columns, pd.MultiIndex):
            daily.columns = daily.columns.get_level_values(0)

        if intra.index.tz is None:
            intra.index = intra.index.tz_localize('UTC').tz_convert(IST)
        else:
            intra.index = intra.index.tz_convert(IST)

        return intra.dropna(), daily.dropna()
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

def scan_potter_setup():
    now_ist = datetime.now(IST).time()
    if not (START_TIME <= now_ist <= END_TIME):
        return

    for ticker in TICKERS:
        sym = ticker.replace(".NS", "")
        if sym in alerted_today:
            continue

        intra, daily = fetch_stock_data(ticker)
        if intra.empty or daily.empty or len(daily) < 15:
            continue

        # CPR & Daily ATR Calculations
        daily['Daily_ATR'] = (daily['High'] - daily['Low']).rolling(14).mean()
        daily['P'] = (daily['High'] + daily['Low'] + daily['Close']) / 3
        daily['BC'] = (daily['High'] + daily['Low']) / 2
        daily['TC'] = 2 * daily['P'] - daily['BC']
        daily['TC_real'] = daily[['TC', 'BC']].max(axis=1)
        daily['BC_real'] = daily[['TC', 'BC']].min(axis=1)
        daily['CPR_Width'] = (daily['TC_real'] - daily['BC_real']).abs()
        daily['R2'] = daily['P'] + (daily['High'] - daily['Low'])
        daily['S2'] = daily['P'] - (daily['High'] - daily['Low'])

        prev_day = daily.iloc[-2]
        if 'Daily_ATR' not in prev_day or 'CPR_Width' not in prev_day:
            continue

        daily_atr = prev_day['Daily_ATR']
        cpr_width = prev_day['CPR_Width']

        if pd.isna(daily_atr) or pd.isna(cpr_width) or cpr_width >= (0.25 * daily_atr):
            continue

        pdh, pdl = prev_day['High'], prev_day['Low']
        tc, bc = prev_day['TC_real'], prev_day['BC_real']
        r2, s2 = prev_day['R2'], prev_day['S2']

        # Intraday VWAP, EMA20 & RVOL Calculations
        intra['EMA20'] = intra['Close'].ewm(span=20, adjust=False).mean()
        intra['Vol_MA10'] = intra['Volume'].rolling(10).mean()
        intra['RVOL'] = intra['Volume'] / intra['Vol_MA10']
        intra['TP'] = (intra['High'] + intra['Low'] + intra['Close']) / 3
        intra['TPV'] = intra['TP'] * intra['Volume']
        intra['Date_Only'] = intra.index.date
        intra['Cum_TPV'] = intra.groupby('Date_Only')['TPV'].cumsum()
        intra['Cum_Vol'] = intra.groupby('Date_Only')['Volume'].cumsum()
        intra['VWAP'] = intra['Cum_TPV'] / intra['Cum_Vol']

        last = intra.iloc[-1]
        close, high, low, open_p = last['Close'], last['High'], last['Low'], last['Open']
        vwap, ema20, rvol = last['VWAP'], last['EMA20'], last['RVOL']

        if close < 300:
            continue

        candle_range = high - low
        is_solid = (candle_range > 0) and ((abs(close - open_p) / candle_range) >= 0.50)
        has_rvol = (not pd.isna(rvol)) and (rvol >= 1.25)

        # BUY Setup
        if has_rvol and is_solid and (close > vwap) and (close > ema20):
            if (high > pdh) and (low <= pdh) and (close > pdh):
                sl = round(min(tc, pdh - (0.20 * daily_atr)), 2)
                risk = round(close - sl, 2)
                if 0 < risk <= (0.35 * daily_atr):
                    target = round(max(r2, close + (2.5 * risk)), 2)
                    trail1 = round(close + (1.2 * risk), 2)
                    trail2 = round(close + (1.8 * risk), 2)

                    msg = (
                        f"🧙‍♂️ *Hey Potterhead, you have an opportunity!*\n\n"
                        f"🚨 *POTTER STRATEGY ALERT (BUY)* 🚨\n\n"
                        f"📈 *Stock:* `{sym}`\n"
                        f"💰 *Entry Price:* ₹{close:.2f}\n"
                        f"🛡️ *Initial Stop Loss (SL):* ₹{sl:.2f} (Risk: ₹{risk:.2f})\n\n"
                        f"🎯 *Final Target (1:2.5 RR):* ₹{target:.2f}\n"
                        f"🔄 *Trailing Target 1 (Breakeven @ 1:1.2 RR):* ₹{trail1:.2f} -> SL to Cost\n"
                        f"🔒 *Trailing Target 2 (Lock 1:1 @ 1:1.8 RR):* ₹{trail2:.2f} -> SL to ₹{close + risk:.2f}\n"
                        f"🛑 *Hard EOD Exit Time:* 02:00 PM IST\n\n"
                        f"📊 *RVOL:* {rvol:.2f}x | CPR: Narrow\n"
                        f"⏰ *Time:* {datetime.now(IST).strftime('%H:%M:%S IST')}"
                    )
                    send_telegram_alert(msg)
                    alerted_today.add(sym)

        # SELL Setup
        if has_rvol and is_solid and (close < vwap) and (close < ema20):
            if (low < pdl) and (high >= pdl) and (close < pdl):
                sl = round(max(bc, pdl + (0.20 * daily_atr)), 2)
                risk = round(sl - close, 2)
                if 0 < risk <= (0.35 * daily_atr):
                    target = round(min(s2, close - (2.5 * risk)), 2)
                    trail1 = round(close - (1.2 * risk), 2)
                    trail2 = round(close - (1.8 * risk), 2)

                    msg = (
                        f"🧙‍♂️ *Hey Potterhead, you have an opportunity!*\n\n"
                        f"🚨 *POTTER STRATEGY ALERT (SELL)* 🚨\n\n"
                        f"📉 *Stock:* `{sym}`\n"
                        f"💰 *Entry Price:* ₹{close:.2f}\n"
                        f"🛡️ *Initial Stop Loss (SL):* ₹{sl:.2f} (Risk: ₹{risk:.2f})\n\n"
                        f"🎯 *Final Target (1:2.5 RR):* ₹{target:.2f}\n"
                        f"🔄 *Trailing Target 1 (Breakeven @ 1:1.2 RR):* ₹{trail1:.2f} -> SL to Cost\n"
                        f"🔒 *Trailing Target 2 (Lock 1:1 @ 1:1.8 RR):* ₹{trail2:.2f} -> SL to ₹{close - risk:.2f}\n"
                        f"🛑 *Hard EOD Exit Time:* 02:00 PM IST\n\n"
                        f"📊 *RVOL:* {rvol:.2f}x | CPR: Narrow\n"
                        f"⏰ *Time:* {datetime.now(IST).strftime('%H:%M:%S IST')}"
                    )
                    send_telegram_alert(msg)
                    alerted_today.add(sym)

        time.sleep(0.3)

if __name__ == "__main__":
    send_telegram_alert("🚀 *Potter Cloud Scanner Online & Monitoring Nifty Basket...*")
    while True:
        try:
            now_time = datetime.now(IST).time()
            if now_time > dt_time(14, 0):
                send_telegram_alert("🛑 *Scanning Window Closed (02:00 PM). Potter Bot going offline.*")
                break
            scan_potter_setup()
        except Exception:
            continue

        time.sleep(60)
