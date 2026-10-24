# -*- coding: utf-8 -*-
"""QQ 事件网关 WebSocket 桥接：接收 C2C 单聊消息 → Codex 处理 → 回传 QQ。

流程：
1. 收到 C2C_MESSAGE_CREATE 事件；
2. 校验发送者在白名单内，后台调用 codex exec 处理（同一用户串行）；
3. 处理期间不发任何状态消息（QQ 客户端自带"加载中"动画，不打断它）；
   但超过 SLOW_HINT_DELAY 秒仍无回复时，会补一句轻提示（如"还在弄哦"），避免显得没反应；
4. 完成后把回复分块陆续发送，模拟流式输出（QQ 官方 API 没有消息编辑/流式接口）。
"""
import asyncio
import json
import logging

import websockets

logger = logging.getLogger("codex_qq.bridge")

INTENT_C2C_MESSAGE = 1 << 25  # 单聊（C2C）消息事件
RECONNECT_BASE_DELAY = 3.0
RECONNECT_MAX_DELAY = 60.0
IDENTIFY_OP = 2
HEARTBEAT_OP = 1
HEARTBEAT_ACK_OP = 11
RECONNECT_OP = 7
INVALID_SESSION_OP = 9

# ---- 消息交互策略 ----
# QQ 客户端自带"加载中"提示，处理期间不再发任何状态消息（避免打断原生动画）；
# 回复完成后拆成小块陆续发出，模拟流式打字效果（QQ 官方 API 无消息编辑接口）。
STREAM_CHUNK_SIZE = 150  # 每个流式块的字符数（越小越像打字）
STREAM_CHUNK_DELAY = 0.35  # 块与块之间的发送间隔秒数
SLOW_HINT_DELAY = 30.0  # 处理超过该秒数仍无回复时，发一句"还在弄"提示，避免显得没反应


