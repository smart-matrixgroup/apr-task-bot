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

# Map Telegram user IDs → person name
# Fill these in your .env after getting your Telegram ID (send /start to bot)
USER_MAP: dict[str, str] = {}


def _build_user_map() -> dict:
    mapping = {}
    sanjeev_id = os.getenv("SANJEEV_TELEGRAM_ID", "")
    shian_id = os.getenv("SHIAN_TELEGRAM_ID", "")
    if sanjeev_id:
        mapping[sanjeev_id] = "SANJEEV"
    if shian_id:
        mapping[shian_id] = "SHIAN"
    return mapping


async def send_message(chat_id: int, text: str):
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

    # /start — show Telegram ID
    if message.get("text", "").startswith("/start"):
        await send_message(chat_id,
            f"👋 Hello {username}!\n\n"
            f"Your Telegram ID: <code>{user_id}</code>\n\n"
            f"Give this ID to the admin to link your account.\n\n"
            f"Commands:\n"
            f"• Voice/text: <i>Task 5 done</i>\n"
            f"• <i>My pending tasks</i>\n"
            f"• <i>Sanjeev report</i>"
        )
        return {"ok": True}

    # Determine person from user map, default SANJEEV
    default_person = USER_MAP.get(user_id, "SANJEEV")

    # Get transcript
    try:
        if "voice" in message:
            await send_message(chat_id, "🎙 Transcribing...")
            text = await transcribe_voice(message["voice"]["file_id"])
            await send_message(chat_id, f"📝 I heard: <i>{text}</i>")
        elif "text" in message:
            text = message["text"]
        else:
            await send_message(chat_id, "Send a voice message or text.")
            return {"ok": True}

        # Extract intent
        intent = extract_intent(text, default_person)

    except Exception as e:
        await send_message(chat_id, f"❌ Error processing message: {str(e)}")
        return {"ok": True}

    # Execute intent
    try:
        if intent["action"] == "update_task":
            success = update_task(
                person=intent["person"],
                task_num=intent["task_number"],
                status=intent["status"],
                finish_date=intent.get("finish_date", "")
            )
            if success:
                await send_message(chat_id,
                    f"✅ Updated!\n"
                    f"👤 {intent['person']}\n"
                    f"📌 Task {intent['task_number']}\n"
                    f"🔖 Status: {intent['status']}"
                )
            else:
                await send_message(chat_id,
                    f"❌ Task {intent['task_number']} not found for {intent['person']}.\n"
                    f"Check the task number and try again."
                )

        elif intent["action"] == "get_report":
            report = get_report(intent["person"])
            await send_message(chat_id, report)

        else:
            await send_message(chat_id,
                "❓ Didn't understand. Try:\n"
                "• <i>Task 5 done</i>\n"
                "• <i>Task 12 pending</i>\n"
                "• <i>My pending tasks</i>\n"
                "• <i>Shian report</i>"
            )

    except Exception as e:
        await send_message(chat_id, f"❌ Sheet update failed: {str(e)}")

    return {"ok": True}


@app.get("/")
async def root():
    return {"status": "APR Task Bot is running ✅"}
