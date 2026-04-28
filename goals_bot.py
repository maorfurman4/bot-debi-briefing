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
# חלק 1: אינטגרציה עם גוגל (שימוש בסודות החדשים!)
# ==========================================
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']
TASKS_SCOPES = ['https://www.googleapis.com/auth/tasks']

def get_calendar_service():
    creds_json = os.getenv("ARCHITECT_GOOGLE_JSON") # משתמש בסוד החדש!
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
        calendar_id = os.getenv("ARCHITECT_CALENDAR_ID").strip() # משתמש בסוד החדש נקי מרווחים!
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        end_of_day = (datetime.datetime.utcnow() + datetime.timedelta(hours=24)).isoformat() + 'Z'
        
        events_result = service.events().list(calendarId=calendar_id, timeMin=now, timeMax=end_of_day, singleEvents=True, orderBy='startTime').execute()
        events = events_result.get('items', [])
        if not events: return "אין אירועים ביומן היום."
        return ", ".join([f"{e.get('summary', 'Unknown')} ({e['start'].get('dateTime', 'All day')})" for e in events])
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
        calendar_id = os.getenv("ARCHITECT_CALENDAR_ID").strip()
        service.events().insert(calendarId=calendar_id, body=event).execute()
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

## ==========================================
# חלק 2 המעודכן: מנוע AI (חוקי פיצול, שבת מנוחה, שיעורי בית)
# ==========================================
def generate_smart_schedule(existing_events):
    # בדיקה אם היום שבת (weekday מחזיר 5 עבור יום שבת)
    # במידה וכן - חותכים הכל ושולחים מנוחה.
    if datetime.datetime.now().weekday() == 5:
        return {
            "calendar_updates": [],
            "tasks_to_add": [],
            "opening_shoutout": "מה קורה אחי. שבת היום! אין משימות, אין יעדים, רק לנוח ולהטעין מצברים. שבת שלום!"
        }

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""
    אתה ה-Architect, מאמן ביצועים אישי של יהודה. טון דיבור: "מה קורה אחי", ישיר, מדרבן.
    
    המטרות של יהודה ואופן הפיצול שלהן:
    - מטרות גדולות: גיטרה, דיקציה, דיבור לקהל, פיתוח אפליקציה. 
    - משימות יומיומיות: אנגלית (10 דק'), בישול בריא (30 דק').
    
    חוקי הברזל לבניית הלו"ז של היום (קריטי!):
    1. שיטת הפיצול (Chunking): אסור לשבץ שעה ברצף למטרות הגדולות! כל סשן של גיטרה/דיקציה/דיבור/אפליקציה יהיה בדיוק **חצי שעה**. 
    2. פיזור שבועי ומינון יומי: אל תכניס את הכל היום. בחר **גג 1 או 2 בלוקים של חצי שעה** מהמטרות הגדולות להיום.
    3. שיעורי בית - יוצא מן הכלל: אם מופיעה ביומן המילה "תרגול", חובה לשבץ היום בלוק של **שעה שלמה ברצף** בשם "שיעורי בית/חזרה על התרגול".
    4. חסימות ביומן וזמני מעבר: "הרצאה" / "תרגול" / עבודה הם קירות בטון. אי אפשר לשים משימות עליהם. השאר 15 דקות רווח אחרי לימודים ו-20 דקות אחרי עבודה להתארגנות ונסיעות.
    5. אימוני כושר: רק בבוקר! (06:00-08:30). השאר 20 דקות למקלחת לפני המשימה הבאה/הלימודים.
    6. שנת לילה: בלי משימות בין 23:00 ל-06:00.
    
    הלו"ז הקיים של יהודה להיום: {existing_events}
    
    החזר JSON בלבד במבנה:
    {{
      "calendar_updates": [
        {{
          "title": "גיטרה - סשן 1",
          "description": "חצי שעה של אימון נטו",
          "start": "{today_str}T16:00:00",
          "end": "{today_str}T16:30:00",
          "free_time_context": "שמתי לך חצי שעה של גיטרה אחרי שחזרת מהלימודים ונחת."
        }}
      ],
      "tasks_to_add": [],
      "opening_shoutout": "מה קורה אחי, הנה המשימות שלך להיום."
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an elite, logical performance coach for Yehuda. JSON output only. Follow spacing and chunking rules perfectly."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"calendar_updates": [], "tasks_to_add": [], "opening_shoutout": "מה קורה אחי, המערכת קצת מגמגמת הבוקר."}
# ==========================================
# חלק 3: שליחה לטלגרם
# ==========================================
async def main():
    token = os.getenv("TELEGRAM_TOKEN_YEHUDA")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id: return
    bot = Bot(token=token)
    
    existing_events = get_todays_events()
    plan = generate_smart_schedule(existing_events)

    message_parts = [plan.get('opening_shoutout', "מה קורה אחי, הנה הלוז:")]
    
    if plan.get('calendar_updates'):
        message_parts.append("\n📅 **מה הולך לקרות היום:**")
        for event in plan['calendar_updates']:
            success = add_to_calendar(event['title'], event['start'], event['end'])
            start_time = event['start'].split('T')[1][:5]
            status_icon = "✅" if success else "❌"
            message_parts.append(
                f"{status_icon} **{start_time} - {event['title']}**\n"
                f"📝 {event.get('description', '')}\n"
                f"⏰ {event.get('free_time_context', '')}\n"
            )
    else:
        message_parts.append("\nהיומן מלא או שצריך מנוחה. תתמקד במה שיש!")

    message_parts.append("\nמקווה שתתמיד ותעשה הכל, אני כאן.")
    
    try:
        await bot.send_message(chat_id=chat_id, text="\n".join(message_parts), parse_mode="Markdown")
    except Exception as e:
        print(f"Telegram Send Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
