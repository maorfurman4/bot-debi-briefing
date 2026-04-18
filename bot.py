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

# כל לוחות השנה — ICS URLs
CALENDARS = [url for url in [
    os.getenv("GOOGLE_CALENDAR_ICS_1", os.getenv("GOOGLE_CALENDAR_ICS", "")),
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


def get_dynamic_exercise_time(lat: float, lon: float, default_temp: float) -> str:
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
                # תנאים לאימון נעים: טמפ' מתחת ל-26 מעלות ו-UV נמוך מ-4, בין 05:00 ל-22:00
                if temp <= 26 and uv < 4 and (5 <= hour <= 22):
                    good_hours.append(hour)
        
        if not good_hours:
            return "🏃 <b>זמן אימון מומלץ:</b> היום חם מדי או קרינה חזקה לאורך כל היום. מומלץ מזגן בלבד 🧊"
        
        # חיבור שעות רצופות לטווחים
        ranges = []
        start = good_hours[0]
        for j in range(1, len(good_hours)):
            if good_hours[j] != good_hours[j-1] + 1:
                ranges.append(f"{start:02d}:00-{good_hours[j-1]:02d}:00")
                start = good_hours[j]
        # סגירת הטווח האחרון
        ranges.append(f"{start:02d}:00-{(good_hours[-1]+1):02d}:00")
        
        return f"🏃 <b>שעות אימון מומלצות היום:</b> {', '.join(ranges)} (טמפ' מתחת ל-26°C וקרינה נמוכה) ✅"
    except Exception as ex:
        logger.error("Exercise calc error: %s", ex)
        return "🏃 <b>זמן אימון:</b> בוקר מוקדם או ערב מאוחר (שגיאה בחישוב מדויק)."


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

        temp        = ow["main"]["temp"]
        temp_max    = ow["main"]["temp_max"]
        temp_min    = ow["main"]["temp_min"]
        feels       = ow["main"]["feels_like"]
        desc        = esc(ow["weather"][0]["description"])
        humidity    = ow["main"]["humidity"]
        wind_ms     = ow["wind"]["speed"]
        visibility  = ow.get("visibility", 10000)
        lat         = ow["coord"]["lat"]
        lon         = ow["coord"]["lon"]
        sunrise_ts  = ow["sys"]["sunrise"]
        sunset_ts   = ow["sys"]["sunset"]
        rain        = "rain" in ow.get("weather", [{}])[0].get("main", "").lower()

        # ממוצע יומי
        avg_temp    = (temp_max + temp_min) / 2

        sunrise_str = datetime.fromtimestamp(sunrise_ts, tz=IL_TZ).strftime("%H:%M")
        sunset_str  = datetime.fromtimestamp(sunset_ts,  tz=IL_TZ).strftime("%H:%M")

        # שיא UV יומיומי מ-Open-Meteo
        uvi_max = 0.0
        try:
            om = requests.get(
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&daily=uv_index_max&timezone=Asia/Jerusalem",
                timeout=8,
            ).json()
            uvi_max = om.get("daily", {}).get("uv_index_max", [0.0])[0]
        except Exception:
            pass

        # ביגוד
        if temp < 8: clothes = "🧥 מעיל חורף כבד, כובע וכפפות — קר מאוד!"
        elif temp < 14: clothes = "🧣 מעיל בינוני + צעיף, שכבות פנימיות"
        elif temp < 19: clothes = "🍂 ג'קט קל וחולצה ארוכה — בוקר קריר"
        elif temp < 24: clothes = "👕 חולצת טי עם שכבה קלה לשינויים"
        elif temp < 29: clothes = "☀️ חולצת טי, קרם הגנה — נעים!"
        else: clothes = "🌊 לבוש קל ככל האפשר + קרם גבוה + מים!"

        rain_note = "\n☔ <b>גשם צפוי</b> — קח מטריה!" if rain else ""
        exercise_text = get_dynamic_exercise_time(lat, lon, temp)

        return (
            f"🌡️ <b>מזג אוויר — תל אביב</b>\n"
            f"טמפ' עכשיו: <b>{temp:.0f}°C</b> | ממוצעת יומית: <b>{avg_temp:.1f}°C</b>\n"
            f"טווח יומי: מקס' {temp_max:.0f}° / מינ' {temp_min:.0f}°\n"
            f"תחושה: {feels:.0f}°C | {desc}\n"
            f"לחות: {humidity}%\n"
            f"רוח: {_wind_text(wind_ms)}\n"
            f"נראות: {_visibility_text(visibility)}\n"
            f"אינדקס UV (שיא להיום): {_uv_text(uvi_max)}\n"
            f"זריחה: {sunrise_str} 🌅 | שקיעה: {sunset_str} 🌇\n"
            f"\n👔 <b>המלצת לבוש:</b> {clothes}{rain_note}\n"
            f"\n{exercise_text}"
        )
    except Exception as ex:
        logger.error("Weather: %s", ex)
        return "🌡️ <b>מזג אוויר</b> — שגיאה בטעינה 😅"


# ── חדשות ─────────────────────────────────────────────────────────────────────

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


def _fetch_news(feeds, keywords, n=5):
    items = []
    dramatic_prefixes = ["🚨 דרמה:", "🔥 חשיפה:", "💥 לא תאמינו:", "⚠️ בוער:", "⚡ עדכון חם:", "😱 מטלטל:"]
    for url in feeds:
        try:
            for entry in feedparser.parse(url).entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if any(k.lower() in title.lower() for k in keywords):
                    translated_title = translate(title)
                    prefix = random.choice(dramatic_prefixes)
                    # יצירת קישור לחיץ ב-HTML
                    items.append(f"• {prefix} <a href='{link}'>{esc(translated_title)}</a>")
                    if len(items) >= n:
                        return items
        except Exception:
            pass
    return items


def get_news() -> str:
    geo = _fetch_news(GEO_FEEDS, GEO_KW, n=5)
    ai  = _fetch_news(AI_FEEDS, AI_KW, n=5)
    
    geo_text = "\n\n".join(geo) if geo else "שקט יחסי בחזית 🕊️"
    ai_text = "\n\n".join(ai) if ai else "הבינה המלאכותית לקחה הפסקה 😴"
    
    return (
        f"🌍 <b>גיאופוליטיקה (ישראל-ארה\"ב)</b>\n{geo_text}\n\n"
        f"🤖 <b>חדשות AI</b>\n{ai_text}"
    )


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
                rec  = yf.Ticker(ticker).info.get("recommendationKey", "")
                note = f" | אנליסטים: {esc(rec)}" if rec else ""
                alerts.append(f"{icon} <b>{ticker}</b>: {pct:+.1f}% → ${curr:.2f}{note}")
        except Exception:
            no_data.append(ticker)

    lines = ["📊 <b>מניות</b>"]
    if alerts:
        lines.append("⚡ <b>התראות — שינוי 5%+:</b>")
        lines.extend(alerts)
    else:
        lines.append("אין תנועות חריגות — השוק ישן 😴")
    watched = ", ".join(t for t in STOCKS if t not in no_data)
    lines.append(f"\n<i>עוקב: {watched}</i>")
    return "\n".join(lines)


# ── Google Calendar ────────────────────────────────────────────────────────────

def _parse_ics(url: str, target_date) -> list:
    events = []
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        cal  = iCal.from_ical(resp.content)
        for c in cal.walk():
            if c.name != "VEVENT":
                continue
            dtstart = c.get("DTSTART")
            if not dtstart:
                continue
            sv = dtstart.dt
            
            if isinstance(sv, datetime):
                if sv.tzinfo is None:
                    sv = sv.replace(tzinfo=timezone.utc)
                sl    = sv.astimezone(IL_TZ)
                edate = sl.date()
                tstr  = sl.strftime("%H:%M")
            else:
                edate = sv
                tstr  = None
                
            if edate == target_date:
                summary = esc(str(c.get("SUMMARY", "(ללא שם)")))
                if tstr:
                    events.append((tstr, f"  🕐 {tstr} — {summary}"))
                else:
                    events.append(("00:00", f"  📌 {summary} (כל היום)"))
    except Exception as ex:
        logger.warning("ICS fetch error %s: %s", url[:60], ex)
    return events


def get_calendar() -> str:
    if not CALENDARS:
        return "📅 <b>לו\"ז של מאור</b> — לא מוגדר ב-.env"
    if not ICAL_AVAILABLE:
        return "📅 <b>לו\"ז של מאור</b> — pip install icalendar"

    today  = datetime.now(IL_TZ).date()
    all_ev = []
    for url in CALENDARS:
        all_ev.extend(_parse_ics(url, today))

    seen = set()
    unique = []
    for key, text in sorted(all_ev, key=lambda x: x[0]):
        if text not in seen:
            seen.add(text)
            unique.append(text)

    lines = ["📅 <b>הלו\"ז של מאור להיום:</b>"]
    if unique:
        lines.extend(unique)
    else:
        lines.append("אין אירועים היום ביומן שלך, מאור — יום פנוי! 🎉")
    return "\n".join(lines)


# ── בניית ההודעה ──────────────────────────────────────────────────────────────

def get_witty_greeting() -> str:
    """מחזיר פתיח רנדומלי ושנון שמכוון למאור."""
    greetings = [
        "בוקר אור מאור! השמש זרחה, הקפה מחכה, והעולם לא יכבוש את עצמו.",
        "קומו קומו מאור! דבי כאן כדי לוודא שאתה לא מפספס שום תנועה בשוק.",
        "בוקר טוב למנכ\"ל העתידי. הנה התדריך שיעשה לך סדר בבלגן.",
        "עוד יום, עוד הזדמנות להיות גרסה טובה יותר של עצמך. קדימה מאור!",
        "ערני? מקווה שכן, כי החדשות של היום לא יחכו שתסיים את החלום על הטסלה.",
        "בוקר טוב בוס! דבי מוכנה לפעולה. בוא נראה מה מחכה לנו היום."
    ]
    return random.choice(greetings)


def build_message() -> str:
    now      = datetime.now(IL_TZ)
    days_he  = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    date_str = now.strftime(f"יום {days_he[now.weekday()]}, %d/%m/%Y")

    return "\n\n".join([
        f"🌅 <b>{get_witty_greeting()}</b> 😄\n<i>{date_str}</i>\nקפה בצד? יש מה לכסות...\n{SEP}",
        get_weather(), SEP,
        get_news(),    SEP,
        get_stocks(),  SEP,
        get_calendar(),
        f"{SEP}\n<i>בהצלחה ביום מאור! — דבי 🤖✨</i>",
    ])


# ── שליחה ──────────────────────────────────────────────────────────────────────

async def main():
    bot = Bot(token=BOT_TOKEN)
    msg = build_message()

    # disable_web_page_preview = True מוודא שטלגרם לא תפתח מלא חלוניות של הקישורים בחדשות
    if len(msg) <= 4000:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="HTML", disable_web_page_preview=True)
    else:
        for section in msg.split(SEP):
            if section.strip():
                await bot.send_message(
                    chat_id=CHAT_ID, text=section.strip(), parse_mode="HTML", disable_web_page_preview=True
                )
    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
