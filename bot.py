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
from datetime import datetime, timedelta, timezone
import datetime as dt_module
from urllib.parse import urlparse

import feedparser
import requests
import yfinance as yf
from dotenv import load_dotenv
from telegram import Bot

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

# הוספת .strip() מנקה אוטומטית רווחים נסתרים או שורות חדשות שהועתקו בטעות לגיטהאב
BOT_TOKEN           = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "").strip()
CHAT_ID             = os.getenv("CHAT_ID", "").strip()
OPENWEATHER_KEY     = os.getenv("OPENWEATHER_API_KEY", "").strip()

# הקישור הסודי שלך מובנה כאן כדי לפתור את בעיית השממה
DEFAULT_ICS = "https://calendar.google.com/calendar/ical/maorfurman123%40gmail.com/private-b134fd273a4b42e3031d97b6af834849/basic.ics"

# כל לוחות השנה — ICS URLs
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
    """תרגום לעברית — מחזיר את הטקסט המקורי אם נכשל."""
    if not TRANSLATE_AVAILABLE or not text:
        return text
    try:
        result = GoogleTranslator(source="auto", target="iw").translate(text[:500])
        return result or text
    except Exception:
        return text


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
    """מושך תחזית שעתית ומחשב שעות אידיאליות לאימון לפי חום וקרינה."""
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
    """ממליץ על לבוש מדויק ופרקטי כולל נעליים בהתאם להפרשי טמפרטורות."""
    if t_min < 15 and t_max > 24:
        return "👕 <b>שיטת השכבות היא חובה:</b> בוקר קריר דורש עליונית, אבל מתחת חולצה קצרה. מכנסיים ארוכים קלילים ונעליים סגורות יהיו הכי נוחות להבדלי הטמפרטורה."
    elif t_max <= 17:
        return "🧥 <b>יום חורפי:</b> חולצה ארוכה, מעיל, מכנסיים ארוכים עבים ונעליים סגורות או מגפיים. אל תתחכם עם קצר."
    elif t_max > 28:
        return "🩳 <b>קיץ לוהט:</b> קצר וקליל ככל האפשר! מכנסיים קצרים, סנדלים או נעלי ספורט מאווררות. אל תשכח כובע למשך היום."
    elif t_min >= 18 and t_max <= 28:
        return "👕 <b>נעים וקליל:</b> חולצה קצרה, מכנסיים ארוכים דקים או קצרים, וסניקרס נוחות. מזג אוויר אידיאלי."
    else:
        return "👖 <b>סתיו/אביב קלאסי:</b> חולצה קצרה עם ג'קט קל לבוקר/ערב, ג'ינס או מכנסי בד נוחים ונעליים סגורות רגילות."


def get_weather() -> str:
    if not OPENWEATHER_KEY:
        return "🌡️ <b>מזג אוויר</b> — מפתח API חסר"
    try:
        ow = requests.get(
            "https://api.openweathermap.org/data/2.5/weather"
            f"?q=Tel+Aviv,
