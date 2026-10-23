# 🌅 דבי — תדריך בוקר

בוט טלגרם ששולח כל בוקר הודעה אחת מסודרת להתחלת היום.

## מה בהודעה
1. ברכת בוקר ותאריך
2. מזג אוויר בתל אביב — 08:00 / 13:00 / 18:00, UV, לחות, רוח, זריחה ושקיעה
3. המלצת לבוש (ביום מעבדה — מכנסיים ארוכים ונעליים סגורות)
4. השעה הכי טובה לאימון לפי מזג האוויר והלו"ז
5. מניות שזזו יותר מ-5%
6. משימות מ-Google Tasks
7. הלו"ז של היום מהיומן

## מתי
כל יום בבוקר (GitHub Actions, `.github/workflows/main.yml`). אפשר גם להריץ ידנית: Actions → "תדריך בוקר דבי" → Run workflow.

## קבצים
| קובץ | תפקיד |
|---|---|
| `bot.py` | כל הלוגיקה |
| `requirements.txt` | ספריות פייתון |
| `.github/workflows/main.yml` | התזמון |

## סודות (Settings → Secrets → Actions)
`BOT_TOKEN`, `CHAT_ID`, `OPENAI_API_KEY`, `OPENWEATHER_API_KEY`, `GOOGLE_TASKS_CREDENTIALS`, `GOOGLE_CALENDAR_ICS`, `GOOGLE_CALENDAR_ICS_2`, `GOOGLE_CALENDAR_ICS_3`
