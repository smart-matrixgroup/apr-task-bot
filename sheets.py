import os
import json
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Map person name → exact sheet tab name
TAB_MAP = {
    "SANJEEV": "SANJEEV_V1.1",
    "SHIAN": "SHIAN_V1.1",
}

# Column positions (0-indexed): A=0, B=1, C=2, D=3, E=4, F=5
# A=SN, B=ASGN DATE, C=TODO'S, D=REMARK, E=FNSH DATE, F=STATUS
COL_SN = 0
COL_TASK = 2
COL_FNSH = 4
COL_STATUS = 5


def get_service():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds).spreadsheets()


def _get_tab_data(person: str) -> tuple:
    """Returns (service, tab_name, values)"""
    tab = TAB_MAP.get(person.upper(), "SANJEEV_V1.1")
    service = get_service()
    result = service.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{tab}!A:F"
    ).execute()
    return service, tab, result.get("values", [])


def update_task(person: str, task_num: str, status: str, finish_date: str = "") -> bool:
    service, tab, values = _get_tab_data(person)
    task_padded = str(task_num).zfill(2)

    # Status display values matching the sheet dropdown
    status_display = {
        "DONE": "Done",
        "PENDING": "Pending",
        "IN PROGRESS": "In Progress",
        "HOLD": "Hold",
    }.get(status.upper(), status.title())

    for i, row in enumerate(values):
        if not row or len(row) < 1:
            continue
        sn = str(row[COL_SN]).strip().zfill(2)
        if sn == task_padded:
            row_num = i + 1  # 1-indexed

            if not finish_date and status.upper() == "DONE":
                finish_date = datetime.now().strftime("%d/%m/%Y")

            updates = [
                {"range": f"{tab}!F{row_num}", "values": [[status_display]]}
            ]
            if finish_date:
                updates.append({"range": f"{tab}!E{row_num}", "values": [[finish_date]]})

            service.values().batchUpdate(
                spreadsheetId=SHEET_ID,
                body={"valueInputOption": "USER_ENTERED", "data": updates}
            ).execute()
            return True

    return False


def get_report(person: str) -> str:
    _, tab, values = _get_tab_data(person)

    pending, done, hold, in_progress = [], [], [], []

    for row in values:
        if not row or len(row) < 1:
            continue
        sn_raw = str(row[COL_SN]).strip()
        # Skip non-task rows (headers, empty, section titles)
        if not sn_raw.isdigit():
            continue

        sn = sn_raw.zfill(2)
        task_name = row[COL_TASK].strip() if len(row) > COL_TASK else "—"
        status = row[COL_STATUS].strip().lower() if len(row) > COL_STATUS else "pending"

        if status == "done":
            done.append(f"✅ {sn}. {task_name}")
        elif status in ("hold",):
            hold.append(f"⏸ {sn}. {task_name}")
        elif status in ("in progress",):
            in_progress.append(f"🔵 {sn}. {task_name}")
        else:
            pending.append(f"🔴 {sn}. {task_name}")

    lines = [f"<b>📋 {person.upper()} Task Report</b>"]

    if pending:
        lines.append(f"\n<b>🔴 Pending ({len(pending)}):</b>")
        lines.extend(pending[:20])
        if len(pending) > 20:
            lines.append(f"  ...+{len(pending)-20} more")

    if in_progress:
        lines.append(f"\n<b>🔵 In Progress ({len(in_progress)}):</b>")
        lines.extend(in_progress)

    if hold:
        lines.append(f"\n<b>⏸ On Hold ({len(hold)}):</b>")
        lines.extend(hold)

    if done:
        lines.append(f"\n<b>✅ Done ({len(done)}):</b>")
        lines.extend(done[:5])
        if len(done) > 5:
            lines.append(f"  ...+{len(done)-5} more")

    if not any([pending, done, hold, in_progress]):
        lines.append("\nNo tasks found.")

    return "\n".join(lines)
