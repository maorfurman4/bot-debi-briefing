"""16.11: כתובת היומן הפרטית לא בקוד — רק בסוד GOOGLE_CALENDAR_ICS_1. DEBI_DIR=<תיקייה> — על קוד אחר."""
import os
import re
import sys
DIR = os.environ.get("DEBI_DIR") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
FAILED = []
def check(name, fn):
    try:
        fn()
        print(f"✅ {name}")
    except Exception as ex:  # noqa: BLE001
        FAILED.append(name)
        print(f"❌ {name} — {type(ex).__name__}: {ex}")

def no_url_in_code():
    for f in ("bot.py", "remind.py", "README.md", "CLAUDE.md"):
        path = os.path.join(DIR, f)
        if os.path.exists(path):
            assert not re.search(r"calendar/ical/[^\s\"']+/private-", open(path, encoding="utf-8").read()), f
check("אין כתובת ICS פרטית בקוד", no_url_in_code)

def workflow_passes_secret():
    wf = open(os.path.join(DIR, ".github/workflows/main.yml"), encoding="utf-8").read()
    assert "GOOGLE_CALENDAR_ICS_1: ${{ secrets.GOOGLE_CALENDAR_ICS_1 }}" in wf
check("ה-workflow מעביר את GOOGLE_CALENDAR_ICS_1", workflow_passes_secret)

def missing_secret_reported():
    os.environ.pop("GOOGLE_CALENDAR_ICS_1", None)
    import bot
    bot.CALENDARS[:] = []
    bot.FAILURES.clear()
    from datetime import date
    bot.get_events(date(2026, 11, 17))
    assert any("GOOGLE_CALENDAR_ICS_1" in f for f in bot.FAILURES)
check("בלי הסוד → שורה ב«מה לא עבד» (לא נעלם בשקט)", missing_secret_reported)

print("\nok" if not FAILED else f"\n{len(FAILED)} נכשלו")
sys.exit(1 if FAILED else 0)
