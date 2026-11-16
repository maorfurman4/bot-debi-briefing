"""16.11: הבוקר מגיע מ-cron-job.org (דרך יהלי); ה-schedule של GitHub רק גיבוי — ולא שולח פעמיים. בלי רשת."""
import os
import yaml

wf = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".github/workflows/main.yml"), encoding="utf-8"))
steps = wf["jobs"]["send-briefing"]["steps"]
assert wf["run-name"] == "דבי ${{ inputs.mode || 'morning' }}"  # הבוקר — "דבי morning" גם ב-dispatch וגם ב-schedule
guard = steps[0]
assert guard["if"] == "github.event_name == 'schedule'" and 'select(.displayTitle == "דבי morning")' in guard["run"]
assert all(s.get("if") == "env.SKIP != '1'" for s in steps[1:])  # כבר נשלח היום — כל השאר מדולג
assert wf["permissions"]["actions"] == "read"
assert wf[True]["schedule"][0]["cron"] == "0 0 * * *" and "mode" in wf[True]["workflow_dispatch"]["inputs"]
print("ok")
