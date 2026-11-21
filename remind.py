"""🎒 מה להביא / לזכור — לפי שם האירוע ביומן (16.11, הרשימה של מאור, קבועה בקוד — הוא לא רוצה להקליד לבוט).
22:00 — על מחר (הודעה רק אם יש משהו); 05:30 — שורה בתדריך על היום. ⛅ מזג אוויר מעשי — לפי השעות של מאור."""

import json
import os
import re
from datetime import date, datetime, timedelta

import requests

import aura_report

DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]

def _clean(title: str) -> str:
    return " ".join(re.sub(r"[^\w\s\"'״׳:\-–()]", " ", title).split())

def _has(title: str, *words) -> bool:
    return any(w in title for w in words)

# בלי תזכורת: פסיכולוגית, משמרות, הרצאות ותרגולים רגילים, תשלומים (תשלומים — רק ביום עצמו, כמו היום)
SKIP = ("פסיכולוג", "משמרת", "🛡", "הרצאה", "תרגול", "להעביר", "לשלם", "שכר דירה", "שכ\"ד")
LAB = ("נעליים סגורות", "מחשב נייד + מטען", "ערכת מעבדה / רכיבים")
EXAM = ("תעודת סטודנט / ת\"ז", "מחשבון", "דף נוסחאות", "עטים, מחק, שעון, מים", "ההתאמות: סטופר, מרקרים, סרגל")
DOCTOR_WORDS = ("רופא", "פסיכיאטר", "שיננית", "רופא שיניים", "📅 תור", "תור ל", "מרפאה", "בדיקת דם")
DOCTOR = ("ת\"ז / כרטיס מכבי", "רשום את השאלות שרצית לשאול")
NO_STUDY = ("חופשת", "חופשה", "בוטל", "מבוטל", "ביטול", "אין לימודים")

def course_of(title: str) -> str:
    """"מבחן: הסתברות - מועד 1" → "הסתברות"; "בוחן באנליזה נומרית" → "אנליזה נומרית"."""
    rest = re.sub(r"^.*?(?:מבחן|בוחן)\s*:?\s*(?:ב|ל)?", "", _clean(title)).strip()
    return re.split(r"\s+[-–]\s+|\s*\(|\s+מועד", rest)[0].strip() or _clean(title)

def rule(title: str) -> tuple | None:
    """(אימוג'י, מה, רשימה) לפי הכללים; ("skip",) — לא מזכירים; None — לא ברשימה (אולי AI)."""
    t = _clean(title)
    if _has(title, "יום הולדת"):
        who = re.sub(r"^.*?יום הולדת\s*(?:ל-?|של\s+)?", "", t).strip() or "מישהו"
        return "🎂", f"יום הולדת ל{'-' if not who.startswith('ה') else ''}{who} — לא לשכוח לברך", ()
    if _has(title, "מעבדה", "מעבדת"):
        return "🔬", t, LAB
    if _has(title, "בוחן"):
        return "✏️", f"בוחן ב{course_of(title)}", ()
    if _has(title, "מבחן"):
        return "📝", f"מבחן ב{course_of(title)}", EXAM
    if _has(title, "פסיכולוג"):
        return ("skip",)
    if _has(title, *DOCTOR_WORDS):
        return "🩺", t, DOCTOR
    if _has(title, "ריצה", "🏃", "לרוץ"):
        return "🏃", t, ()
    if re.search(r"קא?ו?א?צ['׳]?(?:ינג|ר)|coach", title, re.I):  # קאוצר / קאוצ'ינג / קואצ'ינג / coach
        return "🎯", t, ("ודא שהכנת את המטלה שהוא נתן לך",)
    if _has(title, *SKIP):
        return ("skip",)
    return None

AI_PROMPT = """Maor (Israel) has this calendar event tomorrow: "{title}".
Is there something specific he clearly must bring or prepare for it? Only if it is CLEARLY needed
(e.g. a passport for a flight, a swimsuit for swimming). Regular meetings, classes, work, hangouts — nothing.
Return JSON only: {{"bring": "<at most 6 Hebrew words>" or null}}"""

