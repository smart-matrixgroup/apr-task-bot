import os
import json
import tempfile
import httpx
from datetime import datetime
import anthropic
import openai

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
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
            # supports Tamil+English mix
        )

    os.unlink(tmp_path)
    return transcript.text


def extract_intent(text: str, default_person: str) -> dict:
    """Use Claude to extract structured intent from natural language."""
    today = datetime.now().strftime("%d/%m/%Y")

    prompt = f"""Extract task management intent from this message. Return only valid JSON.

Today: {today}
Sender: {default_person}

Message: "{text}"

JSON format:
{{
  "action": "update_task" | "get_report" | "unknown",
  "person": "SANJEEV" | "SHIAN",
  "task_number": "05",        // 2-digit string, only for update_task
  "status": "DONE" | "PENDING" | "IN PROGRESS" | "HOLD",  // only for update_task
  "finish_date": "28/08/2026" // DD/MM/YYYY, only when status=DONE, else ""
}}

Rules:
- Default person is {default_person} unless another name is mentioned
- Tamil words: "mudinjuchu"/"done" → DONE, "pending"/"iruku" → PENDING
- "report"/"summary"/"ena pending" → get_report
- task number can be spoken as "task five", "5th task", "task 05"

Examples:
- "task 5 done" → {{"action":"update_task","person":"{default_person}","task_number":"05","status":"DONE","finish_date":"{today}"}}
- "shian task 3 pending" → {{"action":"update_task","person":"SHIAN","task_number":"03","status":"PENDING","finish_date":""}}
- "ena pending iruku" → {{"action":"get_report","person":"{default_person}"}}
- "sanjeev report" → {{"action":"get_report","person":"SANJEEV"}}"""

    msg = anthropic_client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())
