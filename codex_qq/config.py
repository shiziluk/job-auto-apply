# -*- coding: utf-8 -*-
"""codex_qq 配置：读取 codex_qq/.env 与系统环境变量。"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")


def _load_dotenv(path: str) -> None:
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(os.path.join(BASE_DIR, ".env"))


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _default_codex_bin() -> str:
    npm = os.path.join(os.environ.get("APPDATA", ""), "npm", "codex.cmd")
    if os.path.isfile(npm):
        return npm
    return "codex"


class Config:
    """桥接配置（.env 中的值会被同名环境变量覆盖）。"""

    def __init__(self) -> None:
        self.app_id: str = (os.environ.get("QQ_BOT_APP_ID") or "").strip()
        self.app_secret: str = (os.environ.get("QQ_BOT_APP_SECRET") or "").strip()
        self.sandbox: bool = _as_bool(os.environ.get("QQ_BOT_SANDBOX"), False)
        raw_uids = os.environ.get("QQ_ALLOW_UIDS") or ""
        self.allow_uids: list = [u.strip() for u in raw_uids.split(",") if u.strip()]
        self.codex_bin: str = (os.environ.get("CODEX_BIN") or "").strip() or _default_codex_bin()
        self.workdir: str = (os.environ.get("CODEX_WORKDIR") or PROJECT_ROOT).strip()
        self.timeout: int = _as_int(os.environ.get("CODEX_TIMEOUT"), 900)  # 默认 15 分钟
        self.persona_enabled: bool = _as_bool(os.environ.get("PERSONA_ENABLED"), True)
        persona_file = (os.environ.get("PERSONA_FILE") or os.path.join("codex_qq", "persona", "maya.md")).strip()
        self.persona_file: str = (
            persona_file if os.path.isabs(persona_file) else os.path.normpath(os.path.join(PROJECT_ROOT, persona_file))
        )
        self.slow_hint_text: str = (os.environ.get("QQ_SLOW_HINT") or "……还在弄。小叶你先忙别的去，弄好我叫你。").strip()
        self.http_timeout: int = _as_int(os.environ.get("QQ_HTTP_TIMEOUT"), 20)
        self.data_dir: str = DATA_DIR

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    @property
    def ws_url(self) -> str:
        if self.sandbox:
            return "wss://sandbox.api.sgroup.qq.com/websocket"
        return "wss://api.sgroup.qq.com/websocket"

    @property
    def api_base(self) -> str:
        if self.sandbox:
            return "https://sandbox.api.sgroup.qq.com"
        return "https://api.sgroup.qq.com"




