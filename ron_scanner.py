import os
import time
import math
import requests
import datetime
import yfinance as yf
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ==========================================================
# CONFIGURATION - TELEGRAM & SYSTEM PARAMETERS
# ==========================================================
TELEGRAM_BOT_TOKEN = "8969458120:AAHPn7fb95a8wDDD4XYlpkLcIe5lWoXhumo"
TELEGRAM_CHAT_ID = "8333484358"

CAPITAL = 20000.0
RISK_PER_TRADE = 400.0  # Fixed 2% Risk

# High-Beta F&O Momentum Watchlist
WATCHLIST = [
    "TRENT.NS", "DIXON.NS", "SHRIRAMFIN.NS", "POLYCAB.NS", "BHARATFORG.NS",
    "M&M.NS", "BEL.NS", "ADANIENT.NS", "VOLTAS.NS", "CHOLAFIN.NS",
    "JSWSTEEL.NS", "BAJFINANCE.NS", "PERSISTENT.NS"
]

def send_telegram_msg(message: str):
    """Sends HTML formatted instant alerts to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        print(f"Telegram Delivery Error: {e}")

# In-memory alert state trackers
radar_sent = {}
executed_trades = {}

print("🚀 Ron Weasley Strategy Scanner Active. Monitoring High-Beta Momentum Basket...")
send_telegram_msg("🟢 <b>Ron Weasley System Activated</b>\nMonitoring high-beta momentum basket for Narrow CPR + PDH/PDL breakout setups.")

def get_daily_levels():
    """Calculates CPR, PDH, and PDL levels for each stock."""
    levels = {}
    for sym in WATCHLIST:
        try:
            df = yf.download(sym, period="5d", interval="1d", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if len(df) < 2:
                continue
            
            prev = df.iloc[-2]
            pivot = (prev["High"] + prev["Low"] + prev["Close"]) / 3.0
            bc = (prev["High"] + prev["Low"]) / 2.0
            tc = (pivot - bc) + pivot
            cpr_width = (abs(tc - bc) / prev["Close"]) * 100
            
            levels[sym] = {
                "PDH": float(prev["High"]),
                "PDL": float(prev["Low"]),
                "Top_CPR": max(tc, bc),
                "Bottom_CPR": min(tc, bc),
                "CPR_Width": float(cpr_width),
                "Narrow": cpr_width <= 0.38
            }
        except Exception:
            continue
    return levels

daily_levels = get_daily_levels()

# ==========================================================
# LIVE SCANNING LOOP (09:15 AM - 11:30 AM IST)
# ==========================================================
while True:
    now = datetime.datetime.now()
    curr_min = now.hour * 60 + now.minute
    
    # Check Nifty 50 Direction
    try:
        nifty = yf.download("^NSEI", period="1d", interval="5m", progress=False)
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        nifty_open = float(nifty.iloc[0]["Open"])
        nifty_curr = float(nifty.iloc[-1]["Close"])
        nifty_bullish = nifty_curr >= nifty_open
    except Exception:
        nifty_bullish = True

    for sym in WATCHLIST:
        stock_name = sym.replace(".NS", "")
        if sym not in daily_levels or not daily_levels[sym]["Narrow"]:
            continue
            
        lvl = daily_levels[sym]
        pdh = lvl["PDH"]
        pdl = lvl["PDL"]

        try:
            df_5m = yf.download(sym, period="1d", interval="5m", progress=False)
            if isinstance(df_5m.columns, pd.MultiIndex):
                df_5m.columns = df_5m.columns.get_level_values(0)
            if len(df_5m) < 4:
                continue
                
            curr_price = float(df_5m.iloc[-1]["Close"])
            curr_high = float(df_5m.iloc[-1]["High"])
            curr_low = float(df_5m.iloc[-1]["Low"])
            
            # Cumulative VWAP
            df_5m["TP"] = (df_5m["High"] + df_5m["Low"] + df_5m["Close"]) / 3.0
            vwap = (df_5m["TP"] * df_5m["Volume"]).cumsum() / (df_5m["Volume"].cumsum() + 1e-9)
            curr_vwap = float(vwap.iloc[-1])
            
            # --------------------------------------------------
            # ALERT 1: PRE-BREAKOUT RADAR
            # --------------------------------------------------
            if sym not in radar_sent and (585 <= curr_min <= 690):
                if (0 < (pdh - curr_price) <= pdh * 0.0025) and nifty_bullish:
                    msg = (
                        f"⚠️ <b>RON WEASLEY RADAR: PRE-BREAKOUT WATCH</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📈 <b>Stock:</b> {stock_name}\n"
                        f"🎯 <b>PDH Level:</b> ₹{pdh:.2f}\n"
                        f"⚡ <b>Current Price:</b> ₹{curr_price:.2f} (Approaching PDH)\n"
                        f"📊 <b>Market Context:</b> Nifty 50 Bullish | CPR: Narrow ({lvl['CPR_Width']:.2f}%)\n"
                        f"👉 <i>Action: Keep chart ready. Watching for post-10:01 AM breakout confirmation.</i>"
                    )
                    send_telegram_msg(msg)
                    radar_sent[sym] = "BUY_ALERTED"
                    
                elif (0 < (curr_price - pdl) <= pdl * 0.0025) and not nifty_bullish:
                    msg = (
                        f"⚠️ <b>RON WEASLEY RADAR: PRE-BREAKDOWN WATCH</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📉 <b>Stock:</b> {stock_name}\n"
                        f"🎯 <b>PDL Level:</b> ₹{pdl:.2f}\n"
                        f"⚡ <b>Current Price:</b> ₹{curr_price:.2f} (Approaching PDL)\n"
                        f"📊 <b>Market Context:</b> Nifty 50 Bearish | CPR: Narrow ({lvl['CPR_Width']:.2f}%)\n"
                        f"👉 <i>Action: Keep chart ready. Watching for post-10:01 AM breakdown confirmation.</i>"
                    )
                    send_telegram_msg(msg)
                    radar_sent[sym] = "SELL_ALERTED"

            # --------------------------------------------------
            # ALERT 2: CONFIRMED EXECUTION ORDER
            # --------------------------------------------------
            if sym not in executed_trades and (601 <= curr_min <= 690):
                # LONG TRIGGER
                if curr_price > pdh and curr_price > curr_vwap and nifty_bullish:
                    prev_low = float(df_5m.iloc[-2]["Low"])
                    sl_price = round(min(prev_low, lvl["Bottom_CPR"]), 2)
                    sl_dist = round(curr_price - sl_price, 2)
                    
                    if sl_dist >= (curr_price * 0.0035):
                        qty = math.floor(RISK_PER_TRADE / sl_dist)
                        t1 = round(curr_price + (sl_dist * 1.0), 2)
                        t2 = round(curr_price + (sl_dist * 2.0), 2)
                        
                        msg = (
                            f"🚀 <b>RON WEASLEY EXECUTION: BUY TRIGGERED</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🔹 <b>Stock:</b> {stock_name} (LONG)\n"
                            f"💵 <b>Entry Price:</b> ₹{curr_price:.2f}\n"
                            f"🛑 <b>Initial Stop-Loss:</b> ₹{sl_price:.2f} (Risk Distance: ₹{sl_dist:.2f})\n"
                            f"📦 <b>Position Size:</b> {qty} Shares (₹{RISK_PER_TRADE:.0f} Fixed Risk)\n"
                            f"🎯 <b>Target 1 (+1.0R):</b> ₹{t1:.2f} (Book 50% Quantity)\n"
                            f"🎯 <b>Target 2 (+2.0R):</b> ₹{t2:.2f} (Final Target for Remaining 50%)"
                        )
                        send_telegram_msg(msg)
                        executed_trades[sym] = {
                            "type": "BUY", "entry": curr_price, "sl": sl_price,
                            "t1": t1, "t2": t2, "qty": qty, "p1_done": False
                        }

                # SHORT TRIGGER
                elif curr_price < pdl and curr_price < curr_vwap and not nifty_bullish:
                    prev_high = float(df_5m.iloc[-2]["High"])
                    sl_price = round(max(prev_high, lvl["Top_CPR"]), 2)
                    sl_dist = round(sl_price - curr_price, 2)
                    
                    if sl_dist >= (curr_price * 0.0035):
                        qty = math.floor(RISK_PER_TRADE / sl_dist)
                        t1 = round(curr_price - (sl_dist * 1.0), 2)
                        t2 = round(curr_price - (sl_dist * 2.0), 2)
                        
                        msg = (
                            f"🚀 <b>RON WEASLEY EXECUTION: SELL TRIGGERED</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🔹 <b>Stock:</b> {stock_name} (SHORT)\n"
                            f"💵 <b>Entry Price:</b> ₹{curr_price:.2f}\n"
                            f"🛑 <b>Initial Stop-Loss:</b> ₹{sl_price:.2f} (Risk Distance: ₹{sl_dist:.2f})\n"
                            f"📦 <b>Position Size:</b> {qty} Shares (₹{RISK_PER_TRADE:.0f} Fixed Risk)\n"
                            f"🎯 <b>Target 1 (+1.0R):</b> ₹{t1:.2f} (Book 50% Quantity)\n"
                            f"🎯 <b>Target 2 (+2.0R):</b> ₹{t2:.2f} (Final Target for Remaining 50%)"
                        )
                        send_telegram_msg(msg)
                        executed_trades[sym] = {
                            "type": "SELL", "entry": curr_price, "sl": sl_price,
                            "t1": t1, "t2": t2, "qty": qty, "p1_done": False
                        }

            # --------------------------------------------------
            # ALERT 3: TRAILING SL & 1.0R PARTIAL BOOKING ALERT
            # --------------------------------------------------
            if sym in executed_trades and not executed_trades[sym]["p1_done"]:
                tr = executed_trades[sym]
                if (tr["type"] == "BUY" and curr_high >= tr["t1"]) or (tr["type"] == "SELL" and curr_low <= tr["t1"]):
                    tr["p1_done"] = True
                    msg = (
                        f"🎯 <b>RON WEASLEY UPDATE: TARGET 1 (+1.0R) ACHIEVED</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 <b>Stock:</b> {stock_name}\n"
                        f"✅ <b>Action 1:</b> Book 50% profit ({math.floor(tr['qty']/2)} Shares).\n"
                        f"🔒 <b>Action 2:</b> Move Stop-Loss to <b>Entry Price (₹{tr['entry']:.2f})</b>.\n"
                        f"🚀 <i>Status: Risk-free position. Remaining 50% trailing towards Target 2 (₹{tr['t2']:.2f}).</i>"
                    )
                    send_telegram_msg(msg)

        except Exception as e:
            continue

    time.sleep(60)
