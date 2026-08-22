import os
import base64
import time
from datetime import datetime, timedelta
import urllib.parse
import urllib.request
import pyotp
import requests
from urllib.parse import parse_qs, urlparse
from fyers_apiv3 import fyersModel

# GitHub Secrets se encrypted fetch
FYERS_ID           = os.environ["FYERS_ID"]
APP_ID             = os.environ["APP_ID"]
PIN                = os.environ["PIN"]
TOTP_KEY           = os.environ["TOTP_KEY"]
SECRET_KEY         = os.environ["SECRET_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
REDIRECT_URI       = "https://trade.fyers.in/api-login/redirect-uri/index.html"

SYMBOL        = "NSE:SBIN-EQ"
QUANTITY      = 1
PAPER_TRADING = True  # Paper Trading Active

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Telegram Alert Sent!")
    except Exception as e:
        print(f"Telegram Error: {e}")

print("Connecting to Fyers API...")
session = requests.Session()
encoded_id = base64.b64encode(FYERS_ID.encode("utf-8")).decode("utf-8")
encoded_pin = base64.b64encode(PIN.encode("utf-8")).decode("utf-8")

r1 = session.post("https://api-t2.fyers.in/vagator/v2/send_login_otp_v2", json={"fy_id": encoded_id, "app_id": "2"}).json()
if "request_key" not in r1:
    print("OTP Request Failed:", r1)
    exit(1)

otp_val = pyotp.TOTP(TOTP_KEY).now()
r2 = session.post("https://api-t2.fyers.in/vagator/v2/verify_otp", json={"request_key": r1["request_key"], "otp": otp_val}).json()
if "request_key" not in r2:
    print("TOTP Verification Failed:", r2)
    exit(1)

r3 = session.post("https://api-t2.fyers.in/vagator/v2/verify_pin_v2", json={"request_key": r2["request_key"], "identity_type": "pin", "identifier": encoded_pin}).json()
token_temp = r3.get("data", {}).get("token") or r3.get("data", {}).get("access_token") or r3.get("access_token")

app_id_clean = APP_ID.split("-")[0] if "-" in APP_ID else APP_ID
app_type = APP_ID.split("-")[1] if "-" in APP_ID else "100"

headers = {"authorization": f"Bearer {token_temp}"}
payload = {
    "fyers_id": FYERS_ID, "app_id": app_id_clean, "redirect_uri": REDIRECT_URI,
    "appType": app_type, "code_challenge": "", "state": "None", "scope": "",
    "nonce": "", "response_type": "code", "create_cookie": True
}
r4 = session.post("https://api-t1.fyers.in/api/v3/token", headers=headers, json=payload).json()
auth_code = parse_qs(urlparse(r4["Url"]).query)["auth_code"][0]

fyers_session = fyersModel.SessionModel(
    client_id=APP_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URI,
    response_type="code", grant_type="authorization_code"
)
fyers_session.set_token(auth_code)
access_token = fyers_session.generate_token()["access_token"]
fyers = fyersModel.FyersModel(client_id=APP_ID, is_async=False, token=access_token, log_path="")

print("Login Successful! Monitoring Engine Active.")
send_telegram_alert(f"🚀 <b>Nimbus Bot Cloud Engine Started</b>\nMonitoring: {SYMBOL}\nMode: PAPER TRADING")

def get_fyers_candles():
    now = datetime.now()
    range_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    range_to = now.strftime("%Y-%m-%d")
    data = {
        "symbol": SYMBOL, "resolution": "5", "date_format": "1",
        "range_from": range_from, "range_to": range_to, "cont_flag": "1"
    }
    res = fyers.history(data=data)
    if res.get("s") != "ok" or "candles" not in res:
        return []
    return [{'date': datetime.fromtimestamp(c[0]).strftime('%Y-%m-%d'),
             'time': datetime.fromtimestamp(c[0]).strftime('%H:%M'),
             'open': c[1], 'high': c[2], 'low': c[3], 'close': c[4]} for c in res["candles"]]

start_loop = time.time()
trade_taken = False

# Maximum 2 hours execution per run
while time.time() - start_loop < 7200 and not trade_taken:
    try:
        bars = get_fyers_candles()
        days = {}
        for b in bars:
            days.setdefault(b['date'], []).append(b)
        
        sorted_dates = sorted(list(days.keys()))
        if len(sorted_dates) >= 2:
            prev_bars = days[sorted_dates[-2]]
            pdh = max(b['high'] for b in prev_bars)
            pdl = min(b['low'] for b in prev_bars)
            pdc = prev_bars[-1]['close']
            
            pivot = (pdh + pdl + pdc) / 3.0
            bc = (pdh + pdl) / 2.0
            tc = (pivot - bc) + pivot
            cpr_width = abs(tc - bc)
            atr = (pdh - pdl)
            
            today_bars = days.get(sorted_dates[-1], [])
            if cpr_width < (atr * 0.25) and len(today_bars) > 1:
                last_bar = today_bars[-1]
                
                # BUY TRIGGER
                if last_bar['high'] > pdh and last_bar['low'] <= pdh and last_bar['close'] > pdh:
                    entry = round(last_bar['close'], 2)
                    sl = round(max(tc, pdh - (atr * 0.20)), 2)
                    risk = entry - sl
                    target = round(min(pivot + atr, entry + (risk * 2.5)), 2)
                    
                    msg = (
                        f"⚡ <b>[ NIMBUS PAPER TRADE TRIGGER ]</b> ⚡\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🟢 <b>ACTION: RETEST BUY</b>\n"
                        f"📊 <b>Symbol:</b> {SYMBOL}\n"
                        f"🔹 <b>Entry Price:</b> ₹{entry}\n"
                        f"🛑 <b>Stop Loss:</b> ₹{sl} ({round(risk, 2)} pts)\n"
                        f"🎯 <b>Target:</b> ₹{target} ({round(target - entry, 2)} pts)\n"
                        f"⏰ <b>Trigger Time:</b> {last_bar['time']} IST\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"<i>Cloud Simulation Running via Fyers Data.</i>"
                    )
                    send_telegram_alert(msg)
                    trade_taken = True

                # SELL TRIGGER
                elif last_bar['low'] < pdl and last_bar['high'] >= pdl and last_bar['close'] < pdl:
                    entry = round(last_bar['close'], 2)
                    sl = round(min(bc, pdl + (atr * 0.20)), 2)
                    risk = sl - entry
                    target = round(max(pivot - atr, entry - (risk * 2.5)), 2)
                    
                    msg = (
                        f"⚡ <b>[ NIMBUS PAPER TRADE TRIGGER ]</b> ⚡\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔴 <b>ACTION: RETEST SELL</b>\n"
                        f"📊 <b>Symbol:</b> {SYMBOL}\n"
                        f"🔹 <b>Entry Price:</b> ₹{entry}\n"
                        f"🛑 <b>Stop Loss:</b> ₹{sl} ({round(risk, 2)} pts)\n"
                        f"🎯 <b>Target:</b> ₹{target} ({round(entry - target, 2)} pts)\n"
                        f"⏰ <b>Trigger Time:</b> {last_bar['time']} IST\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"<i>Cloud Simulation Running via Fyers Data.</i>"
                    )
                    send_telegram_alert(msg)
                    trade_taken = True

        time.sleep(60)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(15)
