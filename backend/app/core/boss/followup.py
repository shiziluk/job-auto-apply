"""
Boss直聘 - 自动跟进模块
扫描Boss聊天页，检测HR回复，自动更新投递记录的跟进状态。
判定逻辑：
  - 最后一条消息仍是默认打招呼模板（无HR新消息） -> none（无回复）
  - HR发了消息，含 面试/约面 等词 -> interviewed（已约面）
  - 含 offer/录用/入职 等词 -> offer（已拿Offer）
  - 含 不合适/已招满 等词 -> rejected（被拒）
  - 其他HR消息 -> replied（HR已回复）
"""
import re
from typing import Dict, List, Optional

from app.core.base import async_random_sleep

# Boss默认打招呼模板片段（用于识别"无回复"：最后消息仍是模板说明HR没回）
_DEFAULT_GREETING_MARKERS = [
    "你好，刚刚查看了贵公司的招聘详情，还希望进一步了解一下。",
    # 聊天页空状态系统文案：仅表示“您正在与Boss沟通”，并非HR回复
    "您正在与Boss",
]

# 自定义打招呼模板特征（DB里greeting_sent如“您好，XX的XX您好，我对XX岗位很感兴趣，我的简历已附上，期待您的回复！”）
_OWN_GREETING_PATTERNS = [
    re.compile(r"我对.+?岗位很感兴趣"),
    re.compile(r"期待您的回复"),
    re.compile(r"刚刚查看了贵公司的招聘详情"),
]

# 状态判定关键词（按优先级）
_OFFER_WORDS = ["offer", "录用", "入职", "发offer", "offer函", "offer邮件", "口头offer"]
_INTERVIEW_WORDS = ["面试", "约面", "面谈", "线下面试", "视频面试", "面试邀请", "初试", "复试"]
_REJECT_WORDS = ["不合适", "不太合适", "不匹配", "不符合", "已招满", "招满", "停止招聘", "岗位关闭", "暂不招聘", "抱歉", "遗憾", "暂时没有", "暂时不考虑"]

_CHAT_URL = "https://www.zhipin.com/web/geek/chat"


class BossFollowUpMixin:
    """Boss直聘自动跟进混入类：扫描聊天页 -> 匹配投递记录 -> 更新跟进状态"""

    async def fetch_chat_sessions(self, page_obj=None, max_scroll: int = 12) -> List[Dict]:
        """打开Boss聊天页，滚动加载全部会话，返回结构化会话列表。
        每个会话: {badge, lines, raw}
        lines = [时间, HR+公司+职位, 最后消息...]
        """
        page = page_obj or self.page
        await page.goto(_CHAT_URL, wait_until="domcontentloaded", timeout=45000)
        await async_random_sleep(1, 2)

        # 风控检测：验证/登录页直接返回空，不浪费时间
        cur_url = (page.url or "").lower()
        if "verify" in cur_url or "passport" in cur_url or "security" in cur_url:
            self.log("自动跟进: 聊天页被风控拦截，本次跳过")
            return []

        sessions = []
        prev_len = -1
        for _ in range(max_scroll):
            raw = await page.evaluate("""() => {
                const NL = String.fromCharCode(10);
                const out = [];
                const lis = Array.from(document.querySelectorAll("ul > li"));
                for (const li of lis) {
                    const content = li.querySelector(".friend-content");
                    if (!content) continue;
                    const badgeEl = li.querySelector(".notice-badge");
                    let badge = 0;
                    if (badgeEl) {
                        badge = parseInt(badgeEl.innerText || "0", 10) || 0;
                    }
                    const clone = content.cloneNode(true);
                    const b = clone.querySelector(".notice-badge");
                    if (b) b.remove();
                    const text = (clone.innerText || "").replace(/\s+/g, NL).split(NL)
                        .map(s => s.trim()).filter(Boolean);
                    out.push({ badge, lines: text, raw: text.join(" | ") });
                }
                return out;
            }""")
            sessions = raw or []
            if len(sessions) == prev_len:
                break
            prev_len = len(sessions)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await async_random_sleep(0.6, 1.0)
        return sessions

    @staticmethod
    def _strip_own_greeting(text: str, own_greeting: Optional[str]) -> str:
        """从会话文本中剥离自己发出去的打招呼内容，剩余文本用于判断HR是否回复"""
        t = text
        if own_greeting and own_greeting.strip():
            t = t.replace(own_greeting.strip(), "")
        for marker in _DEFAULT_GREETING_MARKERS:
            t = t.replace(marker, "")
        for pat in _OWN_GREETING_PATTERNS:
            t = pat.sub("", t)
        t = re.sub(r"\[(送达|已读)\]", "", t)
        return t.strip()

    @staticmethod
    def _detect_session_status(session: Dict, own_greeting: Optional[str] = None) -> str:
        """根据会话最后一条消息判定跟进状态：none/replied/interviewed/rejected/offer
        own_greeting：本条投递记录实际发送的打招呼内容（DB apply_records.greeting_sent），
        判定前先剥离自己发的打招呼；剥离后没有剩余内容 -> HR没回复（none）。"""
        lines = session.get("lines") or []
        if len(lines) < 3:
            return "none"
        last_msg = " ".join(lines[2:]).strip()
        if not last_msg:
            return "none"
        # 聊天页空状态系统文案“您正在与Boss xxx沟通”说明会话暂无新内容，直接判无回复
        if "您正在与Boss" in last_msg:
            return "none"
        remaining = BossFollowUpMixin._strip_own_greeting(last_msg, own_greeting)
        if not remaining:
            return "none"
        low = remaining.lower()
        if any(w in low for w in _OFFER_WORDS):
            return "offer"
        if any(w in remaining for w in _INTERVIEW_WORDS):
            return "interviewed"
        if any(w in remaining for w in _REJECT_WORDS):
            return "rejected"
        return "replied"

    @staticmethod
    def _match_record(session: Dict, company_name: str, hr_name: str) -> bool:
        """会话与投递记录匹配：公司名子串 + HR名行首，双条件降低误配。
        公司名可能带“…”省略（如“上海中国电信股份...”），比对前先归一化去除省略号与空白。"""
        if not company_name:
            return False

        def _norm(s: str) -> str:
            return re.sub(r"\s+", "", (s or "").replace("…", "").replace("...", ""))

        raw = session.get("raw") or ""
        norm_company = _norm(company_name)
        if not norm_company:
            return False
        if norm_company not in _norm(raw):
            return False
        if hr_name:
            lines = session.get("lines") or []
            first_line = lines[1] if len(lines) > 1 else ""
            if first_line.startswith(hr_name):
                return True
            if hr_name in raw:
                return True
            return False
        return True

    @staticmethod
    def _build_remark(status: str, session: Dict) -> str:
        """生成跟进备注（记录最后一条HR消息，方便人工复核）"""
        lines = session.get("lines") or []
        last_msg = " ".join(lines[2:]).strip() if len(lines) > 2 else ""
        last_msg = re.sub(r"^\[送达\]", "", last_msg).strip()
        if status == "none":
            return ""
        return f"自动跟进: {last_msg[:100]}"
