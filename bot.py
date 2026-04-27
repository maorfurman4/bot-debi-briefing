#!/usr/bin/env python3
"""
דבי — בוט שגרת בוקר
"""

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

BOT_TOKEN           = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "").strip()
CHAT_ID             = os.getenv("CHAT_ID", "").strip()
OPENWEATHER_KEY     = os.getenv("OPENWEATHER_API_KEY", "").strip()
GOOGLE_TASKS_CREDS  = os.getenv("GOOGLE_TASKS_CREDENTIALS", "").strip()

DEFAULT_ICS = "https://calendar.google.com/calendar/ical/maorfurman123%40gmail.com/private-b134fd273a4b42e3031d97b6af834849/basic.ics"

CALENDARS = [url for url in [
    os.getenv("GOOGLE_CALENDAR_ICS_1", DEFAULT_ICS),
    os.getenv("GOOGLE_CALENDAR_ICS_2", ""),
    os.getenv("GOOGLE_CALENDAR_ICS_3", ""),
    os.getenv("GOOGLE_CALENDAR_ICS_4", ""),
] if url and url.strip()]

STOCKS = [
    "INTC", "TSLA", "MBLY", "ASPI", "TEVA",
    "GOOG", "QBTS", "AMZN", "GRAB", "SEPN", "NVO",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("deby")
SEP = "─" * 30

IL_TZ = timezone(timedelta(hours=3))

def esc(text: str) -> str:
    return html.escape(str(text))

# ── Google Tasks API ─────────────────────────────────────────────────────────

def _get_google_tasks_service():
    if not GOOGLE_TASKS_CREDS:
        return None
    try:
        creds_info = json.loads(GOOGLE_TASKS_CREDS)
        creds = OAuthCredentials(
            token=None,
            refresh_token=creds_info.get("refresh_token"),
            client_id=creds_info.get("client_id"),
            client_secret=creds_info.get("client_secret"),
            token_uri=creds_info.get("token_uri", "https://oauth2.googleapis.com/token"),
            scopes=["https://www.googleapis.com/auth/tasks.readonly"]
        )
        creds.refresh(Request())
        return build("tasks", "v1", credentials=creds)
    except Exception as e:
        logger.error(f"Failed to load Google Tasks: {e}")
        return None

def get_real_google_tasks() -> str:
    service = _get_google_tasks_service()
    if not service:
        return "📋 <b>משימות:</b> תקלת התחברות ל-API. חסר שירות."
    try:
        results = service.tasks().list(tasklist='@default', showCompleted=False).execute()
        items = results.get('items', [])
        
        if not items:
            return "📋 <b>משימות:</b> הכל נקי! אין לך משימות פתוחות. 🎉"

        # למטרת בדיקה - מדפיסים את *כל* המשימות בלי לסנן תאריך
        task_lines = []
        for task in items:
            title = esc(task.get('title', '(ללא כותרת)'))
            due = task.get('due', 'ללא תאריך')
            # הוספתי הדפסה של ה-due כדי שנראה איך גוגל שולח אותו
            task_lines.append(f"✅ {title} (תאריך יעד מ-API: {due})")

        return "📋 <b>כל המשימות הפתוחות שלך (בדיקה):</b>\n" + "\n".join(task_lines)
    except Exception as e:
        logger.error(f"Tasks Fetch Error: {e}")
        return f"📋 <b>משימות:</b> שגיאה בשליפה. קוד שגיאה: {e}"

# ── מזג אוויר ואימון דינמי ────────────────────────────────────────────────────

def _wind_text(speed_ms: float) -> str:
    kmh = speed_ms * 3.6
    if kmh < 10:  return f"רוח קלה ({kmh:.0f} קמ\"ש)"
    if kmh < 20:  return f"רוח עדינה ({kmh:.0f} קמ\"ש)"
    if kmh < 35:  return f"רוח בינונית ({kmh:.0f} קמ\"ש)"
    return f"רוח חזקה ({kmh:.0f} קמ\"ש)"

def _visibility_text(vis_m: int) -> str:
    km = vis_m / 1000
    if km >= 10:  return f"מצוינת ({km:.0f} ק\"מ)"
    if km >= 5:   return f"טובה ({km:.1f} ק\"מ)"
    return f"בינונית ({km:.1f} ק\"מ)"

def get_dynamic_exercise_time(lat: float, lon: float, calendar_text: str) -> str:
    try:
        om = requests.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,uv_index&timezone=Asia/Jerusalem&forecast_days=1",
            timeout=8,
        ).json()
        
        h = om.get("hourly", {})
        weather_summary = " ".join([f"{h['time'][i][11:13]}:00-{h['temperature_2m'][i]}°C" for i in range(5, 20)])

        prompt = f"""
        אתה מאמן כושר. מזג אוויר שעתי: {weather_summary}
        לו"ז המתאמן להיום:
        {calendar_text}
        
        מצא חלון פנוי של שעה וחצי לאימון, החל מ-06:00 בבוקר. אם יש זמן פנוי בבוקר המוקדם, תן לו עדיפות עליונה.
        החזר בדיוק בפורמט הבא, ללא הסברים נוספים:
        🎯 <b>השעה המנצחת לאימון:</b> [השעות, למשל 06:30 עד 08:00]
        💡 <b>טיפ של אלופים:</b> אל תשכח לקחת תוספי תזונה ולשתות מים!
        """
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.6}
        
        response = requests.post(url, json=payload, headers=headers, timeout=10).json()
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"AI Exercise error: {e}")
        return "🎯 <b>השעה המנצחת לאימון:</b> חפש חלון פנוי ביומן\n💡 <b>טיפ של אלופים:</b> לא לשכוח תוספים ומים!"

