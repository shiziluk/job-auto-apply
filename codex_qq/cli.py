# -*- coding: utf-8 -*-
"""codex_qq 命令行入口。

用法（在项目根执行）：
  python -m codex_qq.cli status            # 查看配置与通路状态
  python -m codex_qq.cli bridge            # 启动 QQ 桥接（默认命令）
  python -m codex_qq.cli chat <文本>        # 本地测试 Codex 通路（不经过 QQ）
  python -m codex_qq.cli send <openid> <文本>  # 主动推送一条消息到 QQ
"""
import asyncio
import io
import logging
import os
import sys
import traceback
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from codex_qq.bridge import QqBridge
from codex_qq.codex_runner import CodexRunner
from codex_qq.config import Config
from codex_qq.qq_api import QQApi


def _setup_logging(verbose: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO if verbose else logging.WARNING)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root.addHandler(handler)


def _components():
    cfg = Config()
    api = QQApi(cfg.app_id, cfg.app_secret, cfg.api_base, cfg.http_timeout)
    runner = CodexRunner(cfg.codex_bin, cfg.workdir, cfg.data_dir, cfg.timeout, cfg.persona_file)
    return cfg, api, runner


async def _cmd_status(cfg: Config, api: QQApi, runner: CodexRunner) -> None:
    print("========== QQ↔Codex 桥接状态 ==========")
    print(f"AppID: {cfg.app_id or '(未配置)'}")
    print(f"沙箱: {'是' if cfg.sandbox else '否'}")
    print(f"允许对话的QQ用户: {cfg.allow_uids or '(未配置，将拒绝所有消息)'}")
    print(f"事件网关: {cfg.ws_url}")
    print(runner.status_text())
    print("---------------------------------------")
    if not cfg.configured:
        print("⚠️ 未配置 QQ_BOT_APP_ID / QQ_BOT_APP_SECRET，桥接无法启动。")
        print("   请复制 codex_qq/.env.example 为 codex_qq/.env 并填写。")
        return
    try:
        token = await api.get_access_token()
        print(f"✅ access_token 获取成功（{len(token)} 字符）")
    except Exception as e:
        print(f"❌ access_token 获取失败：{e}")


async def _cmd_chat(runner: CodexRunner, text: str) -> None:
    print("(正在调用 Codex，可能需要一点时间…)")
    reply = await runner.run("local", text)
    print("----- Codex 回复 -----")
    print(reply)


async def _cmd_send(api: QQApi, openid: str, text: str) -> None:
    data = await api.send_message(openid, text)
    print("✅ 已发送", data.get("message") or "")


def _write_crash_report(data_dir: str, exc: BaseException) -> str:
    """把未捕获的桥接崩溃写入 data/crash.log，便于看门狗/人工定位原因。"""
    path = os.path.join(data_dir, "crash.log")
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} 桥接崩溃 =====\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
    except Exception:
        pass
    return path


def main() -> None:
    args = sys.argv[1:]
    cmd = (args[0] if args else "bridge").lower()
    verbose = cmd in ("bridge", "run")
    _setup_logging(verbose)
    cfg, api, runner = _components()
    if cmd in ("status", "-s"):
        asyncio.run(_cmd_status(cfg, api, runner))
    elif cmd == "chat":
        if len(args) < 2:
            print("用法: python -m codex_qq.cli chat <文本>")
            return
        asyncio.run(_cmd_chat(runner, " ".join(args[1:])))
    elif cmd == "send":
        if len(args) < 3:
            print("用法: python -m codex_qq.cli send <openid> <文本>")
            return
        asyncio.run(_cmd_send(api, args[1], " ".join(args[2:])))
    elif cmd in ("bridge", "run"):
        if not cfg.configured:
            asyncio.run(_cmd_status(cfg, api, runner))
            return
        bridge = QqBridge(cfg, api, runner)
        try:
            asyncio.run(bridge.run_forever())
        except KeyboardInterrupt:
            print("\n桥接已停止")
        except BaseException as e:
            # 意外崩溃：把原因写入 data/crash.log 后退出（看门狗会捕获并重启）
            crash_path = _write_crash_report(cfg.data_dir, e)
            print(f"❌ 桥接异常退出，原因已记录: {crash_path}")
            raise
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
