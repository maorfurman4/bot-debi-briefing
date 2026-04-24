"""
דבי — בוט שגרת בוקר (מבוסס 100% AI)
מריצה פעם אחת, שולחת את התדריך, ויוצאת.
"""

import asyncio
import html
import logging
import os
import re
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

BOT_TOKEN           = os.getenv("BOT_TOKEN", "")
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
CHAT_ID             = os.getenv("CHAT_ID", "")
OPENWEATHER_KEY     = os.getenv("OPENWEATHER_API_KEY", "")

DEFAULT_ICS = "https://calendar.google.com/calendar/ical/maorfurman123%40gmail.com/private-b134fd273a4b42e3031d97b6af834849/basic.ics"

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


def esc(text: str) -> str:
    return html.escape(str(text))

def clean_html(raw_html: str) -> str:
    return re.sub(r'<[^>]+>', '', raw_html) if raw_html else ""

def translate(text: str) -> str:
    if not TRANSLATE_AVAILABLE or not text: return text
    try:
        return GoogleTranslator(source="auto", target="iw").translate(text[:500]) or text
    except Exception:
        return text

# ── 1. איסוף נתונים גולמיים (ללא עיצוב סופי, רק מידע ל-AI) ──────────

def get_raw_weather() -> str:
    if not OPENWEATHER_KEY: return "אין נתוני מזג אוויר (חסר מפתח API)."
    try:
        ow = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?q=Tel+Aviv,IL&appid={OPENWEATHER_KEY}&units=metric&lang=he",
            timeout=10
        ).json()
        lat, lon = ow["coord"]["lat"], ow["coord"]["lon"]
        
        t_max, t_min = 0.0, 0.0
        try:
            om_daily = requests.get(
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,uv_index_max&timezone=Asia/Jerusalem",
                timeout=8
            ).json()
            t_max = om_daily["daily"]["temperature_2m_max"][0]
            t_min = om_daily["daily"]["temperature_2m_min"][0]
        except:
            t_max, t_min = ow["main"]["temp_max"], ow["main"]["temp_min"]

        temp = ow["main"]["temp"]
        desc = ow["weather"][0]["description"]
        
        # חישוב שעות אימון יבשות
        om = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,uv_index&timezone=Asia/Jerusalem", timeout=8).json()
        hourly, times, temps, uvs = om.get("hourly", {}), om.get("hourly", {}).get("time", []), om.get("hourly", {}).get("temperature_2m", []), om.get("hourly", {}).get("uv_index", [])
        today_str = datetime.now(IL_TZ).strftime("%Y-%m-%d")
        good_hours = [int(t[11:13]) for i, t in enumerate(times) if t.startswith(today_str) and temps[i] <= 26 and uvs[i] < 4 and (5 <= int(t[11:13]) <= 22)]
        
        ranges = []
        if good_hours:
            start = good_hours[0]
            for j in range(1, len(good_hours)):
                if good_hours[j] != good_hours[j-1] + 1:
                    ranges.append(f"{start:02d}:00-{good_hours[j-1]:02d}:00")
                    start = good_hours[j]
            ranges.append(f"{start:02d}:00-{(good_hours[-1]+1):02d}:00")
        
        exercise_str = ", ".join(ranges) if ranges else "חם מדי או קרינה גבוהה היום, עדיף במזגן."

        return f"טמפ' נוכחית: {temp}°C, מקסימום היום: {t_max}°C, מינימום: {t_min}°C. מצב: {desc}. שעות אידיאליות לאימון (לפי חום/קרינה): {exercise_str}."
    except Exception as e:
        return "שגיאה בשליפת נתוני מזג אוויר."


def get_raw_news() -> str:
    feeds = ["https://feeds.reuters.com/reuters/topNews", "https://techcrunch.com/category/artificial-intelligence/feed/"]
    kw = ["israel", "iran", "hamas", "ai", "artificial intelligence", "openai", "trump"]
    items = []
    for url in feeds:
        try:
            source = urlparse(url).netloc.replace("www.", "").split('.')[0].capitalize()
            for entry in feedparser.parse(url).entries:
                title = entry.get("title", "")
                if any(k.lower() in title.lower() for k in kw):
                    translated_title = translate(title)
                    items.append(f"- [{source}] {translated_title} (Link: {entry.get('link', '')})")
                    if len(items) >= 5: return "\n".join(items)
        except: pass
    return "\n".join(items) if items else "אין חדשות דרמטיות הבוקר."


