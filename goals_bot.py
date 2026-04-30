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
# ─── חלק 1: אינטגרציה עם גוגל ──────────────
# ==========================================
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']
TASKS_SCOPES = ['https://www.googleapis.com/auth/tasks']

def get_calendar_service():
    creds_json = os.getenv("ARCHITECT_GOOGLE_JSON") 
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
        
        events_result = service.events().list(
            calendarId=calendar_id, timeMin=now, timeMax=end_of_day, 
            singleEvents=True, orderBy='startTime').execute()
        events = events_result.get('items', [])
        
        if not events: return "הלוז פנוי לחלוטין."
        
        event_list = []
        for e in events:
            summary = e.get('summary', 'Unknown')
            start = e['start'].get('dateTime')
            end = e['end'].get('dateTime')
            if start and end:
                start_time = start.split('T')[1][:5]
                end_time = end.split('T')[1][:5]
                event_list.append(f"[{start_time} - {end_time}]: תפוס - {summary}")
            else:
                event_list.append(f"[כל היום]: תפוס - {summary}")
                
        return "\n".join(event_list)
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

# ==========================================
# ─── חלק 2: מנוע AI (חוקי התנגשות ופיצול) ──
# ==========================================
def generate_smart_schedule(existing_events):
    now = datetime.datetime.now()
    weekday = now.weekday()
    
    # חוק מנוחה בשבת (5 = שבת)
    if weekday == 5:
        return {
            "calendar_updates": [],
            "opening_shoutout": "מה קורה אחי. שבת היום! אין משימות, אין יעדים, רק לנוח ולהטעין מצברים. שבת שלום!"
        }

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    today_str = now.strftime("%Y-%m-%d")
    
    # פיצול מטרות חכם לפי ימים כדי למנוע עומס
    focus_map = {
        0: "גיטרה ודיקציה",           # שני
        1: "פיתוח אפליקציה",         # שלישי
        2: "דיבור לקהל ודיקציה",      # רביעי
        3: "גיטרה ופיתוח אפליקציה",  # חמישי
        4: "השלמות לשבוע (גיטרה או אפליקציה)", # שישי
        6: "ארגון מטרות, גיטרה"       # ראשון
    }
    todays_focus = focus_map.get(weekday, "גיטרה")

    prompt = f"""
    אתה ה-Architect, מאמן ביצועים אישי של מאור. טון דיבור: "מה קורה אחי", ישיר, מדרבן.
    
    הלו"ז התפוס של מאור להיום ({today_str}):
    {existing_events}
    
    המטרות להיום בלבד (כדי לא להעמיס על השבוע):
    - מיקוד ראשי להיום: **{todays_focus}**
    - חובות יומיות: אנגלית (10 דק'), בישול בריא (30 דק').
    
    חוקי ברזל למניעת התנגשויות (קריטי! קריטי! קריטי!):
    1. אסור לשבץ שום משימה על גבי השעות שרשומות כ"תפוס" בלו"ז! חפש רק את ה"חורים" (זמן פנוי) בין האירועים.
    2. חסימות ביומן: השאר 15 דקות רווח אחרי אירוע לימודים ו-20 דקות אחרי עבודה לנסיעות והתארגנות.
    3. פיצול: כל סשן של מטרה גדולה יהיה בדיוק חצי שעה. אם צריך, שים 2 סשנים בהפרש של שעות.
    4. שיעורי בית: אם מופיע בלו"ז התפוס אירוע שקשור ללימודים (הרצאה/תרגול/מעבדה), חובה לשבץ חלון של שעה אחת ברצף בשם "שיעורי בית/חזרה" בזמן פנוי בערב או אחה"צ.
    5. אימוני כושר: רק בבוקר! (06:00-08:30). השאר 20 דקות למקלחת לפני הלו"ז הבא.
    6. שנת לילה: אין משימות בין 23:00 ל-06:00.
    
    החזר JSON בלבד במבנה מדויק זה:
    {{
      "calendar_updates": [
        {{
          "title": "גיטרה - סשן 1",
          "description": "חצי שעה של אימון נטו",
          "start": "{today_str}T16:00:00",
          "end": "{today_str}T16:30:00",
          "free_time_context": "שמתי לך חצי שעה גיטרה בין התרגול להרצאה."
        }}
      ],
      "opening_shoutout": "מה קורה אחי, הנה המשימות שלך להיום מותאמות בדיוק ללוז."
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an elite, logical performance coach for Maor. JSON output only. Prevent ALL time collisions based on the provided schedule."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" },
            temperature=0.2 # טמפרטורה נמוכה כדי שיהיה מדויק בשעות ולא יהזה
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"calendar_updates": [], "opening_shoutout": "מערכת מגמגמת."}

# ==========================================
# ─── חלק 3: שליחה לטלגרם ───────────────────
# ==========================================
async def main():
    token = os.getenv("TELEGRAM_TOKEN_YEHUDA") # השארתי את השם של הסוד כדי שלא תצטרך לשנות בגיטהאב
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id: 
        print("Missing Telegram Secrets")
        return
        
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
    # התיקון כאן: הוסרה הקריאה הכפולה שגרמה לבוט לשלוח שתי הודעות
    asyncio.run(main())
