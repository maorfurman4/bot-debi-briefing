#!/usr/bin/env python3
"""
deby-bot — Task & Calendar Sync
Reads pending Telegram messages, parses with GPT-4o,
writes to Google Calendar, sends Hebrew summary.
Runs twice daily via GitHub Actions (10:00 & 22:00 Israel time).
"""

import os
import json
import re
import logging
from datetime import datetime, timedelta
import pytz
import requests
from openai import OpenAI
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("task_sync")

ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]

openai_client = OpenAI(api_key=OPENAI_API_KEY)
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

PARSE_PROMPT = """You are a Hebrew personal assistant. The user sent you a message in Hebrew.
Today is {today} (DD/MM/YYYY). Current time (Israel): {time}.

Classify the message and extract structured data.

Rules:
- "task" = something to do without a specific time (e.g. "לקנות חלב", "להתקשר לאמא")
  → date = today unless "מחר"(tomorrow) or a specific date is mentioned
  → start_time = null, end_time = null
- "event" = meeting or appointment with a specific time (e.g. "פגישה מחר ב-15:00")
  → extract date and time precisely
  → if no end time given, assume 1 hour duration
- "ignore" = greeting, question, unclear, or not actionable

Respond with ONLY valid JSON:
{{
  "type": "task|event|ignore",
  "title": "short Hebrew title",
  "date": "DD/MM/YYYY",
  "start_time": "HH:MM or null",
  "end_time": "HH:MM or null",
  "notes": "any extra details or empty string"
}}

Message: "{message}"
"""


# ── Telegram ──────────────────────────────────────────────────────────────────

def get_pending_updates() -> list[dict]:
    resp = requests.get(
        f"{TELEGRAM_API}/getUpdates",
        params={"limit": 100, "timeout": 0},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def acknowledge_updates(last_update_id: int):
    requests.get(
        f"{TELEGRAM_API}/getUpdates",
        params={"offset": last_update_id + 1, "limit": 1, "timeout": 0},
        timeout=15,
    )


def send_telegram(text: str):
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=15,
    ).raise_for_status()


# ── GPT-4o Parsing ────────────────────────────────────────────────────────────

def parse_message(text: str) -> dict:
    now = datetime.now(ISRAEL_TZ)
    prompt = PARSE_PROMPT.format(
        today=now.strftime("%d/%m/%Y"),
        time=now.strftime("%H:%M"),
        message=text,
    )
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
    return json.loads(raw)


# ── Google Calendar ───────────────────────────────────────────────────────────

def _get_calendar_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/calendar"]
    )
    return build("calendar", "v3", credentials=creds)


def _parse_date(date_str: str) -> str:
    """DD/MM/YYYY → YYYY-MM-DD"""
    parts = date_str.split("/")
    day, month = parts[0], parts[1]
    year = parts[2] if len(parts) == 3 else str(datetime.now().year)
    if len(year) == 2:
        year = "20" + year
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def add_to_calendar(parsed: dict) -> str:
    service = _get_calendar_service()
    date_iso = _parse_date(parsed["date"])
    title = parsed["title"]
    notes = parsed.get("notes", "")

    if parsed["type"] == "task" or not parsed.get("start_time"):
        event_body = {
            "summary": f"📌 {title}",
            "description": notes,
            "start": {"date": date_iso},
            "end": {"date": date_iso},
        }
        date_display = parsed["date"]
        time_display = "כל היום"
    else:
        tz_str = "Asia/Jerusalem"
        start_dt = datetime.strptime(f"{date_iso} {parsed['start_time']}", "%Y-%m-%d %H:%M")
        start_dt = ISRAEL_TZ.localize(start_dt)

        if parsed.get("end_time"):
            end_dt = datetime.strptime(f"{date_iso} {parsed['end_time']}", "%Y-%m-%d %H:%M")
            end_dt = ISRAEL_TZ.localize(end_dt)
        else:
            end_dt = start_dt + timedelta(hours=1)

        event_body = {
            "summary": f"📅 {title}",
            "description": notes,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": tz_str},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz_str},
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 30}],
            },
        }
        date_display = parsed["date"]
        time_display = f"{parsed['start_time']}–{end_dt.strftime('%H:%M')}"

    service.events().insert(calendarId="primary", body=event_body).execute()
    return f"{date_display} {time_display}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    updates = get_pending_updates()

    # Filter only text messages from the expected chat
    messages = [
        u for u in updates
        if u.get("message", {}).get("text")
        and str(u["message"]["chat"]["id"]) == str(CHAT_ID)
    ]

    if not messages:
        logger.info("No pending messages.")
        return

    added, failed, ignored = [], [], []

    for update in messages:
        text = update["message"]["text"]
        if text.startswith("/"):
            ignored.append(text)
            continue

        logger.info(f"Processing: {text!r}")
        try:
            parsed = parse_message(text)
            if parsed["type"] == "ignore":
                ignored.append(text)
                logger.info("Ignored.")
                continue

            when = add_to_calendar(parsed)
            icon = "📌" if parsed["type"] == "task" else "📅"
            added.append(f'{icon} "{parsed["title"]}" — {when}')
            logger.info(f"Added: {parsed['title']}")

        except Exception as e:
            logger.error(f"Failed: {e}")
            failed.append(f'• "{text[:50]}" — {e}')

    # Acknowledge all processed updates
    last_id = updates[-1]["update_id"]
    acknowledge_updates(last_id)

    # Build summary
    total = len(messages) - len(ignored)
    lines = [f"✅ <b>עיבדתי {total} הודעות:</b>\n"]

    if added:
        lines.append("➕ <b>נוספו ליומן:</b>")
        lines.extend(added)

    if failed:
        lines.append("\n⚠️ <b>לא הצלחתי לעבד:</b>")
        lines.extend(failed)

    if not added and not failed:
        lines.append("לא היו הודעות לעיבוד.")

    send_telegram("\n".join(lines))
    logger.info("Done.")


if __name__ == "__main__":
    main()
