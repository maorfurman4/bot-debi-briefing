"""בדיקות קצרות: python test_bot.py"""
from datetime import date, datetime

from bot import IL_TZ, GREETINGS, free_gaps, get_greeting

d = date(2026, 10, 25)  # יום ראשון
at = lambda h, m=0: datetime(2026, 10, 25, h, m, tzinfo=IL_TZ)

# חלונות פנויים
assert free_gaps([], d) == [(at(8), at(22))]
assert free_gaps([(at(9), at(12), "a"), (at(12, 30), at(14), "b")], d) == [(at(8), at(9)), (at(14), at(22))]
assert free_gaps([(at(7), at(10), "a"), (at(11, 30), at(21, 30), "b")], d) == [(at(10), at(11, 30))]
assert free_gaps([(at(23), at(23, 30), "late")], d) == [(at(8), at(22))]

# פתיח
assert len(GREETINGS) == 30 and all(g.startswith("בוקר טוב מאור") for g in GREETINGS)
assert get_greeting(date(2026, 1, 31)) == GREETINGS[0]

# דוח כשלונות לא חושף כתובות
import bot
bot.fail("יומן 1", "404 for url: https://calendar.google.com/private-secret/basic.ics")
assert "private-secret" not in bot.FAILURES[-1] and "<url>" in bot.FAILURES[-1].replace("&lt;", "<").replace("&gt;", ">")

# 🗂️ monday: רק דדליין מחר / עוד 3 / עוד שבוע + תקועים; בלי "בוצע" ובלי ארכיון
from bot import monday_lines
def mi(name, deadline="", status="לא התחיל", group="🎯 AMIRNET", planned=""):
    return {"name": name, "deadline": deadline, "status": status, "group": group, "planned": planned}
lines = monday_lines([
    mi("היום", "2026-10-25"), mi("מחר", "2026-10-26"), mi("בעוד 3", "2026-10-28"), mi("בעוד שבוע", "2026-11-01"),
    mi("בעוד 2", "2026-10-27"), mi("בוצע", "2026-10-26", "בוצע"), mi("ארכיון", "2026-10-26", group="📦 ארכיון"),
    mi("תקוע", status="תקוע"),
], d)
assert [l.split(" · ")[1].split(" <i>")[0] for l in lines] == ["מחר", "בעוד 3", "בעוד שבוע", "תקוע"]
assert lines[0].startswith("🔥 <b>מחר — גג להגיש היום</b> · ") and lines[0].endswith("<i>(🎯 AMIRNET)</i>")
assert lines[1].startswith("⏳ <b>עוד 3 ימים</b> (28/10)")
assert monday_lines([], d) == []
# 12.11: פרויקט בלוח העסקים בלי "📅 מתוכנן ל" — לא מזכירים (לא בדדליין ולא בתקוע); מתוכנן — כן; לימודים — כן
biz = lambda name, **k: {**mi(name, **k), "board": "💼 עסקים ופרויקטים"}  # noqa: E731
got = [l.split(" · ")[1].split(" <i>")[0] for l in monday_lines([
    biz("גל 1", deadline="2026-10-26"), biz("תקוע לא מתוכנן", status="תקוע"),
    biz("גל 2", deadline="2026-10-26", planned="2026-10-25"), {**mi("מטלה", "2026-10-26", group="🎲 הסתברות"), "board": "📚 קורסים"}], d)]
assert got == ["גל 2", "מטלה"], got

# 📋 משימות לעשות — רק ביוסי (5.11: הופיעו גם בדבי): לא מתוכנן להיום, לא באיחור, לא דדליין היום, לא שגרה
todo = [mi("לעבוד על SMTP", planned="2026-10-25"), mi("באיחור", "2026-10-20"), mi("היום", "2026-10-25"),
        mi("ראשון · להישקל", planned="2026-10-25", group="🔁 שגרה שבועית")]
assert monday_lines(todo, d) == []
assert not hasattr(bot, "get_tasks") and not hasattr(bot, "todays_routines")
link = '📋 <a href="https://t.me/shifts_calmder_bot?start=today">המשימות של היום — ביוסי</a>'
assert bot.get_monday(d, todo) == "🗂️ <b>monday:</b> אין דדליינים קרובים ואין משימות תקועות ✨\n" + link
assert bot.get_monday(d, [mi("מחר", "2026-10-26")]).startswith("🗂️ <b>monday — דדליינים ותקועים:</b>\n🔥")
assert bot.get_monday(d, None) == link  # monday נפל — רק הקישור

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
assert bot.monday_items() == [{"name": "כן", "board": "", "group": "🎯 AMIRNET", "status": "תקוע", "deadline": "2026-10-26",
                               "planned": "2026-10-25"}]
assert asked == [["1"]]  # פריטים רק מלוחות המשימות, לפי מזהה
bot.requests.post = _post

print("ok")
