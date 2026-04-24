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
        # שליפת נתונים שעתים ל-24 השעות הקרובות
        om = requests.get(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,uv_index,precipitation_probability,wind_speed_10m"
            f"&timezone=Asia/Jerusalem&forecast_days=1",
            timeout=8,
        ).json()
        
        hourly = om.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        uvs = hourly.get("uv_index", [])
        precip = hourly.get("precipitation_probability", [])
        
        # בניית מחרוזת נתונים תמציתית עבור ה-AI
        weather_data_summary = ""
        for i in range(5, 23): # נתמקד בשעות הערנות 05:00 עד 22:00
            weather_data_summary += f"{times[i][11:13]}:00 - {temps[i]}°C, UV:{uvs[i]}, גשם:{precip[i]}% | "

        # פנייה ל-OpenAI לניתוח חכם
        prompt = f"""
        אתה מאמן כושר אישי מקצועי. קיבלת תחזית מזג אוויר שעתית להיום בישראל:
        {weather_data_summary}
        
        נתח את הנתונים והמלץ על חלון הזמן האידיאלי לאימון חוץ (ריצה/הליכה/מתקנים). 
        תתייחס לטמפרטורה, עומס חום (UV) וסיכוי לגשם. 
        כתוב המלצה קצרה (2-3 משפטים), מניעה לפעולה, ושתהיה שונה בכל פעם (לא תבנית קבועה).
        השתמש באימוג'ים מתאימים. התחל ב: "🏃 המלצת המאמן להיום:"
        """

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8 # טמפרטורה גבוהה לגיוון בניסוח
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        result = response.json()
        return result['choices'][0]['message']['content'].strip()

    except Exception as e:
        logger.error(f"AI Exercise analysis error: {e}")
        return "🏃 <b>זמן אימון:</b> היום כדאי להקשיב לגוף ולמזג האוויר בחוץ."

def get_clothing_recommendation(t_min: float, t_max: float, current_temp: float, desc: str) -> str:
    try:
        prompt = f"""
        אתה סטייליסט אישי (ומעט הומוריסטי) למנהל שיוצא ליום עבודה. 
        קיבלת את נתוני מזג האוויר להיום:
        - טמפרטורה עכשיו בבוקר יציאה: {current_temp:.1f}°C
        - טווח יומי: בין {t_min:.1f}°C ל-{t_max:.1f}°C
        - תנאי שמיים: {desc}
        
        תן המלצת לבוש פרקטית להיום (2-3 משפטים). 
        * אם יש פער גדול בין הבוקר לצהריים, תדגיש את "שיטת השכבות". 
        * התייחס למצב השמיים (אם חם מאוד - בגדים נושמים/קצרים, אם גשום - מטרייה/מעיל).
        * השתמש באימוג'ים מתאימים לבגדים. גוון בניסוחים שלך כדי שזה לא יהיה משעמם!
        התחל במילים: "👔 המלצת הסטייליסט להיום:"
        """

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini", # שימוש במודל המהיר והזול מספיק למשימות כאלו
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8 # דואג שהניסוח יהיה שונה בכל בוקר
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        result = response.json()
        return result['choices'][0]['message']['content'].strip()

    except Exception as e:
        logger.error(f"AI Clothing analysis error: {e}")
        return "👔 <b>המלצת הסטייליסט:</b> נראה שיש לי תקלה במלתחה הבוקר, פשוט תלבש משהו נוח! 😅"
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

        clothes = get_clothing_recommendation(t_min, t_max, temp, desc)
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
    """מושך אירועים מקובץ ICS ומחזיר רשימה נקייה וממוינת"""
    events = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        cal = iCal.from_ical(resp.content)
        # שימוש בספרייה לטיפול באירועים חוזרים
        events_on_date = recurring_ical_events.of(cal).at(target_date)

        for event in events_on_date:
            summary = esc(str(event.get("SUMMARY", "(ללא שם)")))
            start_dt = event.get("DTSTART").dt

            # בדיקה אם זה אירוע עם שעה או אירוע של כל היום
            if isinstance(start_dt, dt_module.datetime):
                # המרה לאזור הזמן של ישראל
                if start_dt.tzinfo is None: 
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                
                t_start = start_dt.astimezone(IL_TZ).strftime("%H:%M")
                
                # חישוב שעת סיום אם קיימת
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
                # אירוע של כל היום (כמו חגים או ימי הולדת)
                # מסננים משימות שהתווספו אוטומטית עם 📌 כדי שלא תהיה כפילות
                if not summary.startswith("📌"):
                    events.append(("00:00", f"📌 <b>כל היום</b> - {summary}"))

    except Exception as ex:
        logger.warning(f"ICS fetch error from {url}: {ex}")
    return events

