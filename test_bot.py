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

# AURA HQ: תחנה מדווחת working -> done; חריגה מדווחת error וממשיכה למעלה; בלי רשת
import aura_report
seen = []
aura_report.station = lambda b, sid, status, headline=None, metrics=None, *a, **k: seen.append((b, sid, status, headline, metrics))
bot.get_events = lambda day: ([(at(9), at(10), "סודי")], ["גם סודי"])
bot.station_events(d)
assert [(x[0], x[1], x[2]) for x in seen] == [("debi", "calendar", "working"), ("debi", "calendar", "done")]
assert seen[-1][4] == {"calendars": len(bot.CALENDARS), "events": 2, "failed": 0} and "סודי" not in str(seen)

def boom(day):
    raise RuntimeError("boom")
bot.get_events, seen[:] = boom, []
try:
    bot.station_events(d)
    raise AssertionError("the error must propagate")
except RuntimeError:
    pass
assert [x[2] for x in seen] == ["working", "error"]

# מזג אוויר: המילה "גשם" בכותרת רק כשיש גשם בתחזית; תחזית שלא נטענה — error בלי חריגה
wx = lambda prob: {"hourly": {"time": [f"{d.isoformat()}T{h:02d}:00" for h in range(24)],
                              "temperature_2m": [18] * 24, "precipitation_probability": [prob] * 24}}
assert bot.weather_facts(d, wx(80), "היום") == ("גשם היום, עד 18 מעלות", {"rain": 1, "rain_prob": 80, "temp_max": 18})
dry = bot.weather_facts(d, wx(10), "היום")
assert "גשם" not in dry[0] and dry[1]["rain"] == 0
bot.load_weather, seen[:] = (lambda: None), []
assert bot.station_weather(d, "היום") is None and [x[2] for x in seen] == ["working", "error"]

print("ok")