class QqBridge:
    def __init__(self, config, api, runner) -> None:
        self.config = config
        self.api = api
        self.runner = runner
        self._running = False
        self._last_seq = 0

    async def run_forever(self) -> None:
        """主循环：断线自动重连（指数退避）。"""
        self._running = True
        delay = RECONNECT_BASE_DELAY
        while self._running:
            try:
                await self._run_once()
                delay = RECONNECT_BASE_DELAY
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("[QQ] 网关连接异常: %s，%.0fs 后重连", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _run_once(self) -> None:
        token = await self.api.get_access_token()
        url = self.config.ws_url
        headers = {"Authorization": f"QQBot {token}"}
        logger.info("[QQ] 连接事件网关: %s", url)
        async with websockets.connect(
            url,
            additional_headers=headers,
            ping_interval=None,
            close_timeout=10,
            max_size=2 ** 20,
        ) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            hb_interval = ((hello.get("d") or {}).get("heartbeat_interval") or 41250) / 1000.0
            logger.info("[QQ] 网关握手成功，心跳间隔 %.1fs", hb_interval)
            await self._identify(ws, token)
            hb_task = asyncio.create_task(self._heartbeat(ws, hb_interval))
            try:
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    op = msg.get("op")
                    if op == 0:
                        self._last_seq = msg.get("s") or self._last_seq
                        if msg.get("t") == "C2C_MESSAGE_CREATE":
                            await self._on_message(msg.get("d") or {})
                    elif op == HEARTBEAT_ACK_OP:
                        pass  # 心跳 ack
                    elif op == RECONNECT_OP:
                        logger.info("[QQ] 服务端要求重连")
                        break
                    elif op == INVALID_SESSION_OP:
                        logger.warning("[QQ] session 失效，重新 identify")
                        await self._identify(ws, token)
            finally:
                hb_task.cancel()
                try:
                    await hb_task
                except asyncio.CancelledError:
                    pass  # 心跳任务被取消会抛 CancelledError（BaseException），必须接住，否则服务端重连请求会误杀整个桥接
                except Exception:
                    pass

    async def _identify(self, ws, token: str) -> None:
        await ws.send(json.dumps({
            "op": IDENTIFY_OP,
            "d": {
                "token": f"QQBot {token}",
                "intents": INTENT_C2C_MESSAGE,
                "shard": [0, 1],
            },
        }))

    async def _heartbeat(self, ws, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await ws.send(json.dumps({"op": HEARTBEAT_OP, "d": self._last_seq}))
            except Exception:
                return

    # ---------- 消息处理 ----------
    async def _on_message(self, data: dict) -> None:
        author = data.get("author") or {}
        openid = author.get("id") or ""
        content = (data.get("content") or "").strip()
        msg_id = data.get("id") or ""
        if not openid:
            return
        logger.info("[QQ] 收到来自 %s 的消息: %s", openid, content)
        if self.config.allow_uids and openid not in self.config.allow_uids:
            logger.info("[QQ] 忽略未授权用户 %s 的消息", openid)
            return
        if not content:
            await self._safe_send(openid, "🤖 目前只支持文字消息，请发送文字。", msg_id)
            return
        asyncio.create_task(self._process(openid, content, msg_id))

    async def _process(self, openid: str, content: str, msg_id: str = "") -> None:
        state = {"passive_used": False}
        hint_task = asyncio.create_task(self._slow_hint_loop(openid, msg_id, state))
        try:
            try:
                reply = await self.runner.run(openid, content)
            except TimeoutError as e:
                reply = f"⏰ {e}"
            except Exception as e:
                logger.exception("[Codex] 处理消息失败")
                reply = f"❌ 处理失败：{e}"
        finally:
            hint_task.cancel()
            try:
                await hint_task
            except asyncio.CancelledError:
                pass
        await self._stream_reply(openid, reply, msg_id, state)

    async def _slow_hint_loop(self, openid: str, msg_id: str, state: dict) -> None:
        """长任务最小提示：处理超过 SLOW_HINT_DELAY 秒仍无回复时，只发一句人话（不重复）。"""
        try:
            await asyncio.sleep(SLOW_HINT_DELAY)
        except asyncio.CancelledError:
            return
        text = (self.config.slow_hint_text or "……还在弄。小叶你先忙别的去，弄好我叫你。").strip()
        if text:
            await self._safe_send(openid, text, msg_id, state)

    async def _stream_reply(self, openid: str, reply: str, msg_id: str = "", state: dict = None) -> None:
        """把回复拆成小块陆续发送，模拟流式输出。"""
        state = state or {}
        for i, chunk in enumerate(self._split_reply(reply)):
            if i:
                await asyncio.sleep(STREAM_CHUNK_DELAY)
            await self._safe_send(openid, chunk, msg_id, state)

    @staticmethod
    def _split_reply(reply: str) -> list:
        """按行/超长段切块，每块不超过 STREAM_CHUNK_SIZE 字符。"""
        reply = (reply or "").strip()
        if not reply:
            return [""]
        size = STREAM_CHUNK_SIZE
        chunks: list = []
        current = ""
        for line in reply.splitlines(keepends=True):
            if len(line) > size:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(line[i:i + size] for i in range(0, len(line), size))
                continue
            if len(current) + len(line) > size:
                chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)
        return chunks

    async def _safe_send(self, openid: str, text: str, msg_id: str = "", state: dict = None) -> bool:
        """同一消息事件只有一次被动回复机会（QQ 去重规则），之后直接走主动消息。"""
        state = state or {}
        use_passive = bool(msg_id) and not state.get("passive_used")
        try:
            await self.api.send_message(openid, text, msg_id if use_passive else "")
            if use_passive:
                state["passive_used"] = True
            return True
        except Exception as e:
            logger.error("[QQ] 发送消息失败: %s", e)
            if msg_id:
                try:
                    await self.api.send_message(openid, text)
                    return True
                except Exception as e2:
                    logger.error("[QQ] 改主动发送仍失败: %s", e2)
            return False