def get_clothing_recommendation(current_temp: float, desc: str, is_lab_day: bool) -> str:
    try:
        prompt = f"""
        אתה סטייליסט. מזג האוויר בבוקר: {current_temp:.1f}°C, שמיים: {desc}.
        האם היום יש מעבדה (חובה מכנסיים ארוכים ונעליים סגורות/ספורט)? {'כן' if is_lab_day else 'לא'}
        
        החזר בדיוק בפורמט הבא, ללא הסברים:
        👕 <b>הלוק המומלץ:</b> [פירוט הלוק]
        👟 <b>נעליים:</b> [סוג נעליים. אם יום מעבדה, חובה להמליץ על נעלי ספורט/סגורות]
        """
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.6}
        
        response = requests.post(url, json=payload, headers=headers, timeout=10).json()
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"AI Clothing error: {e}")
        return "👕 <b>הלוק המומלץ:</b> בגדים נוחים\n👟 <b>נעליים:</b> סניקרס"

def get_weather(calendar_text: str) -> str:
    if not OPENWEATHER_KEY:
        return "🌡️ מפתח חסר"
    try:
        ow = requests.get(f"https://api.openweathermap.org/data/2.5/weather?q=Tel+Aviv,IL&appid={OPENWEATHER_KEY}&units=metric&lang=he").json()
        lat, lon = ow["coord"]["lat"], ow["coord"]["lon"]
        
        om = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,uv_index&timezone=Asia/Jerusalem").json()
        h = om["hourly"]
        
        t_8, t_13, t_18 = h["temperature_2m"][8], h["temperature_2m"][13], h["temperature_2m"][18]
        uv_8, uv_13, uv_18 = h["uv_index"][8], h["uv_index"][13], h["uv_index"][18]
        
        desc = esc(ow["weather"][0]["description"])
        humidity = ow["main"]["humidity"]
        wind_ms = ow["wind"]["speed"]
        visibility = ow.get("visibility", 10000)
        
        sunrise_str = datetime.fromtimestamp(ow["sys"]["sunrise"], tz=IL_TZ).strftime("%H:%M")
        sunset_str = datetime.fromtimestamp(ow["sys"]["sunset"], tz=IL_TZ).strftime("%H:%M")

        is_lab_day = "מעבדה" in calendar_text
        clothes = get_clothing_recommendation(ow["main"]["temp"], desc, is_lab_day)
        exercise_text = get_dynamic_exercise_time(lat, lon, calendar_text)

        return (
            f"🌡️ <b>מזג אוויר — תל אביב</b>\n"
            f"08:00 — {t_8:.1f}°C | UV: {uv_8:.1f}\n"
            f"13:00 — {t_13:.1f}°C | UV: {uv_13:.1f}\n"
            f"18:00 — {t_18:.1f}°C | UV: {uv_18:.1f}\n"
            f"💧 לחות: {humidity}% | 💨 רוח: {_wind_text(wind_ms)} | 👁️ ראות: {_visibility_text(visibility)}\n"
            f"🌅 זריחה: {sunrise_str} | 🌇 שקיעה: {sunset_str}\n\n"
            f"{clothes}\n\n"
            f"🏃 <b>המלצת המאמן להיום:</b>\n{exercise_text}"
        )
    except Exception as ex:
        logger.error("Weather error: %s", ex)
        return "🌡️ <b>מזג אוויר</b> — שגיאה בטעינה 😅"

# ── מניות ──────────────────────────────────────────────────────────────────────

