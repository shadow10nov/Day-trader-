import os
import time as t_module
from datetime import datetime, time
import pytz
import requests
import pandas as pd
import numpy as np

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "ITC.NS", "LT.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "AXISBANK.NS", "TATAMOTORS.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "BAJFINANCE.NS", "ASIANPAINT.NS", "HCLTECH.NS", "WIPRO.NS"
]

IST = pytz.timezone('Asia/Kolkata')
START_TIME = time(9, 45)
END_TIME = time(11, 30)

alerted_today = set()

def send_telegram_alert(message):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def fetch_yahoo_chart(ticker, interval="5m", range_str="5d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={range_str}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()['chart']['result'][0]
        quote = data['indicators']['quote'][0]
        df = pd.DataFrame({
            'Open': quote['open'], 'High': quote['high'], 'Low': quote['low'],
            'Close': quote['close'], 'Volume': quote['volume']
        }, index=pd.to_datetime(data['timestamp'], unit='s', utc=True))
        df.index = df.index.tz_convert('Asia/Kolkata')
        df.dropna(inplace=True)
        return df
    except Exception:
        return pd.DataFrame()

def scan_potter_setup():
    now_ist = datetime.now(IST).time()
    if not (START_TIME <= now_ist <= END_TIME):
        return

    for ticker in TICKERS:
        sym = ticker.replace(".NS", "")
        if sym in alerted_today:
            continue
            
        intra = fetch_yahoo_chart(ticker, "5m", "5d")
        daily = fetch_yahoo_chart(ticker, "1d", "30d")
        
        if intra.empty or daily.empty:
            continue
            
        daily['ATR14'] = (daily['High'] - daily['Low']).rolling(14).mean()
        daily['P'] = (daily['High'] + daily['Low'] + daily['Close']) / 3
        daily['BC'] = (daily['High'] + daily['Low']) / 2
        daily['TC'] = 2 * daily['P'] - daily['BC']
        daily['TC_real'] = daily[['TC', 'BC']].max(axis=1)
        daily['BC_real'] = daily[['TC', 'BC']].min(axis=1)
        daily['CPR_Width'] = (daily['TC_real'] - daily['BC_real']).abs()
        daily['R2'] = daily['P'] + (daily['High'] - daily['Low'])
        daily['S2'] = daily['P'] - (daily['High'] - daily['Low'])
        
        prev_day = daily.iloc[-2]
        daily_atr = prev_day['Daily_ATR']
        cpr_width = prev_day['CPR_Width']
        
        if pd.isna(daily_atr) or pd.isna(cpr_width) or cpr_width >= (0.25 * daily_atr):
            continue
            
        pdh, pdl = prev_day['High'], prev_day['Low']
        tc, bc = prev_day['TC_real'], prev_day['BC_real']
        r2, s2 = prev_day['R2'], prev_day['S2']
        
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
                        f"🛑 *Hard EOD Exit Time:* 02:55 PM IST\n\n"
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
                        f"🛑 *Hard EOD Exit Time:* 02:55 PM IST\n\n"
                        f"📊 *RVOL:* {rvol:.2f}x | CPR: Narrow\n"
                        f"⏰ *Time:* {datetime.now(IST).strftime('%H:%M:%S IST')}"
                    )
                    send_telegram_alert(msg)
                    alerted_today.add(sym)
                    
        t_module.sleep(0.3)

if __name__ == "__main__":
    send_telegram_alert("🚀 *Potter Cloud Scanner Online & Monitoring Nifty Basket...*")
    while True:
        now_time = datetime.now(IST).time()
        if now_time > time(11, 35):
            send_telegram_alert("🛑 *Scanning Window Closed (11:35 AM). Potter Bot going offline.*")
            break
        scan_potter_setup()
        t_module.sleep(60)
