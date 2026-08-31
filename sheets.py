import os
import json
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_service():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds).spreadsheets()


def _find_task_row(values: list, person: str, task_num: str) -> int | None:
    """Returns 1-indexed row number or None."""
    header = f"{person.upper()} TODO LIST"
    task_padded = str(task_num).zfill(2)
    in_section = False

    for i, row in enumerate(values):
        if not row:
            continue
        cell = row[0].strip().upper()

        if cell == header:
            in_section = True
            continue

        if in_section:
            # Hit another section — stop
            if "TODO LIST" in cell and header not in cell:
                break
            # Match task number (col A)
            if str(row[0]).strip().zfill(2) == task_padded:
                return i + 1  # 1-indexed

    return None


def update_task(person: str, task_num: str, status: str, finish_date: str = "") -> bool:
    sheet = get_service()
    result = sheet.values().get(spreadsheetId=SHEET_ID, range="A:F").execute()
    values = result.get("values", [])

    row_num = _find_task_row(values, person, task_num)
    if not row_num:
        return False

    if not finish_date and status.upper() == "DONE":
        finish_date = datetime.now().strftime("%d/%m/%Y")

    updates = []
    if finish_date:
        updates.append({"range": f"E{row_num}", "values": [[finish_date]]})
    updates.append({"range": f"F{row_num}", "values": [[status.upper()]]})

    sheet.values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": updates}
    ).execute()

    return True


def get_report(person: str) -> str:
    sheet = get_service()
    result = sheet.values().get(spreadsheetId=SHEET_ID, range="A:F").execute()
    values = result.get("values", [])

    header = f"{person.upper()} TODO LIST"
    in_section = False
    pending, done, hold = [], [], []

    for row in values:
        if not row:
            continue
        cell = row[0].strip().upper()

        if cell == header:
            in_section = True
            continue

        if in_section:
            if "TODO LIST" in cell and header not in cell:
                break

            task_no_raw = row[0].strip()
            # Skip section sub-headers (non-numeric rows)
            if not task_no_raw.isdigit():
                continue

            task_no = task_no_raw.zfill(2)
            task_name = row[1].strip() if len(row) > 1 else "—"
            status = row[5].strip().upper() if len(row) > 5 else "PENDING"

            if status == "DONE":
                done.append(f"✅ {task_no}. {task_name}")
            elif status in ("HOLD",):
                hold.append(f"⏸ {task_no}. {task_name}")
            else:
                pending.append(f"🔴 {task_no}. {task_name} [{status or 'PENDING'}]")

    lines = [f"<b>📋 {person.upper()} Task Report</b>"]

    if pending:
        lines.append(f"\n<b>🔴 Pending ({len(pending)}):</b>")
        lines.extend(pending[:20])
        if len(pending) > 20:
            lines.append(f"  ... +{len(pending) - 20} more")

    if hold:
        lines.append(f"\n<b>⏸ On Hold ({len(hold)}):</b>")
        lines.extend(hold)

    if done:
        lines.append(f"\n<b>✅ Done ({len(done)}):</b>")
        lines.extend(done[:5])
        if len(done) > 5:
            lines.append(f"  ... +{len(done) - 5} more")

    if not pending and not done and not hold:
        lines.append("\nNo tasks found.")

    return "\n".join(lines)
