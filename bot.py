


IDLE

"""
דבי — בוט שגרת בוקר
מריצה פעם אחת, שולחת את התדריך, ויוצאת.
מופעלת אוטומטית כל יום ע"י GitHub Actions.
"""
 
import asyncio
import html
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
    "GOOG", "QBTS", "AMZN", "GRAB", "SEPN", "NVO",
]
 
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("deby")
 
SEP = "─" * 28
 
def e(text: str) -> str:
    """Escape text for Telegram HTML mode."""
    return html.escape(str(text))
 
 
# ── מזג אוויר ──────────────────────────────────────────────────────────────────
 
def get_weather() -> str:
    if not OPENWEATHER_KEY:
        return "🌡️ <b>מזג אוויר</b> — מפתח API חסר"
    try:
        data = requests.get(
            "https://api.openweathermap.org/data/2.5/weather"
            f"?q=Tel+Aviv,IL&appid={OPENWEATHER_KEY}&units=metric&lang=he",
            timeout=10,
        ).json()
        if data.get("cod") != 200:
            return f"🌡️ <b>מזג אוויר</b> — שגיאה: {e(data.get('message', ''))}"
 
        temp  = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        desc  = e(data["weather"][0]["description"])
        hum   = data["main"]["humidity"]
        wind  = data["wind"]["speed"]
        rain  = "rain" in data.get("weather", [{}])[0].get("main", "").lower()
 
        if   temp < 10: clothes = "🧥 מעיל כבד — קר, שים שכבות"
        elif temp < 16: clothes = "🧣 מעיל בינוני, צעיף לא יפגע"
        elif temp < 22: clothes = "👕 חולצה + שכבה קלה — מושלם"
        elif temp < 28: clothes = "☀️ חולצת טי וזהו"
        else:           clothes = "🌊 לבוש קל ותשתה מים!"
 
        return (
            f"🌡️ <b>מזג אוויר — תל אביב</b>\n"
            f"טמפרטורה: {temp:.0f}°C (מורגש {feels:.0f}°C)\n"
            f"מצב: {desc}\n"
            f"לחות: {hum}% | רוח: {wind:.0f} מ\"ש\n"
            f"{clothes}"
            + ("\n☔ גשם צפוי — קח מטריה!" if rain else "")
        )
    except Exception as ex:
        logger.error("Weather: %s", ex)
        return "🌡️ <b>מזג אוויר</b> — לא הצלחתי לקבל נתונים 😅"
 
 
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
            for entry in feedparser.parse(url).entries:
                title = entry.get("title", "")
                body  = entry.get("summary", "")
                if any(k.lower() in (title + body).lower() for k in keywords):
                    items.append(f"• {e(title.strip()[:120])}")
                    if len(items) >= n:
                        return items
        except Exception:
            pass
    return items
 
 
def get_news() -> str:
    geo = _fetch(GEO_FEEDS, GEO_KW)
    ai  = _fetch(AI_FEEDS,  AI_KW)
    return "\n\n".join([
        "🌍 <b>גיאופוליטיקה (ישראל-ארה\"ב)</b>\n" + "\n".join(geo) if geo
        else "🌍 <b>גיאופוליטיקה</b> — שקט יחסי 🕊️",
        "🤖 <b>חדשות AI</b>\n" + "\n".join(ai) if ai
        else "🤖 <b>חדשות AI</b> — הבינה המלאכותית לקחה הפסקה 😴",
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
                note = f" | אנליסטים: {e(rec)}" if rec else ""
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
    if no_data:
        lines.append(f"<i>לא זמין: {', '.join(no_data)}</i>")
    return "\n".join(lines)
 
 
# ── Google Calendar ─────────────────────────────────────────────────────────────
 
def get_calendar() -> str:
    if not GOOGLE_CALENDAR_ICS:
        return "📅 <b>Google Calendar</b> — לא מוגדר"
    if not ICAL_AVAILABLE:
        return "📅 <b>Google Calendar</b> — pip install icalendar"
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
                    summary = e(str(c.get("SUMMARY", "(ללא שם)")))
                    events.append((tstr or "00:00",
                                   f"  🕐 {tstr} — {summary}" if tstr
                                   else f"  📌 {summary} (כל היום)"))
 
        events.sort(key=lambda x: x[0])
        lines = ["📅 <b>Google Calendar</b>"]
        if events:
            lines.append("<b>אירועים היום:</b>")
            lines.extend(ev[1] for ev in events)
        else:
            lines.append("אין פגישות היום — יום פנוי! 🎉")
        return "\n".join(lines)
    except Exception as ex:
        logger.error("Calendar: %s", ex)
        return f"📅 <b>Google Calendar</b> — שגיאה: {e(str(ex)[:60])}"
 
 
# ── בניית ההודעה ────────────────────────────────────────────────────────────────
 
def build_message() -> str:
    il_tz    = timezone(timedelta(hours=3))
    now      = datetime.now(il_tz)
    days_he  = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    date_str = now.strftime(f"יום {days_he[now.weekday()]}, %d/%m/%Y")
 
    return "\n\n".join([
        f"🌅 <b>בוקר טוב! אני דבי</b> 😄\n<i>{date_str}</i>\nקפה בצד? יש לנו מה לכסות...\n{SEP}",
        get_weather(), SEP,
        get_news(),    SEP,
        get_stocks(),  SEP,
        get_calendar(),
        f"{SEP}\n<i>בהצלחה ביום! — דבי 🤖✨</i>",
    ])
 
 
# ── שליחה ──────────────────────────────────────────────────────────────────────
 
async def main():
    bot = Bot(token=BOT_TOKEN)
    msg = build_message()
 
    chunks = []
    if len(msg) <= 4000:
        chunks = [msg]
    else:
        for section in msg.split(SEP):
            if section.strip():
                chunks.append(section.strip())
 
    for chunk in chunks:
        await bot.send_message(chat_id=CHAT_ID, text=chunk, parse_mode="HTML")
 
    logger.info("Done!")
 
 
if __name__ == "__main__":
    asyncio.run(main())
