"""
Decision Bot - FastAPI entry point.
Supports:
  - Feishu custom app event webhook
  - Feishu webhook bot
  - Health check
  - Mock mode for local testing
"""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import config
from feishu_client import feishu
from handlers import dispatch_message
from models import init_db
from scheduler import scheduler, setup_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    init_db()
    setup_scheduler()
    scheduler.start()
    print(f"[Startup] Bot mode: {config.BOT_MODE}")
    print(f"[Startup] Database: {config.DATABASE_URL}")
    print(f"[Startup] Server: http://{config.HOST}:{config.PORT}")
    yield
    # Shutdown
    scheduler.shutdown()
    print("[Shutdown] Scheduler stopped.")


app = FastAPI(title="Decision Bot", lifespan=lifespan)


# ---------- Health check ----------

@app.get("/health")
async def health_check():
    return {"status": "ok", "mode": config.BOT_MODE}


# ---------- Feishu Event Webhook (Custom App) ----------

@app.post("/webhook/feishu/event")
async def feishu_event(request: Request):
    """
    Receive Feishu event push.
    Handles:
      - url_verification (challenge response)
      - im.message.receive_v1 (user messages)
    """
    body = await request.json()

    # 1. URL verification (when configuring webhook)
    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge", "")})

    # 2. Parse event
    event = body.get("event", {})
    if not event:
        return JSONResponse({"status": "ignored", "reason": "no_event"})

    msg_type = event.get("message", {}).get("message_type")
    if msg_type != "text":
        return JSONResponse({"status": "ignored", "reason": "non_text_message"})

    # Extract message info
    message_data = event.get("message", {})
    sender = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
    text_content = json.loads(message_data.get("content", "{}")).get("text", "")
    message_id = message_data.get("message_id", "")

    if not sender or not text_content:
        return JSONResponse({"status": "ignored", "reason": "missing_sender_or_text"})

    # Process and reply
    reply_text = await dispatch_message(sender, text_content, message_id)
    await feishu.reply_message(message_id, reply_text)

    return JSONResponse({"status": "ok"})


# ---------- Feishu Webhook Bot endpoint ----------

@app.post("/webhook/feishu/bot")
async def feishu_webhook_bot(request: Request):
    """
    Receive messages from Feishu webhook bot.
    Webhook bots receive simple POST with message content.
    Note: webhook bots can only receive @mentions in groups, not DM.
    """
    body = await request.json()

    # Webhook challenge verification
    if "challenge" in body:
        return JSONResponse({"challenge": body["challenge"]})

    # Parse webhook payload
    text = ""
    sender = "webhook_user"

    # Try different payload formats
    if "content" in body and isinstance(body["content"], dict):
        text = body["content"].get("text", "")
    elif "text" in body:
        text = body["text"]

    if not text:
        return JSONResponse({"status": "ignored", "reason": "no_text"})

    # Process
    reply_text = await dispatch_message(sender, text)

    # Webhook bots reply by sending back to their configured webhook URL
    # In practice, webhook bots can't reply directly; they send to the group
    result = await feishu.send_message(sender, reply_text)

    return JSONResponse({"status": "ok", "reply_sent": result})


# ---------- Mock testing endpoint ----------

@app.post("/mock/message")
async def mock_message(request: Request):
    """
    Mock endpoint for local testing without Feishu credentials.
    Request body: {"user_id": "test_user", "text": "想买iPhone，8000"}
    """
    body = await request.json()
    user_id = body.get("user_id", "test_user")
    text = body.get("text", "")

    if not text:
        return JSONResponse({"status": "error", "reason": "text_required"})

    reply_text = await dispatch_message(user_id, text)

    return JSONResponse({
        "status": "ok",
        "user_id": user_id,
        "input": text,
        "reply": reply_text,
    })


# ---------- Main ----------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=False)
