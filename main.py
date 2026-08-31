import os
import httpx
from fastapi import FastAPI, Request
from dotenv import load_dotenv
from ai_processor import transcribe_voice, extract_intent
from sheets import update_task, get_report

load_dotenv()

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def _build_user_map() -> dict:
    mapping = {}
    sid = os.getenv("SANJEEV_TELEGRAM_ID", "")
    hid = os.getenv("SHIAN_TELEGRAM_ID", "")
    if sid:
        mapping[sid] = "SANJEEV"
    if hid:
        mapping[hid] = "SHIAN"
    return mapping


USER_MAP: dict = {}


async def send(chat_id: int, text: str):
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        })


@app.on_event("startup")
async def startup():
    global USER_MAP
    USER_MAP = _build_user_map()


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message", {})
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    user_id = str(message.get("from", {}).get("id", ""))
    username = message.get("from", {}).get("first_name", "User")
    default_person = USER_MAP.get(user_id, "SANJEEV")

    # /start command
    if message.get("text", "").strip() == "/start":
        await send(chat_id,
            f"👋 Vanakkam {username}!\n\n"
            f"🆔 Your Telegram ID: <code>{user_id}</code>\n\n"
            f"<b>How to use:</b>\n"
            f"🎙 Send a <b>voice message</b> or <b>text</b> like:\n"
            f"• <i>Task 5 done</i>\n"
            f"• <i>Task 12 mudinjuchu</i>\n"
            f"• <i>My pending tasks</i>\n"
            f"• <i>Shian report kudu</i>\n"
            f"• <i>Task 3 in progress</i>"
        )
        return {"ok": True}

    # Get text content
    try:
        if "voice" in message:
            await send(chat_id, "🎙 Ketukiren...")
            text = await transcribe_voice(message["voice"]["file_id"])
            await send(chat_id, f"📝 Kettatu: <i>{text}</i>")
        elif "text" in message:
            text = message["text"].strip()
        else:
            await send(chat_id, "Voice message or text anuppu.")
            return {"ok": True}

        # AI understands intent
        intent = extract_intent(text, default_person)

    except Exception as e:
        await send(chat_id, f"❌ Error: {str(e)}")
        return {"ok": True}

    # Execute intent
    try:
        action = intent.get("action", "unknown")
        ai_reply = intent.get("reply", "")

        if action == "update_task":
            success = update_task(
                person=intent["person"],
                task_num=intent["task_number"],
                status=intent["status"],
                finish_date=intent.get("finish_date", "")
            )
            if success:
                response = (
                    f"✅ Sheet update aayiduchu!\n"
                    f"👤 {intent['person']} → Task {intent['task_number']}: <b>{intent['status']}</b>"
                )
                if ai_reply:
                    response += f"\n\n{ai_reply}"
            else:
                response = f"❌ Task {intent.get('task_number')} kaanom. Task number correct-a irukka?"

        elif action == "get_report":
            report = get_report(intent["person"])
            response = report

        else:
            response = (
                "❓ Puriyala. Ippadi try pannunga:\n"
                "• <i>Task 5 done</i>\n"
                "• <i>Task 12 pending</i>\n"
                "• <i>My pending tasks</i>\n"
                "• <i>Shian report</i>"
            )
            if ai_reply:
                response = ai_reply + "\n\n" + response

        await send(chat_id, response)

    except Exception as e:
        await send(chat_id, f"❌ Sheet update error: {str(e)}")

    return {"ok": True}


@app.get("/")
async def root():
    return {"status": "APR Task Bot running ✅"}