AI_MODEL = "gpt-5-mini"  # AURA setting AI_MODEL (bot.apply_aura_settings) can replace it

def ai_bring(title: str) -> str | None:
    """gpt-5-mini — רק לאירוע שלא ברשימה, רק השם; אין מפתח — מדלגים בשקט."""
    key = os.getenv("OPEN_API_KEY", "").strip()
    if not key:
        return None
    try:
        resp = requests.post("https://api.openai.com/v1/chat/completions", timeout=40,
                             headers={"Authorization": f"Bearer {key}"},
                             json={"model": AI_MODEL, "reasoning_effort": "low", "response_format": {"type": "json_object"},
                                   "messages": [{"role": "user", "content": AI_PROMPT.format(title=title)}]})
        resp.raise_for_status()
        aura_report.ai(AI_MODEL, resp.json())  # counted for the open "bring" block
        bring = json.loads(resp.json()["choices"][0]["message"]["content"] or "{}").get("bring")
        return str(bring).strip()[:60] if bring else None
    except Exception:
        return None

def weekday_study(day: date) -> bool:
    return day.weekday() in (6, 0, 1, 2, 3)  # ראשון–חמישי

def reminders(day: date, timed: list, all_day: list, wx: dict | None = None, ai=ai_bring) -> list:
    """שורות "🎒": אירוע עם שעה — לפי הכללים (או AI); אירוע של כל היום — יום הולדת / אין לימודים."""
    lines = []
    for name in all_day:
        r = rule(name)
        if r and r[0] == "🎂":
            lines.append(f"🎂 {r[1]}")
        elif _has(name, *NO_STUDY) and weekday_study(day):
            lines.append(f"🏖️ אין לימודים — {_clean(name)}")
    asked = 0
    for start, _, name in sorted(timed):
        hour = start.strftime("%H:%M")
        r = rule(name)
        if r is None:
            if asked >= 4:
                continue
            asked += 1
            bring = ai(name)
            if bring:
                lines.append(f"🎒 {hour} {_clean(name)}: {bring}")
            continue
        if r[0] == "skip":
            continue
        emoji, what, items = r
        if emoji == "✏️":
            lines.append(f"✏️ יש {what} בשעה {hour}")
        elif emoji == "🏃":
            lines.append(f"🏃 {hour} {what}: {run_advice(wx, start)}")
        elif emoji == "🎂":
            lines.append(f"🎂 {what}")
        else:
            lines.append(f"{emoji} {hour} {what}: " + " · ".join(items))
    return lines

def evening_message(day: date, lines: list) -> str | None:
    """22:00 — "🌙 מחר · שלישי 17.11" + השורות; אין כלום — None (לא שולחים)."""
    if not lines:
        return None
    return f"🌙 <b>מחר · {DAYS_HE[day.weekday()]} {day.day}.{day.month}</b>\n" + "\n".join(esc_line(l) for l in lines)

def esc_line(line: str) -> str:
    return line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ── ⛅ מזג אוויר מעשי ─────────────────────────────────────────────────────────

def fetch_weather(lat: float, lon: float, days: int = 2) -> dict:
    resp = requests.get("https://api.open-meteo.com/v1/forecast", timeout=15, params={
        "latitude": lat, "longitude": lon, "timezone": "Asia/Jerusalem", "forecast_days": days,
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,wind_speed_10m",
        "daily": "uv_index_max"})
    resp.raise_for_status()
    return resp.json()

def at_hour(wx: dict | None, when: datetime) -> dict | None:
    if not wx:
        return None
    key = when.strftime("%Y-%m-%dT%H:00")
    h = wx.get("hourly", {})
    if key not in h.get("time", []):
        return None
    k = h["time"].index(key)
    return {name: h[name][k] for name in h if name != "time"}

