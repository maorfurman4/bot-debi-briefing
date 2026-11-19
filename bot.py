#!/usr/bin/env python3
"""
דבי — בוט שגרת בוקר
הרצה מקומית בלי שליחה לטלגרם: python bot.py --dry-run
"""

import asyncio
import html
import logging
import os
import re
import sys
from datetime import date, datetime, time, timedelta
import datetime as dt_module
from zoneinfo import ZoneInfo

import requests

import aura_report
import remind
from dotenv import load_dotenv
from telegram import Bot


from icalendar import Calendar as iCal
import recurring_ical_events


load_dotenv()

BOT_TOKEN           = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID             = os.getenv("CHAT_ID", "").strip()

DEFAULT_ICS = "https://calendar.google.com/calendar/ical/maorfurman123%40gmail.com/private-b134fd273a4b42e3031d97b6af834849/basic.ics"

CALENDARS = [url for url in [
    os.getenv("GOOGLE_CALENDAR_ICS_1", DEFAULT_ICS),
    os.getenv("GOOGLE_CALENDAR_ICS_2", ""),
    os.getenv("GOOGLE_CALENDAR_ICS_3", ""),
    os.getenv("GOOGLE_CALENDAR_ICS_4", ""),
] if url and url.strip()]

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

# ── ⛅ מזג אוויר מעשי + 🎒 מה להביא — ב-remind.py (16.11). דדליינים של monday ירדו מהתדריך (מאור: רעש;
# יהלי ב-07:00 מכסה את מה שבאיחור, ותזכורת 22:00 את מחר).

def get_weather(day: date, timed: list, wx: dict | None) -> str:
    if wx is None:
        return "⛅ <b>מזג אוויר</b> — שגיאה בטעינה 😅"
    try:
        return remind.practical_weather(day, timed, wx)
    except Exception as ex:
        fail("מזג אוויר", ex)
        return "⛅ <b>מזג אוויר</b> — שגיאה בטעינה 😅"

def load_weather() -> dict | None:
    try:
        return remind.fetch_weather(*TEL_AVIV)
    except Exception as ex:
        fail("מזג אוויר", ex)
        return None

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

def get_events(day: date) -> tuple:
    """(אירועים עם שעה, אירועים של כל היום) מכל היומנים, בלי כפילויות."""
    timed, all_day = set(), []
    for i, url in enumerate(CALENDARS, 1):
        t, a = _parse_ics(url, day, f"יומן {i}")
        timed.update(t)
        all_day += [s for s in a if s not in all_day]
    return sorted(timed), all_day

def get_calendar(today: date, events: tuple | None = None) -> str:
    timed, all_day = events or get_events(today)
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

def get_today_reminders(today: date, events: tuple, wx: dict | None) -> str:
    try:
        lines = remind.reminders(today, events[0], events[1], wx)
    except Exception as ex:
        fail("מה להביא", ex)
        return ""
    return "🎒 <b>להיום:</b>\n" + "\n".join(remind.esc_line(l) for l in lines) if lines else ""

# ── AURA HQ: station reports (aura_report.py). Counts only — no event titles, no URLs. ──

BOT = "debi"

def _soft_error(w, headline: str) -> None:
    # the helpers above catch their own errors (fail()), so the station reports "error" without a raise
    w.closed = True
    aura_report.station(BOT, w.station_id, "error", headline)

def weather_facts(day: date, wx: dict | None, when: str) -> tuple | None:
    """(headline, metrics) from the forecast that was already fetched; None when there is nothing to read."""
    try:  # telemetry only: a malformed forecast must not break the brief here (get_weather reports it)
        h = wx["hourly"]
        idx = [k for k, t in enumerate(h["time"]) if t.startswith(day.isoformat()) and 7 <= int(t[11:13]) <= 23]
        tmax = max(h["temperature_2m"][k] for k in idx)
        prob = max((h["precipitation_probability"][k] or 0) for k in idx)
    except Exception:
        return None
    rain = prob >= 50  # same threshold as the umbrella line in remind.practical_weather
    # the office turns its dome on by the word "גשם", so it appears only when rain is forecast
    return (f"{'גשם' if rain else 'יבש'} {when}, עד {tmax:.0f} מעלות",
            {"rain": int(rain), "rain_prob": prob, "temp_max": tmax})

