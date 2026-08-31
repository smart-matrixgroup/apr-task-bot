import os
import re
import tempfile
from datetime import datetime
import httpx
import openai

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")


async def transcribe_voice(file_id: str) -> str:
    """Download voice from Telegram, transcribe with Whisper."""
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}")
        file_path = r.json()["result"]["file_path"]
        audio = await http.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}")

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(audio.content)
        tmp_path = f.name

    with open(tmp_path, "rb") as af:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=af,
            prompt="This is a task management system. User speaks in Tamil and English. Tasks have numbers like task 1, task 5, task 12."
        )

    os.unlink(tmp_path)
    return transcript.text


def extract_intent(text: str, default_person: str) -> dict:
    """Use GPT-4o-mini to understand natural language intent."""
    today = datetime.now().strftime("%d/%m/%Y")

    system = f"""You are a task management assistant. Extract structured intent from messages.
Today is {today}. The sender is {default_person}.

RULES:
- Understand Tamil, English, or mixed Tamil-English messages
- Tamil words: "mudinjuchu/mudinjichu/done/complete/finish" = DONE status
- Tamil: "pending/iruku/baki/mudiyala" related to listing = get_report
- Tamil: "report/summary/ena iruku/paarunga" = get_report
- Default person is {default_person} unless Sanjeev or Shian is mentioned
- Task numbers can be spoken as "task five", "5th task", "task number 5", "ஐந்தாவது task"

Return ONLY valid JSON (no markdown, no explanation):
{{
  "action": "update_task" | "get_report" | "unknown",
  "person": "SANJEEV" | "SHIAN",
  "task_number": "05",
  "status": "DONE" | "PENDING" | "IN PROGRESS" | "HOLD",
  "finish_date": "31/08/2026",
  "reply": "friendly one-line confirmation in same language as user"
}}

For get_report: only include action, person, reply.
For unknown: only include action, reply with helpful suggestion.
For update_task: include all fields. finish_date only when status=DONE, else empty string."""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=200,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text}
        ]
    )

    import json
    raw = resp.choices[0].message.content.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)