def get_calendar() -> str:
    """מרכזת את כל היומנים לרשימה אחת סופית ללא בינה מלאכותית"""
    if not CALENDARS or not ICAL_AVAILABLE:
        return ""
    
    today = datetime.now(IL_TZ).date()
    all_ev = []
    
    # איסוף מכל הכתובות שהוגדרו
    for url in CALENDARS:
        all_ev.extend(_parse_ics(url, today))
    
    # מיון לפי שעה ומניעת כפילויות
    seen = set()
    unique_sorted_events = []
    
    # מיון לפי שעת ההתחלה (האיבר הראשון בטאפל)
    for time_key, display_text in sorted(all_ev, key=lambda x: x[0]):
        if display_text not in seen:
            seen.add(display_text)
            unique_sorted_events.append(display_text)
            
    if not unique_sorted_events:
        return "📅 <b>יומן:</b> אין אירועים מתוזמנים להיום. 🎉"
    
    # החזרה של רשימה פשוטה ונקייה
    return "📅 <b>הלו\"ז שלך להיום:</b>\n" + "\n".join(unique_sorted_events)

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
def _get_google_tasks_service():
    """מתחברת ל-API של Google Tasks באמצעות ה-Secret מהגיטהאב"""
    creds_json = os.getenv("GOOGLE_TASKS_CREDENTIALS")
    if not creds_json:
        logger.warning("GOOGLE_TASKS_CREDENTIALS missing!")
        return None
    try:
        from google.oauth2.credentials import Credentials as OAuthCredentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build 
        
        info = json.loads(creds_json)
        creds = OAuthCredentials(
            token=None,
            refresh_token=info.get("refresh_token"),
            client_id=info.get("client_id"),
            client_secret=info.get("client_secret"),
            token_uri="https://oauth2.googleapis.com/token"
        )
        creds.refresh(Request())
        return build("tasks", "v1", credentials=creds)
    except Exception as e:
        logger.error(f"Tasks Auth Error: {e}")
        return None

def get_real_google_tasks() -> str:
    """שולפת משימות פתוחות להיום מ-Google Tasks"""
    service = _get_google_tasks_service()
    if not service:
        return ""
    
    try:
        # שליפת המשימות שלא הושלמו מהרשימה הראשית
        results = service.tasks().list(tasklist='@default', showCompleted=False).execute()
        items = results.get('items', [])
        
        if not items:
            return "📋 <b>משימות:</b> אין משימות פתוחות. תענוג! 🎉"

        today_str = datetime.now(IL_TZ).strftime("%Y-%m-%d")
        task_lines = []
        
        for task in items:
            title = esc(task.get('title', '(ללא כותרת)'))
            due = task.get('due') # תאריך יעד בפורמט RFC3339
            
            # אם אין תאריך יעד או שהתאריך הוא היום - נציג את המשימה
            if not due or today_str in due:
                task_lines.append(f"✅ {title}")

        if not task_lines:
            return "" # אם יש משימות אבל הן לא להיום, לא נציג סעיף ריק
            
        return "📋 <b>משימות להיום:</b>\n" + "\n".join(task_lines)
    except Exception as e:
        logger.error(f"Tasks Fetch Error: {e}")
        return "📋 <b>משימות:</b> תקלה בשליפת נתונים."



# ── בניית ההודעה ──────────────────────────────────────────────────────────────

def build_message() -> str:
    now      = datetime.now(IL_TZ)
    days_he  = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    date_str = now.strftime(f"יום {days_he[now.weekday()]}, %d/%m/%Y")

    # פתיח, מזג אוויר ומניות
    sections = [
        f"🌅 <b>{get_witty_greeting()}</b> 😄\n<i>{date_str}</i>\n{get_transition()}\n{SEP}",
        get_weather(), SEP,
        get_stocks(),  SEP,
    ]
    
    # משימות - קוראים לפונקציה רק פעם אחת ומכניסים אם יש תוכן
    tasks = get_real_google_tasks()
    if tasks and "אין משימות פתוחות" not in tasks:
        sections.append(tasks)
        sections.append(SEP)
    
    # יומן
    sections.append(get_calendar())
        
    sections.append(f"{SEP}\n<i>שיהיה יום מוצלח אלוף! — דבי ✨</i>")
    
    # סינון סעיפים ריקים וחיבור ברווח כפול
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
                # הוספת קו מפריד חזרה כדי לשמור על עיצוב נקי גם בהודעות מפוצלות
                await bot.send_message(
                    chat_id=CHAT_ID, text=f"{section.strip()}\n{SEP}", parse_mode="HTML", disable_web_page_preview=True
                )
    logger.info("Done!")

if __name__ == "__main__":
    asyncio.run(main())
