"""16.11: 🎒 מה להביא מחר (22:00) / היום (05:30) לפי שם האירוע, ⛅ מזג אוויר מעשי, בלי דדליינים של monday.
python test_remind.py — ✅/❌; בלי רשת. DEBI_DIR=<תיקייה> — על קוד אחר (אדום-ירוק)."""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.environ.get("DEBI_DIR") or os.path.dirname(os.path.abspath(__file__)))
FAILED = []

def check(name, fn):
    try:
        fn()
        print(f"✅ {name}")
    except Exception as ex:  # noqa: BLE001
        FAILED.append(name)
        print(f"❌ {name} — {type(ex).__name__}: {ex}")

def R():
    import remind
    return remind

from zoneinfo import ZoneInfo  # noqa: E402
IL = ZoneInfo("Asia/Jerusalem")
TUE = date(2026, 11, 17)  # שלישי

def at(h, m=0, day=TUE):
    return datetime(day.year, day.month, day.day, h, m, tzinfo=IL)

def ev(h, title, hours=2):
    return (at(h), at(h) + timedelta(hours=hours), title)

def wx(temp=20, feels=None, rain=0, mm=0.0, wind=10, uv=4, day=TUE):
    """שעתי ליומיים — אותו ערך בכל שעה (מספיק לבדיקה), אפשר לשנות שעות בודדות אחרי."""
    times = [f"{(day + timedelta(days=d)).isoformat()}T{h:02d}:00" for d in (0, 1) for h in range(24)]
    n = len(times)
    return {"hourly": {"time": times, "temperature_2m": [temp] * n, "apparent_temperature": [feels if feels is not None else temp] * n,
                       "precipitation_probability": [rain] * n, "precipitation": [mm] * n, "wind_speed_10m": [wind] * n},
            "daily": {"time": [day.isoformat()], "uv_index_max": [uv]}}

NO_AI = lambda title: (_ for _ in ()).throw(AssertionError(f"AI called for {title}"))  # noqa: E731

# ── 🎒 הרשימה של מאור: שם אירוע → מה מגיע ─────────────────────────────────────
TABLE = [
    ("מעבדת מערכות ספרתיות - רון חיים", "🔬 10:00 מעבדת מערכות ספרתיות - רון חיים: נעליים סגורות · מחשב נייד + מטען · ערכת מעבדה / רכיבים"),
    ("מעבדה בפיזיקה", "🔬 10:00 מעבדה בפיזיקה: נעליים סגורות"),
    ("מבחן: מבוא להסתברות - מועד 1", "📝 10:00 מבחן במבוא להסתברות: תעודת סטודנט / ת\"ז · מחשבון · דף נוסחאות · עטים, מחק, שעון, מים · ההתאמות: סטופר, מרקרים, סרגל"),
    ("בוחן באנליזה נומרית", "✏️ יש בוחן באנליזה נומרית בשעה 10:00"),
    ("📅 תור לרופא שיניים", "🩺 10:00 תור לרופא שיניים: ת\"ז / כרטיס מכבי · רשום את השאלות שרצית לשאול"),
    ("פסיכיאטר - ד\"ר כהן", "🩺 10:00 פסיכיאטר - ד\"ר כהן: ת\"ז / כרטיס מכבי"),
    ("שיננית", "🩺 10:00 שיננית: ת\"ז / כרטיס מכבי"),
    ("קאוצ'ינג עם אבי", "🎯 10:00 קאוצ'ינג עם אבי: ודא שהכנת את המטלה שהוא נתן לך"),
    ("קאוצר", "🎯 10:00 קאוצר: ודא שהכנת את המטלה"),
    ("🏃 ריצה", "🏃 10:00 ריצה: 20° — קצר + שכבה דקה"),
]
for title, expect in TABLE:
    def run(title=title, expect=expect):
        lines = R().reminders(TUE, [ev(10, title)], [], wx(), ai=NO_AI)
        assert len(lines) == 1 and lines[0].startswith(expect), lines
    check(f"«{title}» → {expect[:60]}", run)

for title in ("פסיכולוגית", "🛡️ משמרת צהריים — מאבטח", "מבנה מחשבים (הרצאה) - בוסני רם", "אנליזה נומרית (תרגול) - דליה",
              "להעביר לרותי שכר דירה"):
    def run(title=title):
        assert R().reminders(TUE, [ev(10, title)], [], wx(), ai=NO_AI) == []
    check(f"«{title}» → בלי תזכורת (ובלי AI)", run)

def birthday():
    lines = R().reminders(TUE, [], ["יום הולדת לדני"], wx(), ai=NO_AI)
    assert lines == ["🎂 יום הולדת ל-דני — לא לשכוח לברך"] or lines == ["🎂 יום הולדת לדני — לא לשכוח לברך"], lines
check("«יום הולדת לדני» (כל היום) → 🎂 לא לשכוח לברך", birthday)

def no_study():
    assert R().reminders(TUE, [], ["חופשת חנוכה"], wx(), ai=NO_AI) == ["🏖️ אין לימודים — חופשת חנוכה"]
    assert R().reminders(date(2026, 11, 21), [], ["חופשת חנוכה"], wx(day=date(2026, 11, 21)), ai=NO_AI) == []  # שבת — ממילא אין
check("«חופשת חנוכה» ביום לימודים → 🏖️ אין לימודים; בשבת — כלום", no_study)

