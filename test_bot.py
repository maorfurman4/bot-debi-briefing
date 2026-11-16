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

# 🗂️ monday ירד מהתדריך (16.11, מאור: רעש) — אין יותר קריאות ל-monday מדבי
assert not hasattr(bot, "get_monday") and not hasattr(bot, "monday_items")
assert "monday" not in open(bot.__file__, encoding="utf-8").read().split("# ── Google Calendar")[1]

print("ok")
