"""
דבי — בוט שגרת בוקר (הגרסה המלאה והמשופרת למאור)
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
    ICAL_AVAILABLE = True
except ImportError:
    ICAL_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    TRANSLATE_AVAILABLE = True
except ImportError:
    TRANSLATE_AVAILABLE = False

load_dotenv()

BOT_TOKEN           = os.getenv("BOT_TOKEN", "")
CHAT_ID             = os.getenv("CHAT_ID", "")
OPENWEATHER_KEY     = os.getenv("OPENWEATHER_API_KEY", "")

# הקישור הסודי של מאור מוגדר כברירת מחדל כדי להבטיח שהיומן יעבוד מיד
DEFAULT_ICS = "https://calendar.google.com/calendar/ical/maorfurman123%40gmail.com/private-b134fd273a4b42e3031d97b6af834849/basic.ics"

# כל לוחות השנה — ICS URLs
CALENDARS = [url for url in [
    os.getenv("GOOGLE_CALENDAR_ICS_1", DEFAULT_ICS),
    os.getenv("GOOGLE_CALENDAR_ICS_2", ""),
    os.getenv("GOOGLE_CALENDAR_ICS_3", ""),
    os.getenv("GOOGLE_CALENDAR_ICS_4", ""),
] if url.strip()]

STOCKS = [
    "INTC", "TSLA", "MBLY", "ASPI", "TEVA",
    "GOOG", "QBTS", "AMZN", "GRAB", "SEPN", "NVO",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("deby")
SEP = "──────────────────────────────"

IL_TZ = timezone(timedelta(hours=3))


# ── פונקציות עזר ───────────────────────────────────────────────────────────────

def esc(text: str) -> str:
    """בריחת תווים עבור HTML בטלגרם."""
    return html.escape(str(text))


def clean_html(raw_html: str) -> str:
    """ניקוי תגיות HTML מתוך טקסט (חשוב לתקצירי חדשות)."""
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


def get_clothing_advice(t_min: float, t_max: float) -> str:
    """המלצת לבוש מפורטת ומכתיבה כולל התייחסות להפרשי חום ונעליים."""
    if t_max > 28:
        return "👕 <b>מה לובשים:</b> חם היום. לך על מכנסיים קצרים, חולצת טי-שירט דקה ונעלי ספורט מאווררות או סנדלים. אל תתפתה לארוך, אתה תתחרט בצהריים."
    elif t_min < 15 and t_max > 24:
        return "👕 <b>מה לובשים:</b> שיטת השכבות היא חובה. בבוקר מכנסיים ארוכים דקים וסוודר קל/עליונית, אבל מתחת חולצה קצרה. בצהריים העליונית עפה. נעליים סגורות (סניקרס) יתאימו לכל היום."
    elif t_max < 17:
        return "🧥 <b>מה לובשים:</b> יום קר. מכנסיים ארוכים עבים, חולצה ארוכה ומעיל מעל. נעליים סגורות וגרביים גבוהות. אל תתחכם עם קצר."
    else:
        return "👕 <b>מה לובשים:</b> מזג אוויר קלאסי ונוח. ג'ינס או מכנס בד ארוך, חולצה קצרה וסניקרס. אפשר לקחת ג'קט קל לערב."


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
                # תנאים לאימון: טמפ' מתחת ל-26 מעלות ו-UV נמוך מ-4
                if temp <= 26 and uv < 4 and (5 <= hour <= 22):
                    good_hours.append(hour)
        
        if not good_hours:
            return "🏃 <b>שעות אימון:</b> חם מדי או קרינה חזקה היום. עדיף להתאמן במזגן 🧊"
        
        # חיבור שעות רצופות לטווחים קריאים
        ranges = []
        start = good_hours[0]
        for j in range(1, len(good_hours)):
            if good_hours[j] != good_hours[j-1] + 1:
                ranges.append(f"{start:02d}:00-{good_hours[j-1]:02d}:00")
                start = good_hours[j]
        ranges.append(f"{start:02d}:00-{(good_hours[-1]+1):02d}:00")
        
        return f"🏃 <b>שעות אימון מומלצות היום:</b> {', '.join(ranges)}"
    except Exception as ex:
        logger.error("Exercise calc error: %s", ex)
        return "🏃 <b>שעות אימון:</b> בוקר מוקדם או ערב מאוחר (תקלת רשת קלה)."


def get_weather() -> str:
    if not OPENWEATHER_KEY:
        return "🌡️ <b>מזג אוויר</b> — מפתח API חסר"
    try:
        ow = requests.get(
            "https://api.openweathermap.org/data/2.5/weather"
            f"?q=Tel+Aviv,IL&appid={OPENWEATHER_KEY}&units=metric&lang=he",
            timeout=10,
        ).json()
        if ow.get("cod") != 200:
            return f"🌡️ <b>מזג אוויר</b> — שגיאה: {esc(str(ow.get('message', '')))}"

        lat         = ow["coord"]["lat"]
        lon         = ow["coord"]["lon"]
        temp        = ow["main"]["temp"]
        feels       = ow["main"]["feels_like"]
        desc        = esc(ow["weather"][0]["description"])
        humidity    = ow["main"]["humidity"]
        wind_ms     = ow["wind"]["speed"]
        visibility  = ow.get("visibility", 10000)
        sunrise_ts  = ow["sys"]["sunrise"]
        sunset_ts   = ow["sys"]["sunset"]

        # משיכת נתונים יומיים מדויקים מ-Open-Meteo
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

        avg_temp = (t_max + t_min) / 2
        sunrise_str = datetime.fromtimestamp(sunrise_ts, tz=IL_TZ).strftime("%H:%M")
        sunset_str  = datetime.fromtimestamp(sunset_ts,  tz=IL_TZ).strftime("%H:%M")

        clothes_advice = get_clothing_advice(t_min, t_max)
        exercise_time = get_dynamic_exercise_time(lat, lon)

        return (
            f"🌡️ <b>מזג אוויר — תל אביב</b>\n"
            f"טמפ' עכשיו: <b>{temp:.0f}°C</b> | ממוצעת יומית: <b>{avg_temp:.1f}°C</b>\n"
            f"טווח יומי: מקס' {t_max:.0f}° / מינ' {t_min:.0f}°\n"
            f"תחושה: {feels:.0f}°C | {desc}\n"
            f"לחות: {humidity}%\n"
            f"רוח: {_wind_text(wind_ms)}\n"
            f"נראות: {_visibility_text(visibility)}\n"
            f"אינדקס UV (שיא להיום): {_uv_text(uvi_max)}\n"
            f"זריחה: {sunrise_str} 🌅 | שקיעה: {sunset_str} 🌇\n\n"
            f"{clothes_advice}\n\n"
            f"{exercise_time}"
        )
    except Exception as ex:
        logger.error("Weather error: %s", ex)
        return "🌡️ <b>מזג אוויר</b> — שגיאה בטעינה 😅"


# ── חדשות נקיות ומסודרות ──────────────────────────────────────────────────────

GEO_FEEDS = [
    "https://feeds.reuters.com/reuters/topNews",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
]
AI_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
]
GEO_KW = ["israel", "iran", "hamas", "hezbollah", "gaza", "middle east", "trump", "netanyahu", "idf", "west bank", "war"]
AI_KW  = ["ai", "artificial intelligence", "openai", "chatgpt", "llm", "gpt", "claude", "gemini", "machine learning", "nvidia"]


def fetch_news_section(feeds, keywords, title_label, n=5):
    """מושך חדשות, מתרגם ומסדר בצורה נקייה עם לינק ומקור."""
    res = [f"<b>{title_label}</b>"]
    count = 0
    dramatic_prefixes = ["🚨", "🔥", "💥", "⚠️", "⚡", "😱"]
    
    for url in feeds:
        try:
            f = feedparser.parse(url)
            # חילוץ שם האתר מהקישור כדי להציג כמקור
            source = urlparse(url).netloc.replace("www.", "").split('.')[0].capitalize()
            
            for entry in f.entries:
                if any(k.lower() in entry.title.lower() for k in keywords):
                    t_title = translate(entry.title)
                    summary_raw = clean_html(entry.get("summary", "")).split('.')[0]
                    t_summary = translate(summary_raw[:100])
                    prefix = random.choice(dramatic_prefixes)
                    
                    # הוספת הפריט למערך התוצאות
                    res.append(
                        f"• {prefix} <a href='{entry.link}'>{esc(t_title)}</a>\n"
                        f"  <i>\"{esc(t_summary)}...\" ({source})</i>"
                    )
                    count += 1
                    if count >= n: 
                        return "\n\n".join(res)
        except Exception: 
            continue
            
    return "\n\n".join(res) if len(res) > 1 else f"<b>{title_label}</b>\nאין עדכונים חריגים הבוקר."


def get_news() -> str:
    geo = fetch_news_section(GEO_FEEDS, GEO_KW, "🌍 אקטואליה פוליטית", 5)
    ai = fetch_news_section(AI_FEEDS, AI_KW, "🤖 חזית ה-AI", 5)
    
    return f"{geo}\n\n{ai}"


# ── מניות ──────────────────────────────────────────────────────────────────────

def get_stocks() -> str:
    alerts, no_data = [], []
    for ticker in STOCKS:
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if len(hist) < 2:
                no_data.append(ticker)
                continue
            prev, curr = hist["Close"].iloc[-2], hist["Close"].iloc[-1]
            pct = ((curr - prev) / prev) * 100
            if abs(pct) >= 5:
                icon = "📈" if pct > 0 else "📉"
                rec  = yf.Ticker(ticker).info.get("recommend
