"""
דבי — בוט שגרת בוקר
מריצה פעם אחת, שולחת את התדריך, ויוצאת.
מופעלת אוטומטית כל יום ע"י GitHub Actions.
"""

import asyncio
import logging
import os
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

load_dotenv()

BOT_TOKEN           = os.getenv("BOT_TOKEN", "")
CHAT_ID             = os.getenv("CHAT_ID", "")
OPENWEATHER_KEY     = os.getenv("OPENWEATHER_API_KEY", "")
GOOGLE_CALENDAR_ICS = os.getenv("GOOGLE_CALENDAR_ICS", "")

STOCKS = [
    "INTC", "TSLA", "MBLY", "ASPI", "TEVA",
    "GOOG", "QBTS", "AMZN", "GRAB", "SEPN", "NVO", "KLAR",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("deby")
SEP = "─" * 28


# ── מזג אוויר ──────────────────────────────────────────────────────────────────

def get_weather() -> str:
    if not OPENWEATHER_KEY:
        return "🌡️ *מזג אוויר* — מפתח API חסר"
    try:
        data = requests.get(
            "https://api.openweathermap.org/data/2.5/weather"
            f"?q=Tel+Aviv,IL&appid={OPENWEATHER_KEY}&units=metric&lang=he",
            timeout=10,
        ).json()
        if data.get("cod") != 200:
            return f"🌡️ *מזג אוויר* — שגיאה: {data.get('message')}"

        temp  = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        desc  = data["weather"][0]["description"]
        hum   = data["main"]["humidity"]
        wind  = data["wind"]["speed"]
        rain  = "rain" in data.get("weather", [{}])[0].get("main", "").lower()

        if   temp < 10: clothes = "🧥 מעיל כבד — קר, שים שכבות"
        elif temp < 16: clothes = "🧣 מעיל בינוני, צעיף לא יפגע"
        elif temp < 22: clothes = "👕 חולצה + שכבה קלה — מושלם"
        elif temp < 28: clothes = "☀️ חולצת טי וזהו"
        else:           clothes = "🌊 לבוש קל ותשתה מים!"

        return (
            f"🌡️ *מזג אוויר — תל אביב*\n"
            f"טמפרטורה: {temp:.0f}°C (מורגש {feels:.0f}°C)\n"
            f"מצב: {desc}\n"
            f"לחות: {hum}% | רוח: {wind:.0f} מ\"ש\n"
            f"{clothes}"
            + ("\n☔ גשם צפוי — קח מטריה!" if rain else "")
        )
    except Exception as e:
        logger.error("Weather: %s", e)
        return "🌡️ *מזג אוויר* — לא הצלחתי לקבל נתונים 😅"


# ── חדשות ──────────────────────────────────────────────────────────────────────

GEO_FEEDS = [
    "https://feeds.reuters.com/reuters/topNews",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
]
AI_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
]
GEO_KW = ["israel", "iran", "hamas", "hezbollah", "gaza",
           "middle east", "trump", "netanyahu", "idf"]
AI_KW  = ["ai", "artificial intelligence", "openai", "chatgpt",
           "llm", "gpt", "claude", "gemini", "machine learning"]


def _fetch(feeds, keywords, n=3):
    items = []
    for url in feeds:
        try:
            for e in feedparser.parse(url).entries:
                title = e.get("title", "")
                if any(k.lower() in (title + e.get("summary", "")).lower() for k in keywords):
                    items.append(f"• {title.strip()[:120]}")
                    if len(items) >= n:
                        return items
        except Exception:
            pass
    return items


def get_news() -> str:
    geo = _fetch(GEO_FEEDS, GEO_KW)
    ai  = _fetch(AI_FEEDS,  AI_KW)
    return "\n\n".join([
        "🌍 *גיאופוליטיקה (ישראל-ארה\"ב)*\n" + "\n".join(geo) if geo
        else "🌍 *גיאופוליטיקה* — שקט יחסי 🕊️",
        "🤖 *חדשות AI*\n" + "\n".join(ai) if ai
        else "🤖 *חדשות AI* — הבינה המלאכותית לקחה הפסקה 😴",
    ])


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
                note = f" | אנליסטים: {rec}" if rec else ""
                alerts.append(f"{icon} *{ticker}*: {pct:+.1f}% → ${curr:.2f}{note}")
        except Exception:
            no_data.append(ticker)

    lines = ["📊 *מניות*"]
    if alerts:
        lines.append("⚡ *התראות — שינוי 5%+:*")
        lines.extend(alerts)
    else:
        lines.append("אין תנועות חריגות — השוק ישן 😴")
    watched = ", ".join(t for t in STOCKS if t not in no_data)
    lines.append(f"\n_עוקב: {watched}_")
    if no_data:
        lines.append(f"_לא זמין: {', '.join(no_data)}_")
    return "\n".join(lines)


# ── Google Calendar ─────────────────────────────────────────────────────────────

def get_calendar() -> str:
    if not GOOGLE_CALENDAR_ICS:
        return "📅 *Google Calendar* — לא מוגדר"
    if not ICAL_AVAILABLE:
        return "📅 *Google Calendar* — pip install icalendar"
    try:
        resp  = requests.get(GOOGLE_CALENDAR_ICS, timeout=15)
        cal   = iCal.from_ical(resp.content)
        il_tz = timezone(timedelta(hours=3))
        today = datetime.now(il_tz).date()
        events = []

        for c in cal.walk():
            if c.name == "VEVENT":
                dtstart = c.get("DTSTART")
                if not dtstart:
                    continue
                sv = dtstart.dt
                if isinstance(sv, datetime):
                    if sv.tzinfo is None:
                        sv = sv.replace(tzinfo=timezone.utc)
                    sl = sv.astimezone(il_tz)
                    edate, tstr = sl.date(), sl.strftime("%H:%M")
                else:
                    edate, tstr = sv, None
                if edate == today:
                    summary = str(c.get("SUMMARY", "(ללא שם)"))
                    events.append((tstr or "00:00",
                                   f"  🕐 {tstr} — {summary}" if tstr
                                   else f"  📌 {summary} (כל היום)"))

        events.sort(key=lambda x: x[0])
        lines = ["📅 *Google Calendar*"]
        if events:
            lines.append("*אירועים היום:*")
            lines.extend(e[1] for e in events)
        else:
            lines.append("*אין פגישות היום* — יום פנוי! 🎉")
        return "\n".join(lines)
    except Exception as e:
        logger.error("Calendar: %s", e)
        return f"📅 *Google Calendar* — שגיאה: {str(e)[:60]}"


# ── שליחה ──────────────────────────────────────────────────────────────────────

def build_message() -> str:
    il_tz   = timezone(timedelta(hours=3))
    now     = datetime.now(il_tz)
    days_he = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    date_str = now.strftime(f"יום {days_he[now.weekday()]}, %d/%m/%Y")

    return "\n\n".join([
        f"🌅 *בוקר טוב! אני דבי* 😄\n_{date_str}_\nקפה בצד? יש לנו מה לכסות...\n{SEP}",
        get_weather(), SEP,
        get_news(),    SEP,
        get_stocks(),  SEP,
        get_calendar(),
        f"{SEP}\n_בהצלחה ביום! — דבי 🤖✨_",
    ])


async def main():
    bot = Bot(token=BOT_TOKEN)
    msg = build_message()

    if len(msg) <= 4000:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
    else:
        for section in msg.split(SEP):
            if section.strip():
                await bot.send_message(
                    chat_id=CHAT_ID, text=section.strip(), parse_mode="Markdown"
                )
    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