def run_advice(wx: dict | None, when: datetime) -> str:
    w = at_hour(wx, when)
    if not w:
        return "בדוק מזג אוויר לפני"
    t, rain = w["apparent_temperature"], w["precipitation_probability"] or 0
    wear = "שכבה ארוכה + כפפות" if t < 10 else "ארוך דק" if t < 16 else "קצר + שכבה דקה" if t < 22 else "קצר, ובקבוק מים"
    return f"{w['temperature_2m']:.0f}°" + (f", {rain:.0f}% גשם" if rain >= 30 else "") + f" — {wear}"

def practical_weather(day: date, timed: list, wx: dict) -> str:
    """⛅ טווח אחד, מה לקחת/ללבוש, מזג האוויר ביציאה ובחזרה (לפי האירועים), והתראות — רק כשיש."""
    h = wx["hourly"]
    idx = [k for k, t in enumerate(h["time"]) if t.startswith(day.isoformat()) and 7 <= int(t[11:13]) <= 23]
    temps = [h["temperature_2m"][k] for k in idx]
    feels = [h["apparent_temperature"][k] for k in idx]
    rain = max((h["precipitation_probability"][k] or 0) for k in idx) if idx else 0
    mm = sum((h["precipitation"][k] or 0) for k in idx)
    wind = max((h["wind_speed_10m"][k] or 0) for k in idx) if idx else 0
    uv = (wx.get("daily", {}).get("uv_index_max") or [0])[0] or 0
    lines = [f"⛅ <b>מזג אוויר:</b> {min(temps):.0f}°–{max(temps):.0f}°" if temps else "⛅ <b>מזג אוויר</b>"]
    take = []
    if rain >= 50:
        take.append("☂️ מטרייה")
    if feels and min(feels) < 15:
        take.append("🧥 מעיל" if min(feels) < 11 else "🧥 ג'קט")
    if (temps and max(temps) >= 30) or uv >= 8:
        take.append("💧 מים וכובע")
    if take:
        lines.append("קח: " + " · ".join(take))
    if timed:
        out, back = min(s for s, _, _ in timed), max(e for _, e, _ in timed)
        stops = [(f"🚪 {out:%H:%M}", out)] + ([(f"🏠 {back:%H:%M}", back)] if back - out >= timedelta(hours=2) else [])
        parts = [f"{label} {w['temperature_2m']:.0f}°" + (f" ☔ {w['precipitation_probability']:.0f}%" if (w['precipitation_probability'] or 0) >= 40 else "")
                 for label, when in stops if (w := at_hour(wx, when))]
        if parts:
            lines.append(" · ".join(parts))
    alerts = []
    if temps and max(temps) >= 33:
        alerts.append(f"🔥 חם מאוד — עד {max(temps):.0f}°")
    if feels and min(feels) <= 8:
        alerts.append(f"🥶 קר מאוד — מרגיש {min(feels):.0f}°")
    if wind >= 40:
        alerts.append(f"💨 רוח חזקה — {wind:.0f} קמ\"ש")
    if rain >= 80 and mm >= 10:
        alerts.append(f"⛈️ גשם חזק — {mm:.0f} מ\"מ")
    lines += [f"⚠️ {a}" for a in alerts]
    return "\n".join(lines)

# ── 👕 בגדים לשבוע הבא — מוצ"ש 19:00 (mode=week, 21.11). ארון כללי, תל אביב; לפי "מרגיש כמו", גשם, רוח והיומן ──

SPORT = ("ריצה", "🏃", "לרוץ", "אימון", "כושר", "ספורט", "כדורגל", "כדורסל", "שחייה", "בריכה", "יוגה", "פילאטיס", "gym")
DRESSY = ("חתונה", "בר מצווה", "בת מצווה", "ברית", "חינה", "אירוע", "מסיבה", "דייט", "ראיון", "טקס", "הופעה")

def next_week(today: date) -> list:
    """ראשון–שבת של השבוע הבא (משבת: מחר עד שבת הבאה)."""
    start = today + timedelta(days=(6 - today.weekday()) % 7 or 7)
    return [start + timedelta(days=i) for i in range(7)]

