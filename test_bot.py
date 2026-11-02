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
def mi(name, deadline="", status="לא התחיל", group="🎯 AMIRNET", planned=""):
    return {"name": name, "deadline": deadline, "status": status, "group": group, "planned": planned}
lines = monday_lines([
    mi("היום", "2026-10-25"), mi("מחר", "2026-10-26"), mi("בעוד 3", "2026-10-28"), mi("בעוד שבוע", "2026-11-01"),
    mi("בעוד 2", "2026-10-27"), mi("בוצע היום", "2026-10-25", "בוצע"), mi("ארכיון", "2026-10-25", group="📦 ארכיון"),
    mi("תקוע", status="תקוע"),
], d)
assert [l.split(" · ")[1].split(" <i>")[0] for l in lines] == ["היום", "מחר", "בעוד 3", "בעוד שבוע", "תקוע"]
assert lines[1].startswith("🔥 <b>מחר — גג להגיש היום</b> · ")
assert lines[2].startswith("⏳ <b>עוד 3 ימים</b> (28/10)") and lines[0].endswith("<i>(🎯 AMIRNET)</i>")
assert monday_lines([], d) == []

# 🔁 שגרה: מתוכננת היום לא נכנסת ל"מתוכנן להיום" (כבר מוצגת למעלה); שגרה שסומנה ✅ לא מוצגת
assert monday_lines([mi("ראשון · להישקל", planned="2026-10-25", group="🔁 שגרה שבועית")], d) == []
bot.get_google_tasks = lambda today: []
bot.ROUTINES[:] = [{"title": "להישקל", "every": "weekly", "days": ["ראשון"]},
                   {"title": "להתגלח", "every": "weekly", "days": ["ראשון"]}]
done = [mi("ראשון · להישקל", status="בוצע", group="📦 ארכיון")]
assert bot.get_tasks(d, done) == "📋 <b>מה צריך לעשות היום:</b>\n🔁 להתגלח"
assert bot.get_tasks(d, None) == "📋 <b>מה צריך לעשות היום:</b>\n🔁 להישקל\n🔁 להתגלח"  # monday נפל — מציגים הכל

# 📌 מתוכנן להיום — בראש החלק של monday; בלי "בוצע"; שם הפרויקט/הקורס מהקבוצה
lines = monday_lines([
    mi("דדליין מחר", "2026-10-26"),
    mi("לעבוד על SMTP", planned="2026-10-25"),
    mi("מטלה 3", planned="2026-10-25", group="🔢 אנליזה נומרית"),
    mi("כבר בוצע", planned="2026-10-25", status="בוצע"),
    mi("מתוכנן למחר", planned="2026-10-26"),
], d)
assert lines[0] == '📌 <b>מתוכנן להיום:</b> <a href="https://t.me/shifts_calmder_bot?start=today">✅ לסמן ביוסי</a>'
assert lines[1:3] == ["• לעבוד על SMTP <i>(🎯 AMIRNET)</i>", "• מטלה 3 <i>(🔢 אנליזה נומרית)</i>"]
assert lines[3].startswith("🔥 <b>מחר — גג להגיש היום</b> · דדליין מחר") and len(lines) == 4

# 🔎 לוחות לפי שם: רק לוחות עם "סטטוס"; הקבוצה היא הפרויקט
asked = []
class FakeResp:
    ok, status_code = True, 200
    def __init__(self, body): self.body = body
    def json(self):
        if "ids" not in self.body["variables"]:
            return {"data": {"boards": [
                {"id": "1", "type": "board", "columns": [{"title": "סטטוס"}]},
                {"id": "2", "type": "board", "columns": [{"title": "Status"}]},          # My first project
                {"id": "3", "type": "sub_items_board", "columns": [{"title": "סטטוס"}]},
                {"id": "4", "type": "document", "columns": [{"title": "Files"}]},
            ]}}
        asked.append(self.body["variables"]["ids"])
        return {"data": {"boards": [{"items_page": {"items": [{"name": "כן", "group": {"title": "🎯 AMIRNET"},
                "column_values": [{"column": {"title": "סטטוס"}, "text": "תקוע"},
                                  {"column": {"title": "דדליין"}, "text": "2026-10-26"},
                                  {"column": {"title": "📅 מתוכנן ל"}, "text": "2026-10-25"}]}]}}]}}
_post = bot.requests.post
bot.requests.post = lambda *a, **k: FakeResp(k["json"])
assert bot.monday_items() == [{"name": "כן", "group": "🎯 AMIRNET", "status": "תקוע", "deadline": "2026-10-26",
                               "planned": "2026-10-25"}]
assert asked == [["1"]]  # פריטים רק מלוחות המשימות, לפי מזהה
bot.requests.post = _post

print("ok")
