
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
    אתה ה-Architect, מאמן ביצועים אישי וחבר קרוב של יהודה.
    הטון שלך: "מה קורה אחי", ישיר, מדרבן, בלי מילים מיותרות ובלי "בוטיות".
    
    המטרות של יהודה:
    1. גיטרה (שעה בשבוע), אנגלית (10 דק' ביום), דיקציה (שעה בשבוע), בישול (30 דק' ביום - לעודד במקום חטיף), דיבור לקהל (שעה בשבוע), פיתוח אפליקציה (גג שעתיים בשבוע), כושר (3 פעמים בשבוע).
    
    משימה קריטית:
    - אל תשים את האנגלית והבישול ב-Tasks! מצא להם חלון זמן פנוי היום ושבץ אותם ב-Calendar (calendar_updates).
    - לכל משימה שאתה מוסיף, תן תיאור קצר של "למה זה חשוב" או "איך לבצע".
    - תנתח את הלו"ז הקיים: {existing_events}.
    
    החזר JSON במבנה הזה בלבד:
    {{
      "calendar_updates": [
        {{
          "title": "אנגלית - 10 מילים",
          "description": "להרחיב אוצר מילים כדי לשלוט בשפה",
          "start": "{today_str}T10:00:00",
          "end": "{today_str}T10:10:00",
          "free_time_context": "יש לך חלון בין הפגישות בבוקר"
        }}
      ],
      "tasks_to_add": [],
      "opening_shoutout": "מה קורה אחי, הנה המשימות שלך להיום לקידום המטרות שלך."
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a sharp, casual, and motivating performance coach for your brother Yehuda. JSON output only."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"calendar_updates": [], "tasks_to_add": [], "opening_shoutout": "מה קורה אחי, המערכת קצת מגמגמת אבל אל תעצור. תן עבודה היום!"}
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

    # בניית ההודעה לטלגרם
    message_parts = [plan.get('opening_shoutout', "מה קורה אחי, הנה המשימות שלך להיום לקידום המטרות שלך.")]
    
    if plan.get('calendar_updates'):
        message_parts.append("\n📅 **מה בתפריט (נכנס ליומן):**")
        for event in plan['calendar_updates']:
            # הוספה ליומן גוגל
            add_to_calendar(event['title'], event['start'], event['end'])
            
            # חילוץ השעה מתוך פורמט ה-ISO (למשל מ- 2024-05-15T08:00:00 לוקח רק את 08:00)
            time_str = event['start'].split('T')[1][:5] 
            
            # עיצוב משימה בודדת בטלגרם
            message_parts.append(
                f"🔹 *{event['title']}* ({time_str})\n"
                f"📝 {event.get('description', '')}\n"
                f"⏰ {event.get('free_time_context', 'זמן פנוי שמצאתי לך')}\n"
            )

    if plan.get('tasks_to_add'):
        message_parts.append("\n✅ **קטנות בדרך (Tasks):**")
        for task in plan['tasks_to_add']:
            add_to_tasks(task)
            message_parts.append(f"• {task}")

    # סגירת ההודעה כמו שביקשת
    message_parts.append("\nמקווה שתתמיד ותעשה הכל, אני כאן.")
    
    # חיבור כל החלקים להודעה אחת שלימה
    final_message = "\n".join(message_parts)
    
    try:
        await bot.send_message(chat_id=chat_id, text=final_message, parse_mode="Markdown")
        print("Message sent successfully!")
    except Exception as e:
        print(f"Telegram Send Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
