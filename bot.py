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
import time as time_module
from datetime import date, datetime, time, timedelta
import datetime as dt_module
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from telegram import Bot


from icalendar import Calendar as iCal
import recurring_ical_events


load_dotenv()

BOT_TOKEN           = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID             = os.getenv("CHAT_ID", "").strip()
MONDAY_TOKEN        = os.getenv("MONDAY_API_TOKEN", "").strip()

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

# ── מזג אוויר (Open-Meteo, תל אביב): טווח יומי, זריחה ושקיעה ──────────────────

def get_weather() -> str:
    try:
        lat, lon = TEL_AVIV
        om = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "timezone": "Asia/Jerusalem", "forecast_days": 1,
                    "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset"},
            timeout=15,
        )
        om.raise_for_status()
        d = om.json()["daily"]
        return (f"🌡️ <b>מזג אוויר — תל אביב</b>\n"
                f"⬆️ {d['temperature_2m_max'][0]:.0f}° ⬇️ {d['temperature_2m_min'][0]:.0f}° | "
                f"🌅 זריחה {d['sunrise'][0][11:16]} | 🌇 שקיעה {d['sunset'][0][11:16]}")
    except Exception as ex:
        fail("מזג אוויר", ex)
        return "🌡️ <b>מזג אוויר</b> — שגיאה בטעינה 😅"

# ── monday: דדליינים מחר / בעוד 3, 7 ימים, ותקועים — מכל הלוחות ─────────────────
# משימות לעשות (מתוכנן להיום, באיחור, דדליין היום, השגרה) — רק ברשימת ה-✅ של יוסי ב-07:00 (5.11: הופיעו פעמיים)
# בתוכנית Free אין תזכורות של monday — זה ערוץ התזכורות היחיד.
# הלוחות והעמודות נמצאים לפי שם (המזהים משתנים כשמאחדים לוחות).

MONDAY_BOARDS = "{ boards(state: active, limit: 100) { id type columns { title } } }"
# פריטים רק לפי מזהים — אותה שאילתה על כל הלוחות בלי ids מחזירה 429 (נמדד 02/11/2026)
MONDAY_ITEMS = """query ($ids: [ID!]) { boards(ids: $ids) { items_page(limit: 500) { items {
  name group { title } column_values { column { title } text } } } } }"""
# דבי לא יכולה לקבל לחיצות (GitHub Actions) — הקישור פותח את יוסי ושולח "/start today": רשימת היום עם ✅
YOSSI_TODAY = "https://t.me/shifts_calmder_bot?start=today"
# "גג יום לפני" (הכלל של מאור): דדליין מחר = היום הוא היום האחרון להגיש
DUE_IN = {1: "🔥 <b>מחר — גג להגיש היום</b>", 3: "⏳ <b>עוד 3 ימים</b>", 7: "📆 <b>עוד שבוע</b>"}

def monday_gql(query: str, **variables) -> dict:
    for attempt in range(2):  # 429 — monday אומר כמה לחכות; ניסיון אחד נוסף
        resp = requests.post("https://api.monday.com/v2", timeout=30, json={"query": query, "variables": variables},
                             headers={"Authorization": MONDAY_TOKEN, "API-Version": "2025-04"})
        if resp.status_code != 429 or attempt:
            break
        time_module.sleep(min(int(resp.headers.get("Retry-After") or 10), 30))
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:150]}")
    body = resp.json()
    if body.get("errors"):
        raise RuntimeError(str(body["errors"])[:150])
    return body["data"]

def monday_items() -> list:
    # רק לוחות משימות: עם עמודת "סטטוס" (לא "My first project", לא מסמכים, לא לוחות תתי-פריטים)
    ids = [b["id"] for b in monday_gql(MONDAY_BOARDS)["boards"]
           if b["type"] == "board" and any(c["title"] == "סטטוס" for c in b["columns"])]
    # shortcut: עד 500 פריטים ללוח (בלי דפדוף); אם לוח יגדל מעבר — להוסיף next_items_page
    items = []
    for board in monday_gql(MONDAY_ITEMS, ids=ids)["boards"]:
        for it in board["items_page"]["items"]:
            cols = {cv["column"]["title"]: cv["text"] or "" for cv in it["column_values"]}  # לפי שם עמודה, לא מזהה
            # הקבוצה היא הפרויקט / הקורס / סוג המשימה האישית
            items.append({"name": it["name"], "group": it["group"]["title"], "status": cols.get("סטטוס", ""),
                          "deadline": cols.get("דדליין", "")[:10],
                          "planned": cols.get("📅 מתוכנן ל", "")[:10]})  # היום שמאור תכנן לעבוד עליו
    return items

def monday_lines(items: list, today: date) -> list:
    # "בוצע" = נעשה, בכל קבוצה שהוא (אין אוטומציה שמעבירה לארכיון)
    open_items = [i for i in items if i["status"] != "בוצע" and "ארכיון" not in i["group"]]
    row = lambda i: f"{esc(i['name'])} <i>({esc(i['group'])})</i>"
    lines = []
    for i in sorted((i for i in open_items if i["deadline"]), key=lambda i: i["deadline"]):
        days = (date.fromisoformat(i["deadline"]) - today).days
        if days in DUE_IN:
            when = f" ({i['deadline'][8:10]}/{i['deadline'][5:7]})" if days > 1 else ""
            lines.append(f"{DUE_IN[days]}{when} · {row(i)}")
    lines += [f"🧱 <b>תקוע</b> · {row(i)}" for i in open_items if i["status"] == "תקוע"]
    return lines

def get_monday_items() -> list | None:
    if not MONDAY_TOKEN:
        fail("monday", "חסר MONDAY_API_TOKEN")
        return None
    try:
        return monday_items()
    except Exception as ex:
        fail("monday", ex)
        return None

def get_monday(today: date, items: list | None) -> str:
    tasks = f'📋 <a href="{YOSSI_TODAY}">המשימות של היום — ביוסי</a>'
    if items is None:
        return tasks
    lines = monday_lines(items, today)
    if not lines:
        return f"🗂️ <b>monday:</b> אין דדליינים קרובים ואין משימות תקועות ✨\n{tasks}"
    return "🗂️ <b>monday — דדליינים ותקועים:</b>\n" + "\n".join(lines) + f"\n{tasks}"

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
        get_monday(today, get_monday_items()),
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
