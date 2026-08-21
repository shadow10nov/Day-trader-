import json
import time
import urllib.request
from datetime import datetime

# ==========================================================
# 🔴 TELEGRAM CREDENTIALS
# ==========================================================
TELEGRAM_BOT_TOKEN = "8969458120:AAHPn7fb95a8wDDD4XYlpkLcIe5lWoXhumo"
TELEGRAM_CHAT_ID = "8333484358"

# ==========================================================
# CONFIGURATION & NIFTY TOP 200 UNIVERSE
# ==========================================================
MIN_STOCK_PRICE = 200.0
MAX_CPR_WIDTH_PCT = 0.28       # Narrow CPR Threshold (< 0.28%)
MAX_SQUEEZE_RANGE_PCT = 3.5    # Tight Box Range (< 3.5%)
MIN_SQUEEZE_DAYS = 3           # Minimum 3 Days
MAX_SQUEEZE_DAYS = 10          # Maximum 10 Days

NIFTY_200_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "BHARTIARTL.NS", "LT.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS",
    "TATAMOTORS.NS", "M&M.NS", "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "TITAN.NS", "TRENT.NS", "PERSISTENT.NS", "DIXON.NS", "KAYNES.NS",
    "POLYCAB.NS", "HAL.NS", "BEL.NS", "COALINDIA.NS", "VEDL.NS",
    "ADANIENT.NS", "ASIANPAINT.NS", "HINDUNILVR.NS", "NTPC.NS", "POWERGRID.NS",
    "EICHERMOT.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "TATASTEEL.NS", "JSWSTEEL.NS",
    "HCLTECH.NS", "WIPRO.NS", "TECHM.NS", "LTIM.NS", "NESTLEIND.NS",
    "BRITANNIA.NS", "DABUR.NS", "GODREJCP.NS", "TATACONSUM.NS", "DLF.NS",
    "LODHA.NS", "GODREJPROP.NS", "INDUSINDBK.NS", "BANKBARODA.NS", "PNB.NS"
]

