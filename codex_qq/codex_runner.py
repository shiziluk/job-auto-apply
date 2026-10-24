# -*- coding: utf-8 -*-
"""调用本地 codex CLI（exec / exec resume）处理消息，并按 QQ 用户维护连续会话。

会话持久化在 codex_qq/data/sessions.json，重启桥接后仍能续接上下文。
"""
import asyncio
import json
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger("codex_qq.codex_runner")


class CodexRunner:
    def __init__(
        self,
        codex_bin: str,
        workdir: str,
        data_dir: str,
        timeout: int = 1800,
        persona_file: str = "",
    ) -> None:
        self.codex_bin = codex_bin
        self.workdir = workdir
        self.data_dir = data_dir
        self.timeout = timeout
        self.persona_file = persona_file or ""
        self._persona_cache = None
        self._persona_mtime = None
        self._sessions_path = os.path.join(data_dir, "sessions.json")
        self._sessions: dict = self._load_sessions()
        self._locks: dict = {}

    def _load_persona(self) -> str:
        """读取人格设定文件（文件变更时自动重读，避免改完不生效）。"""
        try:
            mtime = os.path.getmtime(self.persona_file)
        except OSError:
            return ""
        if self._persona_cache is None or self._persona_mtime != mtime:
            try:
                with open(self.persona_file, "r", encoding="utf-8") as f:
                    self._persona_cache = f.read().strip()
                self._persona_mtime = mtime
            except Exception:
                self._persona_cache = ""
        return self._persona_cache

    # ---------- 会话持久化 ----------
    def _load_sessions(self) -> dict:
        try:
            with open(self._sessions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_sessions(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = self._sessions_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._sessions, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._sessions_path)

    # ---------- 执行 ----------
    async def run(self, openid: str, text: str) -> str:
        """同一 openid 的消息串行处理，避免 Codex 上下文交错。"""
        lock = self._locks.setdefault(openid, asyncio.Lock())
        async with lock:
            return await self._run_locked(openid, text)

    async def _run_locked(self, openid: str, text: str) -> str:
        self._sessions = self._load_sessions()
        sid = self._sessions.get(openid)
        out_file = ""
        try:
            fd, out_file = tempfile.mkstemp(suffix=".txt", prefix="codex_out_")
            os.close(fd)
            cmd = [self.codex_bin, "exec"]
            if sid:
                cmd += ["resume", sid]
            else:
                cmd += ["-C", self.workdir]
                persona = self._load_persona()
                if persona:
                    text = f"{persona}\n\n---\n\n{text}"
            cmd += ["--json", "-o", out_file, "--skip-git-repo-check", "--", text]
            logger.info("[Codex] %s 会话（%s）处理消息", "续接" if sid else "新建", sid or "新")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout if self.timeout > 0 else None
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise TimeoutError(f"Codex 处理超过 {self.timeout} 秒，已终止")
            if proc.returncode != 0:
                err = (stderr or b"").decode("utf-8", errors="replace")[-500:]
                raise RuntimeError(f"codex 退出码 {proc.returncode}: {err.strip() or '未知错误'}")
            thread_id = self._parse_thread_id(stdout)
            if thread_id and openid not in self._sessions:
                self._sessions[openid] = thread_id
                self._save_sessions()
                logger.info("[Codex] 已为用户 %s 建立会话 %s", openid, thread_id)
            reply = self._read_reply(out_file)
            if not reply:
                reply = self._extract_last_text(stdout) or "(无回复)"
            return reply
        finally:
            if out_file:
                try:
                    os.remove(out_file)
                except OSError:
                    pass

    # ---------- 输出解析 ----------
    @staticmethod
    def _parse_thread_id(stdout: bytes) -> str:
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("type") == "thread.started":
                return ev.get("thread_id") or ""
        return ""

    @staticmethod
    def _extract_last_text(stdout: bytes) -> str:
        last = ""
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            item = ev.get("item") or {}
            if ev.get("type") == "item.completed" and item.get("type") == "agent_message":
                last = item.get("text") or ""
        return last.strip()

    @staticmethod
    def _read_reply(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""

    def status_text(self) -> str:
        lines = [
            f"codex CLI: {self.codex_bin}",
            f"工作目录: {self.workdir}",
            f"已记录会话: {len(self._sessions)} 个",
        ]
        if self.persona_file:
            lines.append(f"人格设定: {self.persona_file}（{'已加载' if self._load_persona() else '未找到'}）")
        if not os.path.isdir(self.workdir):
            lines.append("⚠️ 工作目录不存在")
        return "\n".join(lines)

