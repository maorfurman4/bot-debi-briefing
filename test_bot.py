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
where = seen[-1][4]["where"]  # the error carries its place in our own code: paths, lines, names only
assert (where["file"], where["func"]) == ("test_bot.py", "boom") and any(t.startswith("bot.py:") and t.endswith(" station_events") for t in where["trace"]), where

# מזג אוויר: המילה "גשם" בכותרת רק כשיש גשם בתחזית; תחזית שלא נטענה — error בלי חריגה
wx = lambda prob: {"hourly": {"time": [f"{d.isoformat()}T{h:02d}:00" for h in range(24)],
                              "temperature_2m": [18] * 24, "precipitation_probability": [prob] * 24}}
assert bot.weather_facts(d, wx(80), "היום") == ("גשם היום, עד 18 מעלות", {"rain": 1, "rain_prob": 80, "temp_max": 18})
dry = bot.weather_facts(d, wx(10), "היום")
assert "גשם" not in dry[0] and dry[1]["rain"] == 0
bot.load_weather, seen[:] = (lambda: None), []
assert bot.station_weather(d, "היום") is None and [x[2] for x in seen] == ["working", "error"]

# AURA control: Maor's overrides from AURA; none set -> today's constants; wrong type/shape -> ignored; paused -> nothing runs
import asyncio, time as _t
from datetime import time, timedelta
import remind
real = (bot.DAY_START, bot.DAY_END, bot.MIN_GAP, remind.AI_MODEL)
def aura(settings, paused=False):
    bot.DAY_START, bot.DAY_END, bot.MIN_GAP, remind.AI_MODEL = real  # each case starts from the code's constants
    aura_report._cfg["debi"] = (_t.time(), {"paused": paused, "settings": settings})
    bot.apply_aura_settings()
    return bot.DAY_START, bot.DAY_END, bot.MIN_GAP, remind.AI_MODEL
assert aura({}) == (time(8, 0), time(22, 0), timedelta(hours=1), "gpt-5-mini") == real
assert aura({"FREE_HOURS": [9, 21], "MIN_GAP_H": 1.5, "AI_MODEL": ["gpt-6-luna", "x"]}) == (time(9), time(21), timedelta(hours=1.5), "gpt-6-luna")
assert free_gaps([], d) == [(at(9), at(21))]
assert aura({"FREE_HOURS": "abc", "MIN_GAP_H": "abc", "AI_MODEL": "gpt-6-luna"}) == real
assert aura({"FREE_HOURS": [21, 9], "MIN_GAP_H": 0}) == real and aura({"FREE_HOURS": [9]}) == real
aura({}, paused=True)
built = []
bot.build_message = bot.build_evening = bot.build_week = lambda: built.append(1) or "x"
bot.Bot = lambda **k: (_ for _ in ()).throw(AssertionError("sent while paused"))
seen[:] = []
for argv in (["bot.py"], ["bot.py", "--evening"], ["bot.py", "--week"]):
    bot.sys.argv = argv
    asyncio.run(bot.main())
assert built == [] and seen == [], (built, seen)
aura({})

print("ok")