def station_events(day: date) -> tuple:
    with aura_report.working(BOT, "calendar", "קוראת את היומנים") as w:
        before = len(FAILURES)
        events = get_events(day)
        n, failed = len(events[0]) + len(events[1]), len(FAILURES) - before
        w.done(f"{n} אירועים מ-{len(CALENDARS)} יומנים" + (f", {failed} לא נטענו" if failed else ""),
               calendars=len(CALENDARS), events=n, failed=failed)
    return events

def station_weather(day: date, when: str) -> dict | None:
    with aura_report.working(BOT, "weather", "מביאה תחזית לתל אביב") as w:
        wx = load_weather()
        facts = weather_facts(day, wx, when)
        if facts:
            w.done(facts[0], **facts[1])
        else:
            _soft_error(w, "התחזית לא נטענה")
    return wx

def build_message() -> str:
    now = datetime.now(IL_TZ)
    today = now.date()
    date_str = now.strftime(f"יום {DAYS_HE[now.weekday()]}, %d/%m/%Y")
    events, wx = station_events(today), station_weather(today, "היום")
    with aura_report.working(BOT, "bring", "בודקת מה להביא היום") as w:
        before = len(FAILURES)
        bring = get_today_reminders(today, events, wx)
        if len(FAILURES) > before:
            _soft_error(w, "רשימת מה להביא נכשלה")
        else:
            items = bring.count("\n")  # a header line, then one line per item
            w.done(f"{items} דברים להביא היום" if items else "אין מה להביא היום", items=items)
    sections = [
        f"🌅 <b>{get_greeting(today)}</b>\n<i>{date_str}</i>",
        get_weather(today, events[0], wx),
        get_calendar(today, events),
        bring,
    ]
    if FAILURES:
        sections.append("⚠️ <b>מה לא עבד היום:</b>\n" + "\n".join(FAILURES))
    return f"\n\n{SEP}\n\n".join(s for s in sections if s.strip())

def build_evening() -> str | None:
    """22:00 (מ-cron של יהלי): מה להביא / לזכור מחר. אין אירוע שצריך משהו — None, לא שולחים."""
    tomorrow = datetime.now(IL_TZ).date() + timedelta(days=1)
    timed, all_day = station_events(tomorrow)
    wx = station_weather(tomorrow, "מחר")
    with aura_report.working(BOT, "bring", "בודקת מה להביא מחר") as w:
        lines = remind.reminders(tomorrow, timed, all_day, wx)
        w.done(f"{len(lines)} דברים להביא מחר" if lines else "אין מה להביא מחר", items=len(lines))
    msg = remind.evening_message(tomorrow, lines)
    if msg and FAILURES:
        msg += "\n\n⚠️ <b>מה לא עבד:</b>\n" + "\n".join(FAILURES)
    return msg

# ── שליחה ──────────────────────────────────────────────────────────────────────

async def main():
    if "--dry-run" in sys.argv:
        os.environ["AURA_REPORT"] = "off"  # a dry run does not report to the office
    if "--evening" in sys.argv:
        msg = build_evening()
        if "--dry-run" in sys.argv:
            print(msg or "(אין מה להזכיר — לא נשלח)")
        elif msg:
            with aura_report.working(BOT, "writer", "שולחת את תזכורת הערב") as w:
                await Bot(token=BOT_TOKEN).send_message(chat_id=CHAT_ID, text=msg, parse_mode="HTML", disable_web_page_preview=True)
                w.done("תזכורת הערב נשלחה", messages=1, failures=len(FAILURES))
        else:
            aura_report.station(BOT, "writer", "done", "ערב: אין מה להביא מחר, לא נשלחה הודעה", {"messages": 0})
        return
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

    with aura_report.working(BOT, "writer", "שולחת את תדריך הבוקר") as w:
        bot = Bot(token=BOT_TOKEN)
        if len(msg) <= 4000:
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="HTML", disable_web_page_preview=True)
        else:
            for section in msg.split(SEP):
                if section.strip():
                    await bot.send_message(
                        chat_id=CHAT_ID, text=section.strip(), parse_mode="HTML", disable_web_page_preview=True
                    )
        sent = 1 if len(msg) <= 4000 else sum(1 for section in msg.split(SEP) if section.strip())
        w.done("תדריך הבוקר נשלח", messages=sent, failures=len(FAILURES))
    logger.info("Done!")

if __name__ == "__main__":
    asyncio.run(main())
