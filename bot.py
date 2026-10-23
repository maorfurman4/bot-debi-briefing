#!/usr/bin/env python3
"""
דבי — בוט שגרת בוקר
הרצה מקומית בלי שליחה לטלגרם: python bot.py --dry-run
"""

import asyncio
import calendar
import html
import json
import logging
import os
import re
import sys
from datetime import date, datetime, time, timedelta
import datetime as dt_module
from zoneinfo import ZoneInfo

import requests
import yfinance as yf
from dotenv import load_dotenv
from telegram import Bot

from google.oauth2.credentials import Credentials as OAuthCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from icalendar import Calendar as iCal
import recurring_ical_events

from routines import ROUTINES

load_dotenv()

BOT_TOKEN           = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID             = os.getenv("CHAT_ID", "").strip()
GOOGLE_TASKS_CREDS  = os.getenv("GOOGLE_TASKS_CREDENTIALS", "").strip()

DEFAULT_ICS = "https://calendar.google.com/calendar/ical/maorfurman123%40gmail.com/private-b134fd273a4b42e3031d97b6af834849/basic.ics"

CALENDARS = [url for url in [
    os.getenv("GOOGLE_CALENDAR_ICS_1", DEFAULT_ICS),
    os.getenv("GOOGLE_CALENDAR_ICS_2", ""),
    os.getenv("GOOGLE_CALENDAR_ICS_3", ""),
    os.getenv("GOOGLE_CALENDAR_ICS_4", ""),
] if url and url.strip()]

STOCKS = [
    "INTC", "MBLY", "TSLA", "SPCX", "TEVA",
    "NVO", "QBTS", "AMZN", "GOOG",
]

TEL_AVIV = (32.0853, 34.7818)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("deby")
SEP = "─" * 30

# שעון ישראל אמיתי — מתחלף לבד בין שעון קיץ לחורף
IL_TZ = ZoneInfo("Asia/Jerusalem")
DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]

def esc(text: str) -> str:
    return html.escape(str(text))

# ── דוח כשלונות — מצורף לסוף התדריך כדי שנדע מה לתקן ──────────────────────────

FAILURES = []

def fail(section: str, ex) -> None:
    logger.error("%s: %s", section, ex)
    # בלי כתובות — כתובות ה-ICS מכילות מפתח פרטי
    detail = re.sub(r"https?://\S+", "<url>", str(ex))[:150]
    FAILURES.append(f"• <b>{esc(section)}</b>: {esc(detail)}")

# ── פתיח ──────────────────────────────────────────────────────────────────────

GREETINGS = [
    "בוקר טוב מאור! יום חדש, דף חדש.",
    "בוקר טוב מאור, הכל מסודר — רק לצאת לדרך.",
    "בוקר טוב מאור! היום הולך להיות יום טוב.",
    "בוקר טוב מאור, צעד אחד קדימה וזה כבר ניצחון.",
    "בוקר טוב מאור! קפה, נשימה עמוקה, ויוצאים.",
    "בוקר טוב מאור, מה שתעשה היום — תעשה עד הסוף.",
    "בוקר טוב מאור! עוד יום להתקרב למטרות.",
    "בוקר טוב מאור, תתחיל מהדבר הכי קשה ושאר היום יזרום.",
    "בוקר טוב מאור! אנרגיות טובות מהבוקר.",
    "בוקר טוב מאור, היום בונים עוד לבנה.",
    "בוקר טוב מאור! לאט ובטוח — אבל כל יום.",
    "בוקר טוב מאור, היום שלך — תנצל אותו.",
    "בוקר טוב מאור! משמעת היום, חופש מחר.",
    "בוקר טוב מאור, פוקוס על מה שחשוב.",
    "בוקר טוב מאור! הגרסה הכי טובה שלך מתחילה עכשיו.",
    "בוקר טוב מאור, יום חדש עם הזדמנויות חדשות.",
    "בוקר טוב מאור! קטן קטן, אבל עקבי.",
    "בוקר טוב מאור, תהיה גאה בעצמך הערב.",
    "בוקר טוב מאור! מתחילים חזק.",
    "בוקר טוב מאור, אין קיצורי דרך — ויש לך את זה.",
    "בוקר טוב מאור! היום עושים את זה.",
    "בוקר טוב מאור, חיוך ויוצאים לדרך.",
    "בוקר טוב מאור! כל יום הוא התחלה חדשה.",
    "בוקר טוב מאור, תזכור למה התחלת.",
    "בוקר טוב מאור! עוד יום מעולה בדרך.",
    "בוקר טוב מאור, אחד אחד — וכל המשימות ייסגרו.",
    "בוקר טוב מאור! השמש בחוץ, הזמן להתחיל.",
    "בוקר טוב מאור, היום הוא הזדמנות להפתיע את עצמך.",
    "בוקר טוב מאור! ממשיכים את הרצף.",
    "בוקר טוב מאור, סוף חודש — סוגרים אותו בסטייל.",
]

def get_greeting(today: date) -> str:
    # פתיח קבוע לכל יום בחודש; ה-31 חוזר לראשון
    return GREETINGS[(today.day - 1) % len(GREETINGS)]

