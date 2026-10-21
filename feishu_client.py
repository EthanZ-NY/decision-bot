"""
Feishu client supporting two modes:
1. Custom App (企业自建应用) - Event Subscription + API calls
2. Webhook Bot (群聊自定义机器人) - Simple webhook POST
3. Mock mode - for local testing without real Feishu credentials
"""
import json
import time
from typing import Optional

import httpx

from config import config


class FeishuClient:
    """Unified Feishu client with mode switching."""

    def __init__(self):
        self.mode = config.BOT_MODE
        self.app_id = config.FEISHU_APP_ID
        self.app_secret = config.FEISHU_APP_SECRET
        self.webhook_url = config.FEISHU_WEBHOOK_URL
        self._access_token: Optional[str] = None
        self._token_expires: float = 0.0

    # ---------- Token management (App mode) ----------

    async def _get_tenant_access_token(self) -> Optional[str]:
        """Fetch tenant access token for custom app."""
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        if not self.app_id or not self.app_secret:
            return None

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            })
            data = resp.json()
            if data.get("code") == 0:
                self._access_token = data["tenant_access_token"]
                self._token_expires = time.time() + data.get("expire", 7200)
                return self._access_token
        return None

    # ---------- Send message ----------

    async def send_message(self, receive_id: str, text: str, msg_type: str = "text") -> dict:
        """Send a message to user or chat."""
        if self.mode == "mock":
            print(f"[MOCK] Send to {receive_id}:\n{text}\n")
            return {"ok": True, "mock": True}

        if self.mode == "webhook" and self.webhook_url:
            return await self._send_webhook(text)

        return await self._send_api(receive_id, text, msg_type)

    async def send_to_webhook(self, text: str) -> dict:
        """Send via webhook bot (independent of BOT_MODE)."""
        if not self.webhook_url:
            return {"ok": False, "error": "webhook_url not configured"}

        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.webhook_url, json=payload, timeout=10)
            return resp.json()

    async def _send_webhook(self, text: str) -> dict:
        """Send via webhook bot (internal, used by send_message in webhook mode)."""
        return await self.send_to_webhook(text)

    async def _send_api(self, receive_id: str, text: str, msg_type: str = "text") -> dict:
        """Send via Feishu OpenAPI (custom app mode)."""
        token = await self._get_tenant_access_token()
        if not token:
            return {"ok": False, "error": "Failed to get access token"}

        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {"Authorization": f"Bearer {token}"}

        if msg_type == "text":
            content = json.dumps({"text": text})
        else:
            content = text  # Assume already JSON string for interactive cards

        params = {"receive_id_type": "open_id"}
        body = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, params=params, json=body, timeout=10)
            return resp.json()

    # ---------- Reply to message ----------

    async def reply_message(self, message_id: str, text: str, msg_type: str = "text") -> dict:
        """Reply to a specific message."""
        if self.mode == "mock":
            print(f"[MOCK] Reply to msg {message_id}:\n{text}\n")
            return {"ok": True, "mock": True}

        if self.mode == "webhook":
            # Webhook bot can't reply to specific messages, just send
            return await self._send_webhook(text)

        token = await self._get_tenant_access_token()
        if not token:
            return {"ok": False, "error": "Failed to get access token"}

        url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
        headers = {"Authorization": f"Bearer {token}"}

        if msg_type == "text":
            content = json.dumps({"text": text})
        else:
            content = text

        body = {"content": content, "msg_type": msg_type}

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=body, timeout=10)
            return resp.json()

    # ---------- Event verification ----------

    @staticmethod
    def verify_event_signature(encrypt_key: str, timestamp: str, nonce: str, body: str) -> str:
        """
        Verify Feishu event signature.
        In production, compute HMAC-SHA256 and compare.
        MVP: simple placeholder - full implementation when encrypt_key is available.
        """
        # TODO: implement proper HMAC-SHA256 verification when encrypt_key is set
        return "placeholder"


# Global client instance
feishu = FeishuClient()
