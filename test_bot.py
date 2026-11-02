"""בדיקות קצרות: python test_bot.py"""
from datetime import date, datetime

from bot import IL_TZ, GREETINGS, free_gaps, get_greeting, todays_routines

d = date(2026, 10, 25)  # יום ראשון
at = lambda h, m=0: datetime(2026, 10, 25, h, m, tzinfo=IL_TZ)

# חלונות פנויים
assert free_gaps([], d) == [(at(8), at(22))]
assert free_gaps([(at(9), at(12), "a"), (at(12, 30), at(14), "b")], d) == [(at(8), at(9)), (at(14), at(22))]
assert free_gaps([(at(7), at(10), "a"), (at(11, 30), at(21, 30), "b")], d) == [(at(10), at(11, 30))]
assert free_gaps([(at(23), at(23, 30), "late")], d) == [(at(8), at(22))]

# משימות קבועות
R = [
    {"title": "daily", "every": "daily"},
    {"title": "sun", "every": "weekly", "days": ["ראשון"]},
    {"title": "mon", "every": "weekly", "days": ["שני"]},
    {"title": "25th", "every": "monthly", "day": 25},
    {"title": "31st", "every": "monthly", "day": 31},
    {"title": "bday", "every": "yearly", "date": "25/10"},
]
assert todays_routines(d, R) == ["daily", "sun", "25th", "bday"]
assert "31st" in todays_routines(date(2026, 11, 30), R)  # נובמבר נגמר ב-30

# פתיח
assert len(GREETINGS) == 30 and all(g.startswith("בוקר טוב מאור") for g in GREETINGS)
assert get_greeting(date(2026, 1, 31)) == GREETINGS[0]

# דוח כשלונות לא חושף כתובות
import bot
bot.fail("יומן 1", "404 for url: https://calendar.google.com/private-secret/basic.ics")
assert "private-secret" not in bot.FAILURES[-1] and "<url>" in bot.FAILURES[-1].replace("&lt;", "<").replace("&gt;", ">")

# 🗂️ monday: היום / מחר / עוד 3 / עוד שבוע + תקועים; בלי "בוצע" ובלי ארכיון
from bot import monday_lines
def mi(name, deadline="", status="לא התחיל", group="g"):
    return {"name": name, "deadline": deadline, "status": status, "group": group, "where": "🎯 AMIRNET"}
lines = monday_lines([
    mi("היום", "2026-10-25"), mi("מחר", "2026-10-26"), mi("בעוד 3", "2026-10-28"), mi("בעוד שבוע", "2026-11-01"),
    mi("בעוד 2", "2026-10-27"), mi("בוצע היום", "2026-10-25", "בוצע"), mi("ארכיון", "2026-10-25", group="📦 ארכיון"),
    mi("תקוע", status="תקוע"),
], d)
assert [l.split(" · ")[1].split(" <i>")[0] for l in lines] == ["היום", "מחר", "בעוד 3", "בעוד שבוע", "תקוע"]
assert lines[2].startswith("⏳ <b>עוד 3 ימים</b> (28/10)") and lines[0].endswith("<i>(🎯 AMIRNET)</i>")
assert monday_lines([], d) == []

print("ok")