def get_stocks() -> str:
    alerts, no_data = [], []
    for ticker in STOCKS:
        try:
            hist = yf.Ticker(ticker).history(period="2d", prepost=True)
            if len(hist) < 2:
                no_data.append(ticker)
                continue
            prev, curr = hist["Close"].iloc[0], hist["Close"].iloc[-1]
            pct = ((curr - prev) / prev) * 100
            
            if abs(pct) >= 5:
                icon = "📈" if pct > 0 else "📉"
                alerts.append(f"{icon} <b>{ticker}</b>: {pct:+.1f}% → ${curr:.2f}")
        except Exception:
            no_data.append(ticker)

    lines = ["📊 <b>מניות (תנועות מעל 5%)</b>"]
    if alerts:
        lines.extend(alerts)
    else:
        lines.append("השוק שקט למדי, אין דרמות משמעותיות (>5%). 😴")
    return "\n".join(lines)

# ── Google Calendar ────────────────────────────────────────────────────────────

def _parse_ics(url: str, target_date) -> list:
    events = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        cal = iCal.from_ical(resp.content)
        events_on_date = recurring_ical_events.of(cal).at(target_date)

        for event in events_on_date:
            summary = esc(str(event.get("SUMMARY", "(ללא שם)")))
            start_dt = event.get("DTSTART").dt

            if isinstance(start_dt, dt_module.datetime):
                if start_dt.tzinfo is None: 
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                t_start = start_dt.astimezone(IL_TZ).strftime("%H:%M")
                
                end_prop = event.get("DTEND")
                if end_prop and isinstance(end_prop.dt, dt_module.datetime):
                    end_dt = end_prop.dt
                    if end_dt.tzinfo is None: 
                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                    t_end = end_dt.astimezone(IL_TZ).strftime("%H:%M")
                    t_range = f"{t_start}-{t_end}"
                else:
                    t_range = t_start
                
                events.append((t_start, f"🕐 <b>{t_range}</b> - {summary}"))
            else:
                if not summary.startswith("📌"):
                    events.append(("00:00", f"📌 <b>כל היום</b> - {summary}"))

    except Exception as ex:
        logger.warning(f"ICS fetch error from {url}: {ex}")
    return events

def get_calendar() -> str:
    if not CALENDARS or not ICAL_AVAILABLE:
        return ""
    
    today = datetime.now(IL_TZ).date()
    all_ev = []
    
    for url in CALENDARS:
        all_ev.extend(_parse_ics(url, today))
    
    seen = set()
    unique_sorted_events = []
    
    for time_key, display_text in sorted(all_ev, key=lambda x: x[0]):
        if display_text not in seen:
            seen.add(display_text)
            unique_sorted_events.append(display_text)
            
    if not unique_sorted_events:
        return "📅 <b>יומן:</b> אין אירועים מתוזמנים להיום. 🎉"
    
    return "📅 <b>הלו\"ז שלך להיום:</b>\n" + "\n".join(unique_sorted_events)

# ── פתיחים ומעברים ────────────────────────────────────────────────────────────

def get_witty_greeting() -> str:
    greetings = [
        "בוקר אור מאור! השמש זרחה והעולם מחכה שתכבוש אותו.",
        "קום מאור! אל תדאג, אני כבר סרקתי הכל בשבילך בזמן שישנת.",
        "עוד יום, עוד הזדמנות לשבור שיאים. קדימה מאור!",
        "בוקר טוב בוס. דבי כאן מציג לך את היום.",
        "  בוקר טוב! מקווה שישנת טוב יאח ,סידרתי לך תיום כבר."
    ]
    return random.choice(greetings)

# ── בניית ההודעה ──────────────────────────────────────────────────────────────

def build_message() -> str:
    now      = datetime.now(IL_TZ)
    days_he  = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    date_str = now.strftime(f"יום {days_he[now.weekday()]}, %d/%m/%Y")

    calendar_data = get_calendar()

    sections = [
        f"🌅 <b>{get_witty_greeting()}</b> 😄\n<i>{date_str}</i>\n{SEP}",
        get_weather(calendar_data), SEP,
        get_stocks(),  SEP,
    ]
    
    # תמיד מדפיסים את המשימות עכשיו, אפילו אם הן "ריקות", כדי לזהות את הבעיה
    tasks = get_real_google_tasks()
    sections.append(tasks)
    sections.append(SEP)
    
    sections.append(calendar_data)
    sections.append(f"{SEP}\n<i>שיהיה יום מעולה גבר! — דבי ✨</i>")
    
    return "\n\n".join([s for s in sections if s.strip()])
# ── שליחה ──────────────────────────────────────────────────────────────────────

async def main():
    bot = Bot(token=BOT_TOKEN)
    msg = build_message()

    if len(msg) <= 4000:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="HTML", disable_web_page_preview=True)
    else:
        for section in msg.split(SEP):
            if section.strip():
                await bot.send_message(
                    chat_id=CHAT_ID, text=f"{section.strip()}\n{SEP}", parse_mode="HTML", disable_web_page_preview=True
                )
    logger.info("Done!")

if __name__ == "__main__":
    asyncio.run(main())
