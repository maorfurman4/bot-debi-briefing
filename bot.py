#!/usr/bin/env python3
import asyncio
import html
import logging
import os
import re
import random
import json
from datetime import datetime, timedelta, timezone
import datetime as dt_module
import requests
import yfinance as yf
from dotenv import load_dotenv
from telegram import Bot
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

try:
    from icalendar import Calendar as iCal
    import recurring_ical_events
    ICAL_AVAILABLE = True
except ImportError:
    ICAL_AVAILABLE = False

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
GOOGLE_TASKS_CREDS = os.getenv("GOOGLE_TASKS_CREDENTIALS", "").strip()
IL_TZ = timezone(timedelta(hours=3))
SEP = "─" * 30
STOCKS = ["INTC", "TSLA", "MBLY", "ASPI", "TEVA", "GOOG", "QBTS", "AMZN", "GRAB", "SEPN", "NVO"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("deby")

def esc(text: str) -> str:
    return html.escape(str(text))

def _wind_text(speed_ms: float) -> str:
    kmh = speed_ms * 3.6
    if kmh < 10: return f"קלה ({kmh:.0f} קמ\"ש)"
    if kmh < 30: return f"בינונית ({kmh:.0f} קמ\"ש)"
    return f"חזקה ({kmh:.0f} קמ\"ש)"

def _visibility_text(vis_m: int) -> str:
    km = vis_m / 1000
    return f"מצוינת ({km:.0f} ק\"מ)" if km >= 10 else f"בינונית ({km:.1f} ק\"מ)"

# ── פונקציות AI (לבוש ואימון) ──────────────────────────────────────────────

def get_clothing_recommendation(current_temp: float, desc: str, is_lab_day: bool) -> str:
    try:
        prompt = f"מזג אוויר: {current_temp}°C, {desc}. יום מעבדה: {'כן' if is_lab_day else 'לא'}. המלץ על לוק ונעליים (במעבדה חובה סגורות/ספורט ומכנס ארוך). החזר בפורמט HTML: 👕 <b>לוק:</b>... 👟 <b>נעליים:</b>..."
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.6}
        res = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=10).json()
        return res['choices'][0]['message']['content'].strip()
    except: return "👕 <b>לוק:</b> נוח\n👟 <b>נעליים:</b> סניקרס"

def get_dynamic_exercise_time(lat: float, lon: float, calendar_text: str) -> str:
    try:
        om = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,uv_index&timezone=Asia/Jerusalem&forecast_days=1").json()
        h = om.get("hourly", {})
        weather_summary = " ".join([f"{h['time'][i][11:13]}:00-{h['temperature_2m'][i]}°C" for i in range(6, 21)])
        prompt = f"מזג אוויר: {weather_summary}\nלוז: {calendar_text}\nמצא חלון של 1.5 שעות לאימון (עדיפות לבוקר מ-06:00). החזר רק: 🎯 <b>השעה המנצחת:</b>... 💡 <b>טיפ:</b> לא לשכוח תוספים ומים!"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.6}
        res = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=10).json()
        return res['choices'][0]['message']['content'].strip()
    except: return "🎯 <b>אימון:</b> חפש חלון פנוי\n💡 <b>טיפ:</b> שתה מים!"

# ── שירותים (מזג אוויר, משימות, יומן) ────────────────────────────────────────