def run_weather():
    rainy = wx(temp=12, feels=9, rain=70)
    line = R().reminders(TUE, [ev(18, "ריצה")], [], rainy, ai=NO_AI)[0]
    assert line == "🏃 18:00 ריצה: 12°, 70% גשם — שכבה ארוכה + כפפות", line
check("🏃 ריצה → מזג האוויר בשעת הריצה + מה ללבוש", run_weather)

def unknown_uses_ai_only_when_needed():
    asked = []
    def ai(title):
        asked.append(title)
        return "דרכון + כרטיס טיסה" if "טיסה" in title else None
    lines = R().reminders(TUE, [ev(6, "טיסה לאתונה"), ev(12, "פגישה עם שירה"), ev(15, "🛡️ משמרת")], [], wx(), ai=ai)
    assert lines == ["🎒 06:00 טיסה לאתונה: דרכון + כרטיס טיסה"] and asked == ["טיסה לאתונה", "פגישה עם שירה"]
check("אירוע לא ברשימה → AI זול, ומופיע רק כשבאמת צריך משהו (טיסה כן, פגישה לא); משמרת — בלי AI", unknown_uses_ai_only_when_needed)

def ai_without_key_is_silent():
    os.environ.pop("OPEN_API_KEY", None)
    assert R().ai_bring("טיסה לאתונה") is None
check("בלי OPEN_API_KEY — AI מדולג בשקט (לא נכשל)", ai_without_key_is_silent)

def evening():
    r = R()
    assert r.evening_message(TUE, []) is None  # אין אירוע — אין הודעה ב-22:00
    msg = r.evening_message(TUE, r.reminders(TUE, [ev(9, "מבחן: הסתברות - מועד 1")], [], wx(), ai=NO_AI))
    assert msg.startswith("🌙 <b>מחר · שלישי 17.11</b>\n📝 09:00 מבחן בהסתברות:"), msg
check("22:00: «🌙 מחר · שלישי 17.11» + השורות; אין כלום — לא שולחים", evening)

# ── ⛅ מזג אוויר מעשי ─────────────────────────────────────────────────────────
def weather_plain_day():
    text = R().practical_weather(TUE, [], wx(temp=22))
    assert text == "⛅ <b>מזג אוויר:</b> 22°–22°", text  # בלי זריחה/שקיעה, בלי "קח", בלי התראות
check("⛅ יום רגיל → שורה אחת, בלי מספרים מיותרים (זריחה/שקיעה) ובלי התראות", weather_plain_day)

def weather_take():
    text = R().practical_weather(TUE, [], wx(temp=13, feels=10, rain=60))
    assert "קח: ☂️ מטרייה · 🧥 מעיל" in text, text
    assert "💧 מים וכובע" in R().practical_weather(TUE, [], wx(temp=31))
check("⛅ גשם/קר → «קח: ☂️ מטרייה · 🧥 מעיל»; חם → 💧 מים וכובע", weather_take)

def weather_at_his_hours():
    w = wx(temp=22)
    h = w["hourly"]
    h["temperature_2m"][h["time"].index("2026-11-17T23:00")] = 15
    h["precipitation_probability"][h["time"].index("2026-11-17T23:00")] = 50
    text = R().practical_weather(TUE, [ev(14, "🛡️ משמרת צהריים", hours=9)], w)
    assert "🚪 14:00 22° · 🏠 23:00 15° ☔ 50%" in text, text
check("⛅ לפי השעות שלו: יציאה למשמרת ב-14:00 וחזרה ב-23:00", weather_at_his_hours)

def weather_alerts():
    text = R().practical_weather(TUE, [], wx(temp=35, wind=45))
    assert "⚠️ 🔥 חם מאוד — עד 35°" in text and "⚠️ 💨 רוח חזקה — 45 קמ\"ש" in text
    assert "⚠️" not in R().practical_weather(TUE, [], wx(temp=24))
check("⛅ התראות רק כשיש (חום / רוח / קור / גשם חזק)", weather_alerts)

# ── התדריך: בלי monday ────────────────────────────────────────────────────────
def no_monday():
    import bot
    src = open(bot.__file__, encoding="utf-8").read()
    assert "api.monday.com" not in src and "MONDAY_API_TOKEN" not in src
    assert hasattr(bot, "build_evening") and hasattr(bot, "get_today_reminders")
check("התדריך: בלי דדליינים של monday (אין קריאה ל-monday); יש 🎒 להיום ומצב 22:00", no_monday)

def morning_section():
    import bot
    text = bot.get_today_reminders(TUE, ([ev(9, "מבחן: הסתברות - מועד 1")], []), wx())
    assert text.startswith("🎒 <b>להיום:</b>\n📝 09:00 מבחן בהסתברות:"), text
    assert bot.get_today_reminders(TUE, ([ev(9, "פסיכולוגית")], []), wx()) == ""
check("05:30: שורת «🎒 להיום» רק כשיש משהו", morning_section)

def workflow_has_evening_mode():
    path = os.path.join(os.environ.get("DEBI_DIR") or os.path.dirname(os.path.abspath(__file__)), ".github/workflows/main.yml")
    wf = open(path, encoding="utf-8").read()
    assert "mode:" in wf and "--evening" in wf and "schedule:" not in wf  # 16.11: רק cron-job.org (בלי schedule כפול)
check("ה-workflow: רק workflow_dispatch עם mode (cron-job.org) — בלי schedule שהיה שולח פעמיים", workflow_has_evening_mode)

print("\nok" if not FAILED else f"\n{len(FAILED)} נכשלו:\n" + "\n".join(f"· {f}" for f in FAILED))
sys.exit(1 if FAILED else 0)
