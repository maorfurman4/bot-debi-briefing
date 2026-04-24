#!/usr/bin/env python3
"""
דבי — בוט שגרת בוקר
מריצה פעם אחת, שולחת את התדריך, ויוצאת.
מופעלת אוטומטית כל יום ע"י GitHub Actions.
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
from urllib.parse import urlparse

import feedparser
import requests
import yfinance as yf
from dotenv import load_dotenv
from telegram import Bot

# ספריות Google API
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

try:
    from icalendar import Calendar as iCal
    import recurring_ical_events
    ICAL_AVAILABLE = True
except ImportError:
    ICAL_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    TRANSLATE_AVAILABLE = True
except ImportError:
    TRANSLATE_AVAILABLE = False

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

def clean_html(raw_html: str) -> str:
    return re.sub(r'<[^>]+>', '', raw_html) if raw_html else ""

def translate(text: str) -> str:
    if not TRANSLATE_AVAILABLE or not text:
        return text
    try:
        result = GoogleTranslator(source="auto", target="iw").translate(text[:500])
        return result or text
    except Exception:
        return text

# ── Google Tasks API ─────────────────────────────────────────────────────────

def _get_google_tasks_service():
    if not GOOGLE_TASKS_CREDS:
        logger.warning("GOOGLE_TASKS_CREDENTIALS is missing.")
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
        return ""
    
    try:
        results = service.tasks().list(tasklist='@default', showCompleted=False).execute()
        items = results.get('items', [])
        
        if not items:
            return "📋 <b>משימות:</b> הכל נקי! אין לך משימות פתוחות. 🎉"

        today_str = datetime.now(IL_TZ).strftime("%Y-%m-%d")
        today_tasks = []
        no_date_tasks = []

        for task in items:
            title = task.get('title', '(ללא כותרת)')
            due = task.get('due')
            
            if due and today_str in due:
                today_tasks.append(f"  ✅ {esc(title)}")
            elif not due:
                no_date_tasks.append(f"  🔹 {esc(title)}")

        lines = ["📋 <b>משימות מ-Google Tasks:</b>"]
        if today_tasks:
            lines.append("<b>משימות להיום:</b>")
            lines.extend(today_tasks)
        
        if no_date_tasks:
            if today_tasks: lines.append("") 
            lines.append("<b>משימות כלליות:</b>")
            lines.extend(no_date_tasks[:5]) # נציג רק עד 5 כדי לא להציף את ההודעה
            
        return "\n".join(lines) if (today_tasks or no_date_tasks) else ""
    except Exception as e:
        logger.error(f"Error fetching Google Tasks: {e}")
        return "📋 <b>משימות:</b> תקלת התחברות ל-Google Tasks."

# ── מזג אוויר ואימון דינמי ────────────────────────────────────────────────────

def _wind_text(speed_ms: float) -> str:
    kmh = speed_ms * 3.6
    if kmh < 2:   return f"שקט ({kmh:.0f} קמ\"ש)"
    if kmh < 10:  return f"רוח קלה ({kmh:.0f} קמ\"ש)"
    if kmh < 20:  return f"רוח עדינה ({kmh:.0f} קמ\"ש)"
    if kmh < 35:  return f"רוח בינונית ({kmh:.0f} קמ\"ש)"
    if kmh < 55:  return f"רוח חזקה ({kmh:.0f} קמ\"ש)"
    return f"רוח סוערת! ({kmh:.0f} קמ\"ש)"

def _uv_text(uvi: float) -> str:
    if uvi < 3:   return f"{uvi:.0f} — נמוך 🟢"
    if uvi < 6:   return f"{uvi:.0f} — בינוני 🟡"
    if uvi < 8:   return f"{uvi:.0f} — גבוה 🟠"
    if uvi < 11:  return f"{uvi:.0f} — גבוה מאוד 🔴"
    return f"{uvi:.0f} — קיצוני ☢️"

def _visibility_text(vis_m: int) -> str:
    km = vis_m / 1000
    if km >= 10:  return f"מצוינת ({km:.0f} ק\"מ)"
    if km >= 5:   return f"טובה ({km:.1f} ק\"מ)"
    if km >= 2:   return f"בינונית ({km:.1f} ק\"מ)"
    return f"ירודה ({km:.1f} ק\"מ) ⚠️"

def get_dynamic_exercise_time(lat: float, lon: float) -> str:
    try:
        om = requests.get(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,uv_index&timezone=Asia/Jerusalem",
            timeout=8,
        ).json()
        
        hourly = om.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        uvs = hourly.get("uv_index", [])
        
        today_str = datetime.now(IL_TZ).strftime("%Y-%m-%d")
        good_hours = []
        
        for i, t_str in enumerate(times):
            if t_str.startswith(today_str):
                hour = int(t_str[11:13])
                temp = temps[i]
                uv = uvs[i]
                if temp <= 26 and uv < 4 and (5 <= hour <= 22):
                    good_hours.append(hour)
        
        if not good_hours:
            return "🏃 <b>זמן אימון:</b> חם מדי או קרינה חזקה היום. עדיף במזגן 🧊"
        
        ranges = []
        start = good_hours[0]
        for j in range(1, len(good_hours)):
            if good_hours[j] != good_hours[j-1] + 1:
                ranges.append(f"{start:02d}:00-{good_hours[j-1]:02d}:00")
                start = good_hours[j]
        ranges.append(f"{start:02d}:00-{(good_hours[-1]+1):02d}:00")
        
        return f"🏃 <b>שעות אימון מומלצות היום:</b> {', '.join(ranges)}"
    except Exception:
        return "🏃 <b>זמן אימון:</b> בוקר מוקדם או ערב מאוחר."

def get_clothing_recommendation(t_min: float, t_max: float) -> str:
    if t_min < 15 and t_max > 24:
        return "👕 <b>שיטת השכבות היא חובה:</b> בוקר קריר דורש עליונית, אבל מתחת חולצה קצרה. מכנסיים ארוכים קלילים ונעליים סגורות יהיו הכי נוחות להבדלי הטמפרטורה."
    elif t_max <= 17:
        return "🧥 <b>יום חורפי:</b> חולצה ארוכה, מעיל, מכנסיים ארוכים עבים ונעליים סגורות או מגפיים."
    elif t_max > 28:
        return "🩳 <b>קיץ לוהט:</b> קצר וקליל ככל האפשר! מכנסיים קצרים, סנדלים או נעלי ספורט מאווררות."
    elif t_min >= 18 and t_max <= 28:
        return "👕 <b>נעים וקליל:</b> חולצה קצרה, מכנסיים ארוכים דקים או קצרים, וסניקרס נוחות."
    else:
        return "👖 <b>סתיו/אביב קלאסי:</b> חולצה קצרה עם ג'קט קל לבוקר/ערב, ג'ינס נוחים ונעליים סגורות."

def get_weather() -> str:
    if not OPENWEATHER_KEY:
        return "🌡️ <b>מזג אוויר</b> — מפתח API חסר"
    try:
        ow = requests.get(
            "https://api.openweathermap.org/data/2.5/weather"
            f"?q=Tel+Aviv,IL&appid={OPENWEATHER_KEY}&units=metric&lang=he",
            timeout=10,
        ).json()
        
        lat = ow["coord"]["lat"]
        lon = ow["coord"]["lon"]
        
        t_max, t_min, uvi_max = 0.0, 0.0, 0.0
        try:
            om_daily = requests.get(
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&daily=temperature_2m_max,temperature_2m_min,uv_index_max&timezone=Asia/Jerusalem",
                timeout=8,
            ).json()
            t_max = om_daily["daily"]["temperature_2m_max"][0]
            t_min = om_daily["daily"]["temperature_2m_min"][0]
            uvi_max = om_daily["daily"]["uv_index_max"][0]
        except Exception:
            t_max, t_min = ow["main"]["temp_max"], ow["main"]["temp_min"]

        temp        = ow["main"]["temp"]
        feels       = ow["main"]["feels_like"]
        desc        = esc(ow["weather"][0]["description"])
        humidity    = ow["main"]["humidity"]
        wind_ms     = ow["wind"]["speed"]
        visibility  = ow.get("visibility", 10000)
        sunrise_ts  = ow["sys"]["sunrise"]
        sunset_ts   = ow["sys"]["sunset"]
        avg_temp    = (t_max + t_min) / 2

        sunrise_str = datetime.fromtimestamp(sunrise_ts, tz=IL_TZ).strftime("%H:%M")
        sunset_str  = datetime.fromtimestamp(sunset_ts,  tz=IL_TZ).strftime("%H:%M")

        clothes = get_clothing_recommendation(t_min, t_max)
        exercise_text = get_dynamic_exercise_time(lat, lon)

        return (
            f"🌡️ <b>מזג אוויר — תל אביב</b>\n"
            f"טמפ' עכשיו: <b>{temp:.0f}°C</b> | ממוצעת יומית: <b>{avg_temp:.1f}°C</b>\n"
            f"טווח יומי אמיתי: מקס' {t_max:.0f}° / מינ' {t_min:.0f}°\n"
            f"תחושה: {feels:.0f}°C | {desc}\n"
            f"לחות: {humidity}%\n"
            f"רוח: {_wind_text(wind_ms)}\n"
            f"נראות: {_visibility_text(visibility)}\n"
            f"אינדקס UV (שיא להיום): {_uv_text(uvi_max)}\n"
            f"זריחה: {sunrise_str} 🌅 | שקיעה: {sunset_str} 🌇\n\n"
            f"👔 <b>לבוש להיום:</b>\n{clothes}\n\n"
            f"{exercise_text}"
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
                if start_dt.tzinfo is None: start_dt = start_dt.replace(tzinfo=timezone.utc)
                t_start = start_dt.astimezone(IL_TZ).strftime("%H:%M")
                end_prop = event.get("DTEND")
                if end_prop and isinstance(end_prop.dt, dt_module.datetime):
                    end_dt = end_prop.dt
                    if end_dt.tzinfo is None: end_dt = end_dt.replace(tzinfo=timezone.utc)
                    t_end = end_dt.astimezone(IL_TZ).strftime("%H:%M")
                    t_range = f"{t_start}-{t_end}"
                else:
                    t_range = t_start
                events.append((t_start, f"  🕐 {t_range} — {summary}", "timed"))
            else:
                if not summary.startswith("📌"): 
                    events.append(("00:00", f"  📌 {summary} (כל היום)", "allday"))

    except Exception as ex:
        logger.warning("ICS fetch error: %s", ex)
    return events

def summarize_calendar_with_openai(events: list) -> str:
    if not events:
        return "שממה ביומן! נצל את הזמן למנוחה או לפיתוח. 🎉"
    
    prompt = f"אתה העוזרת האישית דבי. סכמי למאור את הלוז היומי שלו מתוך אירועי היומן בלבד בצורה זורמת, נעימה ומסודרת. צייני את הזמנים. אירועים:\n\n{chr(10).join(events)}"
    
    if not OPENAI_API_KEY:
        return "📅 <b>היומן של מאור להיום:</b>\n" + "\n".join(events)

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }
    try:
        resp = requests.post(url, json=payload, headers=headers).json()
        if "error" in resp:
            return "📅 <b>היומן של מאור להיום:</b>\n" + "\n".join(events)
        return "📅 <b>הלוז שלך מתוך היומן להיום:</b>\n" + resp['choices'][0]['message']['content']
    except Exception:
        return "📅 <b>היומן של מאור להיום:</b>\n" + "\n".join(events)

def get_calendar() -> str:
    if not CALENDARS or not ICAL_AVAILABLE:
        return ""
    today = datetime.now(IL_TZ).date()
    all_ev = []
    for url in CALENDARS:
        all_ev.extend(_parse_ics(url, today))
    seen, unique = set(), []
    for item in sorted(all_ev, key=lambda x: x[0]):
        if item[1] not in seen:
            seen.add(item[1])
            unique.append(item)
            
    calendar_items = [text for _, text, kind in unique if kind in ("timed", "allday")]
    if not calendar_items: return "📅 <b>יומן:</b> היום שלך פנוי לחלוטין מאירועים מתוזמנים."
    return summarize_calendar_with_openai(calendar_items)

# ── פתיחים ומעברים ────────────────────────────────────────────────────────────

def get_witty_greeting() -> str:
    greetings = [
        "בוקר אור מאור! השמש זרחה והעולם לא יכבוש את עצמו.",
        "קומו קומו מאור! אל תדאג, אני כבר סרקתי הכל בשבילך בזמן שישנת.",
        "עוד יום, עוד הזדמנות לשבור שיאים. קדימה מאור!",
        "בוקר טוב בוס. דבי כאן עם כל מה שאתה צריך כדי להתחיל את היום ברגל ימין.",
        "בוקר טוב! קח נשימה, התארגנתי על התדריך שיעשה לך סדר בבלגן."
    ]
    return random.choice(greetings)

def get_transition() -> str:
    transitions = [
        "בלי יותר מדי חפירות, בוא ניגש לעניינים...",
        "קפה ביד? יופי, יש לנו לא מעט דברים לעבור עליהם הבוקר.",
        "תמתח איברים, הנה מה שמחכה לנו היום בעולם האמיתי.",
        "יאללה, בוא נראה מה העולם תכנן לנו היום.",
        "מוכן לזה? הנה התקציר המלא שלך:"
    ]
    return random.choice(transitions)

# ── בניית ההודעה ──────────────────────────────────────────────────────────────

def build_message() -> str:
    now      = datetime.now(IL_TZ)
    days_he  = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    date_str = now.strftime(f"יום {days_he[now.weekday()]}, %d/%m/%Y")

    sections = [
        f"🌅 <b>{get_witty_greeting()}</b> 😄\n<i>{date_str}</i>\n{get_transition()}\n{SEP}",
        get_weather(), SEP,
        get_stocks(),  SEP,
        get_calendar(),
    ]
    
    # נוסיף את רשימת המשימות
    tasks = get_real_google_tasks()
    if tasks:
        sections += [SEP, tasks]
        
    sections.append(f"{SEP}\n<i>שיהיה יום מוצלח אלוף! — דבי ✨</i>")
    return "\n\n".join(sections)

# ── שליחה ──────────────────────────────────────────────────────────────────────

async def main():
    bot = Bot(token=BOT_TOKEN)
    msg = build_message()

    if len(msg) <= 4000:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="HTML", disable_web_page_preview=True)
    else:
        for section in msg.split(SEP):
            if section.strip():
                # הוספת קו מפריד חזרה כדי לשמור על עיצוב נקי גם בהודעות מפוצלות
                await bot.send_message(
                    chat_id=CHAT_ID, text=f"{section.strip()}\n{SEP}", parse_mode="HTML", disable_web_page_preview=True
                )
    logger.info("Done!")

if __name__ == "__main__":
    asyncio.run(main())
