
import os
import json
import datetime
import asyncio
import openai
from telegram import Bot
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ==========================================
# חלק 1: אינטגרציה עם Google Calendar & Tasks
# ==========================================
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']
TASKS_SCOPES = ['https://www.googleapis.com/auth/tasks']

def get_calendar_service():
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json: return None
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json), scopes=CALENDAR_SCOPES)
    return build('calendar', 'v3', credentials=creds)

def get_tasks_service():
    creds_json = os.getenv("GOOGLE_TASKS_CREDENTIALS")
    if not creds_json: return None
    creds = Credentials.from_authorized_user_info(json.loads(creds_json), TASKS_SCOPES)
    return build('tasks', 'v1', credentials=creds)

def get_todays_events():
    try:
        service = get_calendar_service()
        if not service: return "אין גישה ליומן."
        calendar_id = os.getenv("GOOGLE_CALENDAR_ICS", "primary")
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        end_of_day = (datetime.datetime.utcnow() + datetime.timedelta(hours=24)).isoformat() + 'Z'
        
        events_result = service.events().list(calendarId=calendar_id, timeMin=now, timeMax=end_of_day, singleEvents=True, orderBy='startTime').execute()
        events = events_result.get('items', [])
        if not events: return "אין אירועים ביומן היום."
        return ", ".join([e.get('summary', 'Unknown') for e in events])
    except Exception as e:
        return f"שגיאת קריאת יומן: {e}"

def add_to_calendar(title, start_iso, end_iso):
    try:
        service = get_calendar_service()
        if not service: return False
        event = {
            'summary': title,
            'start': {'dateTime': start_iso, 'timeZone': 'Asia/Jerusalem'},
            'end': {'dateTime': end_iso, 'timeZone': 'Asia/Jerusalem'},
        }
        service.events().insert(calendarId=os.getenv("GOOGLE_CALENDAR_ICS", "primary"), body=event).execute()
        return True
    except Exception as e:
        print(f"Calendar Insert Error: {e}")
        return False

def add_to_tasks(title, notes="נוצר על ידי ה-Architect Bot"):
    try:
        service = get_tasks_service()
        if not service: return False
        task = {'title': title, 'notes': notes}
        service.tasks().insert(tasklist='@default', body=task).execute()
        return True
    except Exception as e:
        print(f"Tasks Insert Error: {e}")
        return False

# ==========================================
# חלק 2: מנוע AI (OpenAI)
# ==========================================
def generate_smart_schedule(existing_events):
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""
    המטרות השבועיות של יהודה:
    1. גיטרה: שעה בשבוע.
    2. אנגלית: 10 דקות ביום.
    3. דיקציה: שעה בשבוע.
    4. בישול: חצי שעה ביום (במקום חטיף).
    5. דיבור לקהל: שעה בשבוע.
    6. פיתוח אפליקציה: גג שעתיים בשבוע.
    7. כושר: 3 אימונים בשבוע (יעד 78 ק"ג).
    
    חוקים:
    - משימות בישול ואנגלית נכנסות ל-Google Tasks.
    - אם ביומן הקיים יש 'תרגול'/'שיעור', הוסף שעה של 'שיעורי בית' ל-Tasks או ל-Calendar ביום פנוי.
    - אל תיצור עומס. הוסף מקסימום 1-2 מטרות ליומן היום לפי העומס.
    
    תאריך היום: {today_str}
    אירועים קיימים היום ביומן: {existing_events}
    
    החזר תשובה אך ורק כ-JSON תקין:
    {{
      "calendar_updates": [{{"title": "...", "start": "{today_str}T18:00:00", "end": "{today_str}T19:00:00"}}],
      "tasks_to_add": ["..."],
      "telegram_message": "הודעת מוטיבציה וסיכום היום בעברית. פנה אלי כ'יהודה'."
    }}
    אם היום עמוס מאוד, השאר את "calendar_updates" ריק [].
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a JSON-only output AI. You are an elite productivity architect for Yehuda."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"calendar_updates": [], "tasks_to_add": [], "telegram_message": "שגיאה בניתוח ה-AI. קח משימה קטנה אחת היום וקדם אותה!"}

# ==========================================
# חלק 3: טלגרם ותזמור המערכת
# ==========================================
async def main():
    token = os.getenv("TELEGRAM_TOKEN_YEHUDA")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id:
        print("Missing Telegram Tokens.")
        return

    bot = Bot(token=token)
    
    # שליפת נתונים וניתוח
    existing_events = get_todays_events()
    plan = generate_smart_schedule(existing_events)

    # עדכון שירותי גוגל
    calendar_msg = "לא הוספו אירועים חדשים ליומן."
    if plan.get('calendar_updates'):
        for event in plan['calendar_updates']:
            add_to_calendar(event['title'], event['start'], event['end'])
        calendar_msg = f"📅 **נוסף ליומן:** {', '.join([e['title'] for e in plan['calendar_updates']])}"

    tasks_msg = "לא הוספו משימות חדשות."
    if plan.get('tasks_to_add'):
        for task in plan['tasks_to_add']:
            add_to_tasks(task)
        tasks_msg = f"✅ **נוסף למשימות:** {', '.join(plan['tasks_to_add'])}"

    # שליחה לטלגרם
    final_message = (
        f"🔥 **בוקר טוב יהודה!**\n\n"
        f"🧠 {plan.get('telegram_message', '')}\n\n"
        f"{calendar_msg}\n"
        f"{tasks_msg}\n\n"
        f"תצליח!"
    )
    
    try:
        await bot.send_message(chat_id=chat_id, text=final_message, parse_mode="Markdown")
        print("Message sent successfully!")
    except Exception as e:
        print(f"Telegram Send Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
