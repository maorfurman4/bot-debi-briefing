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
        calendar_id = os.getenv("ARCHITECT_CALENDAR_ID").strip()
        
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        end_of_day = (datetime.datetime.utcnow() + datetime.timedelta(hours=24)).isoformat() + 'Z'
        
        # הדרישה לקבל את השעות אך ורק בשעון ישראל!
        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=now, 
            timeMax=end_of_day, 
            singleEvents=True, 
            orderBy='startTime',
            timeZone='Asia/Jerusalem' 
        ).execute()
        
        events = events_result.get('items', [])
        if not events: return "אין אירועים ביומן. הלוז פנוי לחלוטין."
        
        event_list = []
        for e in events:
            summary = e.get('summary', 'Unknown')
            start = e['start'].get('dateTime')
            end = e['end'].get('dateTime')
            if start and end:
                start_time = start.split('T')[1][:5]
                end_time = end.split('T')[1][:5]
                event_list.append(f"[{start_time}-{end_time}: {summary}]")
            else:
                event_list.append(f"[כל היום: {summary}]")
                
        return " | ".join(event_list)
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
    if datetime.datetime.now().weekday() == 5:
        return {
            "calendar_updates": [], "tasks_to_add": [],
            "opening_shoutout": "מה קורה אחי. שבת היום! אין משימות, אין יעדים, רק לנוח ולהטעין מצברים. שבת שלום!"
        }

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""
    אתה ה-Architect, מאמן ביצועים אישי של יהודה. טון: "מה קורה אחי", ישיר ומדרבן.
    
    מטרות גדולות: גיטרה, דיקציה, דיבור לקהל, פיתוח אפליקציה (בלוקים של חצי שעה בלבד!).
    משימות קטנות: אנגלית (10 דק'), בישול (30 דק').
    
    חוקי ברזל לבניית הלו"ז - קריטי:
    1. קריאת היומן: אלו האירועים שכבר קיימים היום ביומן של יהודה: {existing_events}.
    2. סכנת דריסה: **אסור בשום פנים ואופן לשבץ משימה בתוך השעות של האירועים הקיימים!** אלו קירות בטון.
    3. זמני נסיעה ומעבר (חובה): חובה להשאיר **לפחות 20 דקות ריקות** לפני תחילת כל הרצאה ביומן, ו-20 דקות ריקות אחרי סיום כל הרצאה ביומן (עבור נסיעה הביתה).
    4. עומס שפוי: שים היום **גג מטרה גדולה אחת** של חצי שעה. 
    5. אימון כושר רק בבוקר מוקדם, והשאר תמיד 20 דקות למקלחת לפני המשימה/ההרצאה הבאה.
    
    החזר JSON בלבד:
    {{
      "calendar_updates": [
        {{
          "title": "גיטרה - סשן",
          "description": "חצי שעה אימון",
          "start": "{today_str}T18:00:00",
          "end": "{today_str}T18:30:00",
          "free_time_context": "שמתי את זה כאן כי ראיתי שיש לך רווח אחרי ההרצאה והנסיעה."
        }}
      ],
      "tasks_to_add": [],
      "opening_shoutout": "מה קורה אחי, הנה המשימות להיום."
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a precise AI that NEVER overlaps events. JSON output only."},{"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"calendar_updates": [], "tasks_to_add": [], "opening_shoutout": "שגיאת AI הבוקר."}
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
    
    # "הרנטגן" - כך נדע בוודאות מה הבוט קרא מהיומן
    message_parts.append(f"\n👀 **מה שזיהיתי ביומן שלך לפני השיבוץ:**\n`{existing_events}`\n")
    
    if plan.get('calendar_updates'):
        message_parts.append("📅 **המשימות שהכנסתי לך היום:**")
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
        message_parts.append("\nאין לי אירועים חדשים להוסיף לך היום. יום נקי!")

    message_parts.append("\nמקווה שתתמיד ותעשה הכל, אני כאן.")
    
    try:
        await bot.send_message(chat_id=chat_id, text="\n".join(message_parts), parse_mode="Markdown")
    except Exception as e:
        print(f"Telegram Send Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
