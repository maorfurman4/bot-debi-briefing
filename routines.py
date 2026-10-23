"""
משימות קבועות של מאור — דבי מציג בתדריך את מה שחל היום.

every:
  "daily"                       — כל יום
  "weekly",  days=["ראשון", ...] — בימים קבועים בשבוע
  "monthly", day=1               — יום קבוע בחודש (31 בחודש קצר → היום האחרון)
  "yearly",  date="15/03"        — תאריך קבוע בשנה

דוגמאות:
  {"title": "10 דק' אנגלית", "every": "daily"},
  {"title": "כביסה", "every": "weekly", "days": ["ראשון", "רביעי"]},
  {"title": "לשלם שכר דירה", "every": "monthly", "day": 1},
  {"title": "חידוש ביטוח רכב", "every": "yearly", "date": "15/03"},
"""

ROUTINES = [
    # שבת
    {"title": "להתגלח", "every": "weekly", "days": ["שבת"]},
    {"title": "לעשות גבות", "every": "weekly", "days": ["שבת"]},
    {"title": "לקצוץ ציפורניים", "every": "weekly", "days": ["שבת"]},
    {"title": "להכין אוכל לשבוע", "every": "weekly", "days": ["שבת"]},
    {"title": "להכין בגדים לכל השבוע", "every": "weekly", "days": ["שבת"]},
    {"title": "ניקיון חדר", "every": "weekly", "days": ["שבת"]},
    {"title": "החלפת מצעים", "every": "weekly", "days": ["שבת"]},
    # שישי
    {"title": "בדיקת שמן ומים באוטו", "every": "weekly", "days": ["שישי"]},
    {"title": "להכניס לו\"ז ליומן", "every": "weekly", "days": ["שישי"]},
    {"title": "לבדוק שעות עבודה", "every": "weekly", "days": ["שישי"]},
    {"title": "בדיקת חשבון בנק", "every": "weekly", "days": ["שישי"]},
    {"title": "לסדר את הטלפון והגלריה", "every": "weekly", "days": ["שישי"]},
    # ראשון
    {"title": "להישקל", "every": "weekly", "days": ["ראשון"]},
    # שני
    {"title": "לשלוח סידור עבודה", "every": "weekly", "days": ["שני"]},
    # חמישי
    {"title": "בדיקת חשבון השקעות", "every": "weekly", "days": ["חמישי"]},
]