def get_weather(calendar_text: str) -> str:
    try:
        ow = requests.get(f"https://api.openweathermap.org/data/2.5/weather?q=Tel+Aviv,IL&appid={OPENWEATHER_KEY}&units=metric&lang=he").json()
        lat, lon = ow["coord"]["lat"], ow["coord"]["lon"]
        om = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,uv_index&timezone=Asia/Jerusalem").json()
        h = om["hourly"]
        
        times = [8, 13, 18]
        weather_rows = "\n".join([f"{t:02}:00 — {h['temperature_2m'][t]:.1f}°C | UV: {h['uv_index'][t]:.1f}" for t in times])
        
        sunrise = datetime.fromtimestamp(ow["sys"]["sunrise"], tz=IL_TZ).strftime("%H:%M")
        sunset = datetime.fromtimestamp(ow["sys"]["sunset"], tz=IL_TZ).strftime("%H:%M")
        
        is_lab = "מעבדה" in calendar_text
        return (f"🌡️ <b>מזג אוויר — תל אביב</b>\n{weather_rows}\n"
                f"💧 לחות: {ow['main']['humidity']}% | 💨 רוח: {_wind_text(ow['wind']['speed'])} | 👁️ ראות: {_visibility_text(ow.get('visibility', 10000))}\n"
                f"🌅 זריחה: {sunrise} | 🌇 שקיעה: {sunset}\n\n"
                f"👔 <b>לבוש להיום:</b>\n{get_clothing_recommendation(ow['main']['temp'], ow['weather'][0]['description'], is_lab)}\n\n"
                f"🏃 <b>המלצת המאמן:</b>\n{get_dynamic_exercise_time(lat, lon, calendar_text)}")
    except: return "🌡️ שגיאה במזג האוויר"

def get_stocks() -> str:
    alerts = []
    for ticker in STOCKS:
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            prev, curr = hist["Close"].iloc[0], hist["Close"].iloc[-1]
            pct = ((curr - prev) / prev) * 100
            if abs(pct) >= 5: alerts.append(f"{'📈' if pct > 0 else '📉'} <b>{ticker}</b>: {pct:+.1f}% → ${curr:.2f}")
        except: continue
    return "📊 <b>מניות (>5%):</b>\n" + ("\n".join(alerts) if alerts else "השוק שקט. 😴")

def get_real_google_tasks() -> str:
    try:
        info = json.loads(GOOGLE_TASKS_CREDS)
        creds = OAuthCredentials(token=None, refresh_token=info.get("refresh_token"), client_id=info.get("client_id"), client_secret=info.get("client_secret"), token_uri="https://oauth2.googleapis.com/token")
        creds.refresh(Request())
        service = build("tasks", "v1", credentials=creds)
        items = service.tasks().list(tasklist='@default', showCompleted=False).execute().get('items', [])
        today_str = datetime.now(IL_TZ).strftime("%Y-%m-%d")
        lines = [f"✅ {esc(t['title'])}" for t in items if not t.get('due') or today_str in t.get('due')]
        return "📋 <b>משימות להיום:</b>\n" + "\n".join(lines) if lines else ""
    except: return ""

def get_calendar() -> str:
    if not ICAL_AVAILABLE: return ""
    today = datetime.now(IL_TZ).date()
    events = []
    for url in [os.getenv(f"GOOGLE_CALENDAR_ICS_{i}", "") for i in range(1, 5)] + [os.getenv("DEFAULT_ICS", "")]:
        if not url: continue
        try:
            resp = requests.get(url, timeout=10)
            cal = iCal.from_ical(resp.content)
            for ev in recurring_ical_events.of(cal).at(today):
                start = ev.get("DTSTART").dt
                time_str = start.astimezone(IL_TZ).strftime("%H:%M") if isinstance(start, datetime) else "כל היום"
                events.append(f"🕐 <b>{time_str}</b> - {esc(ev.get('SUMMARY'))}")
        except: continue
    return "📅 <b>הלו\"ז שלך:</b>\n" + "\n".join(sorted(set(events))) if events else "📅 יום חופשי!"

# ── הרצה ──────────────────────────────────────────────────────────────────────

def build_message() -> str:
    cal = get_calendar()
    sections = [f"🌅 <b>בוקר טוב מאור!</b>\n<i>{datetime.now(IL_TZ).strftime('%d/%m/%Y')}</i>\n{SEP}", get_weather(cal), SEP, get_stocks(), SEP, get_real_google_tasks(), SEP, cal, f"{SEP}\n<i>בהצלחה היום אלוף! — דבי ✨</i>"]
    return "\n\n".join([s for s in sections if s.strip() and s != SEP])

async def main():
    bot = Bot(token=BOT_TOKEN)
    msg = build_message()
    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="HTML", disable_web_page_preview=True)

if __name__ == "__main__":
    asyncio.run(main())