def _base(t: float) -> str:  # לפי ה"מרגיש כמו" הכי חם ביום
    return ("טישרט + מכנס קצר, סנדלים" if t >= 27 else "טישרט + מכנס קצר או ג'ינס" if t >= 23 else
            "טישרט + ג'ינס" if t >= 19 else "חולצה ארוכה / סווטשירט דק + ג'ינס" if t >= 15 else
            "סווטשירט או קפוצ'ון + ג'ינס" if t >= 11 else "סוודר + מעיל + ג'ינס")

def _layer(t: float) -> str | None:  # לשעות הקרות (בוקר / ערב)
    return None if t >= 20 else "סווטשירט דק" if t >= 16 else "קפוצ'ון" if t >= 12 else "ג'קט"

def outfit(day: date, wx: dict, titles: list) -> tuple | None:
    """(טווח טמפ', שורות) ליום אחד; None — אין תחזית ליום הזה."""
    h = wx["hourly"]
    idx = [k for k, t in enumerate(h["time"]) if t.startswith(day.isoformat()) and 7 <= int(t[11:13]) <= 22]
    if not idx:
        return None
    feels = {int(h["time"][k][11:13]): h["apparent_temperature"][k] for k in idx}
    warm = max(feels.values())
    temps = [h["temperature_2m"][k] for k in idx]
    rain = max((h["precipitation_probability"][k] or 0) for k in idx)
    wind = max((h["wind_speed_10m"][k] or 0) for k in idx)
    base = _base(warm)
    cold = {"בבוקר": min(v for k, v in feels.items() if k <= 10), "בערב": min(v for k, v in feels.items() if k >= 18)}
    when = [w for w, v in cold.items() if v <= warm - 4 and _layer(v)]
    if "מכנס קצר" in base and min(cold.values()) < 16:  # 21.11, Maor: no shorts on a hoodie/jacket day
        base = "טישרט + ג'ינס"
    lines = [f"👕 {base}"]
    if when and "מעיל" not in base:
        lines.append(f"🧥 {' ו'.join(when)}: {_layer(min(cold[w] for w in when))}")
    if rain >= 50:
        lines.append(f"☂️ גשם ({rain:.0f}%) — מטרייה ונעליים סגורות")
    elif rain >= 30:
        lines.append(f"☂️ אולי גשם ({rain:.0f}%) — מטרייה קטנה בתיק")
    if wind >= 30 and "מעיל" not in base:
        lines.append(f"💨 רוח ({wind:.0f} קמ\"ש) — ג'קט רוח")
    if any(_has(t, *SPORT) for t in titles):
        lines.append("🎽 אימון ביומן — בגדי ספורט")
    if any(_has(t, *DRESSY) for t in titles):
        lines.append("👔 אירוע ביומן — חולצה מכופתרת + מכנס ארוך")
    if any(_has(t, "מעבדה", "מעבדת") for t in titles):
        lines.append("👟 מעבדה — נעליים סגורות")
    return f"{min(temps):.0f}°–{max(temps):.0f}°", lines

def week_message(today: date, wx: dict | None, events: dict) -> str:
    """events: {יום: (timed, all_day)}. שמות האירועים לא מוצגים — רק מה ללבוש בגללם."""
    days = next_week(today)
    blocks = []
    for d in days:
        timed, all_day = events.get(d, ([], []))
        got = outfit(d, wx, [n for _, _, n in timed] + list(all_day)) if wx else None
        head = f"<b>{DAYS_HE[d.weekday()]} {d.day}.{d.month}</b>"
        blocks.append(f"{head} · {got[0]}\n" + "\n".join(got[1]) if got else f"{head}\nאין תחזית — תציץ בתדריך של הבוקר")
    first, last = days[0], days[-1]
    return (f"👕 <b>בגדים לשבוע הבא · {first.day}.{first.month}–{last.day}.{last.month}</b>\n"
            "<i>תל אביב, לפי התחזית והיומן. סוף השבוע פחות בטוח — התדריך של הבוקר מעדכן.</i>\n\n" + "\n\n".join(blocks))