def get_raw_stocks() -> str:
    alerts = []
    for ticker in STOCKS:
        try:
            hist = yf.Ticker(ticker).history(period="2d", prepost=True)
            if len(hist) < 2: continue
            prev, curr = hist["Close"].iloc[0], hist["Close"].iloc[-1]
            pct = ((curr - prev) / prev) * 100
            if abs(pct) >= 5:
                alerts.append(f"{ticker}: {pct:+.1f}% (Now: ${curr:.2f})")
        except: pass
    return "\n".join(alerts) if alerts else "אין תנועות מעל 5% במניות במעקב."


def get_raw_calendar() -> str:
    if not CALENDARS or not ICAL_AVAILABLE: return "מערכת היומן לא זמינה."
    today = datetime.now(IL_TZ).date()
    events = []
    for url in CALENDARS:
        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            cal = iCal.from_ical(resp.content)
            for event in recurring_ical_events.of(cal).at(today):
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
                        events.append(f"{t_start}-{t_end}: {summary}")
                    else:
                        events.append(f"{t_start}: {summary}")
                else:
                    events.append(f"כל היום: {summary}")
        except: pass
    return "\n".join(list(set(events))) if events else "היומן ריק להיום."


# ── 2. המוח המלא (הפקת כל ההודעה דרך OpenAI) ──────────────────────

def generate_full_message_with_ai(weather: str, news: str, stocks: str, calendar: str) -> str:
    now = datetime.now(IL_TZ)
    days_he = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    date_str = f"יום {days_he[now.weekday()]}, {now.strftime('%d/%m/%Y')}"

    prompt = f"""
    אתה 'דבי', העוזרת האישית החכמה, השנונה והקצת עוקצנית של מאור.
    המטרה שלך היא לכתוב את *כל* תדריך הבוקר של מאור להיום ({date_str}), מההתחלה ועד הסוף, כהודעה אחת מושלמת וזורמת.
    
    הנה הנתונים הגולמיים שאספתי עבורך הבוקר:
    - 🌡️ מזג אוויר ואימון: {weather}
    - 🌍 חדשות: {news}
    - 📊 מניות (תנועות מעל 5%): {stocks}
    - 📅 הלו"ז של מאור: {calendar}
    
    משימות חובה לכתיבת ההודעה:
    1. פתיח אישי: עוקצני בחן, מתייחס ליום בשבוע או למה שמחכה לו בלו"ז/מזג אוויר.
    2. מזג אוויר והמלצות: שלב את נתוני מזג האוויר בטקסט אנושי. תן המלצת לבוש חכמה על בסיס הטמפרטורות, ופרט בדיוק באילו שעות כדאי לו להתאמן היום (לפי הנתונים שקיבלת).
    3. חדשות: הצג את החדשות החשובות עם קישורים (השתמש ב-<a href='link'>טקסט</a>).
    4. מניות: ציין אם יש דרמות, ואם שקט - תעיר על זה.
    5. לו"ז: סכם את היומן שלו بصורה מסודרת (אם יש משחק של ריאל, תתלהב! אם ריק, תציע לו מנוחה או קידוד).
    6. פורמט: חובה לחלק את ההודעה לקטגוריות, ולהשתמש בקו מפריד {SEP} בין נושא לנושא. השתמש באימוג'יז, ובתגיות <b> ו-<i> להדגשות.
    7. חתימה בסוף: משפט פרידה קצר עם השם שלך.
    
    חובה להחזיר *רק* את ההודעה המוכנה לשליחה לטלגרם, בפורמט HTML. אל תוסיף הקדמות כמו "הנה ההודעה".
    """

    if not OPENAI_API_KEY:
        return "שגיאה: מפתח OpenAI חסר. לא ניתן לייצר הודעה חכמה."

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.8}
        ).json()
        return resp['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"OpenAI Error: {e}")
        return "שגיאה ביצירת ההודעה מול OpenAI."


# ── 3. תזמור ושליחה ────────────────────────────────────────────

async def main():
    bot = Bot(token=BOT_TOKEN)
    
    # 1. איסוף המידע
    weather_raw  = get_raw_weather()
    news_raw     = get_raw_news()
    stocks_raw   = get_raw_stocks()
    calendar_raw = get_raw_calendar()
    
    # 2. שליחה למוח החכם לעיבוד וכתיבת ההודעה כולה
    msg = generate_full_message_with_ai(weather_raw, news_raw, stocks_raw, calendar_raw)

    # 3. שליחה לטלגרם
    if len(msg) <= 4000:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="HTML", disable_web_page_preview=True)
    else:
        for section in msg.split(SEP):
            if section.strip():
                await bot.send_message(
                    chat_id=CHAT_ID, text=section.strip() + f"\n{SEP}", parse_mode="HTML", disable_web_page_preview=True
                )
    logger.info("Done!")

if __name__ == "__main__":
    asyncio.run(main())