# ── מזג אוויר (Open-Meteo, תחזית שעתית לתל אביב) ─────────────────────────────

WEATHER_HOURS = ["07:00", "10:00", "13:00", "16:00", "19:00", "22:00"]

def _weather_icon(code: int) -> str:
    if code == 0:            return "☀️"
    if code in (1, 2):       return "🌤️"
    if code == 3:            return "☁️"
    if code in (45, 48):     return "🌫️"
    if 51 <= code <= 67:     return "🌧️"
    if 80 <= code <= 82:     return "🌦️"
    if code >= 95:           return "⛈️"
    return "🌡️"

def get_weather() -> str:
    try:
        lat, lon = TEL_AVIV
        om = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon, "timezone": "Asia/Jerusalem", "forecast_days": 1,
                "hourly": "temperature_2m,apparent_temperature,precipitation_probability,weather_code,wind_speed_10m,relative_humidity_2m",
                "daily": "temperature_2m_max,temperature_2m_min,uv_index_max,precipitation_probability_max,sunrise,sunset",
            },
            timeout=15,
        )
        om.raise_for_status()
        om = om.json()
        h, d = om["hourly"], om["daily"]

        t_max, t_min = d["temperature_2m_max"][0], d["temperature_2m_min"][0]
        uv_max, rain_max = d["uv_index_max"][0], d["precipitation_probability_max"][0] or 0
        sunrise, sunset = d["sunrise"][0][11:16], d["sunset"][0][11:16]

        lines = [
            "🌡️ <b>מזג אוויר — תל אביב</b>",
            f"⬆️ {t_max:.0f}° ⬇️ {t_min:.0f}° | ☔ גשם עד {rain_max}% | UV מקס' {uv_max:.0f}",
        ]
        for hour in WEATHER_HOURS:
            i = h["time"].index(f"{h['time'][0][:10]}T{hour}")
            lines.append(
                f"{_weather_icon(h['weather_code'][i])} <b>{hour}</b> {h['temperature_2m'][i]:.0f}° "
                f"(מרגיש {h['apparent_temperature'][i]:.0f}°) · ☔ {h['precipitation_probability'][i]}% "
                f"· 💧 {h['relative_humidity_2m'][i]}% · 💨 {h['wind_speed_10m'][i]:.0f} קמ\"ש"
            )
        lines.append(f"🌅 זריחה {sunrise} | 🌇 שקיעה {sunset}")
        if uv_max >= 8:
            lines.append("🧴 UV גבוה — קרם הגנה")
        if rain_max >= 40:
            lines.append("☂️ סיכוי לגשם — לקחת מטריה")
        return "\n".join(lines)
    except Exception as ex:
        fail("מזג אוויר", ex)
        return "🌡️ <b>מזג אוויר</b> — שגיאה בטעינה 😅"

# ── מניות ──────────────────────────────────────────────────────────────────────

def get_stocks() -> str:
    rows, no_data = [], []
    for ticker in STOCKS:
        try:
            closes = yf.Ticker(ticker).history(period="5d")["Close"].dropna()
            if len(closes) < 2:
                no_data.append(ticker)
                continue
            prev, curr = closes.iloc[-2], closes.iloc[-1]
            rows.append((((curr - prev) / prev) * 100, ticker, curr))
        except Exception:
            no_data.append(ticker)

    if no_data:
        fail("מניות", f"אין נתונים ל-{', '.join(no_data)}")
    if not rows:
        return ""
    lines = ["📊 <b>המניות שלי</b> <i>(שינוי יומי בסגירה האחרונה)</i>"]
    for pct, ticker, curr in sorted(rows, reverse=True):
        icon = "🚀" if pct >= 5 else "📈" if pct > 0 else "💥" if pct <= -5 else "📉" if pct < 0 else "➖"
        lines.append(f"{icon} <b>{ticker}</b> {pct:+.1f}% · ${curr:.2f}")
    return "\n".join(lines)

# ── משימות: קבועות (routines.py) + של יוסי (Google Tasks) ───────────────────

def todays_routines(today: date, routines: list = ROUTINES) -> list:
    last_day = calendar.monthrange(today.year, today.month)[1]
    titles = []
    for r in routines:
        every = r.get("every")
        if (
            every == "daily"
            or (every == "weekly" and DAYS_HE[today.weekday()] in r.get("days", []))
            or (every == "monthly" and min(int(r.get("day", 0)), last_day) == today.day)
            or (every == "yearly" and r.get("date") == today.strftime("%d/%m"))
        ):
            titles.append(r["title"])
    return titles

def _get_google_tasks_service():
    if not GOOGLE_TASKS_CREDS:
        fail("משימות (Google Tasks)", "חסר GOOGLE_TASKS_CREDENTIALS")
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
        fail("משימות (Google Tasks) — התחברות", e)
        return None

