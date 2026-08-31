import os
import re
import json
import tempfile
from datetime import datetime
import httpx
import openai
 
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
 
 
async def transcribe_voice(file_id: str) -> str:
    """Download voice from Telegram and transcribe with Whisper."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}")
        file_path = r.json()["result"]["file_path"]
        audio = await client.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}")
 
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(audio.content)
        tmp_path = f.name
 
    with open(tmp_path, "rb") as audio_file:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
 
    os.unlink(tmp_path)
    return transcript.text
 
 
def extract_intent(text: str, default_person: str) -> dict:
    """
    Pure regex intent extraction — no API cost, instant response.
    Handles English + Tamil-English mix.
    """
    t = text.lower().strip()
    today = datetime.now().strftime("%d/%m/%Y")
 
    # --- Detect person ---
    person = default_person
    if re.search(r'\bshian\b', t):
        person = "SHIAN"
    elif re.search(r'\bsanjeev\b', t):
        person = "SANJEEV"
 
    # --- Detect report request ---
    report_keywords = [
        "report", "summary", "pending", "what.*pending", "ena.*pending",
        "pending.*iruku", "pending.*task", "status", "overview",
        "mudiyala", "baki", "remaining"
    ]
    if any(re.search(kw, t) for kw in report_keywords):
        # Only if no task number mentioned
        if not re.search(r'\b(\d{1,2})\b', t):
            return {"action": "get_report", "person": person}
 
    # --- Detect task update ---
    # Extract task number — supports: "task 5", "task5", "5th task", "#5", "task number 5"
    task_match = re.search(
        r'(?:task\s*(?:number\s*)?#?\s*(\d{1,2}))|(?:#(\d{1,2}))|(?:(\d{1,2})\s*(?:st|nd|rd|th)?\s*task)',
        t
    )
 
    if task_match:
        task_num = next(g for g in task_match.groups() if g is not None)
        task_num = str(int(task_num)).zfill(2)
 
        # Detect status
        status = "PENDING"  # default
        finish_date = ""
 
        done_keywords = ["done", "complete", "finish", "finished", "mudinjuchu",
                         "mudinja", "completed", "over", "mudinjichu", "ok panni"]
        hold_keywords = ["hold", "wait", "pause", "later"]
        progress_keywords = ["progress", "working", "start", "in progress", "ongoing"]
 
        if any(kw in t for kw in done_keywords):
            status = "DONE"
            finish_date = today
        elif any(kw in t for kw in hold_keywords):
            status = "HOLD"
        elif any(kw in t for kw in progress_keywords):
            status = "IN PROGRESS"
 
        return {
            "action": "update_task",
            "person": person,
            "task_number": task_num,
            "status": status,
            "finish_date": finish_date
        }
 
    # --- Fallback ---
    return {"action": "unknown", "person": person}
 