def fetch_historical_ohlcv(symbol, period="1mo", interval="1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            res = data['chart']['result'][0]
            quote = res['indicators']['quote'][0]
            timestamps = res['timestamp']

            bars = []
            for i in range(len(timestamps)):
                o, h, l, c, v = quote['open'][i], quote['high'][i], quote['low'][i], quote['close'][i], quote['volume'][i]
                if None not in (o, h, l, c, v) and v > 0:
                    bars.append({
                        "date": datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d"),
                        "open": float(o), "high": float(h), "low": float(l),
                        "close": float(c), "volume": int(v)
                    })
            return bars
    except Exception:
        return []

def calculate_cpr(high, low, close):
    pivot = (high + low + close) / 3.0
    bc = (high + low) / 2.0
    tc = (pivot - bc) + pivot
    tc_actual = max(tc, bc)
    bc_actual = min(tc, bc)
    cpr_width_pct = ((tc_actual - bc_actual) / pivot) * 100.0
    
    return {
        "pivot": round(pivot, 2),
        "tc": round(tc_actual, 2),
        "bc": round(bc_actual, 2),
        "width_pct": round(cpr_width_pct, 3)
    }

def analyze_dynamic_cpr_compression(bars):
    if len(bars) < (MAX_SQUEEZE_DAYS + 5):
        return None

    today_bar = bars[-1]
    cmp = today_bar["close"]

    # Minimum Price Condition (₹200)
    if cmp < MIN_STOCK_PRICE:
        return None

    # CPR of Prior Day
    prev_day = bars[-2]
    cpr = calculate_cpr(prev_day["high"], prev_day["low"], prev_day["close"])
    is_narrow_cpr = cpr["width_pct"] <= MAX_CPR_WIDTH_PCT

    # Dynamic 3 to 10 Days Box Scanner
    best_squeeze = None
    for length in range(MIN_SQUEEZE_DAYS, MAX_SQUEEZE_DAYS + 1):
        window = bars[-(length + 1):-1]
        b_high = max(b["high"] for b in window)
        b_low = min(b["low"] for b in window)
        b_range = ((b_high - b_low) / b_low) * 100.0

        if b_range <= MAX_SQUEEZE_RANGE_PCT:
            best_squeeze = {
                "days": length,
                "high": round(b_high, 2),
                "low": round(b_low, 2),
                "range_pct": round(b_range, 2)
            }

    if not best_squeeze:
        return None

    box_high = best_squeeze["high"]
    box_low = best_squeeze["low"]
    box_days = best_squeeze["days"]

    # RVOL Calculation (Relative Volume)
    prior_vols = [b["volume"] for b in bars[-20:-1]]
    avg_vol = sum(prior_vols) / len(prior_vols) if prior_vols else 1
    rvol = round(today_bar["volume"] / avg_vol, 2) if avg_vol > 0 else 1.0

    # Breakout & Breakdown Conditions
    breakout_up = cmp > box_high and cmp > cpr["tc"]
    breakout_down = cmp < box_low and cmp < cpr["bc"]
    in_squeeze = is_narrow_cpr and (box_low <= cmp <= box_high)

    if not (breakout_up or breakout_down or in_squeeze):
        return None

    if breakout_up:
        bias = "BULLISH BREAKOUT"
        entry = cmp
        sl = round(max(cpr["pivot"], box_high * 0.992), 2)
        risk = entry - sl
        t1 = round(entry + (risk * 2.0), 2)
        t2 = round(entry + (risk * 3.5), 2)
        confidence = 9 if (rvol >= 1.4 and is_narrow_cpr) else 7
    elif breakout_down:
        bias = "BEARISH BREAKDOWN"
        entry = cmp
        sl = round(min(cpr["pivot"], box_low * 1.008), 2)
        risk = sl - entry
        t1 = round(entry - (risk * 2.0), 2)
        t2 = round(entry - (risk * 3.5), 2)
        confidence = 9 if (rvol >= 1.4 and is_narrow_cpr) else 7
    else:
        bias = "VOLATILITY SQUEEZE (WATCH)"
        entry = cmp
        sl = round(cpr["bc"], 2)
        t1 = round(box_high * 1.02, 2)
        t2 = round(box_high * 1.04, 2)
        confidence = 6

    return {
        "cmp": cmp,
        "cpr": cpr,
        "box_high": box_high,
        "box_low": box_low,
        "box_days": box_days,
        "box_range_pct": best_squeeze["range_pct"],
        "rvol": rvol,
        "bias": bias,
        "entry": entry,
        "sl": sl,
        "t1": t1,
        "t2": t2,
        "confidence": confidence
    }

def send_telegram(html_msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": html_msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def run_dynamic_cpr_scanner():
    print("=" * 68)
    print("⚡ NIFTY TOP 200: DYNAMIC 3-10 DAYS CPR SCANNER ⚡")
    print(f"Time: {datetime.now().strftime('%d %b %Y | %I:%M %p')} IST")
    print("=" * 68)

    scanned_count = 0
    signals = []

    for sym in NIFTY_200_UNIVERSE:
        print(f"Scanning {sym:16} ...", end=" ")
        bars = fetch_historical_ohlcv(sym)
        if not bars:
            print("No Data.")
            continue

        scanned_count += 1
        res = analyze_dynamic_cpr_compression(bars)

        if res and res["confidence"] >= 7:
            print(f"🔥 [{res['bias']}] ({res['box_days']}D Box) Detected!")
            signals.append((sym, res))

            alert_msg = (
                f"🎯 <b>CPR SQUEEZE BREAKOUT — {sym}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 <b>Action:</b> {res['bias']}\n"
                f"⭐ <b>Confidence:</b> {res['confidence']}/10 | <b>RVOL:</b> {res['rvol']}x\n\n"
                f"📊 <b>TECHNICAL SETUP</b>\n"
                f"• <b>CMP:</b> ₹{res['cmp']:,.2f}\n"
                f"• <b>Squeeze Horizon:</b> {res['box_days']} Days Consolidation\n"
                f"• <b>Consolidation Box:</b> ₹{res['box_low']} - ₹{res['box_high']} ({res['box_range_pct']}% Squeeze)\n"
                f"• <b>CPR Width:</b> {res['cpr']['width_pct']}% (Ultra-Narrow)\n"
                f"• <b>TC / Pivot / BC:</b> ₹{res['cpr']['tc']} | ₹{res['cpr']['pivot']} | ₹{res['cpr']['bc']}\n\n"
                f"🧭 <b>EXECUTION PLAN (1:2+ R:R)</b>\n"
                f"• <b>Trigger Entry:</b> ₹{res['entry']:,.2f}\n"
                f"• <b>Target 1:</b> ₹{res['t1']:,.2f}\n"
                f"• <b>Target 2:</b> ₹{res['t2']:,.2f}\n"
                f"• <b>Stop Loss:</b> ₹{res['sl']:,.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Nifty 200 Dynamic CPR Strategy · Risk management strictly advised.</i>"
            )
            send_telegram(alert_msg)
            time.sleep(0.3)
        else:
            print("No Setup.")
        time.sleep(0.15)

    summary = (
        f"📊 <b>NIFTY 200 DYNAMIC SCAN SUMMARY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Scanned:</b> {scanned_count} Top 200 Equities\n"
        f"• <b>Active Signals:</b> {len(signals)} Breakout Setup(s)\n"
        f"• <b>Squeeze Scope:</b> 3 to 10 Days Compression Box\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    send_telegram(summary)
    print("=" * 68)
    print(f"Scan complete. {len(signals)} trade alert(s) dispatched to Telegram.")

if __name__ == "__main__":
    run_dynamic_cpr_scanner()
