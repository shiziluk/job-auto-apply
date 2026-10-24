# -*- coding: utf-8 -*-
"""QQ 开放平台 API v2 封装：获取 access_token / 发送 C2C 消息。

参考官方文档：https://bot.q.qq.com/wiki/develop/api-v2/
- 获取凭证:  POST https://bots.qq.com/app/getAppAccessToken
- 发送 C2C:  POST {api_base}/v2/users/{openid}/messages  （Authorization: QQBot <token>）
"""
import logging
import time

import httpx

logger = logging.getLogger("codex_qq.qq_api")

GET_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
TOKEN_EARLY_REFRESH_SECONDS = 120  # 官方有效期 7200s，提前刷新


class QQApiError(RuntimeError):
    pass


class QQApi:
    def __init__(self, app_id: str, app_secret: str, base_url: str, http_timeout: int = 20) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self.http_timeout = http_timeout
        self._token = ""
        self._token_expires_at = 0.0

    async def get_access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at:
            return self._token
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"qqbot/{self.app_id}",
        }
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            resp = await client.post(
                GET_TOKEN_URL,
                json={"appId": self.app_id, "clientSecret": self.app_secret},
                headers=headers,
            )
        data = _parse(resp)
        token = data.get("access_token") or ""
        if not token:
            raise QQApiError(f"获取 access_token 失败: {data}")
        expires = int(data.get("expires_in") or 7200)
        self._token = token
        self._token_expires_at = now + max(expires - TOKEN_EARLY_REFRESH_SECONDS, 60)
        logger.info("[QQ] access_token 已刷新，有效期 %ss", expires)
        return token

    async def send_message(self, openid: str, content: str, msg_id: str = "") -> dict:
        """发送 C2C 消息；msg_id 非空表示被动回复（事件后 5 分钟内有效）。"""
        token = await self.get_access_token()
        url = f"{self.base_url}/v2/users/{openid}/messages"
        body = {"content": content, "msg_type": 0}
        if msg_id:
            body["msg_id"] = msg_id
        headers = {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json",
            "User-Agent": f"qqbot/{self.app_id}",
        }
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
        return _parse(resp)


def _parse(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except Exception:
        data = {}
    if resp.status_code >= 400:
        msg = data.get("message") or data.get("msg") or resp.text[:200]
        raise QQApiError(f"HTTP {resp.status_code}: {msg}")
    return data if isinstance(data, dict) else {"data": data}