def get_google_tasks(today: date) -> list:
    service = _get_google_tasks_service()
    if not service:
        return []
    try:
        items = service.tasks().list(tasklist="@default", showCompleted=False, maxResults=100).execute().get("items", [])
    except Exception as e:
        fail("משימות (Google Tasks)", e)
        return []
    today_str = today.isoformat()
    lines = []
    for t in items:
        title, due = esc(t.get("title", "(ללא כותרת)")), (t.get("due") or "")[:10]
        if not due or due == today_str:
            lines.append(f"✅ {title}")
        elif due < today_str:
            lines.append(f"⏰ {title} <i>(באיחור מ-{due[8:10]}/{due[5:7]})</i>")
    return lines

def get_tasks(today: date) -> str:
    lines = [f"🔁 {esc(t)}" for t in todays_routines(today)] + get_google_tasks(today)
    return "📋 <b>מה צריך לעשות היום:</b>\n" + "\n".join(lines) if lines else ""

# ── Google Calendar ────────────────────────────────────────────────────────────

DAY_START, DAY_END = time(8, 0), time(22, 0)
MIN_GAP = timedelta(hours=1)

def _to_il(value) -> datetime:
    # שעה בלי אזור זמן ב-ICS היא שעה מקומית
    return value.replace(tzinfo=IL_TZ) if value.tzinfo is None else value.astimezone(IL_TZ)

def _parse_ics(url: str, target_date: date, label: str) -> tuple:
    timed, all_day = [], []
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        for event in recurring_ical_events.of(iCal.from_ical(resp.content)).at(target_date):
            summary = str(event.get("SUMMARY", "(ללא שם)"))
            start = event.get("DTSTART").dt
            if isinstance(start, dt_module.datetime):
                end_prop = event.get("DTEND")
                end = end_prop.dt if end_prop and isinstance(end_prop.dt, dt_module.datetime) else start
                start, end = _to_il(start), _to_il(end)
                if end - start >= timedelta(hours=23):
                    all_day.append(summary)  # "00:00–23:59" הוא בפועל אירוע של כל היום
                else:
                    timed.append((start, end, summary))
            elif not summary.startswith("📌"):
                all_day.append(summary)
    except Exception as ex:
        fail(label, ex)
    return timed, all_day

def free_gaps(events: list, day: date) -> list:
    """חלונות פנויים של שעה ומעלה בין 08:00 ל-22:00."""
    cursor = datetime.combine(day, DAY_START, IL_TZ)
    day_end = datetime.combine(day, DAY_END, IL_TZ)
    gaps = []
    for start, end, _ in sorted(events):
        if start - cursor >= MIN_GAP:
            gaps.append((cursor, min(start, day_end)))
        cursor = max(cursor, end)
        if cursor >= day_end:
            break
    if day_end - cursor >= MIN_GAP:
        gaps.append((cursor, day_end))
    return [(s, e) for s, e in gaps if e - s >= MIN_GAP]

def get_calendar(today: date) -> str:
    timed, all_day = set(), []
    for i, url in enumerate(CALENDARS, 1):
        t, a = _parse_ics(url, today, f"יומן {i}")
        timed.update(t)
        all_day += [s for s in a if s not in all_day]

    if not timed and not all_day:
        return "📅 <b>הלו\"ז שלך היום:</b> אין אירועים — יום פנוי 🎉"

    fmt = lambda d: d.strftime("%H:%M")
    rows = [(s, f"🕐 <b>{fmt(s)}–{fmt(e)}</b> {esc(name)}") for s, e, name in timed]
    rows += [(s, f"🟢 <i>{fmt(s)}–{fmt(e)} פנוי</i>") for s, e in free_gaps(list(timed), today)]
    lines = ["📅 <b>הלו\"ז שלך היום:</b>"]
    lines += [f"📌 <b>כל היום</b> {esc(name)}" for name in all_day]
    lines += [text for _, text in sorted(rows, key=lambda r: r[0])]
    return "\n".join(lines)

# ── בניית ההודעה ──────────────────────────────────────────────────────────────

def build_message() -> str:
    now = datetime.now(IL_TZ)
    today = now.date()
    date_str = now.strftime(f"יום {DAYS_HE[now.weekday()]}, %d/%m/%Y")
    sections = [
        f"🌅 <b>{get_greeting(today)}</b>\n<i>{date_str}</i>",
        get_weather(),
        get_calendar(today),
        get_tasks(today),
        get_stocks(),
    ]
    if FAILURES:
        sections.append("⚠️ <b>מה לא עבד היום:</b>\n" + "\n".join(FAILURES))
    return f"\n\n{SEP}\n\n".join(s for s in sections if s.strip())

# ── שליחה ──────────────────────────────────────────────────────────────────────

async def main():
    try:
        msg = build_message()
    except Exception as ex:
        # קריסה כללית — לפחות לדעת עליה בטלגרם; ה-raise מסמן את ההרצה ב-Actions כנכשלת
        if "--dry-run" not in sys.argv:
            await Bot(token=BOT_TOKEN).send_message(chat_id=CHAT_ID, text=f"⚠️ דבי נכשל ולא שלח תדריך היום:\n{type(ex).__name__}: {str(ex)[:300]}")
        raise
    if "--dry-run" in sys.argv:
        print(msg)
        return

    bot = Bot(token=BOT_TOKEN)
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
